from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = (ROOT / "mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5").read_text(
    encoding="utf-8"
)

EXPECTED = 'input string InpApiBaseUrl="https://api.nexustrade.ir";'


def test_ea_uses_public_nexus_api_by_default():
    assert EXPECTED in EA


def test_ea_default_api_is_not_localhost():
    declaration = next(
        line.strip()
        for line in EA.splitlines()
        if "InpApiBaseUrl" in line and line.strip().startswith("input string")
    )
    assert "127.0.0.1" not in declaration
    assert "localhost" not in declaration.lower()
    assert declaration == EXPECTED