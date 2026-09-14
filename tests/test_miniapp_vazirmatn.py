from pathlib import Path


CDN = "https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css"


def _text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_user_and_admin_miniapps_load_vazirmatn():
    user = _text("miniapp/index.html")
    admin = _text("miniapp/admin.html")
    for html in (user, admin):
        assert CDN in html
        assert "vazirmatn.css" in html


def test_vazirmatn_is_the_global_ui_family():
    css = _text("miniapp/vazirmatn.css")
    assert '--nexus-font-family: "Vazirmatn"' in css
    assert "body *" in css
    assert "font-family: var(--nexus-font-family) !important" in css
