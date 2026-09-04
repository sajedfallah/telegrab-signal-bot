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


content_settings = ContentSettings()
