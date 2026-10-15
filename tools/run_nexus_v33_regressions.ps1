$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify test commit' }
python -m pytest tests/test_agent_setup_tracker_v31.py tests/test_agent_setup_lifecycle_v32.py tests/test_full_ict_gate_v3.py -q
if ($LASTEXITCODE -ne 0) { throw 'Baseline tracker/lifecycle/full-gate tests failed' }
python -m unittest discover -s tests -p test_agent_v32_recovery_unittest.py -v
if ($LASTEXITCODE -ne 0) { throw 'V3.2 recovery tests failed' }
python -m unittest discover -s tests -p 'test_agent_*v33*unittest.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Full isolated V3.3 regressions failed' }
Write-Output 'Regression commands passed; detector-equivalence characterization still identifies integration blockers. No watcher integration approval.'
