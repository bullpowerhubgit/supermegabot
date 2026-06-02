"""
Supabase client — thin wrapper that reads credentials from environment.

Required env vars:
  SUPABASE_URL  — project URL (https://<ref>.supabase.co)
  SUPABASE_ANON_KEY — anon/publishable key (safe for server use with RLS)

Optional:
  NEXT_PUBLIC_SUPABASE_URL            — alias accepted too
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY — alias accepted too
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger("supabase_client")

_client = None


def get_client():
    global _client
    if _client is not None:
        return _client

    try:
        from supabase import create_client, Client  # type: ignore
    except ImportError:
        raise RuntimeError("supabase-py not installed: pip install supabase")

    url = (
        os.getenv("SUPABASE_URL")
        or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    )
    key = (
        os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    )

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment"
        )

    _client = create_client(url, key)
    return _client


def is_configured() -> bool:
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    return bool(url and key)
