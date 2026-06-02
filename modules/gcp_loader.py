"""
GCP Config Loader — sicherer Zugriff auf Google Cloud Credentials.

Ladereihenfolge:
  1. GOOGLE_APPLICATION_CREDENTIALS (Pfad zur JSON-Datei)
  2. GCP_SERVICE_ACCOUNT_JSON_B64 (base64-kodierter JSON-Inhalt)
  3. gcloud Application Default Credentials (~/.config/gcloud/...)

Niemals werden Credentials geloggt oder ausgegeben.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("gcp_loader")


def get_project_id() -> Optional[str]:
    """Gibt die GCP Project-ID zurück (nicht sensitiv)."""
    pid = os.getenv("GCP_PROJECT_ID")
    if pid:
        return pid
    # Aus Service-Account-JSON lesen falls vorhanden
    creds = _load_credentials_dict()
    if creds:
        return creds.get("project_id")
    return None


def get_region() -> str:
    return os.getenv("GCP_REGION", "europe-west1")


def _load_credentials_dict() -> Optional[dict[str, Any]]:
    """Lädt Service-Account-JSON als Dict — Inhalt wird nie geloggt."""
    # Option 1: Pfad zur JSON-Datei
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        p = Path(creds_path)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception as e:
                log.error("GCP credentials file unreadable: %s", e)
                return None
        else:
            log.warning("GOOGLE_APPLICATION_CREDENTIALS path not found: %s", creds_path)

    # Option 2: base64-kodierter JSON-Inhalt
    b64 = os.getenv("GCP_SERVICE_ACCOUNT_JSON_B64")
    if b64:
        try:
            return json.loads(base64.b64decode(b64).decode())
        except Exception as e:
            log.error("GCP base64 credentials invalid: %s", e)
            return None

    # Option 3: Application Default Credentials (gcloud auth)
    adc_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    if adc_path.exists():
        try:
            return json.loads(adc_path.read_text())
        except Exception:
            pass

    return None


def is_configured() -> bool:
    """Gibt True zurück wenn GCP-Credentials verfügbar sind."""
    return _load_credentials_dict() is not None or bool(os.getenv("GCP_PROJECT_ID"))


def get_api_key(api_name: str) -> Optional[str]:
    """
    Gibt den API-Key für eine bestimmte Google-API zurück.
    api_name: z.B. 'GEMINI', 'MAPS', 'VISION', 'TRANSLATE', 'SHEETS', 'DRIVE'
    """
    normalized = api_name.upper().replace("-", "_").replace(" ", "_")
    # Suche nach spezifischem Key
    for pattern in (
        f"GOOGLE_{normalized}_API_KEY",
        f"GOOGLE_{normalized}_KEY",
        f"{normalized}_API_KEY",
    ):
        val = os.getenv(pattern)
        if val:
            return val
    return None


def credentials_summary() -> dict[str, Any]:
    """Gibt eine Zusammenfassung zurück — ohne sensitiven Inhalt."""
    creds = _load_credentials_dict()
    project_id = get_project_id()
    configured = is_configured()

    summary: dict[str, Any] = {
        "configured": configured,
        "project_id": project_id,
        "region": get_region(),
        "auth_method": None,
        "client_email": None,
    }

    if creds:
        cred_type = creds.get("type", "unknown")
        summary["auth_method"] = cred_type
        # client_email ist nicht sensitiv (öffentliche Identität)
        summary["client_email"] = creds.get("client_email")

    # Welche API-Keys sind gesetzt (nur Namen, keine Werte)
    api_keys_set = []
    for var in (
        "GOOGLE_GEMINI_API_KEY", "GOOGLE_MAPS_API_KEY", "GOOGLE_VISION_API_KEY",
        "GOOGLE_TRANSLATE_API_KEY", "GOOGLE_SHEETS_API_KEY", "GOOGLE_DRIVE_API_KEY",
        "YOUTUBE_DATA_API_KEY", "GMAIL_CLIENT_ID", "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GMC_MERCHANT_ID",
    ):
        if os.getenv(var):
            api_keys_set.append(var)
    summary["api_keys_configured"] = api_keys_set

    return summary


if __name__ == "__main__":
    import sys

    # .env laden
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip()

    summary = credentials_summary()
    print("GCP Configuration Summary")
    print("=" * 40)
    for k, v in summary.items():
        print(f"  {k}: {v}")
    sys.exit(0 if summary["configured"] else 1)
