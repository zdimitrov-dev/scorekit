"""Supabase client accessor."""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from .config import settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set (see .env.example)."
        )
    return create_client(settings.supabase_url, settings.supabase_service_key)
