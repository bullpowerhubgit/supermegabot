#!/usr/bin/env python3
"""
Google Drive Automation
File listing, upload, backup, search via Google Drive API v3
Uses service account or OAuth2 access token from environment
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

log = logging.getLogger("GoogleDrive")

_BASE   = "https://www.googleapis.com/drive/v3"
_UPLOAD = "https://www.googleapis.com/upload/drive/v3"
_DATA_DIR = Path(__file__).parent.parent / "data"


async def _get_token() -> str:
    try:
        from modules.google_oauth import ensure_valid_token
        token = await ensure_valid_token()
        if token:
            return token
    except Exception:
        pass
    token = os.getenv("GOOGLE_ACCESS_TOKEN", "")
    if not token:
        raise ValueError("GOOGLE_ACCESS_TOKEN nicht gesetzt — bitte /api/google/auth aufrufen")
    return token


async def _auth_headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {await _get_token()}"}


def _session(total: int = 30) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=total))


# ── Health ────────────────────────────────────────────────────────────────────

async def ping() -> tuple[bool, str]:
    token = os.getenv("GOOGLE_ACCESS_TOKEN", "")
    if not token:
        return False, "GOOGLE_ACCESS_TOKEN nicht gesetzt"
    try:
        async with _session() as s:
            async with s.get(
                f"{_BASE}/about",
                headers=await _auth_headers(),
                params={"fields": "user,storageQuota"}
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    email = d.get("user", {}).get("emailAddress", "OK")
                    return True, email
                return False, f"HTTP {r.status}"
    except Exception as e:
        return False, str(e)


# ── List Files ────────────────────────────────────────────────────────────────

async def list_files(
    query: str = "",
    page_size: int = 20,
    order_by: str = "modifiedTime desc",
    mime_filter: str = "",
) -> List[Dict]:
    params = {
        "pageSize": page_size,
        "orderBy":  order_by,
        "fields":   "files(id,name,mimeType,size,modifiedTime,webViewLink,parents)",
    }
    q_parts = []
    if query:
        q_parts.append(f"name contains '{query}'")
    if mime_filter:
        q_parts.append(f"mimeType='{mime_filter}'")
    if q_parts:
        params["q"] = " and ".join(q_parts)

    try:
        async with _session() as s:
            async with s.get(f"{_BASE}/files", headers=await _auth_headers(), params=params) as r:
                if r.status != 200:
                    return []
                d = await r.json()
                return [
                    {
                        "id":           f["id"],
                        "name":         f["name"],
                        "mimeType":     f["mimeType"],
                        "size":         int(f.get("size", 0)),
                        "modifiedTime": f.get("modifiedTime", ""),
                        "webViewLink":  f.get("webViewLink", ""),
                    }
                    for f in d.get("files", [])
                ]
    except Exception as e:
        log.error(f"list_files: {e}")
        return []


# ── Search ────────────────────────────────────────────────────────────────────

async def search_files(keyword: str, limit: int = 10) -> List[Dict]:
    return await list_files(query=keyword, page_size=limit)


# ── Upload File ───────────────────────────────────────────────────────────────

async def upload_file(
    local_path: str,
    remote_name: str = "",
    folder_id: str = "",
    mime_type: str = "application/octet-stream",
) -> Optional[str]:
    path = Path(local_path)
    if not path.exists():
        log.error(f"upload_file: {local_path} not found")
        return None
    name = remote_name or path.name
    metadata: Dict = {"name": name}
    if folder_id:
        metadata["parents"] = [folder_id]

    try:
        data = aiohttp.FormData()
        data.add_field(
            "metadata",
            json.dumps(metadata),
            content_type="application/json; charset=UTF-8"
        )
        data.add_field(
            "file",
            path.read_bytes(),
            filename=name,
            content_type=mime_type
        )
        async with _session(total=120) as s:
            async with s.post(
                f"{_UPLOAD}/files?uploadType=multipart&fields=id,name,webViewLink",
                headers=await _auth_headers(),
                data=data,
            ) as r:
                if r.status in (200, 201):
                    d = await r.json()
                    file_id = d.get("id")
                    log.info(f"Uploaded '{name}' → {file_id}")
                    return file_id
                log.warning(f"upload_file HTTP {r.status}: {await r.text()}")
                return None
    except Exception as e:
        log.error(f"upload_file: {e}")
        return None


# ── Create Folder ─────────────────────────────────────────────────────────────

async def create_folder(name: str, parent_id: str = "") -> Optional[str]:
    metadata: Dict = {
        "name":     name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]
    try:
        async with _session() as s:
            async with s.post(
                f"{_BASE}/files",
                headers={**(await _auth_headers()), "Content-Type": "application/json"},
                json=metadata,
            ) as r:
                if r.status in (200, 201):
                    return (await r.json()).get("id")
                return None
    except Exception as e:
        log.error(f"create_folder: {e}")
        return None


# ── Backup Data Directory ─────────────────────────────────────────────────────

async def backup_data_dir(folder_id: str = "") -> Dict:
    """Upload all JSON files from data/ to Google Drive."""
    uploaded = []
    failed   = []
    for f in _DATA_DIR.glob("*.json"):
        try:
            file_id = await upload_file(
                str(f),
                remote_name=f"supermegabot_backup_{f.name}",
                folder_id=folder_id,
                mime_type="application/json",
            )
            if file_id:
                uploaded.append(f.name)
            else:
                failed.append(f.name)
        except Exception as e:
            failed.append(f"{f.name}: {e}")
    return {"uploaded": uploaded, "failed": failed, "total": len(uploaded)}


# ── Get Storage Quota ─────────────────────────────────────────────────────────

async def get_storage_info() -> Dict:
    try:
        async with _session() as s:
            async with s.get(
                f"{_BASE}/about",
                headers=await _auth_headers(),
                params={"fields": "user,storageQuota"}
            ) as r:
                if r.status != 200:
                    return {}
                d = await r.json()
                quota = d.get("storageQuota", {})
                used  = int(quota.get("usage", 0))
                total = int(quota.get("limit", 0))
                return {
                    "email": d.get("user", {}).get("emailAddress", ""),
                    "used_gb":  round(used  / 1e9, 2),
                    "total_gb": round(total / 1e9, 2),
                    "pct":      round(used / total * 100, 1) if total else 0,
                }
    except Exception as e:
        log.error(f"get_storage_info: {e}")
        return {}


# ── Stats (dashboard) ─────────────────────────────────────────────────────────

async def get_stats() -> Dict:
    ok, account = await ping()
    if not ok:
        return {"ok": False, "error": account}
    files   = await list_files(page_size=10)
    storage = await get_storage_info()
    return {
        "ok":       True,
        "account":  account,
        "files":    files,
        "storage":  storage,
    }


# ── Auto-Backup Task ──────────────────────────────────────────────────────────

async def auto_backup() -> str:
    """Scheduler task: backup data JSON files to Google Drive."""
    ok, account = await ping()
    if not ok:
        return f"Google Drive nicht verfügbar: {account}"

    folder_name = f"SMB_Backup_{datetime.now().strftime('%Y-%m-%d')}"
    folder_id   = await create_folder(folder_name)
    result      = await backup_data_dir(folder_id=folder_id or "")

    return (
        f"Drive Backup: {result['total']} Dateien hochgeladen"
        + (f" | Fehler: {result['failed']}" if result["failed"] else "")
    )
