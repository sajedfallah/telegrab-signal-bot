
import ast
from pathlib import Path

try:
    from app import ui
except ModuleNotFoundError as exc:
    if exc.name == "aiogram":
        import pytest
        pytest.skip("aiogram is required for UI navigation tests", allow_module_level=True)
    raise

ROOT = Path(__file__).resolve().parents[1]


def buttons(markup):
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


def test_admin_home_is_compact_grid():
    fa = ui.admin_menu("fa")
    assert len(fa.inline_keyboard) <= 5
    codes = {c for _, c in buttons(fa)}
    assert {"admin_group_users", "admin_group_finance", "admin_group_rewards",
            "admin_signals", "admin_group_marketing", "admin_group_reports",
            "admin_group_system", "change_language", "main"} <= codes


def test_main_home_has_compact_service_grid():
    fa = ui.main_menu("fa")
    rows = fa.inline_keyboard
    assert len(rows) <= 5
    codes = {c for _, c in buttons(fa)}
    assert {"client_signals", "account", "vip", "guide_hub",
            "support", "change_language"} <= codes
    assert "client_autotrade_access" not in codes


def test_account_groups_payments_and_referral():
    fa = ui.account_menu("fa", True, True)
    codes = {c for _, c in buttons(fa)}
    assert {"my_payments", "referral", "vip", "client_vip_access",
            "client_autotrade_access", "change_language", "main"} <= codes


def test_subscription_has_exactly_three_real_products():
    fa = buttons(ui.subscription_service_menu("fa", False, False))
    products = [(t, c) for t, c in fa if c in {
        "buyservice:VIP", "buyservice:AUTO", "buyservice:BUNDLE"
    }]
    assert [c for _, c in products] == [
        "buyservice:VIP", "buyservice:AUTO", "buyservice:BUNDLE"
    ]


def test_all_static_ui_callback_literals_have_a_router_handler():
    ui_tree = ast.parse((ROOT / "app" / "ui.py").read_text(encoding="utf-8"))
    main_tree = ast.parse((ROOT / "app" / "main.py").read_text(encoding="utf-8"))

    callbacks = set()
    for node in ast.walk(ui_tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "InlineKeyboardButton":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                if isinstance(node.args[1].value, str):
                    callbacks.add(node.args[1].value)
            for kw in node.keywords:
                if kw.arg == "callback_data" and isinstance(kw.value, ast.Constant):
                    if isinstance(kw.value.value, str):
                        callbacks.add(kw.value.value)

    exact = set()
    prefixes = set()
    for node in ast.walk(main_tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            # Do not depend on ast.unparse choosing single or double quotes.
            # Extract the actual constant from the filter expression instead.
            for expr in ast.walk(dec):
                if not isinstance(expr, ast.Compare) or len(expr.ops) != 1 or len(expr.comparators) != 1:
                    continue
                if not isinstance(expr.left, ast.Attribute) or expr.left.attr != "data":
                    continue
                if not (isinstance(expr.left.value, ast.Name) and expr.left.value.id == "F"):
                    continue
                rhs = expr.comparators[0]
                if not isinstance(rhs, ast.Constant) or not isinstance(rhs.value, str):
                    continue
                if isinstance(expr.ops[0], ast.Eq):
                    exact.add(rhs.value)
            for expr in ast.walk(dec):
                if not isinstance(expr, ast.Call) or not isinstance(expr.func, ast.Attribute):
                    continue
                if expr.func.attr != "startswith" or len(expr.args) != 1:
                    continue
                receiver = expr.func.value
                if not (isinstance(receiver, ast.Attribute) and receiver.attr == "data"):
                    continue
                if not (isinstance(receiver.value, ast.Name) and receiver.value.id == "F"):
                    continue
                arg = expr.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    prefixes.add(arg.value)

    missing = sorted(c for c in callbacks if c not in exact and not any(c.startswith(p) for p in prefixes))
    assert not missing, f"UI callbacks without router handlers: {missing}"
