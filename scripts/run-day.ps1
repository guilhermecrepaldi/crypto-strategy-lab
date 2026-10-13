<#
.SYNOPSIS
Runs one pre-registered daily research campaign from Windows Task Scheduler.

.DESCRIPTION
This wrapper deliberately does not create campaign files, choose a model, or retry a
run. The `day-run` command remains the authority for state and one-shot validation.
It captures the campaign date in UTC once, verifies the checked-out runner is on
main, writes the process output to that campaign's runner.log, and returns the
command's exit code to Task Scheduler.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$RepoRoot,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$UvExe,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$GitExe,

    [string]$CampaignDate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$capturedUtcDate = [DateTime]::UtcNow.ToString(
    "yyyy-MM-dd",
    [System.Globalization.CultureInfo]::InvariantCulture
)

function Write-RunnerLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LogPath,

        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $timestamp = [DateTime]::UtcNow.ToString(
        "o",
        [System.Globalization.CultureInfo]::InvariantCulture
    )
    Add-Content -LiteralPath $LogPath -Value ("{0} {1}" -f $timestamp, $Message) -Encoding UTF8
}

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

$logPath = $null
$exitCode = 1

try {
    if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
        throw "REPOSITORY_ROOT_NOT_FOUND: $RepoRoot"
    }
    $resolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

    foreach ($requiredRepositoryFile in @("pyproject.toml", "uv.lock", "docs/research/CURRENT_STATE.md")) {
        $requiredPath = Join-Path $resolvedRepoRoot $requiredRepositoryFile
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "REPOSITORY_PRECONDITION_MISSING: $requiredRepositoryFile"
        }
    }

    if (-not (Test-Path -LiteralPath $UvExe -PathType Leaf)) {
        throw "UV_EXECUTABLE_NOT_FOUND: $UvExe"
    }
    $resolvedUvExe = (Resolve-Path -LiteralPath $UvExe).Path

    if (-not (Test-Path -LiteralPath $GitExe -PathType Leaf)) {
        throw "GIT_EXECUTABLE_NOT_FOUND: $GitExe"
    }
    $resolvedGitExe = (Resolve-Path -LiteralPath $GitExe).Path

    if ([string]::IsNullOrWhiteSpace($CampaignDate)) {
        $CampaignDate = $capturedUtcDate
    }
    else {
        try {
            $parsedDate = [DateTime]::ParseExact(
                $CampaignDate,
                "yyyy-MM-dd",
                [System.Globalization.CultureInfo]::InvariantCulture,
                [System.Globalization.DateTimeStyles]::None
            )
        }
        catch {
            throw "CAMPAIGN_DATE_MUST_BE_UTC_YYYY_MM_DD: $CampaignDate"
        }
        if ($parsedDate.ToString(
            "yyyy-MM-dd",
            [System.Globalization.CultureInfo]::InvariantCulture
        ) -ne $CampaignDate) {
            throw "CAMPAIGN_DATE_MUST_BE_UTC_YYYY_MM_DD: $CampaignDate"
        }
    }

    $campaignRelativePath = "campaigns/$CampaignDate"
    $campaignPath = Join-Path $resolvedRepoRoot ("campaigns\{0}" -f $CampaignDate)
    if (-not (Test-Path -LiteralPath $campaignPath -PathType Container)) {
        throw "CAMPAIGN_NOT_PREREGISTERED: $campaignRelativePath"
    }

    $logPath = Join-Path $campaignPath "runner.log"
    foreach ($requiredCampaignFile in @("STRATEGY.md", "model_spec.json", "job.yaml")) {
        $requiredPath = Join-Path $campaignPath $requiredCampaignFile
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "CAMPAIGN_PRECONDITION_MISSING: $campaignRelativePath/$requiredCampaignFile"
        }
    }

    $branch = Get-GitSingleLine `
        -GitPath $resolvedGitExe `
        -Repository $resolvedRepoRoot `
        -Arguments @("branch", "--show-current")
    if ($branch -ne "main") {
        throw "RUNNER_BRANCH_MUST_BE_MAIN: $branch"
    }
    $gitHead = Get-GitSingleLine `
        -GitPath $resolvedGitExe `
        -Repository $resolvedRepoRoot `
        -Arguments @("rev-parse", "--verify", "HEAD")
    if ([string]::IsNullOrWhiteSpace($gitHead)) {
        throw "RUNNER_HEAD_UNRESOLVED"
    }

    Write-RunnerLog -LogPath $logPath -Message (
        "START repo={0} campaign={1} utc_day={2} branch={3} head={4} uv={5}" -f $resolvedRepoRoot, $campaignRelativePath, $capturedUtcDate, $branch, $gitHead, $resolvedUvExe
    )
    Write-RunnerLog -LogPath $logPath -Message (
        "COMMAND uv run --locked --no-sync crypto-lab day-run --campaign {0}" -f $campaignRelativePath
    )

    Push-Location -LiteralPath $resolvedRepoRoot
    try {
        $invocationUtcDate = [DateTime]::UtcNow.ToString(
            "yyyy-MM-dd",
            [System.Globalization.CultureInfo]::InvariantCulture
        )
        if ($invocationUtcDate -ne $capturedUtcDate) {
            throw "UTC_DATE_ROLLED_BEFORE_INVOCATION: captured=$capturedUtcDate current=$invocationUtcDate"
        }
        & $resolvedUvExe run --locked --no-sync crypto-lab day-run --campaign $campaignRelativePath *>> $logPath
        if ($null -eq $LASTEXITCODE) {
            $exitCode = 1
        }
        else {
            $exitCode = [int]$LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }

    Write-RunnerLog -LogPath $logPath -Message ("END exit_code={0}" -f $exitCode)
}
catch {
    $failure = $_.Exception.Message
    if ($null -ne $logPath) {
        Write-RunnerLog -LogPath $logPath -Message ("FAILURE {0}" -f $failure)
    }
    [Console]::Error.WriteLine($failure)
    $exitCode = 1
}

exit $exitCode
