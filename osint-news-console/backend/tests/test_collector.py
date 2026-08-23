from datetime import datetime, timedelta

from app import collector


def test_entry_without_timestamp_remains_unknown():
    assert collector._entry_published_at({"title": "无时间新闻"}) is None


def test_latest_timestamp_is_selected_from_all_entries():
    entries = [
        {"published_parsed": (2026, 8, 18, 1, 0, 0, 0, 0, 0)},
        {"published_parsed": (2026, 8, 19, 2, 0, 0, 0, 0, 0)},
    ]
    assert collector._latest_entry_published_at(entries) == datetime(
        2026, 8, 19, 2, 0, 0
    )


def test_stale_feed_is_not_reported_as_ok(monkeypatch):
    now = datetime(2026, 8, 19, 12, 0, 0)
    monkeypatch.setattr(collector, "utc_now", lambda: now)
    status, message = collector._freshness_status(
        {"interval_minutes": 5, "stale_after_hours": 24},
        now - timedelta(hours=25),
    )
    assert status == "stale"
    assert "25.0 小时" in message


def test_aggregator_preserves_original_publisher_name():
    source = {"name": "聚合源", "use_entry_source": True}
    entry = {"source": {"title": "原始媒体"}}
    assert collector._entry_source_name(source, entry) == "原始媒体"
