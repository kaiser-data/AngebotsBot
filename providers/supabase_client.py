"""Singleton Supabase client."""

from functools import lru_cache

from supabase import create_client, Client

import config


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return a cached Supabase client instance."""
    return create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
