param(
    [Parameter(Mandatory=$true)][string]$BundlePath
)
$ErrorActionPreference='Stop'
$branch='feature/nexus-agent-system-v1'
$testRoot=(Resolve-Path -LiteralPath 'C:\NEXUS_AGENT_TEST').Path.TrimEnd('\')
if ($testRoot -ine 'C:\NEXUS_AGENT_TEST') { throw 'Unexpected test root' }
$bundle=(Resolve-Path -LiteralPath $BundlePath).Path
Set-Location -LiteralPath $testRoot
if ((git branch --show-current) -ne $branch) { throw 'Wrong development branch; no checkout was performed' }
git status --short
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect worktree' }
$initialStatus=@(git status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect worktree' }
$unexpected=@($initialStatus | Where-Object { $_ -ne '?? data/' })
if ($unexpected.Count -gt 0) { throw 'Unexpected local changes; preserve local work before continuing' }
$remote=git remote get-url origin
if ($LASTEXITCODE -ne 0 -or $remote -notmatch '^(https://github\.com/|git@github\.com:)sajedfallah/telegrab-signal-bot(\.git)?$') {
    throw 'Unexpected origin repository'
}
git fetch origin $branch
if ($LASTEXITCODE -ne 0) { throw 'Remote fetch failed' }
$remotePaths=@(git diff --name-only HEAD "origin/$branch")
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect remote paths' }
if (@($remotePaths | Where-Object { $_ -eq 'data' -or $_ -like 'data/*' }).Count -gt 0) {
    throw 'Remote changes overlap protected test data; stop for review'
}
git pull --ff-only origin $branch
if ($LASTEXITCODE -ne 0) { throw 'Remote update failed; no bundle was merged' }
git bundle verify $bundle
if ($LASTEXITCODE -ne 0) { throw 'Bundle prerequisites not available' }
git fetch $bundle ('refs/heads/'+$branch+':refs/nexus/recovery-v33')
if ($LASTEXITCODE -ne 0) { throw 'Bundle fetch failed; inspect existing recovery ref before retrying' }
git merge-base --is-ancestor HEAD refs/nexus/recovery-v33
if ($LASTEXITCODE -ne 0) { throw 'Remote/local changes diverge from recovery bundle; stop for review' }
$incoming=@(git diff --name-only HEAD refs/nexus/recovery-v33)
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect incoming paths' }
if (@($incoming | Where-Object { $_ -eq 'data' -or $_ -like 'data/*' }).Count -gt 0) {
    throw 'Incoming changes overlap protected test data; stop for review'
}
git merge --ff-only refs/nexus/recovery-v33
if ($LASTEXITCODE -ne 0) { throw 'Fast-forward merge failed' }
git rev-parse HEAD
python -m pytest tests/test_agent_setup_tracker_v31.py tests/test_agent_setup_lifecycle_v32.py -q
if ($LASTEXITCODE -ne 0) { throw 'V3.2 pytest gate failed; preserve and return the complete output' }
python -m unittest discover -s tests -p test_agent_v32_recovery_unittest.py -v
if ($LASTEXITCODE -ne 0) { throw 'V3.2 regression checks failed' }
python -m unittest discover -s tests -p test_agent_lifecycle_v33_unittest.py -v
if ($LASTEXITCODE -ne 0) { throw 'V3.3 lifecycle checks failed' }
python -m unittest discover -s tests -p test_agent_lifecycle_snapshot_v33_unittest.py -v
if ($LASTEXITCODE -ne 0) { throw 'V3.3 snapshot boundary checks failed' }
git status --short
Write-Output 'Focused test commands passed. Return this output for review; watcher integration remains disabled.'
Write-Output 'This script does not push, publish, start services or deploy.'
