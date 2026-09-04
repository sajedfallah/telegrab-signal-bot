from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Topic:
    slug: str
    template_key: str
    title_fa: str
    definition_fa: str
    key_points_fa: tuple[str, ...]
    example_fa: str
    level: str = "foundation"


@dataclass
class ContentDraft:
    scheduled_date: str
    template_key: str
    topic_slug: str
    title: str
    kicker: str
    definition: str
    key_points: list[str]
    example: str
    cta: str
    hashtags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def caption(self) -> str:
        bullets = "\n".join(f"• {item}" for item in self.key_points[:4])
        tags = " ".join(self.hashtags[:6])
        parts = [
            f"<b>📘 NEXUS ICT | {self.title}</b>",
            self.definition,
            bullets,
            f"<b>مثال:</b> {self.example}" if self.example else "",
            self.cta,
            tags,
        ]
        return "\n\n".join(part for part in parts if part).strip()[:950]
