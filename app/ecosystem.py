from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_NEXUS_FOLDER_URL = "https://t.me/addlist/ASXi4-91edg2YzA8"
DEFAULT_ACADEMY_CHANNEL_ID = "-1003994692349"
DEFAULT_ACADEMY_CHANNEL_URL = "https://t.me/nexus_ict_learning"


@dataclass(frozen=True)
class EcosystemSettings:
    folder_url: str = os.getenv("NEXUS_FOLDER_URL", DEFAULT_NEXUS_FOLDER_URL).strip() or DEFAULT_NEXUS_FOLDER_URL
    academy_channel_id: str = os.getenv("ACADEMY_CHANNEL_ID", DEFAULT_ACADEMY_CHANNEL_ID).strip() or DEFAULT_ACADEMY_CHANNEL_ID
    academy_channel_url: str = os.getenv("ACADEMY_CHANNEL_URL", DEFAULT_ACADEMY_CHANNEL_URL).strip() or DEFAULT_ACADEMY_CHANNEL_URL


ecosystem_settings = EcosystemSettings()
