from pathlib import Path


def test_run_api_initializes_canonical_schema_before_runtime_extensions():
    source = Path("run_api.py").read_text(encoding="utf-8-sig")
    assert "from app import db" in source
    assert "db.init_db()" in source
    assert source.index("db.init_db()") < source.index("install_web_chart_capture_runtime()")
