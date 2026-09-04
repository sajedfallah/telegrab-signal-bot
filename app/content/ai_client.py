from __future__ import annotations

import json
import logging
from typing import Any

import httpx

log = logging.getLogger("nexus-content-ai")


class OpenAICompatibleTextClient:
    """Small OpenAI-compatible chat-completions client.

    Gemini, OpenAI and OpenRouter can all be selected through environment
    variables. The API key is never logged. If the provider is unavailable,
    the content pipeline falls back to the curated NEXUS knowledge base.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        provider: str = "openai-compatible",
        timeout: float = 45.0,
    ):
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.base_url = (base_url or "").strip().rstrip("/")
        self.provider = (provider or "openai-compatible").strip().lower()
        self.timeout = float(timeout)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

    async def complete(self, prompt: str) -> str | None:
        if not self.enabled:
            return None

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the official NEXUS educational content writer. "
                        "Follow the requested output format exactly."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1500,
            "temperature": 0.35,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return None
            content = ((choices[0] or {}).get("message") or {}).get("content")
            if isinstance(content, str):
                return content.strip() or None
            if isinstance(content, list):
                chunks: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("content")
                        if isinstance(text, str):
                            chunks.append(text)
                return "\n".join(chunks).strip() or None
            return None
        except Exception as exc:
            log.warning(
                "content AI request failed provider=%s model=%s; curated fallback will be used: %s",
                self.provider,
                self.model,
                exc,
            )
            return None


OpenAITextClient = OpenAICompatibleTextClient


def extract_json_object(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            value = json.loads(text[start:end + 1])
            return value if isinstance(value, dict) else None
        except Exception:
            return None
    return None
