from app import web_chart_capture_runtime as capture


def test_staging_telegram_publish_is_fail_closed(monkeypatch):
    monkeypatch.setenv("NEXUS_ENV", "staging")
    monkeypatch.delenv("NEXUS_ALLOW_STAGING_TELEGRAM_PUBLISH", raising=False)
    assert capture.staging_telegram_publication_allowed() is False


def test_staging_telegram_publish_needs_explicit_local_acknowledgement(monkeypatch):
    monkeypatch.setenv("NEXUS_ENV", "staging")
    monkeypatch.setenv("NEXUS_ALLOW_STAGING_TELEGRAM_PUBLISH", "true")
    assert capture.staging_telegram_publication_allowed() is True


def test_production_behavior_is_not_changed_by_staging_guard(monkeypatch):
    monkeypatch.setenv("NEXUS_ENV", "production")
    monkeypatch.delenv("NEXUS_ALLOW_STAGING_TELEGRAM_PUBLISH", raising=False)
    assert capture.staging_telegram_publication_allowed() is True
