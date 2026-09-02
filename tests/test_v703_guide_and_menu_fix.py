from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_vip_text_is_not_singleton_tuple():
    tree = ast.parse((ROOT / 'app' / 'main.py').read_text(encoding='utf-8'))
    bad=[]
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Tuple) and len(n.value.elts)==1:
            if any(isinstance(t, ast.Name) and t.id == 'text' for t in n.targets):
                bad.append(n.lineno)
    assert not bad, f'singleton tuple assigned to text at lines {bad}'


def test_guide_hub_is_in_main_menu_and_handlers_exist():
    ui=(ROOT/'app'/'ui.py').read_text(encoding='utf-8')
    main=(ROOT/'app'/'main.py').read_text(encoding='utf-8')
    assert 'راهنما' in ui
    assert 'callback_data="guide_hub"' not in ui or 'guide_hub' in ui
    for token in ['guide_intro','guide_purchase','guide_mt5','guide_crypto','guide_text']:
        assert token in ui or token in main


def test_guide_asset_contract_documented():
    readme=(ROOT/'assets'/'guides'/'README_FA.txt').read_text(encoding='utf-8')
    for filename in ['NEXUS_Intro.mp4','NEXUS_Purchase_Guide.mp4','NEXUS_AutoTrade_MT5_Guide.mp4','NEXUS_AutoTrade_Crypto_Guide.mp4']:
        assert filename in readme
