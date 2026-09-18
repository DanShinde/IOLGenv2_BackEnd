<#
.SYNOPSIS
    Pulls new commits from origin/main into the IIS deployment and refreshes the app.

.DESCRIPTION
    Intended to run unattended from a Windows Scheduled Task on the deployment VM
    (see Register-AutoPullTask.ps1 and README.md in this folder).

    Each run:
      1. Fetches the remote branch and compares it with the local HEAD.
      2. Exits quietly when there is nothing new (the common case).
      3. Refuses to touch a dirty working tree - it never force-resets local work.
      4. Fast-forwards, then runs only the follow-up steps the diff actually needs:
         pip install (requirements.txt changed), migrate (migrations changed),
         collectstatic (static assets changed).
      5. Recycles the app so IIS/wfastcgi picks up the new code.

    Everything is appended to logs\auto_pull.log inside the repo (logs/ is gitignored).

.PARAMETER RepoPath
    The deployment checkout. Defaults to C:\IOLGenv2_BackEnd (the path baked into web.config).

.PARAMETER Branch
    Branch to track. Defaults to main.

.PARAMETER Remote
    Remote name. Defaults to origin.

.PARAMETER VenvPath
    Virtual environment root. Defaults to <RepoPath>\.venv - the interpreter web.config
    points IIS at, so package installs must land there.

.PARAMETER AppPoolName
    IIS application pool to recycle after a successful update. When omitted, the script
    touches web.config instead, which makes IIS reload the app without needing the pool name.

.PARAMETER TriggerFile
    Marker file written by the GitHub webhook view (deploy/views.py). When present it is
    consumed and its contents logged, so the log records which push caused the update.
    Its absence never blocks a run - the scheduled poll is the fallback for missed
    webhook deliveries. Defaults to <RepoPath>\logs\deploy.trigger.

.PARAMETER Force
    Run the update steps even when the branch has not moved. Useful for a manual re-sync.

.PARAMETER SkipCollectStatic
    Never run collectstatic, even when static files changed.

.EXAMPLE
    .\auto_pull.ps1
    Normal unattended run against C:\IOLGenv2_BackEnd.

.EXAMPLE
    .\auto_pull.ps1 -AppPoolName "IOLGenPool" -Force
    Re-run every step and recycle the named pool, even if there are no new commits.

.NOTES
    Exit codes: 0 = up to date or updated successfully
                1 = error (fetch/pull/migrate failed, repo misconfigured)
                2 = blocked (dirty working tree, wrong branch, diverged history)
#>

[CmdletBinding()]
param(
    [string] $RepoPath = 'C:\IOLGenv2_BackEnd',
    [string] $Branch = 'main',
    [string] $Remote = 'origin',
    [string] $VenvPath,
    [string] $AppPoolName,
    [string] $TriggerFile,
    [switch] $Force,
    [switch] $SkipCollectStatic
)

$ErrorActionPreference = 'Stop'

# --- Logging -----------------------------------------------------------------

$script:LogFile = $null
$script:MaxLogBytes = 5MB

function Initialize-Log {
    param([string] $Directory)

    if (-not (Test-Path $Directory)) {
        New-Item -Path $Directory -ItemType Directory -Force | Out-Null
    }

    $path = Join-Path $Directory 'auto_pull.log'

    # Size-based rotation; rotate_log.ps1 at the repo root only handles out/err logs.
    if (Test-Path $path) {
        $existing = Get-Item $path
        if ($existing.Length -gt $script:MaxLogBytes) {
            $stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
            Move-Item -Path $path -Destination (Join-Path $Directory "auto_pull-$stamp.log") -Force
        }
    }

    $script:LogFile = $path
}

function Write-Log {
    param(
        [Parameter(Mandatory = $true)] [string] $Message,
        [ValidateSet('INFO', 'WARN', 'ERROR')] [string] $Level = 'INFO'
    )

    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message

    if ($script:LogFile) {
        Add-Content -Path $script:LogFile -Value $line -Encoding utf8
    }

    switch ($Level) {
        'ERROR' { Write-Error $Message -ErrorAction Continue }
        'WARN'  { Write-Warning $Message }
        default { Write-Verbose $line -Verbose }
    }
}

# --- Native command helpers --------------------------------------------------

# Windows PowerShell 5.1 turns native stderr into ErrorRecords when redirected, which
# trips $ErrorActionPreference = 'Stop' even on exit code 0. Run natives under
# 'Continue' and decide on $LASTEXITCODE instead.
function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)] [string] $FilePath,
        [string[]] $Arguments = @(),
        [string] $WorkingDirectory
    )

    $previousEap = $ErrorActionPreference
    $previousLocation = $null

    try {
        $ErrorActionPreference = 'Continue'

        if ($WorkingDirectory) {
            $previousLocation = Get-Location
            Set-Location -Path $WorkingDirectory
        }

        $output = & $FilePath @Arguments 2>&1 | ForEach-Object { $_.ToString() }
        $code = $LASTEXITCODE
    }
    finally {
        if ($previousLocation) { Set-Location -Path $previousLocation }
        $ErrorActionPreference = $previousEap
    }

    [pscustomobject]@{
        ExitCode = $code
        Output   = (($output | Where-Object { $_ -ne $null }) -join [Environment]::NewLine).Trim()
    }
}

function Invoke-Git {
    param([Parameter(Mandatory = $true)] [string[]] $Arguments)
    Invoke-Native -FilePath $script:GitExe -Arguments $Arguments -WorkingDirectory $RepoPath
}

function Invoke-ManagePy {
    param(
        [Parameter(Mandatory = $true)] [string[]] $Arguments,
        [Parameter(Mandatory = $true)] [string] $Description
    )

    Write-Log "Running: manage.py $($Arguments -join ' ')"
    $result = Invoke-Native -FilePath $script:PythonExe `
                            -Arguments (@((Join-Path $RepoPath 'manage.py')) + $Arguments) `
                            -WorkingDirectory $RepoPath

    if ($result.ExitCode -ne 0) {
        Write-Log "$Description failed (exit $($result.ExitCode)):`n$($result.Output)" -Level ERROR
        return $false
    }

    if ($result.Output) { Write-Log "$Description output:`n$($result.Output)" }
    return $true
}

# --- Single-instance lock ----------------------------------------------------

$script:LockStream = $null

function Enter-Lock {
    param([Parameter(Mandatory = $true)] [string] $Path)

    try {
        # Exclusive handle: a second run started by the scheduler while this one is
        # still installing packages fails here instead of racing the working tree.
        $script:LockStream = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None)
        return $true
    }
    catch {
        return $false
    }
}

function Exit-Lock {
    if ($script:LockStream) {
        $script:LockStream.Close()
        $script:LockStream.Dispose()
        $script:LockStream = $null
    }
}

# --- Refresh steps -----------------------------------------------------------

function Update-Dependencies {
    $requirements = Join-Path $RepoPath 'requirements.txt'
    Write-Log 'requirements.txt changed - installing dependencies'

    $pip = Join-Path $script:VenvScripts 'pip.exe'
    if (-not (Test-Path $pip)) {
        Write-Log "pip not found at $pip - skipping dependency install" -Level WARN
        return $false
    }

    $result = Invoke-Native -FilePath $pip `
                            -Arguments @('install', '--no-input', '-r', $requirements) `
                            -WorkingDirectory $RepoPath

    if ($result.ExitCode -ne 0) {
        Write-Log "pip install failed (exit $($result.ExitCode)):`n$($result.Output)" -Level ERROR
        return $false
    }

    Write-Log 'Dependencies installed'
    return $true
}

function Restart-Application {
    if ($AppPoolName) {
        try {
            Import-Module WebAdministration -ErrorAction Stop
            Restart-WebAppPool -Name $AppPoolName -ErrorAction Stop
            Write-Log "Recycled IIS app pool '$AppPoolName'"
            return
        }
        catch {
            Write-Log "Could not recycle app pool '$AppPoolName' ($($_.Exception.Message)) - falling back to touching web.config" -Level WARN
        }
    }

    # Changing web.config's timestamp is enough for IIS to restart the FastCGI app.
    # Only mtime changes, so git still sees the file as clean.
    $webConfig = Join-Path $RepoPath 'web.config'
    if (Test-Path $webConfig) {
        (Get-Item $webConfig).LastWriteTime = Get-Date
        Write-Log 'Touched web.config to trigger an IIS app restart'
    }
    else {
        Write-Log "web.config not found at $webConfig - the app was NOT restarted" -Level WARN
    }
}

# --- Main --------------------------------------------------------------------

$exitCode = 0

try {
    if (-not (Test-Path $RepoPath)) {
        throw "RepoPath '$RepoPath' does not exist."
    }
    $RepoPath = (Resolve-Path $RepoPath).Path

    Initialize-Log -Directory (Join-Path $RepoPath 'logs')

    if (-not (Test-Path (Join-Path $RepoPath '.git'))) {
        Write-Log "'$RepoPath' is not a git repository - nothing to pull" -Level ERROR
        exit 1
    }

    if (-not $VenvPath) { $VenvPath = Join-Path $RepoPath '.venv' }
    $script:VenvScripts = Join-Path $VenvPath 'Scripts'
    $script:PythonExe = Join-Path $script:VenvScripts 'python.exe'

    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $git) {
        Write-Log 'git.exe not found on PATH for this account - cannot continue' -Level ERROR
        exit 1
    }
    $script:GitExe = $git.Source

    if (-not (Enter-Lock -Path (Join-Path $RepoPath 'logs\auto_pull.lock'))) {
        Write-Log 'Another auto_pull run is still in progress - skipping this tick' -Level WARN
        exit 0
    }

    # --- Consume the webhook marker, if the view left one ---------------------

    if (-not $TriggerFile) { $TriggerFile = Join-Path $RepoPath 'logs\deploy.trigger' }

    if (Test-Path $TriggerFile) {
        $triggerDetail = ''
        try {
            $triggerDetail = (Get-Content -Path $TriggerFile -Raw -ErrorAction Stop).Trim()
        }
        catch {
            $triggerDetail = "(could not be read: $($_.Exception.Message))"
        }

        # Consumed before the pull, not after: if this run dies mid-way the next
        # scheduled tick still picks the commits up by comparing SHAs.
        Remove-Item -Path $TriggerFile -Force -ErrorAction SilentlyContinue
        Write-Log "Webhook trigger consumed - $triggerDetail"
    }

    # --- Preconditions on the checkout itself --------------------------------

    $currentBranch = (Invoke-Git @('rev-parse', '--abbrev-ref', 'HEAD')).Output
    if ($currentBranch -ne $Branch) {
        Write-Log "Checkout is on '$currentBranch', not '$Branch' - refusing to pull. Switch the deployment back to '$Branch' by hand." -Level ERROR
        exit 2
    }

    $status = Invoke-Git @('status', '--porcelain', '--untracked-files=no')
    if ($status.ExitCode -ne 0) {
        Write-Log "git status failed (exit $($status.ExitCode)):`n$($status.Output)" -Level ERROR
        exit 1
    }
    if ($status.Output) {
        Write-Log "Working tree has local modifications to tracked files - refusing to pull (no force-reset). Resolve these on the VM first:`n$($status.Output)" -Level ERROR
        exit 2
    }

    # --- Is there anything new? ----------------------------------------------

    $fetch = Invoke-Git @('fetch', '--prune', $Remote, $Branch)
    if ($fetch.ExitCode -ne 0) {
        Write-Log "git fetch failed (exit $($fetch.ExitCode)):`n$($fetch.Output)" -Level ERROR
        exit 1
    }

    $localSha = (Invoke-Git @('rev-parse', 'HEAD')).Output
    $remoteSha = (Invoke-Git @('rev-parse', "$Remote/$Branch")).Output

    if ($localSha -eq $remoteSha -and -not $Force) {
        # Quiet by design: this is what almost every scheduled tick does.
        Write-Log "Up to date at $($localSha.Substring(0, 7))"
        exit 0
    }

    if ($localSha -eq $remoteSha) {
        Write-Log "Already at $($localSha.Substring(0, 7)) - continuing anyway because -Force was passed"
        $changedFiles = @()
    }
    else {
        Write-Log "New commits on $Remote/$Branch : $($localSha.Substring(0, 7)) -> $($remoteSha.Substring(0, 7))"

        $diff = Invoke-Git @('diff', '--name-only', 'HEAD', "$Remote/$Branch")
        if ($diff.ExitCode -ne 0) {
            Write-Log "git diff failed (exit $($diff.ExitCode)):`n$($diff.Output)" -Level ERROR
            exit 1
        }
        $changedFiles = @($diff.Output -split "`r?`n" | Where-Object { $_ })

        $pull = Invoke-Git @('pull', '--ff-only', $Remote, $Branch)
        if ($pull.ExitCode -ne 0) {
            Write-Log "git pull --ff-only failed (exit $($pull.ExitCode)). The deployment has probably diverged from $Remote/$Branch and needs a human:`n$($pull.Output)" -Level ERROR
            exit 2
        }
        Write-Log "Pulled to $($remoteSha.Substring(0, 7)) ($($changedFiles.Count) file(s) changed)"
    }

    # --- Follow-up steps, driven by what actually changed ---------------------

    $needsDeps = [bool]($Force -or ($changedFiles -contains 'requirements.txt'))
    $needsMigrate = [bool]($Force -or ($changedFiles | Where-Object { $_ -match '(^|/)migrations/.*\.py$' }))
    $needsStatic = [bool]($Force -or ($changedFiles | Where-Object { $_ -match '(^|/)static/' }))

    $failed = $false

    # Only a step that actually shells out to Python needs the venv; a docs- or
    # template-only commit is a perfectly good deploy without one.
    if (($needsDeps -or $needsMigrate -or ($needsStatic -and -not $SkipCollectStatic)) -and
        -not (Test-Path $script:PythonExe)) {
        Write-Log "Virtualenv interpreter not found at $script:PythonExe - skipping pip/migrate/collectstatic. Code is updated but the app may not start." -Level ERROR
        Restart-Application
        exit 1
    }

    if ($needsDeps) {
        if (-not (Update-Dependencies)) { $failed = $true }
    }

    if ($needsMigrate) {
        Write-Log 'Migrations changed - applying'
        if (-not (Invoke-ManagePy -Arguments @('migrate', '--noinput') -Description 'migrate')) { $failed = $true }
    }

    if ($needsStatic -and -not $SkipCollectStatic) {
        Write-Log 'Static files changed - collecting'
        if (-not (Invoke-ManagePy -Arguments @('collectstatic', '--noinput') -Description 'collectstatic')) { $failed = $true }
    }

    Restart-Application

    if ($failed) {
        Write-Log 'Update finished WITH ERRORS - see above. The app was restarted anyway; check it.' -Level ERROR
        $exitCode = 1
    }
    else {
        Write-Log "Update complete at $($remoteSha.Substring(0, 7))"
    }
}
catch {
    if ($script:LogFile) {
        Write-Log "Unhandled error: $($_.Exception.Message)`n$($_.ScriptStackTrace)" -Level ERROR
    }
    else {
        Write-Error $_
    }
    $exitCode = 1
}
finally {
    Exit-Lock
}

exit $exitCode
