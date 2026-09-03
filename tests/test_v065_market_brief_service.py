from __future__ import annotations

from datetime import datetime, timezone

from app.services import market_brief_service as svc


RSS = """<?xml version='1.0'?>
<rss><channel><title>FX Test</title>
<item>
<title>Breaking: US CPI inflation surprises markets as Gold jumps</title>
<link>https://example.com/cpi</link>
<pubDate>Fri, 04 Sep 2026 01:00:00 GMT</pubDate>
</item>
<item>
<title>Minor company update with no macro relevance</title>
<link>https://example.com/minor</link>
<pubDate>Fri, 04 Sep 2026 00:55:00 GMT</pubDate>
</item>
</channel></rss>"""

CALENDAR = """<?xml version='1.0'?>
<weeklyevents>
<event>
<title>Non-Farm Employment Change</title>
<country>USD</country>
<date>09-04-2026</date>
<time>4:00pm</time>
<impact>High</impact>
<forecast>80K</forecast>
<previous>75K</previous>
<url>https://example.com/nfp</url>
</event>
<event>
<title>Low Impact Survey</title>
<country>EUR</country>
<date>09-04-2026</date>
<time>10:00am</time>
<impact>Low</impact>
</event>
</weeklyevents>"""


def test_rss_parser_scores_important_market_headlines():
    rows = svc.parse_rss(RSS, "FXStreet")
    assert len(rows) == 2
    assert rows[0].source == "FXStreet"
    important = next(x for x in rows if "CPI" in x.title)
    minor = next(x for x in rows if "Minor" in x.title)
    assert important.score >= 10
    assert minor.score == 0
    assert important.published_at == datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc)


def test_important_recent_news_filters_low_score_and_old_items():
    rows = svc.parse_rss(RSS, "FXStreet")
    now = datetime(2026, 9, 4, 1, 30, tzinfo=timezone.utc)
    selected = svc.important_recent_news(rows, now_utc=now, minimum_score=5, max_age_minutes=60)
    assert [x.link for x in selected] == ["https://example.com/cpi"]


def test_forex_factory_calendar_parser_and_high_impact_filter():
    rows = svc.parse_forex_factory_calendar(CALENDAR, feed_timezone="UTC")
    assert len(rows) == 2
    nfp = rows[0]
    assert nfp.country == "USD"
    assert nfp.impact == "High"
    assert nfp.when_utc == datetime(2026, 9, 4, 16, 0, tzinfo=timezone.utc)

    high = svc.today_high_impact_events(
        rows,
        now_utc=datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc),
        local_timezone="UTC",
    )
    assert len(high) == 1
    assert high[0].title == "Non-Farm Employment Change"


def test_morning_brief_contains_calendar_and_headline_without_invented_analysis():
    news = svc.parse_rss(RSS, "FXStreet")
    events = svc.parse_forex_factory_calendar(CALENDAR, feed_timezone="UTC")
    text = svc.render_morning_brief(
        lang="fa",
        now_utc=datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc),
        local_timezone="UTC",
        events=events,
        news=news,
    )
    assert "NEXUS Morning Brief" in text
    assert "Non-Farm Employment Change" in text
    assert "US CPI inflation surprises markets" in text
    assert "80K" in text
    assert "75K" in text


def test_event_alert_is_pre_event_and_contains_forecast_previous():
    event = svc.parse_forex_factory_calendar(CALENDAR, feed_timezone="UTC")[0]
    text = svc.render_event_alert(event, lang="fa", local_timezone="UTC", minutes_left=30)
    assert "30 دقیقه" in text
    assert "80K" in text
    assert "75K" in text


def test_news_item_key_is_stable_for_deduplication():
    item = svc.parse_rss(RSS, "FXStreet")[0]
    again = svc.parse_rss(RSS, "FXStreet")[0]
    assert item.key == again.key
    assert len(item.key) == 24
