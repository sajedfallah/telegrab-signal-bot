from __future__ import annotations

from datetime import datetime, timezone

from .. import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_schema() -> None:
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS content_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheduled_date TEXT NOT NULL UNIQUE,
                template_key TEXT,
                topic_slug TEXT,
                title TEXT,
                caption TEXT,
                image_path TEXT,
                status TEXT NOT NULL DEFAULT 'building',
                attempts INTEGER NOT NULL DEFAULT 1,
                telegram_message_id INTEGER,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_content_posts_status
                ON content_posts(status, scheduled_date);
            CREATE INDEX IF NOT EXISTS idx_content_posts_topic
                ON content_posts(topic_slug, scheduled_date);
            """
        )


def claim_day(scheduled_date: str, max_attempts: int = 3) -> bool:
    ensure_schema()
    now = _now()
    with db.conn() as con:
        row = con.execute(
            "SELECT status, attempts FROM content_posts WHERE scheduled_date=?",
            (scheduled_date,),
        ).fetchone()
        if row is None:
            con.execute(
                "INSERT INTO content_posts(scheduled_date,status,attempts,created_at,updated_at) VALUES(?,?,?,?,?)",
                (scheduled_date, "building", 1, now, now),
            )
            return True
        status = str(row["status"])
        attempts = int(row["attempts"] or 0)
        if status == "failed" and attempts < max_attempts:
            con.execute(
                "UPDATE content_posts SET status='building', attempts=attempts+1, error=NULL, updated_at=? WHERE scheduled_date=?",
                (now, scheduled_date),
            )
            return True
        return False


def save_draft(
    scheduled_date: str,
    template_key: str,
    topic_slug: str,
    title: str,
    caption: str,
    image_path: str,
) -> None:
    with db.conn() as con:
        con.execute(
            """UPDATE content_posts
               SET template_key=?, topic_slug=?, title=?, caption=?, image_path=?,
                   status='ready', updated_at=?
               WHERE scheduled_date=?""",
            (template_key, topic_slug, title, caption, image_path, _now(), scheduled_date),
        )


def mark_published(scheduled_date: str, message_id: int) -> None:
    now = _now()
    with db.conn() as con:
        con.execute(
            "UPDATE content_posts SET status='published', telegram_message_id=?, published_at=?, updated_at=? WHERE scheduled_date=?",
            (int(message_id), now, now, scheduled_date),
        )


def mark_previewed(scheduled_date: str, message_id: int | None = None) -> None:
    with db.conn() as con:
        con.execute(
            "UPDATE content_posts SET status='previewed', telegram_message_id=?, updated_at=? WHERE scheduled_date=?",
            (int(message_id) if message_id else None, _now(), scheduled_date),
        )


def mark_failed(scheduled_date: str, error: str) -> None:
    with db.conn() as con:
        con.execute(
            "UPDATE content_posts SET status='failed', error=?, updated_at=? WHERE scheduled_date=?",
            (str(error)[:1500], _now(), scheduled_date),
        )


def recent_topic_slugs(limit: int = 12) -> list[str]:
    ensure_schema()
    with db.conn() as con:
        rows = con.execute(
            "SELECT topic_slug FROM content_posts WHERE topic_slug IS NOT NULL AND status IN ('ready','previewed','published') ORDER BY scheduled_date DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [str(row["topic_slug"]) for row in rows if row["topic_slug"]]


def status_for_day(scheduled_date: str) -> str | None:
    ensure_schema()
    with db.conn() as con:
        row = con.execute(
            "SELECT status FROM content_posts WHERE scheduled_date=?",
            (scheduled_date,),
        ).fetchone()
        return str(row["status"]) if row else None
