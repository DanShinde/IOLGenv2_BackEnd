<#
.SYNOPSIS
    Registers (or removes) the Windows Scheduled Task that runs auto_pull.ps1 on the VM.

.DESCRIPTION
    Run this ONCE on the deployment VM from an elevated PowerShell prompt.

    Pick the logon type with -LogonType. It determines whether a password has to be
    stored, and that in turn dictates how git authenticates:

      Password  (default)  Stores the account's Windows password in Task Scheduler.
                           The only mode where Windows Credential Manager works, because
                           its secrets are sealed with the user's DPAPI key, which needs
                           a password logon to unlock. AVOID if the password rotates -
                           the task starts failing silently the day it changes.

      S4U                  Runs as the same account with NO stored password. Survives
                           password rotation. Credential Manager is NOT available, so
                           git must authenticate with a PAT or an SSH deploy key.

      System               Runs as NT AUTHORITY\SYSTEM. No password, nothing to rotate,
                           but no user profile and no Credential Manager either - same
                           PAT / deploy-key requirement as S4U.

    See docs/AUTO_DEPLOY.md for the git credential setup each mode needs.

.PARAMETER RepoPath
    The deployment checkout. Defaults to C:\IOLGenv2_BackEnd.

.PARAMETER IntervalMinutes
    How often to check the remote. Defaults to 3.

.PARAMETER TaskName
    Scheduled Task name. Defaults to 'IOLGen AutoPull'.

.PARAMETER UserId
    Account the task runs as. Defaults to the account running this script.

.PARAMETER AppPoolName
    Passed through to auto_pull.ps1 so it recycles that IIS pool instead of touching web.config.

.PARAMETER ScriptPath
    Location of auto_pull.ps1. Defaults to the copy sitting next to this script.

.PARAMETER LogonType
    Password (default), S4U, or System. See the description above. Use S4U or System
    when the account's password rotates.

.PARAMETER Unregister
    Remove the task instead of creating it.

.EXAMPLE
    .\Register-AutoPullTask.ps1
    Registers the task for the current user, checking every 3 minutes. Prompts for the password.

.EXAMPLE
    .\Register-AutoPullTask.ps1 -IntervalMinutes 5 -AppPoolName "IOLGenPool"

.EXAMPLE
    .\Register-AutoPullTask.ps1 -IntervalMinutes 1 -LogonType S4U
    No stored password, so a monthly password change never breaks the task. Requires
    git to be set up with a PAT or deploy key first.

.EXAMPLE
    .\Register-AutoPullTask.ps1 -Unregister
#>

[CmdletBinding()]
param(
    [string] $RepoPath = 'C:\IOLGenv2_BackEnd',
    [ValidateRange(1, 1440)]
    [int] $IntervalMinutes = 3,
    [string] $TaskName = 'IOLGen AutoPull',
    [string] $UserId = "$env:USERDOMAIN\$env:USERNAME",
    [string] $AppPoolName,
    [string] $ScriptPath,
    [ValidateSet('Password', 'S4U', 'System')]
    [string] $LogonType = 'Password',
    [switch] $Unregister
)

$ErrorActionPreference = 'Stop'

function Test-Elevated {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Elevated)) {
    throw 'This script must be run from an elevated (Run as Administrator) PowerShell prompt.'
}

# --- Removal path ------------------------------------------------------------

if ($Unregister) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $existing) {
        Write-Host "No scheduled task named '$TaskName' - nothing to remove."
        return
    }

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task '$TaskName'."
    return
}

# --- Validation --------------------------------------------------------------

if (-not $ScriptPath) {
    $ScriptPath = Join-Path $PSScriptRoot 'auto_pull.ps1'
}

if (-not (Test-Path $ScriptPath)) {
    throw "auto_pull.ps1 not found at '$ScriptPath'. Pass -ScriptPath explicitly."
}
$ScriptPath = (Resolve-Path $ScriptPath).Path

if (-not (Test-Path $RepoPath)) {
    throw "RepoPath '$RepoPath' does not exist on this machine."
}
$RepoPath = (Resolve-Path $RepoPath).Path

if (-not (Test-Path (Join-Path $RepoPath '.git'))) {
    throw "'$RepoPath' is not a git repository."
}

# --- Task definition ---------------------------------------------------------

$scriptArgs = @(
    '-NoProfile'
    '-NonInteractive'
    '-ExecutionPolicy', 'Bypass'
    '-File', "`"$ScriptPath`""
    '-RepoPath', "`"$RepoPath`""
)

if ($AppPoolName) {
    $scriptArgs += @('-AppPoolName', "`"$AppPoolName`"")
}

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
                                  -Argument ($scriptArgs -join ' ') `
                                  -WorkingDirectory $RepoPath

# One trigger, repeating forever. -RepetitionDuration of MaxValue means "indefinitely".
$trigger = New-ScheduledTaskTrigger -Once `
                                    -At (Get-Date).AddMinutes(1) `
                                    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
                                    -RepetitionDuration ([TimeSpan]::MaxValue)

$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
                                         -StartWhenAvailable `
                                         -AllowStartIfOnBatteries `
                                         -DontStopIfGoingOnBatteries `
                                         -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
                                         -RestartCount 2 `
                                         -RestartInterval (New-TimeSpan -Minutes 5)

if ($LogonType -eq 'System') { $UserId = 'NT AUTHORITY\SYSTEM' }

$description = 'Pulls new commits from origin/main and refreshes the IIS-hosted Django app.'

Write-Host "Registering '$TaskName'"
Write-Host "  runs as        : $UserId"
Write-Host "  logon type     : $LogonType$(if ($LogonType -eq 'Password') { ' (password stored by Task Scheduler)' } else { ' (no password stored)' })"
Write-Host "  every          : $IntervalMinutes minute(s)"
Write-Host "  script         : $ScriptPath"
Write-Host "  repo           : $RepoPath"
Write-Host "  restart method : $(if ($AppPoolName) { "recycle app pool '$AppPoolName'" } else { 'touch web.config' })"
Write-Host ''

if ($LogonType -ne 'Password') {
    # Neither S4U nor SYSTEM can open the user's Credential Manager - its secrets are
    # sealed with a DPAPI key that only a password logon unlocks. Catch that here
    # rather than letting the first unattended run hang on a credential prompt.
    Write-Host "NOTE: with -LogonType $LogonType there is no Credential Manager access." -ForegroundColor Yellow
    Write-Host '      git must authenticate with a PAT or an SSH deploy key instead.' -ForegroundColor Yellow
    Write-Host '      See the "Git credentials" section of docs/AUTO_DEPLOY.md.' -ForegroundColor Yellow
    Write-Host ''
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Task '$TaskName' already exists - replacing it."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

if ($LogonType -eq 'Password') {
    Write-Host "Enter the Windows password for $UserId (stored by Task Scheduler so the task"
    Write-Host 'can run while nobody is logged on, and so git can read Credential Manager).'
    Write-Host 'If this password rotates, re-run with -LogonType S4U instead.'

    $credential = Get-Credential -UserName $UserId -Message "Password for $UserId (scheduled task logon)"
    if (-not $credential) {
        throw 'No credentials supplied - aborting.'
    }

    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($credential.Password))

    try {
        # -Password only exists on the -User form of Register-ScheduledTask, so this
        # branch cannot use the -Principal object the other logon types build below.
        Register-ScheduledTask -TaskName $TaskName `
                               -Description $description `
                               -Action $action `
                               -Trigger $trigger `
                               -Settings $settings `
                               -User $credential.UserName `
                               -Password $plainPassword `
                               -RunLevel Highest | Out-Null
    }
    finally {
        $plainPassword = $null
        [GC]::Collect()
    }
}
else {
    $principalLogon = if ($LogonType -eq 'System') { 'ServiceAccount' } else { 'S4U' }

    $principal = New-ScheduledTaskPrincipal -UserId $UserId `
                                            -LogonType $principalLogon `
                                            -RunLevel Highest

    Register-ScheduledTask -TaskName $TaskName `
                           -Description $description `
                           -Action $action `
                           -Trigger $trigger `
                           -Settings $settings `
                           -Principal $principal | Out-Null
}

Write-Host ''
Write-Host "Registered. Verify with a manual run:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Get-Content '$RepoPath\logs\auto_pull.log' -Tail 20"
