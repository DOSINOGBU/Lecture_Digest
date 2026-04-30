param(
    [string]$RepoRoot = (Join-Path $PSScriptRoot ".."),
    [ValidateSet("Passed", "Partial", "Failed", "NotRun")]
    [string]$VerificationStatus = "NotRun",
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$repoRootPath = (Resolve-Path $RepoRoot).Path

function Invoke-Git {
    param(
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $previousErrorActionPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        $output = @(& git -C $repoRootPath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $text = ($output | ForEach-Object { $_.ToString() }) -join "`n"

    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "git $($Arguments -join ' ') failed with exit code $exitCode. $text"
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = $text
    }
}

function New-Recommendation {
    param(
        [ValidateSet("recommended", "hold", "blocked", "not_needed")]
        [string]$Status,
        [string[]]$Reasons
    )

    return [ordered]@{
        status = $Status
        reasons = @($Reasons)
    }
}

function Get-ChangedFiles {
    $status = Invoke-Git -Arguments @("status", "--porcelain=v1")
    $lines = @($status.Output -split "`r?`n" | Where-Object { $_ -ne "" })
    $files = @()

    foreach ($line in $lines) {
        if ($line.Length -lt 3) {
            continue
        }

        $statusCode = $line.Substring(0, 2)
        $path = if ($line.Length -ge 4) { $line.Substring(3) } else { "" }

        if ($path -match " -> ") {
            $path = @($path -split " -> ")[-1]
        }

        $indexStatus = [string]$statusCode[0]
        $workTreeStatus = [string]$statusCode[1]
        $isUntracked = $statusCode -eq "??"
        $isConflict = $statusCode -match "U" -or @("AA", "DD") -contains $statusCode

        $files += [pscustomobject]@{
            status = $statusCode
            path = $path
            category = Get-ChangeCategory -Path $path
            isStaged = (-not $isUntracked -and $indexStatus -ne " ")
            isUnstaged = (-not $isUntracked -and $workTreeStatus -ne " ")
            isUntracked = $isUntracked
            isConflict = $isConflict
            isSensitive = Test-SensitivePath -Path $path
        }
    }

    return @($files)
}

function Get-ChangeCategory {
    param(
        [string]$Path
    )

    $normalized = ($Path.Trim('"') -replace "\\", "/")

    if ($normalized -match "^docs/" -or $normalized -match "^Harness Template Use Docs/") {
        return "docs"
    }

    if ($normalized -match "^\.harness/") {
        return "harness"
    }

    if ($normalized -match "^scripts/") {
        return "scripts"
    }

    if ($normalized -match "^tests/") {
        return "tests"
    }

    if ($normalized -match "^lecturedigest/") {
        return "source"
    }

    if ($normalized -match "^\.github/" -or $normalized -match "(^|/)(pyproject\.toml|package\.json|requirements.*\.txt|\.gitignore)$") {
        return "config"
    }

    return "other"
}

function Test-SensitivePath {
    param(
        [string]$Path
    )

    $normalized = ($Path.Trim('"') -replace "\\", "/").ToLowerInvariant()
    $leaf = [System.IO.Path]::GetFileName($normalized)

    if ($leaf -eq ".env" -or $leaf -match "^\.env\.(local|development|production|test|dev|prod)$") {
        return $true
    }

    if ($leaf -match "\.(pem|key|p12|pfx)$") {
        return $true
    }

    if ($leaf -match "^(id_rsa|id_ed25519)(\.pub)?$") {
        return $true
    }

    return $false
}

function Get-DiffCheck {
    $workTreeCheck = Invoke-Git -Arguments @("diff", "--check") -AllowFailure
    $stagedCheck = Invoke-Git -Arguments @("diff", "--cached", "--check") -AllowFailure
    $messages = @()

    if ($workTreeCheck.Output) {
        $messages += @($workTreeCheck.Output -split "`r?`n" | Where-Object { $_ -ne "" })
    }

    if ($stagedCheck.Output) {
        $messages += @($stagedCheck.Output -split "`r?`n" | Where-Object { $_ -ne "" })
    }

    return [pscustomobject]@{
        passed = ($workTreeCheck.ExitCode -eq 0 -and $stagedCheck.ExitCode -eq 0)
        messages = @($messages)
    }
}

function Get-Upstream {
    $upstream = Invoke-Git -Arguments @("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") -AllowFailure

    if ($upstream.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($upstream.Output)) {
        return $null
    }

    return $upstream.Output.Trim()
}

function Get-AheadBehind {
    param(
        [string]$Upstream
    )

    if ([string]::IsNullOrWhiteSpace($Upstream)) {
        return [pscustomobject]@{
            ahead = 0
            behind = 0
        }
    }

    $counts = Invoke-Git -Arguments @("rev-list", "--left-right", "--count", "$Upstream...HEAD") -AllowFailure

    if ($counts.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($counts.Output)) {
        return [pscustomobject]@{
            ahead = 0
            behind = 0
        }
    }

    $parts = @($counts.Output.Trim() -split "\s+")

    return [pscustomobject]@{
        behind = [int]$parts[0]
        ahead = [int]$parts[1]
    }
}

function Get-CommitsSinceOriginMain {
    $originMain = Invoke-Git -Arguments @("rev-parse", "--verify", "origin/main") -AllowFailure

    if ($originMain.ExitCode -ne 0) {
        return $null
    }

    $count = Invoke-Git -Arguments @("rev-list", "--count", "origin/main..HEAD") -AllowFailure

    if ($count.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($count.Output)) {
        return $null
    }

    return [int]$count.Output.Trim()
}

function Test-MixedPurpose {
    param(
        [object[]]$ChangedFiles
    )

    $categories = @($ChangedFiles | ForEach-Object { $_.category } | Sort-Object -Unique)

    if ($categories.Count -gt 3) {
        return $true
    }

    if (($categories -contains "source") -and ($categories -contains "scripts") -and ($categories -contains "docs")) {
        return $true
    }

    if (($categories -contains "other") -and $categories.Count -gt 1) {
        return $true
    }

    return $false
}

function Get-CommitRecommendation {
    param(
        [object[]]$ChangedFiles,
        [object]$DiffCheck,
        [bool]$HasMixedPurpose
    )

    if ($ChangedFiles.Count -eq 0) {
        return New-Recommendation -Status "not_needed" -Reasons @("No working tree changes.")
    }

    $sensitivePaths = @($ChangedFiles | Where-Object { $_.isSensitive } | ForEach-Object { $_.path })
    $hasConflict = @($ChangedFiles | Where-Object { $_.isConflict }).Count -gt 0
    $hasUntracked = @($ChangedFiles | Where-Object { $_.isUntracked }).Count -gt 0
    $blockedReasons = @()
    $holdReasons = @()
    $readyReasons = @()

    if ($hasConflict) {
        $blockedReasons += "Unresolved conflict markers are present in git status."
    }

    if ($sensitivePaths.Count -gt 0) {
        $blockedReasons += "Sensitive-looking paths are changed: $($sensitivePaths -join ', ')."
    }

    if (-not $DiffCheck.passed) {
        $blockedReasons += "git diff --check reported whitespace or conflict-marker issues."
    }

    if ($VerificationStatus -eq "Failed") {
        $blockedReasons += "Verification failed."
    }

    if ($blockedReasons.Count -gt 0) {
        return New-Recommendation -Status "blocked" -Reasons $blockedReasons
    }

    if ($VerificationStatus -eq "NotRun") {
        $holdReasons += "Verification has not been run."
    }

    if ($hasUntracked) {
        $holdReasons += "Untracked files need an explicit staging decision."
    }

    if ($HasMixedPurpose) {
        $holdReasons += "Changed file categories suggest more than one commit purpose; review split boundaries."
    }

    if ($holdReasons.Count -gt 0) {
        return New-Recommendation -Status "hold" -Reasons $holdReasons
    }

    if ($VerificationStatus -eq "Partial") {
        $readyReasons += "Changes exist and partial verification was recorded; include the missing checks in the report."
    }
    else {
        $readyReasons += "Changes exist and verification passed."
    }

    $readyReasons += "No sensitive paths, conflicts, or diff-check errors were detected."

    return New-Recommendation -Status "recommended" -Reasons $readyReasons
}

function Get-PushRecommendation {
    param(
        [bool]$HasChanges,
        [string]$Branch,
        [string]$Upstream,
        [int]$Ahead,
        [int]$Behind
    )

    if ($VerificationStatus -eq "Failed") {
        return New-Recommendation -Status "blocked" -Reasons @("Verification failed.")
    }

    if ($HasChanges) {
        return New-Recommendation -Status "hold" -Reasons @("The working tree has uncommitted changes.")
    }

    if ($VerificationStatus -eq "NotRun") {
        return New-Recommendation -Status "hold" -Reasons @("Verification has not been run.")
    }

    if ($VerificationStatus -eq "Partial") {
        return New-Recommendation -Status "hold" -Reasons @("Verification is partial; finish or document missing checks before push.")
    }

    if ([string]::IsNullOrWhiteSpace($Upstream)) {
        if ($Branch -eq "main" -and $Ahead -le 0) {
            return New-Recommendation -Status "not_needed" -Reasons @("No upstream branch is configured and no local push target is pending.")
        }

        return New-Recommendation -Status "hold" -Reasons @("No upstream branch is configured.")
    }

    if ($Behind -gt 0) {
        return New-Recommendation -Status "hold" -Reasons @("The branch is behind upstream; integrate remote changes before push.")
    }

    if ($Ahead -le 0) {
        return New-Recommendation -Status "not_needed" -Reasons @("No local commits are ahead of upstream.")
    }

    if ($Branch -eq "main") {
        return New-Recommendation -Status "hold" -Reasons @("Direct push from main is held by project policy; use a topic branch or PR flow.")
    }

    return New-Recommendation -Status "recommended" -Reasons @("The working tree is clean, verification passed, and local commits are ahead of upstream.")
}

function Get-PrRecommendation {
    param(
        [bool]$HasChanges,
        [string]$Branch,
        [string]$Upstream,
        [int]$Ahead,
        [int]$Behind,
        [Nullable[int]]$CommitsSinceOriginMain
    )

    if ($VerificationStatus -eq "Failed") {
        return New-Recommendation -Status "blocked" -Reasons @("Verification failed.")
    }

    if ($Branch -eq "main" -or $Branch -eq "DETACHED") {
        return New-Recommendation -Status "hold" -Reasons @("Open PRs from a topic branch, not $Branch.")
    }

    if ($HasChanges) {
        return New-Recommendation -Status "hold" -Reasons @("Commit or discard working tree changes before preparing a PR.")
    }

    if ($VerificationStatus -eq "NotRun") {
        return New-Recommendation -Status "hold" -Reasons @("Verification has not been run.")
    }

    if ($VerificationStatus -eq "Partial") {
        return New-Recommendation -Status "hold" -Reasons @("Verification is partial; document or finish missing checks before PR.")
    }

    if ([string]::IsNullOrWhiteSpace($Upstream)) {
        return New-Recommendation -Status "hold" -Reasons @("Push the topic branch and set upstream before preparing a PR.")
    }

    if ($Behind -gt 0) {
        return New-Recommendation -Status "hold" -Reasons @("The branch is behind upstream; integrate remote changes before PR.")
    }

    if ($Ahead -gt 0) {
        return New-Recommendation -Status "hold" -Reasons @("Push local commits before preparing a PR.")
    }

    if ($null -ne $CommitsSinceOriginMain -and $CommitsSinceOriginMain -le 0) {
        return New-Recommendation -Status "not_needed" -Reasons @("No commits differ from origin/main.")
    }

    return New-Recommendation -Status "recommended" -Reasons @("The topic branch is clean, pushed, and verified.")
}

function Write-HumanRecommendation {
    param(
        [object]$Result
    )

    $facts = $Result.facts
    Write-Host "[VersionControlRecommendation] summary { verification=$($facts.verification); branch=$($facts.branch); upstream=$($facts.upstream); workingTree=$($facts.workingTree); ahead=$($facts.ahead); behind=$($facts.behind) }"
    Write-Host ""

    foreach ($name in @("commit", "push", "pr")) {
        $recommendation = $Result.$name
        $label = if ($name -eq "pr") { "PR" } else { $name.Substring(0, 1).ToUpperInvariant() + $name.Substring(1) }
        Write-Host "$($label): $($recommendation.status)"

        foreach ($reason in $recommendation.reasons) {
            Write-Host "- $reason"
        }

        Write-Host ""
    }
}

Invoke-Git -Arguments @("rev-parse", "--is-inside-work-tree") | Out-Null

$branchResult = Invoke-Git -Arguments @("branch", "--show-current") -AllowFailure
$branch = if ([string]::IsNullOrWhiteSpace($branchResult.Output)) { "DETACHED" } else { $branchResult.Output.Trim() }
$upstream = Get-Upstream
$aheadBehind = Get-AheadBehind -Upstream $upstream
$changedFiles = @(Get-ChangedFiles)
$diffCheck = Get-DiffCheck
$hasChanges = $changedFiles.Count -gt 0
$hasMixedPurpose = Test-MixedPurpose -ChangedFiles $changedFiles
$commitsSinceOriginMain = Get-CommitsSinceOriginMain

$facts = [ordered]@{
    verification = $VerificationStatus
    branch = $branch
    upstream = if ($null -eq $upstream) { "" } else { $upstream }
    ahead = $aheadBehind.ahead
    behind = $aheadBehind.behind
    workingTree = if ($hasChanges) { "dirty" } else { "clean" }
    hasStaged = @($changedFiles | Where-Object { $_.isStaged }).Count -gt 0
    hasUnstaged = @($changedFiles | Where-Object { $_.isUnstaged }).Count -gt 0
    hasUntracked = @($changedFiles | Where-Object { $_.isUntracked }).Count -gt 0
    diffCheckPassed = [bool]$diffCheck.passed
    mixedPurposeSuspected = [bool]$hasMixedPurpose
    commitsSinceOriginMain = $commitsSinceOriginMain
    changedFiles = @($changedFiles)
}

$blockers = @()

if (@($changedFiles | Where-Object { $_.isConflict }).Count -gt 0) {
    $blockers += "conflict"
}

if (@($changedFiles | Where-Object { $_.isSensitive }).Count -gt 0) {
    $blockers += "sensitive_path"
}

if (-not $diffCheck.passed) {
    $blockers += "diff_check"
}

if ($VerificationStatus -eq "Failed") {
    $blockers += "verification_failed"
}

$result = [ordered]@{
    facts = $facts
    commit = Get-CommitRecommendation -ChangedFiles $changedFiles -DiffCheck $diffCheck -HasMixedPurpose $hasMixedPurpose
    push = Get-PushRecommendation -HasChanges $hasChanges -Branch $branch -Upstream $upstream -Ahead $aheadBehind.ahead -Behind $aheadBehind.behind
    pr = Get-PrRecommendation -HasChanges $hasChanges -Branch $branch -Upstream $upstream -Ahead $aheadBehind.ahead -Behind $aheadBehind.behind -CommitsSinceOriginMain $commitsSinceOriginMain
    blockers = @($blockers)
    diffCheckMessages = @($diffCheck.messages)
}

if ($Json) {
    $result | ConvertTo-Json -Depth 8
}
else {
    Write-HumanRecommendation -Result $result
}
