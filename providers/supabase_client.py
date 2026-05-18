"""Singleton Supabase client."""

from functools import lru_cache

from supabase import create_client, Client

import config


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return a cached Supabase client. Uses the service_role key so writes
    bypass the public-dashboard RLS policies (migration 007)."""
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
