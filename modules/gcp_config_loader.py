#!/usr/bin/env python3
"""
🔐 GCP CONFIG LOADER
Liest die zentrale GCP-Konfiguration aus RudiBot-Secure-API/gcp-config.json
und stellt sie für alle Python-Module im SuperMegaBot-Projekt bereit.

Usage:
    from modules.gcp_config_loader import get_gcp_config, get_project_id, get_enabled_apis

    config = get_gcp_config()
    print(config.project.id)
    for api in get_enabled_apis():
        print(api.name, api.service_name)
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Suche-Pfade für die Config (inkl. Downloads und Projekt-Root)
_CONFIG_SEARCH_PATHS = [
    Path(__file__).parent.parent / "RudiBot-Secure-API" / "gcp-config.json",
    Path.home() / "Downloads" / "RudiBot-Secure-API" / "gcp-config.json",
    Path("/Users/rudolfsarkany/Downloads/RudiBot-Secure-API/gcp-config.json"),
    Path("/Users/rudolfsarkany/supermegabot-windsurf-agents/RudiBot-Secure-API/gcp-config.json"),
    Path("RudiBot-Secure-API/gcp-config.json"),
]

_cached_config: Optional[Dict[str, Any]] = None


def _find_config_path() -> Path:
    """Finde den ersten existierenden gcp-config.json Pfad."""
    env_path = os.environ.get("GCP_CONFIG_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    for p in _CONFIG_SEARCH_PATHS:
        if p.exists():
            return p

    raise FileNotFoundError(
        "gcp-config.json nicht gefunden. "
        "Setze GCP_CONFIG_PATH oder kopiere RudiBot-Secure-API ins Projekt."
    )


def get_gcp_config() -> Dict[str, Any]:
    """Lade und cachte die GCP-Konfiguration."""
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    path = _find_config_path()
    with open(path, "r", encoding="utf-8") as f:
        _cached_config = json.load(f)
    return _cached_config


def get_project_id() -> str:
    """Gibt die GCP Project ID zurück."""
    return get_gcp_config()["project"]["id"]


def get_region() -> str:
    """Gibt die Default-Region zurück."""
    return get_gcp_config()["project"]["region"]


def get_zone() -> str:
    """Gibt die Default-Zone zurück."""
    return get_gcp_config()["project"]["zone"]


def get_enabled_apis() -> List[Dict[str, Any]]:
    """Gibt alle aktivierten APIs als Liste zurück."""
    return [a for a in get_gcp_config()["apis"] if a.get("enabled", False)]


def get_api_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Finde eine API anhand ihres Anzeigenamens."""
    for api in get_gcp_config()["apis"]:
        if api["name"].lower() == name.lower():
            return api
    return None


def get_api_by_service(service_name: str) -> Optional[Dict[str, Any]]:
    """Finde eine API anhand ihres Service-Namens."""
    for api in get_gcp_config()["apis"]:
        if api["service_name"] == service_name:
            return api
    return None


def get_service_account_roles() -> List[str]:
    """Gibt die IAM-Rollen des rudibot-app Service Accounts zurück."""
    sas = get_gcp_config().get("service_accounts", [])
    for sa in sas:
        if sa.get("name") == "rudibot-app":
            return sa.get("roles", [])
    return []


def get_auth_env() -> Dict[str, str]:
    """Gibt die empfohlenen Auth-Umgebungsvariablen zurück."""
    return get_gcp_config().get("auth", {}).get("environment_variables", {})


def get_billing_limits() -> Dict[str, Any]:
    """Gibt Billing-Limits zurück."""
    return get_gcp_config().get("billing", {}).get("alerts", {})


def get_security_settings() -> Dict[str, Any]:
    """Gibt Sicherheitseinstellungen zurück."""
    return get_gcp_config().get("security", {})


def get_api_names() -> List[str]:
    """Gibt eine Liste aller API-Namen zurück."""
    return [a["name"] for a in get_gcp_config()["apis"]]


def get_api_service_names() -> List[str]:
    """Gibt eine Liste aller API Service-Namen zurück."""
    return [a["service_name"] for a in get_gcp_config()["apis"]]


def reload_config() -> Dict[str, Any]:
    """Lösche den Cache und lade die Config neu."""
    global _cached_config
    _cached_config = None
    return get_gcp_config()


# ════════════════════════════════════════════════════════════════
# Dashboard / API Helpers
# ════════════════════════════════════════════════════════════════

def to_dashboard_dict() -> Dict[str, Any]:
    """Bereite die Config für das Dashboard auf (keine Secrets)."""
    cfg = get_gcp_config()
    return {
        "project": cfg["project"],
        "apis": [
            {
                "name": a["name"],
                "service_name": a["service_name"],
                "description": a["description"],
                "enabled": a.get("enabled", False),
                "pricing_tier": a.get("pricing_tier", "?"),
                "features": a.get("features", []),
                "max_requests_per_minute": a.get("max_requests_per_minute", 0),
            }
            for a in cfg["apis"]
        ],
        "region": cfg["project"]["region"],
        "zone": cfg["project"]["zone"],
        "billing": cfg.get("billing", {}).get("alerts", {}),
        "security": {
            "rotate_keys_every_days": cfg.get("security", {}).get("rotate_keys_every_days", 90),
            "audit_logging": cfg.get("security", {}).get("audit_logging", False),
            "iam_principle": cfg.get("security", {}).get("iam_principle", "least_privilege"),
        },
        "service_accounts": [
            {
                "name": sa["name"],
                "description": sa["description"],
                "roles": sa.get("roles", []),
            }
            for sa in cfg.get("service_accounts", [])
        ],
    }


if __name__ == "__main__":
    print("🔐 GCP Config Loader — Self Test\n")
    try:
        cfg = get_gcp_config()
        print(f"Project ID : {get_project_id()}")
        print(f"Region     : {get_region()}")
        print(f"Zone       : {get_zone()}")
        print(f"APIs       : {len(get_enabled_apis())}/19 enabled")
        print(f"Roles      : {len(get_service_account_roles())} roles")
        print(f"Daily Limit: {get_billing_limits().get('daily_budget_eur', '?')} EUR")
        print("\n✅ Config loaded successfully")
    except Exception as e:
        print(f"❌ Error: {e}")
