<#
.SYNOPSIS
Registers the daily `crypto-lab day-run` Task Scheduler action.

.DESCRIPTION
The task is disabled unless -Enable is explicitly supplied. By default it uses an
S4U token, which permits a local, logged-out run without storing a password. It uses
absolute executable paths, the repository as its working directory, and ignores a
second invocation while one is still running.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^([01]\d|2[0-3]):[0-5]\d$")]
    [string]$At,

    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),

    [string]$UvExe,

    [string]$GitExe,

    [ValidateSet("S4U", "Interactive")]
    [string]$LogonType = "S4U",

    [ValidateRange(1, 1440)]
    [int]$ExecutionTimeLimitMinutes = 360,

    [ValidateNotNullOrEmpty()]
    [string]$TaskName = "CryptoStrategyLab-DayRun",

    [switch]$Enable
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-GitSingleLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GitPath,

        [Parameter(Mandatory = $true)]
        [string]$Repository,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $result = & $GitPath -C $Repository @Arguments
    $gitExitCode = $LASTEXITCODE
    if ($gitExitCode -ne 0) {
        throw "GIT_PREFLIGHT_FAILED exit_code=$gitExitCode command=$($Arguments -join ' ')"
    }
    return ($result | Out-String).Trim()
}

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "REPOSITORY_ROOT_NOT_FOUND: $RepoRoot"
}
$resolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

$runnerScript = Join-Path $resolvedRepoRoot "scripts\run-day.ps1"
if (-not (Test-Path -LiteralPath $runnerScript -PathType Leaf)) {
    throw "RUNNER_SCRIPT_NOT_FOUND: $runnerScript"
}

if ([string]::IsNullOrWhiteSpace($UvExe)) {
    $uvCommand = Get-Command -Name "uv.exe" -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $uvCommand) {
        $uvCommand = Get-Command -Name "uv" -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
    }
    if ($null -eq $uvCommand) {
        throw "UV_EXECUTABLE_NOT_FOUND_ON_PATH: install uv or pass -UvExe with its absolute path"
    }
    $UvExe = $uvCommand.Path
}

if (-not (Test-Path -LiteralPath $UvExe -PathType Leaf)) {
    throw "UV_EXECUTABLE_NOT_FOUND: $UvExe"
}
$resolvedUvExe = (Resolve-Path -LiteralPath $UvExe).Path

if ([string]::IsNullOrWhiteSpace($GitExe)) {
    $gitCommand = Get-Command -Name "git.exe" -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $gitCommand) {
        $gitCommand = Get-Command -Name "git" -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
    }
    if ($null -eq $gitCommand) {
        throw "GIT_EXECUTABLE_NOT_FOUND_ON_PATH: install Git or pass -GitExe with its absolute path"
    }
    $GitExe = $gitCommand.Path
}

if (-not (Test-Path -LiteralPath $GitExe -PathType Leaf)) {
    throw "GIT_EXECUTABLE_NOT_FOUND: $GitExe"
}
$resolvedGitExe = (Resolve-Path -LiteralPath $GitExe).Path

$registrationBranch = Get-GitSingleLine `
    -GitPath $resolvedGitExe `
    -Repository $resolvedRepoRoot `
    -Arguments @("branch", "--show-current")
if ($registrationBranch -ne "main") {
    throw "TASK_REGISTRATION_REQUIRES_MAIN_BRANCH: $registrationBranch"
}

$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path -LiteralPath $powershellExe -PathType Leaf)) {
    throw "WINDOWS_POWERSHELL_NOT_FOUND: $powershellExe"
}

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $existingTask -and $existingTask.State -eq "Running") {
    throw "TASK_IS_RUNNING: $TaskName. Do not replace its registration during a campaign."
}

$runTime = [DateTime]::ParseExact(
    $At,
    "HH:mm",
    [System.Globalization.CultureInfo]::InvariantCulture,
    [System.Globalization.DateTimeStyles]::None
)
$firstRun = (Get-Date).Date.Add($runTime.TimeOfDay)
if ($firstRun -le (Get-Date)) {
    $firstRun = $firstRun.AddDays(1)
}

$arguments = @(
    "-NoLogo",
    "-NoProfile",
    "-NonInteractive",
    "-WindowStyle Hidden",
    ("-File `"{0}`"" -f $runnerScript),
    ("-RepoRoot `"{0}`"" -f $resolvedRepoRoot),
    ("-UvExe `"{0}`"" -f $resolvedUvExe),
    ("-GitExe `"{0}`"" -f $resolvedGitExe)
) -join " "

$action = New-ScheduledTaskAction `
    -Execute $powershellExe `
    -Argument $arguments `
    -WorkingDirectory $resolvedRepoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $firstRun
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType $LogonType `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -Disable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 0 `
    -StartWhenAvailable:$false `
    -ExecutionTimeLimit (New-TimeSpan -Minutes $ExecutionTimeLimitMinutes)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description ("Runs a pre-registered Crypto Strategy Lab day-run without UI; logon={0}; timeout_minutes={1}." -f $LogonType, $ExecutionTimeLimitMinutes) `
    -Force | Out-Null

if ($Enable) {
    Enable-ScheduledTask -TaskName $TaskName | Out-Null
    Write-Output "REGISTERED_AND_ENABLED task=$TaskName at_local=$At logon=$LogonType timeout_minutes=$ExecutionTimeLimitMinutes"
}
else {
    Disable-ScheduledTask -TaskName $TaskName | Out-Null
    Write-Output "REGISTERED_DISABLED task=$TaskName at_local=$At logon=$LogonType timeout_minutes=$ExecutionTimeLimitMinutes"
}
