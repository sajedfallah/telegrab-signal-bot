from __future__ import annotations

import os
from dataclasses import dataclass


_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ContentSettings:
    enabled: bool = os.getenv("CONTENT_AGENTS_ENABLED", "false").strip().lower() in _TRUE
    daily_time: str = os.getenv("CONTENT_DAILY_TIME", "12:00").strip()
    catchup_enabled: bool = os.getenv("CONTENT_CATCHUP_ENABLED", "true").strip().lower() in _TRUE
    approval_mode: bool = os.getenv("CONTENT_APPROVAL_MODE", "true").strip().lower() in _TRUE
    protect_content: bool = os.getenv("CONTENT_PROTECT_CONTENT", "false").strip().lower() in _TRUE

    editorial_enabled: bool = os.getenv("CONTENT_EDITORIAL_ENABLED", "true").strip().lower() in _TRUE
    max_posts_per_day: int = max(1, min(12, int(os.getenv("CONTENT_MAX_POSTS_PER_DAY", "4"))))

    ai_provider: str = os.getenv("CONTENT_AI_PROVIDER", "gemini").strip().lower() or "gemini"
    ai_api_key: str = os.getenv(
        "CONTENT_AI_API_KEY",
        os.getenv("GEMINI_API_KEY", os.getenv("CONTENT_OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))),
    ).strip()
    ai_base_url: str = os.getenv(
        "CONTENT_AI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ).strip()
    text_model: str = os.getenv("CONTENT_TEXT_MODEL", "gemini-3.8-flash").strip()

    image_ai_enabled: bool = os.getenv("CONTENT_IMAGE_AI_ENABLED", "false").strip().lower() in _TRUE
    image_model: str = os.getenv("CONTENT_IMAGE_MODEL", "gemini-3.1-flash-image").strip()


content_settings = ContentSettings()
