from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AcademySettings:
    enabled: bool = os.getenv("ACADEMY_AGENT_ENABLED", "false").strip().lower() in _TRUE
    daily_time: str = os.getenv("ACADEMY_DAILY_TIME", "20:30").strip()
    timezone: str = os.getenv("ACADEMY_TIMEZONE", os.getenv("TIMEZONE", "Asia/Tehran")).strip() or "Asia/Tehran"
    approval_mode: bool = os.getenv("ACADEMY_APPROVAL_MODE", "true").strip().lower() in _TRUE
    catchup_enabled: bool = os.getenv("ACADEMY_CATCHUP_ENABLED", "true").strip().lower() in _TRUE
    image_count: int = max(2, min(3, int(os.getenv("ACADEMY_IMAGE_COUNT", "3"))))
    max_retries: int = max(1, min(5, int(os.getenv("ACADEMY_MAX_RETRIES", "3"))))


academy_settings = AcademySettings()
