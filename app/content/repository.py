from __future__ import annotations

import json
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

            CREATE TABLE IF NOT EXISTS content_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT NOT NULL UNIQUE,
                scheduled_date TEXT NOT NULL,
                category_key TEXT NOT NULL,
                template_key TEXT,
                topic_slug TEXT,
                title TEXT,
                priority INTEGER NOT NULL DEFAULT 50,
                hashtags_json TEXT NOT NULL DEFAULT '[]',
                source_urls_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'proposed',
                telegram_message_id INTEGER,
                permalink TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_content_registry_day
                ON content_registry(scheduled_date, status);
            CREATE INDEX IF NOT EXISTS idx_content_registry_category
                ON content_registry(category_key, scheduled_date, status);
            CREATE INDEX IF NOT EXISTS idx_content_registry_topic
                ON content_registry(topic_slug, published_at);
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


def mark_skipped(scheduled_date: str, reason: str) -> None:
    with db.conn() as con:
        con.execute(
            "UPDATE content_posts SET status='skipped', error=?, updated_at=? WHERE scheduled_date=?",
            (str(reason)[:1500], _now(), scheduled_date),
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


def registry_upsert(
    *,
    post_id: str,
    scheduled_date: str,
    category_key: str,
    template_key: str,
    topic_slug: str,
    title: str,
    priority: int,
    hashtags: list[str],
    source_urls: list[str],
    status: str = "ready",
) -> None:
    ensure_schema()
    now = _now()
    with db.conn() as con:
        con.execute(
            """
            INSERT INTO content_registry(
                post_id,scheduled_date,category_key,template_key,topic_slug,title,
                priority,hashtags_json,source_urls_json,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(post_id) DO UPDATE SET
                scheduled_date=excluded.scheduled_date,
                category_key=excluded.category_key,
                template_key=excluded.template_key,
                topic_slug=excluded.topic_slug,
                title=excluded.title,
                priority=excluded.priority,
                hashtags_json=excluded.hashtags_json,
                source_urls_json=excluded.source_urls_json,
                status=excluded.status,
                updated_at=excluded.updated_at,
                error=NULL
            """,
            (
                post_id,
                scheduled_date,
                category_key,
                template_key,
                topic_slug,
                title,
                max(0, min(100, int(priority))),
                json.dumps(list(hashtags), ensure_ascii=False),
                json.dumps(list(source_urls), ensure_ascii=False),
                status,
                now,
                now,
            ),
        )


def registry_mark_previewed(post_id: str, message_id: int | None = None) -> None:
    ensure_schema()
    with db.conn() as con:
        con.execute(
            "UPDATE content_registry SET status='previewed', telegram_message_id=?, updated_at=? WHERE post_id=?",
            (int(message_id) if message_id else None, _now(), post_id),
        )


def registry_mark_published(post_id: str, message_id: int, permalink: str | None) -> None:
    ensure_schema()
    now = _now()
    with db.conn() as con:
        con.execute(
            """UPDATE content_registry
               SET status='published', telegram_message_id=?, permalink=?, published_at=?, updated_at=?
               WHERE post_id=?""",
            (int(message_id), permalink, now, now, post_id),
        )


def registry_mark_failed(post_id: str, error: str) -> None:
    ensure_schema()
    with db.conn() as con:
        con.execute(
            "UPDATE content_registry SET status='failed', error=?, updated_at=? WHERE post_id=?",
            (str(error)[:1500], _now(), post_id),
        )


def registry_mark_skipped(post_id: str, reason: str) -> None:
    ensure_schema()
    with db.conn() as con:
        con.execute(
            "UPDATE content_registry SET status='skipped', error=?, updated_at=? WHERE post_id=?",
            (str(reason)[:1500], _now(), post_id),
        )


def registry_count_for_day(scheduled_date: str, category_key: str | None = None) -> int:
    ensure_schema()
    with db.conn() as con:
        if category_key:
            row = con.execute(
                "SELECT COUNT(*) AS n FROM content_registry WHERE scheduled_date=? AND category_key=? AND status='published'",
                (scheduled_date, category_key),
            ).fetchone()
        else:
            row = con.execute(
                "SELECT COUNT(*) AS n FROM content_registry WHERE scheduled_date=? AND status='published'",
                (scheduled_date,),
            ).fetchone()
        return int(row["n"] or 0) if row else 0


def related_published(category_key: str, exclude_post_id: str, limit: int = 2) -> list[tuple[str, str]]:
    ensure_schema()
    with db.conn() as con:
        rows = con.execute(
            """SELECT title, permalink
               FROM content_registry
               WHERE category_key=? AND post_id<>? AND status='published'
                 AND permalink IS NOT NULL AND permalink<>''
               ORDER BY published_at DESC LIMIT ?""",
            (category_key, exclude_post_id, max(1, min(5, int(limit)))),
        ).fetchall()
        return [
            (str(row["title"] or "مطلب مرتبط"), str(row["permalink"]))
            for row in rows
            if row["permalink"]
        ]
