#!/usr/bin/env python3
"""
GCP Integration — Vertex AI, Text-to-Speech, Agent Registry, Cloud Storage.

Projekt: gen-lang-client-0895465231 (Shopy)
Aktivierte APIs: aiplatform, agentregistry, texttospeech, storage, compute, iam
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("gcp_integration")

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "rudibot-gcp-project")
GCP_REGION = os.getenv("GCP_REGION", "europe-west1")
# Config path: env var → known local path → fallback
_CONFIG_CANDIDATES = [
    os.getenv("GCP_CONFIG_PATH", ""),
    str(Path.home() / "CascadeProjects" / "rudibot" / "RudiBot-Secure-API" / "gcp-config.json"),
    str(Path(__file__).parent.parent / "RudiBot-Secure-API" / "gcp-config.json"),
]
GCP_CONFIG_PATH = Path(next((p for p in _CONFIG_CANDIDATES if p and Path(p).exists()), _CONFIG_CANDIDATES[1]))

ENABLED_APIS = [
    "aiplatform.googleapis.com",
    "agentregistry.googleapis.com",
    "modelarmor.googleapis.com",
    "texttospeech.googleapis.com",
    "storage-component.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
]


def load_gcp_config() -> dict:
    if GCP_CONFIG_PATH.exists():
        try:
            return json.loads(GCP_CONFIG_PATH.read_text())
        except Exception:
            pass
    return {
        "project": {"id": GCP_PROJECT_ID},
        "apis": {"enabled": [{"name": a} for a in ENABLED_APIS]},
    }


def get_access_token() -> Optional[str]:
    """Holt OAuth2 Access Token via Service Account oder ADC."""
    b64 = os.getenv("GCP_SERVICE_ACCOUNT_JSON_B64")
    if b64:
        try:
            sa = json.loads(base64.b64decode(b64).decode())
            return _jwt_access_token(sa)
        except Exception as e:
            log.error("GCP SA token error: %s", e)

    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and Path(creds_path).exists():
        try:
            sa = json.loads(Path(creds_path).read_text())
            return _jwt_access_token(sa)
        except Exception as e:
            log.error("GCP credentials file error: %s", e)

    # Metadata server (bei Cloud Run / GCE)
    try:
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read()).get("access_token")
    except Exception:
        pass

    return None


def _jwt_access_token(sa: dict) -> Optional[str]:
    """Erstellt JWT Bearer Token aus Service Account JSON."""
    try:
        import time
        import hmac
        import hashlib

        now = int(time.time())
        header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(json.dumps({
            "iss": sa["client_email"],
            "sub": sa["client_email"],
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
            "scope": "https://www.googleapis.com/auth/cloud-platform",
        }).encode()).rstrip(b"=").decode()

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend

        private_key = serialization.load_pem_private_key(
            sa["private_key"].encode(), password=None, backend=default_backend()
        )
        sig_input = f"{header}.{payload}".encode()
        signature = base64.urlsafe_b64encode(
            private_key.sign(sig_input, padding.PKCS1v15(), hashes.SHA256())
        ).rstrip(b"=").decode()

        jwt = f"{header}.{payload}.{signature}"
        data = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt,
        }).encode()
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("access_token")
    except ImportError:
        log.warning("cryptography package nicht installiert — GCP JWT Auth nicht verfügbar")
        return None
    except Exception as e:
        log.error("JWT token error: %s", e)
        return None


def vertex_ai_generate(prompt: str, model: str = "gemini-1.5-flash") -> str:
    """Vertex AI Text-Generierung via Gemini."""
    token = get_access_token()
    if not token:
        return "[GCP: kein Access Token]"
    try:
        url = (
            f"https://{GCP_REGION}-aiplatform.googleapis.com/v1/"
            f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/"
            f"publishers/google/models/{model}:generateContent"
        )
        body = json.dumps({
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.7},
        }).encode()
        req = urllib.request.Request(url, data=body, method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
            return resp["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        log.error("Vertex AI error: %s", e)
        return f"[Vertex AI Fehler: {e}]"


def text_to_speech(text: str, language: str = "de-DE", voice: str = "de-DE-Neural2-B") -> Optional[bytes]:
    """Google Text-to-Speech → MP3 bytes."""
    token = get_access_token()
    if not token:
        return None
    try:
        body = json.dumps({
            "input": {"text": text},
            "voice": {"languageCode": language, "name": voice},
            "audioConfig": {"audioEncoding": "MP3"},
        }).encode()
        req = urllib.request.Request(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            data=body, method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            return base64.b64decode(resp["audioContent"])
    except Exception as e:
        log.error("TTS error: %s", e)
        return None


def upload_to_gcs(bucket: str, blob_name: str, data: bytes, content_type: str = "application/octet-stream") -> Optional[str]:
    """Lädt Daten in Google Cloud Storage hoch. Gibt öffentliche URL zurück."""
    token = get_access_token()
    if not token:
        return None
    try:
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o?uploadType=media&name={blob_name}"
        req = urllib.request.Request(url, data=data, method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": content_type})
        with urllib.request.urlopen(req, timeout=30) as r:
            return f"https://storage.googleapis.com/{bucket}/{blob_name}"
    except Exception as e:
        log.error("GCS upload error: %s", e)
        return None


def get_status() -> dict:
    config = load_gcp_config()
    token = get_access_token()
    return {
        "configured": token is not None,
        "project_id": GCP_PROJECT_ID,
        "region": GCP_REGION,
        "auth": "ok" if token else "missing_credentials",
        "enabled_apis": len(config.get("apis", {}).get("enabled", [])),
        "capabilities": ["vertex_ai", "text_to_speech", "cloud_storage", "agent_registry"],
    }
