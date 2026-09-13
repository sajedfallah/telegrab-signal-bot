from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "miniapp"


def test_performance_chart_is_unique_and_uses_canonical_equity_curve():
    track = (ROOT / "track-record.js").read_text(encoding="utf-8")
    assert "risk.equity_curve_r" in track
    assert "performanceChart(overview.risk)" in track
    assert "داده معتبر کافی" in track
    for name in ("home-v2.js", "signals-v2.js", "pricing-v2.js", "account-v2.js", "vip-preview-v1.js"):
        assert "track-equity-chart" not in (ROOT / name).read_text(encoding="utf-8")


def test_landing_transition_keeps_existing_bootstrap_and_reduced_motion():
    js = (ROOT / "landing-v5.js").read_text(encoding="utf-8")
    css = (ROOT / "landing-v5.css").read_text(encoding="utf-8")
    assert "window.render === 'function'" in js and "window.hydrateNexusHome" in js
    assert "nexus-app-entering" in js and "is-leaving" in js
    assert "prefers-reduced-motion" in js and "prefers-reduced-motion" in css
    assert "340ms" in css


def test_main_routes_hide_back_but_nested_routes_can_show_it():
    js = (ROOT / "navigation-v7.js").read_text(encoding="utf-8")
    css = (ROOT / "user-v066-final.css").read_text(encoding="utf-8")
    assert "['landing', 'home', 'signals', 'subscriptions', 'account'].includes(currentRoute)" in js
    assert ".nexus-page-back[hidden]" in css
    assert "left: 12px" in css
