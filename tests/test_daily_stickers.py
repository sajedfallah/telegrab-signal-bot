from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.daily_stickers.storage import StickerStore


def test_store_and_delivery_idempotency(tmp_path: Path):
    store = StickerStore(tmp_path / "daily.db")
    day = date(2026, 9, 6)
    store.set_sticker(day, "file-1", file_unique_id="u1", set_name="pack")
    row = store.get_sticker(day)
    assert row is not None
    assert row["file_id"] == "file-1"
    assert not store.was_delivered(day, -100123)
    store.mark_delivered(day, -100123, 77)
    assert store.was_delivered(day, -100123)


def test_import_pack_maps_consecutive_dates(tmp_path: Path):
    store = StickerStore(tmp_path / "daily.db")
    stickers = [
        SimpleNamespace(file_id=f"f{i}", file_unique_id=f"u{i}", set_name="pack", emoji="📅")
        for i in range(3)
    ]
    assert store.import_pack(date(2026, 9, 6), stickers, 3) == 3
    assert store.get_sticker("2026-09-06")["file_id"] == "f0"
    assert store.get_sticker("2026-09-08")["file_id"] == "f2"
