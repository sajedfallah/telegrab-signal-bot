from pathlib import Path
import re, sys

ROOT = Path(__file__).resolve().parents[1]
ea = ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5"
assert ea.exists(), f"Missing EA source: {ea}"

text = ea.read_text(encoding="utf-8")
m = re.search(r'#property\s+version\s+"([^"]+)"', text)
assert m, "EA version property missing"
print("EA version:", m.group(1))

expected = "1.64"
assert m.group(1) == expected, f"EA version {m.group(1)} != {expected}"

files = sorted(p.name for p in (ROOT/"mt5"/"NEXUS_AutoTrade").iterdir())
assert "NEXUS_AutoTrade.mq5" in files
assert "NEXUS_Reset_Runtime.mq5" in files
assert "Include" in files
assert not any(x.lower().endswith(".ex5") for x in files)
print("MT5 source package: PASS")

print("Release static checks: PASS")
