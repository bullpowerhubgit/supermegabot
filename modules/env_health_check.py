"""
env_health_check.py — Production environment validation & Railway sync module
Validates all required API keys, checks format integrity, and syncs vars to Railway.
"""

import os
import re
import json
import logging
import asyncio
from typing import Any

import aiohttp
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required keys — must be present and non-empty
# ---------------------------------------------------------------------------

REQUIRED_KEYS: list[str] = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "SHOPIFY_ADMIN_API_TOKEN",
    "SHOPIFY_SHOP_DOMAIN",
    "STRIPE_SECRET_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "KLAVIYO_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "META_ACCESS_TOKEN",
    "SENDGRID_API_KEY",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "YOUTUBE_API_KEY",
    "YOUTUBE_CHANNEL_ID",
    "GITHUB_TOKEN",
    "RAILWAY_TOKEN",
]

# Placeholder strings that count as "missing"
_PLACEHOLDER_PATTERNS = re.compile(
    r"^(undefined|null|none|your[_\-]?key[_\-]?here|changeme|placeholder|todo|xxx+|<.+>|\{\{.+\}\})$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Format validators  key → (regex_pattern, human_label)
# ---------------------------------------------------------------------------

_FORMAT_RULES: dict[str, tuple[str, str]] = {
    "ANTHROPIC_API_KEY":      (r"^sk-ant-", "must start with sk-ant-"),
    "OPENAI_API_KEY":         (r"^sk-", "must start with sk-"),
    "SHOPIFY_ADMIN_API_TOKEN":(r"^shpat_", "must start with shpat_"),
    "STRIPE_SECRET_KEY":      (r"^sk_(live|test)_", "must start with sk_live_ or sk_test_"),
    "TELEGRAM_BOT_TOKEN":     (r"^\d+:[A-Za-z0-9_\-]{35,}$", "format: <numeric_id>:<token>"),
    "SUPABASE_URL":           (r"^https://", "must be a full https URL"),
    "SUPABASE_SERVICE_KEY":   (r"^eyJ", "must be a JWT (starts with eyJ)"),
    "KLAVIYO_API_KEY":        (r"^pk_", "must start with pk_"),
    "SENDGRID_API_KEY":       (r"^SG\.", "must start with SG."),
    "TWILIO_ACCOUNT_SID":     (r"^AC[0-9a-f]{32}$", "must start with AC + 32 hex chars"),
    "YOUTUBE_API_KEY":        (r"^AIza", "must start with AIza"),
    "GITHUB_TOKEN":           (r"^(ghp_|github_pat_)", "must start with ghp_ or github_pat_"),
    "RAILWAY_TOKEN":          (r"^[0-9a-f\-]{36}$", "must be a UUID (36 chars)"),
    "META_ACCESS_TOKEN":      (r"^EAA", "must start with EAA"),
}

# Railway GraphQL endpoint
_RAILWAY_GQL = "https://backboard.railway.app/graphql/v2"


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

def validate_env(env: dict[str, str] | None = None) -> dict[str, Any]:
    """
    Validate environment variables.

    Returns:
        {
            ok: bool,
            missing: list[str],    # keys absent or empty
            invalid: list[dict],   # keys with bad format
            warnings: list[str],   # non-critical issues
            summary: str
        }
    """
    if env is None:
        env = dict(os.environ)

    missing: list[str] = []
    invalid: list[dict] = []
    warnings: list[str] = []

    for key in REQUIRED_KEYS:
        value = env.get(key, "").strip()

        # Check presence
        if not value or _PLACEHOLDER_PATTERNS.match(value):
            missing.append(key)
            continue

        # Check format
        if key in _FORMAT_RULES:
            pattern, label = _FORMAT_RULES[key]
            if not re.match(pattern, value):
                invalid.append({
                    "key": key,
                    "issue": label,
                    "value_preview": value[:12] + "..." if len(value) > 12 else value,
                })

    # Non-critical warnings
    if not env.get("RAILWAY_PROJECT_ID", "").strip():
        warnings.append("RAILWAY_PROJECT_ID not set — Railway sync will attempt auto-discovery")
    if not env.get("RAILWAY_SERVICE_ID", "").strip():
        warnings.append("RAILWAY_SERVICE_ID not set — Railway sync will attempt auto-discovery")
    if not env.get("RAILWAY_ENVIRONMENT_ID", "").strip():
        warnings.append("RAILWAY_ENVIRONMENT_ID not set — will use 'production' environment")

    ok = len(missing) == 0 and len(invalid) == 0

    total = len(REQUIRED_KEYS)
    good = total - len(missing) - len(invalid)
    summary = (
        f"{good}/{total} keys OK"
        + (f", {len(missing)} missing" if missing else "")
        + (f", {len(invalid)} invalid format" if invalid else "")
        + (f", {len(warnings)} warnings" if warnings else "")
    )

    return {
        "ok": ok,
        "missing": missing,
        "invalid": invalid,
        "warnings": warnings,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Railway helpers
# ---------------------------------------------------------------------------

async def _railway_post(session: aiohttp.ClientSession, query: str, variables: dict, token: str) -> dict:
    """Execute a Railway GraphQL request and return parsed JSON."""
    payload = {"query": query, "variables": variables}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    async with session.post(_RAILWAY_GQL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        return await resp.json()


async def _discover_project_ids(session: aiohttp.ClientSession, token: str) -> dict[str, str | None]:
    """
    Auto-discover the first project + service + production environment IDs
    when RAILWAY_PROJECT_ID / SERVICE_ID / ENVIRONMENT_ID are not in env.
    Returns dict with keys: project_id, service_id, environment_id (may be None on failure).
    """
    query = """
    query {
      me {
        projects {
          edges {
            node {
              id
              name
              environments {
                edges {
                  node { id name }
                }
              }
              services {
                edges {
                  node { id name }
                }
              }
            }
          }
        }
      }
    }
    """
    try:
        data = await _railway_post(session, query, {}, token)
        projects = data.get("data", {}).get("me", {}).get("projects", {}).get("edges", [])
        if not projects:
            return {"project_id": None, "service_id": None, "environment_id": None}

        # Pick first project named "supermegabot" or fall back to first
        project = None
        for edge in projects:
            node = edge["node"]
            if "supermegabot" in node.get("name", "").lower():
                project = node
                break
        if project is None:
            project = projects[0]["node"]

        project_id = project["id"]

        # Pick "production" environment or first
        environment_id = None
        for env_edge in project.get("environments", {}).get("edges", []):
            env_node = env_edge["node"]
            if env_node.get("name", "").lower() == "production":
                environment_id = env_node["id"]
                break
        if environment_id is None:
            envs = project.get("environments", {}).get("edges", [])
            if envs:
                environment_id = envs[0]["node"]["id"]

        # Pick first service
        service_id = None
        services = project.get("services", {}).get("edges", [])
        if services:
            service_id = services[0]["node"]["id"]

        return {
            "project_id": project_id,
            "service_id": service_id,
            "environment_id": environment_id,
        }
    except Exception as exc:
        logger.warning("Railway project auto-discovery failed: %s", exc)
        return {"project_id": None, "service_id": None, "environment_id": None}


async def _get_railway_vars(
    session: aiohttp.ClientSession,
    token: str,
    project_id: str,
    environment_id: str,
    service_id: str,
) -> dict[str, str]:
    """Fetch all env vars currently set on Railway for the given service."""
    query = """
    query Variables($projectId: String!, $environmentId: String!, $serviceId: String!) {
      variables(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId)
    }
    """
    try:
        data = await _railway_post(
            session, query,
            {"projectId": project_id, "environmentId": environment_id, "serviceId": service_id},
            token,
        )
        raw = data.get("data", {}).get("variables") or {}
        return raw if isinstance(raw, dict) else {}
    except Exception as exc:
        logger.warning("Failed to fetch Railway variables: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def check_railway_sync(env: dict[str, str] | None = None) -> dict[str, Any]:
    """
    Compare local .env vars against Railway service vars.

    Returns:
        {
            in_sync: bool,
            missing_on_railway: list[str],   # keys in local env but not on Railway
            stale_on_railway: list[str],     # keys where values differ
            errors: list[str]
        }
    """
    if env is None:
        env = dict(os.environ)

    token = env.get("RAILWAY_TOKEN", "").strip()
    if not token:
        return {
            "in_sync": False,
            "missing_on_railway": [],
            "stale_on_railway": [],
            "errors": ["RAILWAY_TOKEN not set"],
        }

    project_id = env.get("RAILWAY_PROJECT_ID", "").strip()
    service_id = env.get("RAILWAY_SERVICE_ID", "").strip()
    environment_id = env.get("RAILWAY_ENVIRONMENT_ID", "").strip()

    async with aiohttp.ClientSession() as session:
        if not project_id or not service_id or not environment_id:
            ids = await _discover_project_ids(session, token)
            project_id = project_id or ids["project_id"] or ""
            service_id = service_id or ids["service_id"] or ""
            environment_id = environment_id or ids["environment_id"] or ""

        if not project_id or not service_id or not environment_id:
            return {
                "in_sync": False,
                "missing_on_railway": [],
                "stale_on_railway": [],
                "errors": ["Could not determine Railway project/service/environment IDs"],
            }

        railway_vars = await _get_railway_vars(session, token, project_id, environment_id, service_id)

    missing_on_railway: list[str] = []
    stale_on_railway: list[str] = []

    for key in REQUIRED_KEYS:
        local_val = env.get(key, "").strip()
        if not local_val:
            continue  # skip locally missing keys — validate_env() handles that

        railway_val = railway_vars.get(key, "")
        if not railway_val:
            missing_on_railway.append(key)
        elif railway_val.strip() != local_val:
            stale_on_railway.append(key)

    return {
        "in_sync": len(missing_on_railway) == 0 and len(stale_on_railway) == 0,
        "missing_on_railway": missing_on_railway,
        "stale_on_railway": stale_on_railway,
        "errors": [],
    }


async def sync_to_railway(
    env: dict[str, str] | None = None,
    keys_to_sync: list[str] | None = None,
    batch_size: int = 20,
) -> dict[str, Any]:
    """
    Bulk-upsert environment variables to Railway via GraphQL.

    Args:
        env: variable dict (defaults to os.environ)
        keys_to_sync: specific keys to sync; if None, syncs ALL non-empty vars in env
        batch_size: how many upsert mutations to run per request batch

    Returns:
        {
            synced: int,
            skipped: int,
            errors: list[str]
        }
    """
    if env is None:
        env = dict(os.environ)

    token = env.get("RAILWAY_TOKEN", "").strip()
    if not token:
        return {"synced": 0, "skipped": 0, "errors": ["RAILWAY_TOKEN not set"]}

    project_id = env.get("RAILWAY_PROJECT_ID", "").strip()
    service_id = env.get("RAILWAY_SERVICE_ID", "").strip()
    environment_id = env.get("RAILWAY_ENVIRONMENT_ID", "").strip()

    async with aiohttp.ClientSession() as session:
        if not project_id or not service_id or not environment_id:
            ids = await _discover_project_ids(session, token)
            project_id = project_id or ids["project_id"] or ""
            service_id = service_id or ids["service_id"] or ""
            environment_id = environment_id or ids["environment_id"] or ""

        if not project_id or not service_id or not environment_id:
            return {
                "synced": 0,
                "skipped": 0,
                "errors": ["Could not determine Railway project/service/environment IDs"],
            }

        # Build pairs to sync
        if keys_to_sync is None:
            pairs = [(k, v.strip()) for k, v in env.items() if v.strip() and not k.startswith("#")]
        else:
            pairs = [(k, env.get(k, "").strip()) for k in keys_to_sync if env.get(k, "").strip()]

        synced = 0
        skipped = 0
        errors: list[str] = []

        # Upsert one at a time (Railway API does not support bulk upsert in one call),
        # but we execute batches concurrently for speed.
        upsert_mutation = """
        mutation VariableUpsert($input: VariableUpsertInput!) {
          variableUpsert(input: $input)
        }
        """

        async def _upsert_one(key: str, value: str) -> bool:
            try:
                variables = {
                    "input": {
                        "projectId": project_id,
                        "environmentId": environment_id,
                        "serviceId": service_id,
                        "name": key,
                        "value": value,
                    }
                }
                result = await _railway_post(session, upsert_mutation, variables, token)
                if result.get("errors"):
                    msg = result["errors"][0].get("message", "unknown error")
                    logger.warning("Railway upsert failed for %s: %s", key, msg)
                    errors.append(f"{key}: {msg}")
                    return False
                return True
            except Exception as exc:
                logger.error("Railway upsert exception for %s: %s", key, exc)
                errors.append(f"{key}: {exc}")
                return False

        # Process in batches of batch_size concurrently
        for i in range(0, len(pairs), batch_size):
            chunk = pairs[i : i + batch_size]
            results = await asyncio.gather(*[_upsert_one(k, v) for k, v in chunk])
            for ok in results:
                if ok:
                    synced += 1
                else:
                    skipped += 1

        logger.info("Railway sync complete: %d synced, %d skipped, %d errors", synced, skipped, len(errors))
        return {"synced": synced, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Dashboard report
# ---------------------------------------------------------------------------

async def get_env_report(env: dict[str, str] | None = None) -> dict[str, Any]:
    """
    Full combined report for the dashboard.

    Returns:
        {
            validation: {...},     # from validate_env()
            railway_sync: {...},   # from check_railway_sync()
            total_keys: int,
            ok: bool
        }
    """
    if env is None:
        env = dict(os.environ)

    validation = validate_env(env)
    railway_sync = await check_railway_sync(env)

    return {
        "validation": validation,
        "railway_sync": railway_sync,
        "total_keys": len(REQUIRED_KEYS),
        "ok": validation["ok"] and railway_sync["in_sync"],
    }


# ---------------------------------------------------------------------------
# Convenience: load .env file and return populated dict
# ---------------------------------------------------------------------------

def load_env_file(path: str = ".env") -> dict[str, str]:
    """Load a .env file and return its contents as a dict (overrides os.environ)."""
    load_dotenv(path, override=True)
    return dict(os.environ)


# ---------------------------------------------------------------------------
# Sync wrappers for callers that prefer synchronous code
# ---------------------------------------------------------------------------

def validate_env_sync(env: dict[str, str] | None = None) -> dict[str, Any]:
    return validate_env(env)


def check_railway_sync_sync(env: dict[str, str] | None = None) -> dict[str, Any]:
    return asyncio.run(check_railway_sync(env))


def sync_to_railway_sync(
    env: dict[str, str] | None = None,
    keys_to_sync: list[str] | None = None,
    batch_size: int = 20,
) -> dict[str, Any]:
    return asyncio.run(sync_to_railway(env, keys_to_sync, batch_size))


def get_env_report_sync(env: dict[str, str] | None = None) -> dict[str, Any]:
    return asyncio.run(get_env_report(env))
