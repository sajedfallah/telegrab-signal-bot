param(
    [Parameter(Mandatory=$true)][string]$SourceCommit,
    [Parameter(Mandatory=$true)][string]$ExpectedRemoteHead
)
$ErrorActionPreference='Stop'
$branch='feature/nexus-agent-system-v1'
Set-Location -LiteralPath 'C:\NEXUS_AGENT_TEST'
if ((git branch --show-current) -ne $branch) { throw 'Wrong branch' }
$status=@(git status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect worktree' }
if (@($status | Where-Object { $_ -ne '?? data/' }).Count -gt 0) { throw 'Unexpected local changes; no push' }
$origin=git remote get-url origin
if ($LASTEXITCODE -ne 0 -or $origin -notmatch '^(https://github\.com/|git@github\.com:)sajedfallah/telegrab-signal-bot(\.git)?$') { throw 'Unexpected origin' }
$source=git rev-parse --verify "${SourceCommit}^{commit}"
if ($LASTEXITCODE -ne 0) { throw 'Source commit is unavailable locally' }
if ((git rev-parse HEAD) -ne $source) { throw 'HEAD differs from requested source commit' }
git fetch origin $branch
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
$actual=git rev-parse "origin/$branch"
if ($actual -ne $ExpectedRemoteHead) { throw 'Remote HEAD changed; inspect before retrying' }
git merge-base --is-ancestor $actual $source
if ($LASTEXITCODE -ne 0) { throw 'Remote is not an ancestor; no push' }
$remoteLine=git ls-remote --heads origin "refs/heads/$branch"
if ($LASTEXITCODE -ne 0 -or -not $remoteLine -or ($remoteLine -split '\s+')[0] -ne $actual) {
    throw 'Remote HEAD changed during preflight'
}
git push origin "${source}:refs/heads/$branch"
if ($LASTEXITCODE -ne 0) { throw 'Non-force push failed' }
$confirmed=git ls-remote --heads origin "refs/heads/$branch"
if ($LASTEXITCODE -ne 0 -or ($confirmed -split '\s+')[0] -ne $source) { throw 'Remote commit could not be confirmed' }
Write-Output "Verified remote development HEAD: $source"
