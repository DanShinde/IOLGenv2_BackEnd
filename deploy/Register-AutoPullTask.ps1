<#
.SYNOPSIS
    Registers (or removes) the Windows Scheduled Task that runs auto_pull.ps1 on the VM.

.DESCRIPTION
    Run this ONCE on the deployment VM from an elevated PowerShell prompt.

    The task is registered to run as a real user account with a stored password rather
    than as SYSTEM or with S4U logon. That is deliberate: git needs credentials for the
    private GitHub remote, and the Windows Credential Manager entry used by
    credential.helper=manager can only be decrypted under a password logon. See
    README.md for the token-file alternative if you would rather not store a password.

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

.PARAMETER Unregister
    Remove the task instead of creating it.

.EXAMPLE
    .\Register-AutoPullTask.ps1
    Registers the task for the current user, checking every 3 minutes. Prompts for the password.

.EXAMPLE
    .\Register-AutoPullTask.ps1 -IntervalMinutes 5 -AppPoolName "IOLGenPool"

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

Write-Host "Registering '$TaskName'"
Write-Host "  runs as        : $UserId"
Write-Host "  every          : $IntervalMinutes minute(s)"
Write-Host "  script         : $ScriptPath"
Write-Host "  repo           : $RepoPath"
Write-Host "  restart method : $(if ($AppPoolName) { "recycle app pool '$AppPoolName'" } else { 'touch web.config' })"
Write-Host ''
Write-Host "Enter the Windows password for $UserId (stored by Task Scheduler so the task"
Write-Host 'can run while nobody is logged on, and so git can read Credential Manager):'

$credential = Get-Credential -UserName $UserId -Message "Password for $UserId (scheduled task logon)"
if (-not $credential) {
    throw 'No credentials supplied - aborting.'
}

$plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($credential.Password))

try {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Write-Host "Task '$TaskName' already exists - replacing it."
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    Register-ScheduledTask -TaskName $TaskName `
                           -Description 'Pulls new commits from origin/main and refreshes the IIS-hosted Django app.' `
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

Write-Host ''
Write-Host "Registered. Verify with a manual run:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Get-Content '$RepoPath\logs\auto_pull.log' -Tail 20"
