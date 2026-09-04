from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import Any

from .taxonomy import category, safe_source_urls


@dataclass(frozen=True)
class Topic:
    slug: str
    template_key: str
    title_fa: str
    definition_fa: str
    key_points_fa: tuple[str, ...]
    example_fa: str
    level: str = "foundation"


@dataclass(frozen=True)
class VisualBrief:
    prompt: str
    motif: str
    mood: str = "premium dark editorial"


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
    category_key: str = "ict_education"
    post_id: str = ""
    priority: int = 50
    source_urls: list[str] = field(default_factory=list)
    related_links: list[tuple[str, str]] = field(default_factory=list)

    @staticmethod
    def _clip(value: str, limit: int) -> str:
        value = " ".join(str(value or "").split())
        return value if len(value) <= limit else value[: max(1, limit - 1)].rstrip() + "…"

    def caption(self, permalink: str | None = None) -> str:
        cat = category(self.category_key)
        title = escape(self._clip(self.title, 76))
        definition = escape(self._clip(self.definition, 250))
        points = [escape(self._clip(item, 82)) for item in self.key_points[:4]]
        example = escape(self._clip(self.example, 145)) if self.example else ""
        cta = escape(self._clip(self.cta, 105)) if self.cta else ""
        tags = " ".join(self.hashtags[:8])

        blocks: list[str] = [
            f"<b>{cat.emoji} NEXUS | {escape(cat.label_fa)}</b>",
            f"<b>{title}</b>",
            definition,
        ]
        if points:
            blocks.append("\n".join(f"• {point}" for point in points))
        if example:
            blocks.append(f"<b>مثال:</b> {example}")
        if cta:
            blocks.append(cta)

        source_urls = safe_source_urls(self.source_urls)
        if source_urls:
            source_links = " | ".join(
                f'<a href="{escape(url, quote=True)}">منبع {index}</a>'
                for index, url in enumerate(source_urls[:2], start=1)
            )
            blocks.append(f"🔗 {source_links}")

        related = []
        for label, url in self.related_links[:2]:
            safe_urls = safe_source_urls([url])
            if safe_urls:
                related.append(f'<a href="{escape(safe_urls[0], quote=True)}">{escape(self._clip(label, 42))}</a>')
        if related:
            blocks.append("📚 مرتبط: " + " | ".join(related))

        if tags:
            blocks.append(tags)
        if self.post_id:
            blocks.append(f"🆔 <code>{escape(self.post_id)}</code>")
        if permalink:
            valid = safe_source_urls([permalink])
            if valid:
                blocks.append(f'🔗 <a href="{escape(valid[0], quote=True)}">لینک مستقیم پست</a>')

        caption = "\n\n".join(block for block in blocks if block).strip()
        if len(caption) <= 1010:
            return caption

        # Preserve valid HTML if the complete caption is too long. Drop the
        # least important prose blocks instead of slicing through HTML tags.
        for optional in (f"<b>مثال:</b> {example}" if example else "", cta):
            if optional and optional in blocks:
                blocks.remove(optional)
                caption = "\n\n".join(block for block in blocks if block).strip()
                if len(caption) <= 1010:
                    return caption
        return "\n\n".join(block for block in blocks if block).strip()[:1010]
