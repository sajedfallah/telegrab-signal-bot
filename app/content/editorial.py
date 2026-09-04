from __future__ import annotations

from dataclasses import dataclass

from . import repository
from .settings import content_settings
from .taxonomy import category


@dataclass(frozen=True)
class EditorialDecision:
    allowed: bool
    reason: str


class ChannelEditorAgent:
    """Deterministic editorial gate for the public NEXUS channel.

    The agent does not create content. It decides whether a proposed post is
    worth publishing, using category priority thresholds and daily caps. Urgent
    high-impact alerts can bypass the global daily cap but never their own
    category cap.
    """

    def evaluate(self, scheduled_date: str, category_key: str, priority: int) -> EditorialDecision:
        if not content_settings.editorial_enabled:
            return EditorialDecision(True, "editorial gate disabled")

        cat = category(category_key)
        priority = max(0, min(100, int(priority)))
        if priority < cat.min_priority:
            return EditorialDecision(
                False,
                f"priority {priority} below {cat.key} threshold {cat.min_priority}",
            )

        category_count = repository.registry_count_for_day(scheduled_date, cat.key)
        if category_count >= cat.max_per_day:
            return EditorialDecision(
                False,
                f"daily category cap reached for {cat.key}: {cat.max_per_day}",
            )

        total_count = repository.registry_count_for_day(scheduled_date)
        if not cat.urgent and total_count >= content_settings.max_posts_per_day:
            return EditorialDecision(
                False,
                f"global public-channel cap reached: {content_settings.max_posts_per_day}",
            )

        return EditorialDecision(True, "approved")
