
import os
from functools import lru_cache

from supabase import create_client


@lru_cache(maxsize=1)
def get_supabase_client():
    """
    Create and cache the Supabase client.
    Credentials are read from backend environment variables.
    """

    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_secret_key = os.getenv("SUPABASE_SECRET_KEY", "").strip()

    if not supabase_url or not supabase_secret_key:
        return None

    return create_client(supabase_url, supabase_secret_key)
