"""Runtime configuration, loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    google_cse_id: str = os.getenv("GOOGLE_CSE_ID", "")
    google_cse_key: str = os.getenv("GOOGLE_CSE_KEY", "")
    # IMSLP (Phase 2) is inert until enabled — confirm IMSLP's terms of use first.
    imslp_enabled: bool = os.getenv("IMSLP_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


settings = Settings()
