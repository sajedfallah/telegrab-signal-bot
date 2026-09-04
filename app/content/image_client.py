from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

log = logging.getLogger("nexus-content-image")


class GeminiImageClient:
    """Optional native Gemini image generation client.

    Image generation is intentionally opt-in because Gemini image models do not
    have the same free tier as the text model. The caller must enable it through
    CONTENT_IMAGE_AI_ENABLED. Failures always fall back to the local NEXUS visual
    renderer and never stop the publishing pipeline.
    """

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(self, api_key: str, model: str, enabled: bool, timeout: float = 70.0):
        self.api_key = (api_key or "").strip()
        self.model = (model or "gemini-3.1-flash-image").strip()
        self.enabled = bool(enabled and self.api_key and self.model)
        self.timeout = float(timeout)

    async def generate(self, prompt: str) -> bytes | None:
        if not self.enabled or not prompt.strip():
            return None
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "input": [{"type": "text", "text": prompt.strip()}],
            "response_format": {
                "type": "image",
                "mime_type": "image/jpeg",
                "aspect_ratio": "4:5",
                "image_size": "1K",
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.ENDPOINT, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            direct = data.get("output_image")
            if isinstance(direct, dict) and direct.get("data"):
                return base64.b64decode(str(direct["data"]))

            for step in data.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                for item in step.get("content") or []:
                    if isinstance(item, dict) and item.get("type") == "image" and item.get("data"):
                        return base64.b64decode(str(item["data"]))
            return None
        except Exception as exc:
            log.warning(
                "Gemini image generation failed model=%s; local visual fallback will be used: %s",
                self.model,
                exc,
            )
            return None
