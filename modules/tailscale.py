#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  TailscaleController — DNS & Network Management via Tailscale API          ║
║  Befehle: /ts, /ts_dns, /ts_devices, /ts_nameservers, /ts_magicdns, etc.  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import aiohttp
from pathlib import Path
from typing import Dict, List, Optional, Any

BASE_DIR = Path(__file__).parent.parent

try:
    from dotenv import load_dotenv as _ld
    _ld(BASE_DIR / ".env", override=True)
except ImportError:
    pass

TAILSCALE_API_BASE = "https://api.tailscale.com/api/v2"


class TailscaleController:
    """Tailscale DNS & Network management via Tailscale API v2."""

    def __init__(self):
        self.api_key  = os.getenv("TAILSCALE_API_KEY", "")
        self.tailnet  = os.getenv("TAILSCALE_TAILNET", "-")  # "-" = default tailnet

    # ─────────────────────────────────────────────────────────────────────────
    # Interne HTTP-Helfer
    # ─────────────────────────────────────────────────────────────────────────

    def _headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, timeout: int = 10) -> Dict:
        if not self.api_key:
            return {"ok": False, "data": None, "error": "TAILSCALE_API_KEY nicht gesetzt"}
        url = f"{TAILSCALE_API_BASE}{path}"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                async with session.get(url, headers=self._headers()) as r:
                    body = await r.json(content_type=None)
                    return {"ok": r.status < 400, "data": body, "error": None}
        except Exception as e:
            return {"ok": False, "data": None, "error": str(e)[:120]}

    async def _post(self, path: str, payload: Any, timeout: int = 10) -> Dict:
        if not self.api_key:
            return {"ok": False, "data": None, "error": "TAILSCALE_API_KEY nicht gesetzt"}
        url = f"{TAILSCALE_API_BASE}{path}"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                async with session.post(url, headers=self._headers(), json=payload) as r:
                    body = await r.json(content_type=None)
                    return {"ok": r.status < 400, "data": body, "error": None}
        except Exception as e:
            return {"ok": False, "data": None, "error": str(e)[:120]}

    async def _patch(self, path: str, payload: Any, timeout: int = 10) -> Dict:
        if not self.api_key:
            return {"ok": False, "data": None, "error": "TAILSCALE_API_KEY nicht gesetzt"}
        url = f"{TAILSCALE_API_BASE}{path}"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                async with session.patch(url, headers=self._headers(), json=payload) as r:
                    body = await r.json(content_type=None)
                    return {"ok": r.status < 400, "data": body, "error": None}
        except Exception as e:
            return {"ok": False, "data": None, "error": str(e)[:120]}

    async def _delete(self, path: str, timeout: int = 10) -> Dict:
        if not self.api_key:
            return {"ok": False, "data": None, "error": "TAILSCALE_API_KEY nicht gesetzt"}
        url = f"{TAILSCALE_API_BASE}{path}"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                async with session.delete(url, headers=self._headers()) as r:
                    text = await r.text()
                    return {"ok": r.status < 400, "data": text, "error": None}
        except Exception as e:
            return {"ok": False, "data": None, "error": str(e)[:120]}

    # ─────────────────────────────────────────────────────────────────────────
    # DNS-Einstellungen
    # ─────────────────────────────────────────────────────────────────────────

    async def dns_status(self) -> str:
        """Zeigt alle DNS-Einstellungen des Tailnets."""
        r = await self._get(f"/tailnet/{self.tailnet}/dns/preferences")
        if not r["ok"]:
            return f"<b>Tailscale DNS — Fehler:</b>\n{r['error'] or r['data']}"

        prefs = r["data"]
        magic = prefs.get("magicDNS", False)

        r2 = await self._get(f"/tailnet/{self.tailnet}/dns/nameservers")
        ns_list = r2["data"].get("dns", []) if r2["ok"] else []

        r3 = await self._get(f"/tailnet/{self.tailnet}/dns/searchpaths")
        search = r3["data"].get("searchPaths", []) if r3["ok"] else []

        lines = [
            "<b>🌐 Tailscale DNS-Status</b>\n",
            f"<b>MagicDNS:</b> {'✅ Aktiv' if magic else '❌ Deaktiviert'}",
            f"<b>Tailnet:</b> <code>{self.tailnet}</code>",
        ]
        if ns_list:
            lines.append("\n<b>Nameserver:</b>")
            for ns in ns_list:
                lines.append(f"  • <code>{ns}</code>")
        else:
            lines.append("<b>Nameserver:</b> (keine benutzerdefinierten)")
        if search:
            lines.append("\n<b>Search Domains:</b>")
            for s in search:
                lines.append(f"  • <code>{s}</code>")
        return "\n".join(lines)

    async def devices(self) -> str:
        """Listet alle Geräte im Tailnet."""
        r = await self._get(f"/tailnet/{self.tailnet}/devices")
        if not r["ok"]:
            return f"<b>Tailscale Geräte — Fehler:</b>\n{r['error'] or r['data']}"

        devs = r["data"].get("devices", [])
        if not devs:
            return "<b>Tailscale Geräte:</b> Keine Geräte gefunden."

        lines = [f"<b>🖥 Tailscale Geräte ({len(devs)}):</b>\n"]
        for d in devs:
            name    = d.get("name", d.get("hostname", "?"))
            ip      = d.get("addresses", ["?"])[0]
            os_     = d.get("os", "?")
            online  = "🟢" if d.get("online") else "🔴"
            lines.append(f"{online} <b>{name}</b>")
            lines.append(f"   IP: <code>{ip}</code>  OS: {os_}")
        return "\n".join(lines)

    async def nameservers_get(self) -> str:
        """Zeigt aktuelle Nameserver."""
        r = await self._get(f"/tailnet/{self.tailnet}/dns/nameservers")
        if not r["ok"]:
            return f"<b>Nameserver — Fehler:</b>\n{r['error'] or r['data']}"
        ns = r["data"].get("dns", [])
        if not ns:
            return "<b>Nameserver:</b> Keine benutzerdefinierten Nameserver gesetzt."
        lines = ["<b>🔧 Nameserver:</b>"]
        for n in ns:
            lines.append(f"  • <code>{n}</code>")
        return "\n".join(lines)

    async def nameservers_set(self, servers: List[str]) -> str:
        """Setzt Nameserver (ersetzt bestehende)."""
        r = await self._post(
            f"/tailnet/{self.tailnet}/dns/nameservers",
            {"dns": servers},
        )
        if not r["ok"]:
            return f"<b>Nameserver setzen — Fehler:</b>\n{r['error'] or r['data']}"
        set_ns = r["data"].get("dns", servers)
        lines = ["<b>✅ Nameserver gesetzt:</b>"]
        for n in set_ns:
            lines.append(f"  • <code>{n}</code>")
        return "\n".join(lines)

    async def nameservers_add(self, server: str) -> str:
        """Fügt einen Nameserver hinzu (bestehende bleiben)."""
        r = await self._get(f"/tailnet/{self.tailnet}/dns/nameservers")
        if not r["ok"]:
            return f"<b>Fehler beim Lesen:</b>\n{r['error'] or r['data']}"
        current = r["data"].get("dns", [])
        if server in current:
            return f"<b>ℹ️ Nameserver</b> <code>{server}</code> ist bereits gesetzt."
        return await self.nameservers_set(current + [server])

    async def nameservers_remove(self, server: str) -> str:
        """Entfernt einen Nameserver."""
        r = await self._get(f"/tailnet/{self.tailnet}/dns/nameservers")
        if not r["ok"]:
            return f"<b>Fehler beim Lesen:</b>\n{r['error'] or r['data']}"
        current = r["data"].get("dns", [])
        updated = [n for n in current if n != server]
        if len(updated) == len(current):
            return f"<b>ℹ️ Nameserver</b> <code>{server}</code> nicht gefunden."
        return await self.nameservers_set(updated)

    async def search_domains_get(self) -> str:
        """Zeigt Search Domains."""
        r = await self._get(f"/tailnet/{self.tailnet}/dns/searchpaths")
        if not r["ok"]:
            return f"<b>Search Domains — Fehler:</b>\n{r['error'] or r['data']}"
        paths = r["data"].get("searchPaths", [])
        if not paths:
            return "<b>Search Domains:</b> Keine benutzerdefinierten Domains."
        lines = ["<b>🔍 Search Domains:</b>"]
        for p in paths:
            lines.append(f"  • <code>{p}</code>")
        return "\n".join(lines)

    async def search_domains_set(self, domains: List[str]) -> str:
        """Setzt Search Domains."""
        r = await self._post(
            f"/tailnet/{self.tailnet}/dns/searchpaths",
            {"searchPaths": domains},
        )
        if not r["ok"]:
            return f"<b>Search Domains setzen — Fehler:</b>\n{r['error'] or r['data']}"
        set_d = r["data"].get("searchPaths", domains)
        lines = ["<b>✅ Search Domains gesetzt:</b>"]
        for d in set_d:
            lines.append(f"  • <code>{d}</code>")
        return "\n".join(lines)

    async def search_domains_add(self, domain: str) -> str:
        """Fügt eine Search Domain hinzu."""
        r = await self._get(f"/tailnet/{self.tailnet}/dns/searchpaths")
        if not r["ok"]:
            return f"<b>Fehler beim Lesen:</b>\n{r['error'] or r['data']}"
        current = r["data"].get("searchPaths", [])
        if domain in current:
            return f"<b>ℹ️ Domain</b> <code>{domain}</code> ist bereits gesetzt."
        return await self.search_domains_set(current + [domain])

    async def search_domains_remove(self, domain: str) -> str:
        """Entfernt eine Search Domain."""
        r = await self._get(f"/tailnet/{self.tailnet}/dns/searchpaths")
        if not r["ok"]:
            return f"<b>Fehler beim Lesen:</b>\n{r['error'] or r['data']}"
        current = r["data"].get("searchPaths", [])
        updated = [d for d in current if d != domain]
        if len(updated) == len(current):
            return f"<b>ℹ️ Domain</b> <code>{domain}</code> nicht gefunden."
        return await self.search_domains_set(updated)

    async def magicdns_enable(self) -> str:
        """Aktiviert MagicDNS."""
        r = await self._post(
            f"/tailnet/{self.tailnet}/dns/preferences",
            {"magicDNS": True},
        )
        if not r["ok"]:
            return f"<b>MagicDNS — Fehler:</b>\n{r['error'] or r['data']}"
        return "<b>✅ MagicDNS aktiviert.</b>"

    async def magicdns_disable(self) -> str:
        """Deaktiviert MagicDNS."""
        r = await self._post(
            f"/tailnet/{self.tailnet}/dns/preferences",
            {"magicDNS": False},
        )
        if not r["ok"]:
            return f"<b>MagicDNS — Fehler:</b>\n{r['error'] or r['data']}"
        return "<b>✅ MagicDNS deaktiviert.</b>"

    # ─────────────────────────────────────────────────────────────────────────
    # Hilfe
    # ─────────────────────────────────────────────────────────────────────────

    def cmd_help(self) -> str:
        return (
            "<b>🌐 Tailscale DNS-Befehle:</b>\n\n"
            "/ts — DNS-Übersicht (MagicDNS, Nameserver, Search Domains)\n"
            "/ts_devices — Alle Geräte im Tailnet\n\n"
            "<b>Nameserver:</b>\n"
            "/ts_ns — Nameserver anzeigen\n"
            "/ts_ns_add &lt;ip&gt; — Nameserver hinzufügen\n"
            "/ts_ns_del &lt;ip&gt; — Nameserver entfernen\n"
            "/ts_ns_set &lt;ip1&gt; [ip2...] — Nameserver ersetzen\n\n"
            "<b>Search Domains:</b>\n"
            "/ts_search — Search Domains anzeigen\n"
            "/ts_search_add &lt;domain&gt; — Domain hinzufügen\n"
            "/ts_search_del &lt;domain&gt; — Domain entfernen\n\n"
            "<b>MagicDNS:</b>\n"
            "/ts_magic_on — MagicDNS aktivieren\n"
            "/ts_magic_off — MagicDNS deaktivieren\n\n"
            "<i>Konfiguration: TAILSCALE_API_KEY und TAILSCALE_TAILNET in .env</i>"
        )
