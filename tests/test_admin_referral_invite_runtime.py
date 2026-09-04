from urllib.parse import parse_qs, urlparse

from app.admin_referral_invite_runtime import build_invite_link, build_share_url, invite_copy


def test_build_invite_link_uses_existing_referral_code():
    assert build_invite_link("NexusBot", "NXABC123") == (
        "https://t.me/NexusBot?start=ref_NXABC123"
    )


def test_build_invite_link_accepts_at_prefixed_username():
    assert build_invite_link("@NexusBot", "R1") == "https://t.me/NexusBot?start=ref_R1"


def test_build_share_url_contains_link_and_short_copy():
    link = "https://t.me/NexusBot?start=ref_R1"
    text = invite_copy("fa")
    url = build_share_url(link, text)
    parsed = urlparse(url)
    values = parse_qs(parsed.query)
    assert parsed.netloc == "t.me"
    assert parsed.path == "/share/url"
    assert values["url"] == [link]
    assert values["text"] == [text]
    assert "NEXUS" in text
