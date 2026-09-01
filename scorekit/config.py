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
    # Direct Postgres connection — only for migrations, since DDL cannot be issued over
    # PostgREST, which everything else in the codebase goes through.
    supabase_db_url: str = os.getenv("SUPABASE_DB_URL", "")
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    # MuseScore (Phase 3) via the Tavily search API, restricted to musescore.com.
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    # IMSLP (Phase 2) is inert until enabled — confirm IMSLP's terms of use first.
    imslp_enabled: bool = os.getenv("IMSLP_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


settings = Settings()
