import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _db_sync_functions():
    tree = ast.parse((ROOT / "app" / "db.py").read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def test_main_does_not_await_synchronous_db_functions():
    sync_db = _db_sync_functions()
    tree = ast.parse((ROOT / "app" / "main.py").read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "db"
            and call.func.attr in sync_db
        ):
            bad.append((node.lineno, call.func.attr))
    assert not bad, f"Synchronous db functions awaited in main.py: {bad}"


def test_autotrade_source_and_runtime_delivery_versions_match():
    source = (ROOT / "mt5" / "NEXUS_AutoTrade" / "NEXUS_AutoTrade.mq5").read_text(encoding="utf-8")
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert '#property version   "1.64"' in source
    assert 'NEXUS_AutoTrade.ex5' in main
    assert 'NEXUS v0.6.4' in main
