#!/usr/bin/env python3
"""SEMrush API client — keyword research, domain analytics, backlinks, traffic."""
import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger("SEMrushClient")

SEMRUSH_BASE = "https://api.semrush.com/"
SEMRUSH_API_KEY = os.getenv("SEMRUSH_API_KEY", "")


def _key() -> str:
    if not SEMRUSH_API_KEY:
        raise ValueError("SEMRUSH_API_KEY not set — get it at https://www.semrush.com/api-analytics/")
    return SEMRUSH_API_KEY


async def _get(params: Dict[str, Any]) -> str:
    """Raw GET to SEMrush API. Returns raw text (CSV or JSON depending on export_escape)."""
    try:
        import aiohttp
    except ImportError:
        raise RuntimeError("aiohttp not installed")
    params["key"] = _key()
    async with aiohttp.ClientSession() as s:
        async with s.get(SEMRUSH_BASE, params=params) as r:
            text = await r.text()
            if r.status != 200:
                raise RuntimeError(f"SEMrush {r.status}: {text[:200]}")
            return text


def _parse_csv(raw: str) -> List[Dict[str, str]]:
    """Parse SEMrush semicolon-delimited CSV into list of dicts."""
    lines = [l for l in raw.strip().splitlines() if l]
    if len(lines) < 2:
        return []
    headers = lines[0].split(";")
    rows = []
    for line in lines[1:]:
        vals = line.split(";")
        rows.append(dict(zip(headers, vals)))
    return rows


# ── Keyword Analytics ──────────────────────────────────────────────────────────

async def keyword_overview(phrase: str, database: str = "de") -> Dict:
    """Keyword overview: search volume, CPC, competition."""
    raw = await _get({
        "type": "phrase_this",
        "phrase": phrase,
        "export_columns": "Ph,Nq,Cp,Co,Nr,Td",
        "database": database,
    })
    rows = _parse_csv(raw)
    return rows[0] if rows else {"error": "no data"}


async def keyword_related(phrase: str, database: str = "de", limit: int = 20) -> List[Dict]:
    """Related keywords with volume + CPC."""
    raw = await _get({
        "type": "phrase_related",
        "phrase": phrase,
        "export_columns": "Ph,Nq,Cp,Co,Nr",
        "database": database,
        "display_limit": limit,
    })
    return _parse_csv(raw)


async def keyword_organic_results(phrase: str, database: str = "de") -> List[Dict]:
    """Top organic SERP results for a keyword."""
    raw = await _get({
        "type": "phrase_organic",
        "phrase": phrase,
        "export_columns": "Dn,Ur,Po,Nq,Cp,Co,Tr,Tc",
        "database": database,
        "display_limit": 10,
    })
    return _parse_csv(raw)


# ── Domain Analytics ───────────────────────────────────────────────────────────

async def domain_overview(domain: str, database: str = "de") -> Dict:
    """Domain overview: organic keywords, traffic, authority score."""
    raw = await _get({
        "type": "domain_ranks",
        "domain": domain,
        "export_columns": "Dn,Rk,Or,Ot,Oc,Ad,At,Ac",
        "database": database,
    })
    rows = _parse_csv(raw)
    return rows[0] if rows else {"error": "no data"}


async def domain_organic_keywords(domain: str, database: str = "de", limit: int = 20) -> List[Dict]:
    """Organic keywords a domain ranks for."""
    raw = await _get({
        "type": "domain_organic",
        "domain": domain,
        "export_columns": "Ph,Po,Nq,Cp,Ur,Tr,Tc,Co,Nr,Td",
        "database": database,
        "display_limit": limit,
        "display_sort": "tr_desc",
    })
    return _parse_csv(raw)


async def domain_competitors(domain: str, database: str = "de", limit: int = 10) -> List[Dict]:
    """Organic competitors for a domain."""
    raw = await _get({
        "type": "domain_organic_organic",
        "domain": domain,
        "export_columns": "Dn,Or,Ot,Oc,Ad,At,Ac,Np",
        "database": database,
        "display_limit": limit,
    })
    return _parse_csv(raw)


async def domain_backlinks(domain: str) -> Dict:
    """Backlink overview for a domain."""
    raw = await _get({
        "type": "backlinks_overview",
        "target": domain,
        "target_type": "root_domain",
        "export_columns": "total,domains_num,urls_num,ips_num,follows_num,nofollows_num",
    })
    rows = _parse_csv(raw)
    return rows[0] if rows else {"error": "no data"}


# ── Traffic Analytics ──────────────────────────────────────────────────────────

async def traffic_summary(domain: str) -> Dict:
    """Monthly traffic estimates for a domain (Traffic Analytics API)."""
    try:
        import aiohttp
    except ImportError:
        raise RuntimeError("aiohttp not installed")
    url = "https://api.semrush.com/analytics/ta/api/v3/summary"
    params = {
        "key": _key(),
        "targets": domain,
        "display_date": "",
        "country": "de",
        "display_limit": 1,
    }
    async with aiohttp.ClientSession() as s:
        async with s.get(url, params=params) as r:
            if r.status != 200:
                text = await r.text()
                return {"error": f"HTTP {r.status}: {text[:200]}"}
            return await r.json(content_type=None)


# ── Convenience wrapper for SuperMegaBot ──────────────────────────────────────

async def research_niche(keyword: str, own_domain: Optional[str] = None, database: str = "de") -> Dict:
    """Full niche research: keyword overview + related + competitors (if domain given)."""
    import asyncio
    tasks = [keyword_overview(keyword, database), keyword_related(keyword, database, 10)]
    if own_domain:
        tasks.append(domain_competitors(own_domain, database, 5))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: Dict[str, Any] = {
        "keyword_overview": results[0] if not isinstance(results[0], Exception) else str(results[0]),
        "related_keywords": results[1] if not isinstance(results[1], Exception) else str(results[1]),
    }
    if own_domain:
        out["competitors"] = results[2] if not isinstance(results[2], Exception) else str(results[2])
    return out
