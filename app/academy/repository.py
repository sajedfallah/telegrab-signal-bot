from __future__ import annotations

import json
from datetime import date, datetime, timezone

from .. import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_schema() -> None:
    with db.conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS academy_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheduled_date TEXT NOT NULL UNIQUE,
                course_key TEXT NOT NULL,
                module_key TEXT NOT NULL,
                lesson_number INTEGER NOT NULL,
                topic_slug TEXT NOT NULL,
                title TEXT NOT NULL,
                primary_keyword TEXT,
                secondary_keywords_json TEXT NOT NULL DEFAULT '[]',
                meta_description TEXT,
                slug TEXT,
                caption TEXT,
                image_paths_json TEXT NOT NULL DEFAULT '[]',
                exercise_prompt TEXT,
                exercise_options_json TEXT NOT NULL DEFAULT '[]',
                correct_option INTEGER,
                status TEXT NOT NULL DEFAULT 'planned',
                telegram_message_id INTEGER,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_academy_lessons_status
                ON academy_lessons(status, scheduled_date);
            CREATE INDEX IF NOT EXISTS idx_academy_lessons_topic
                ON academy_lessons(topic_slug, published_at);

            CREATE TABLE IF NOT EXISTS academy_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                selected_option INTEGER NOT NULL,
                is_correct INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(lesson_id, user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_academy_answers_lesson
                ON academy_answers(lesson_id, is_correct);

            CREATE TABLE IF NOT EXISTS academy_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheduled_date TEXT NOT NULL,
                stage TEXT NOT NULL,
                error TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def next_sequence_index() -> int:
    ensure_schema()
    with db.conn() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM academy_lessons WHERE status='published'").fetchone()
        return int(row["n"] or 0) if row else 0


def status_for_day(day: date | str) -> str | None:
    ensure_schema()
    key = day.isoformat() if isinstance(day, date) else str(day)
    with db.conn() as con:
        row = con.execute("SELECT status FROM academy_lessons WHERE scheduled_date=?", (key,)).fetchone()
        return str(row["status"]) if row else None


def save_ready(*, scheduled_date: str, course_key: str, module_key: str, lesson_number: int,
               topic_slug: str, title: str, primary_keyword: str, secondary_keywords: list[str],
               meta_description: str, slug: str, caption: str, image_paths: list[str],
               exercise_prompt: str, exercise_options: list[str], correct_option: int) -> int:
    ensure_schema()
    now = _now()
    with db.conn() as con:
        con.execute(
            """
            INSERT INTO academy_lessons(
                scheduled_date,course_key,module_key,lesson_number,topic_slug,title,
                primary_keyword,secondary_keywords_json,meta_description,slug,caption,
                image_paths_json,exercise_prompt,exercise_options_json,correct_option,
                status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(scheduled_date) DO UPDATE SET
                course_key=excluded.course_key,module_key=excluded.module_key,
                lesson_number=excluded.lesson_number,topic_slug=excluded.topic_slug,
                title=excluded.title,primary_keyword=excluded.primary_keyword,
                secondary_keywords_json=excluded.secondary_keywords_json,
                meta_description=excluded.meta_description,slug=excluded.slug,
                caption=excluded.caption,image_paths_json=excluded.image_paths_json,
                exercise_prompt=excluded.exercise_prompt,
                exercise_options_json=excluded.exercise_options_json,
                correct_option=excluded.correct_option,status='ready',error=NULL,updated_at=excluded.updated_at
            """,
            (scheduled_date, course_key, module_key, int(lesson_number), topic_slug, title,
             primary_keyword, json.dumps(secondary_keywords, ensure_ascii=False), meta_description,
             slug, caption, json.dumps(image_paths, ensure_ascii=False), exercise_prompt,
             json.dumps(exercise_options, ensure_ascii=False), int(correct_option), "ready", now, now),
        )
        row = con.execute("SELECT id FROM academy_lessons WHERE scheduled_date=?", (scheduled_date,)).fetchone()
        return int(row["id"])


def get_by_day(day: date | str):
    ensure_schema()
    key = day.isoformat() if isinstance(day, date) else str(day)
    with db.conn() as con:
        return con.execute("SELECT * FROM academy_lessons WHERE scheduled_date=?", (key,)).fetchone()


def get_by_id(lesson_id: int):
    ensure_schema()
    with db.conn() as con:
        return con.execute("SELECT * FROM academy_lessons WHERE id=?", (int(lesson_id),)).fetchone()


def mark_previewed(day: str) -> None:
    with db.conn() as con:
        con.execute("UPDATE academy_lessons SET status='previewed',updated_at=? WHERE scheduled_date=?", (_now(), day))


def mark_published(day: str, message_id: int) -> None:
    now = _now()
    with db.conn() as con:
        con.execute(
            "UPDATE academy_lessons SET status='published',telegram_message_id=?,published_at=?,updated_at=? WHERE scheduled_date=?",
            (int(message_id), now, now, day),
        )


def mark_cancelled(day: str) -> None:
    with db.conn() as con:
        con.execute("UPDATE academy_lessons SET status='cancelled',updated_at=? WHERE scheduled_date=?", (_now(), day))


def record_failure(day: str, stage: str, error: str) -> None:
    ensure_schema()
    now = _now()
    with db.conn() as con:
        con.execute("INSERT INTO academy_failures(scheduled_date,stage,error,created_at) VALUES(?,?,?,?)",
                    (day, stage[:80], str(error)[:1500], now))
        con.execute("UPDATE academy_lessons SET status='failed',error=?,updated_at=? WHERE scheduled_date=?",
                    (str(error)[:1500], now, day))


def record_answer(lesson_id: int, user_id: int, selected_option: int, is_correct: bool) -> None:
    ensure_schema()
    with db.conn() as con:
        con.execute(
            """INSERT INTO academy_answers(lesson_id,user_id,selected_option,is_correct,created_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(lesson_id,user_id) DO UPDATE SET selected_option=excluded.selected_option,
                   is_correct=excluded.is_correct,created_at=excluded.created_at""",
            (int(lesson_id), int(user_id), int(selected_option), 1 if is_correct else 0, _now()),
        )


def stats_for_lesson(lesson_id: int) -> tuple[int, int]:
    ensure_schema()
    with db.conn() as con:
        row = con.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(is_correct),0) AS correct FROM academy_answers WHERE lesson_id=?",
            (int(lesson_id),),
        ).fetchone()
        return (int(row["total"] or 0), int(row["correct"] or 0)) if row else (0, 0)


def recent_lessons(limit: int = 10):
    ensure_schema()
    with db.conn() as con:
        return con.execute(
            "SELECT * FROM academy_lessons ORDER BY scheduled_date DESC LIMIT ?", (max(1, min(30, int(limit))),)
        ).fetchall()
