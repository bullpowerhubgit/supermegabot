#!/usr/bin/env python3
"""
Meta ROAS Monitor — Automatisches Budget-Scaling
=================================================
Prüft täglich ROAS aller aktiven Meta-Kampagnen.
- ROAS >= 3.0 → Budget +20% (max €15/Tag)
- ROAS >= 5.0 → Budget +50% (max €15/Tag)
- ROAS < 0.5 und Spend > €5 → Kampagne pausieren (optional)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import aiohttp

log = logging.getLogger("MetaROASMonitor")

META_TOKEN  = lambda: os.getenv("META_ACCESS_TOKEN") or os.getenv("FACEBOOK_ACCESS_TOKEN", "")
AD_ACCOUNT  = os.getenv("META_AD_ACCOUNT_ID_AIITEC", "act_878505274898620").replace("act_", "")
API_BASE    = "https://graph.facebook.com/v21.0"

ROAS_SCALE_LOW    = 3.0    # +20% Budget
ROAS_SCALE_HIGH   = 5.0    # +50% Budget
MAX_DAILY_BUDGET  = 1500   # Cent — €15/Tag Obergrenze (sicher)
MIN_SPEND_EUR     = 2.0    # Mindest-Spend bevor Entscheidung


@dataclass
class CampaignResult:
    campaign_id: str
    name: str
    roas: float
    spend_eur: float
    old_budget_eur: float
    new_budget_eur: float
    action: str
    ok: bool
    error: str = ""


async def _get(session: aiohttp.ClientSession, path: str, params: dict) -> dict:
    params["access_token"] = META_TOKEN()
    async with session.get(f"{API_BASE}/{path}", params=params,
                           timeout=aiohttp.ClientTimeout(total=20)) as r:
        return await r.json()


async def _set_budget(session: aiohttp.ClientSession, campaign_id: str,
                      new_budget_cents: int) -> bool:
    data = {"daily_budget": str(new_budget_cents),
            "access_token": META_TOKEN()}
    async with session.post(f"{API_BASE}/{campaign_id}", data=data,
                            timeout=aiohttp.ClientTimeout(total=15)) as r:
        d = await r.json()
        return bool(d.get("success"))


async def run_roas_monitor(dry_run: bool = False) -> list[CampaignResult]:
    """
    Holt ROAS der letzten 3 Tage für alle aktiven Kampagnen
    und skaliert Budget bei guter Performance.
    """
    results = []
    tok = META_TOKEN()
    if not tok:
        log.error("META_ACCESS_TOKEN nicht gesetzt")
        return results

    async with aiohttp.ClientSession() as s:
        # 1. Alle aktiven Kampagnen mit Budget holen
        camps_raw = await _get(s, f"act_{AD_ACCOUNT}/campaigns", {
            "fields": "id,name,daily_budget,effective_status",
            "limit": "50",
        })
        active = [c for c in camps_raw.get("data", [])
                  if c.get("effective_status") == "ACTIVE"
                  and int(c.get("daily_budget", 0)) > 0]

        if not active:
            log.info("Keine aktiven Kampagnen mit Budget gefunden")
            return results

        # 2. Insights der letzten 3 Tage
        insights_raw = await _get(s, f"act_{AD_ACCOUNT}/insights", {
            "fields": "campaign_id,spend,purchase_roas,action_values",
            "date_preset": "last_3d",
            "level": "campaign",
            "limit": "50",
        })
        roas_map = {}
        spend_map = {}
        for ins in insights_raw.get("data", []):
            cid = ins["campaign_id"]
            roas_list = ins.get("purchase_roas", [])
            roas_map[cid] = float(roas_list[0]["value"]) if roas_list else 0.0
            spend_map[cid] = float(ins.get("spend", 0))

        # 3. Budget-Entscheidung pro Kampagne
        for c in active:
            cid = c["id"]
            name = c["name"]
            old_budget_cents = int(c.get("daily_budget", 0))
            old_budget_eur = old_budget_cents / 100
            roas = roas_map.get(cid, 0.0)
            spend = spend_map.get(cid, 0.0)

            action = "keine Änderung"
            new_budget_cents = old_budget_cents

            if spend >= MIN_SPEND_EUR:
                if roas >= ROAS_SCALE_HIGH:
                    # +50%
                    new_budget_cents = min(int(old_budget_cents * 1.5), MAX_DAILY_BUDGET)
                    action = f"+50% (ROAS={roas:.2f})"
                elif roas >= ROAS_SCALE_LOW:
                    # +20%
                    new_budget_cents = min(int(old_budget_cents * 1.2), MAX_DAILY_BUDGET)
                    action = f"+20% (ROAS={roas:.2f})"
                else:
                    action = f"warten (ROAS={roas:.2f}, Spend=€{spend:.2f})"
            else:
                action = f"zu wenig Spend (€{spend:.2f} < €{MIN_SPEND_EUR})"

            new_budget_eur = new_budget_cents / 100
            ok = True

            if new_budget_cents != old_budget_cents and not dry_run:
                ok = await _set_budget(s, cid, new_budget_cents)
                if ok:
                    log.info("Budget geändert: %s → €%.0f/Tag (%s)", name, new_budget_eur, action)
                else:
                    log.warning("Budget-Änderung fehlgeschlagen: %s", name)

            results.append(CampaignResult(
                campaign_id=cid,
                name=name[:50],
                roas=roas,
                spend_eur=spend,
                old_budget_eur=old_budget_eur,
                new_budget_eur=new_budget_eur,
                action=action,
                ok=ok,
            ))

    return results


async def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    import sys
    dry = "--dry" in sys.argv
    if dry:
        log.info("DRY RUN — keine Budget-Änderungen")

    results = await run_roas_monitor(dry_run=dry)

    print("\n=== META ROAS MONITOR ===")
    changed = 0
    for r in results:
        marker = "→" if r.new_budget_eur != r.old_budget_eur else " "
        print(f"{marker} ROAS:{r.roas:5.2f} | €{r.old_budget_eur:.0f}→€{r.new_budget_eur:.0f}/Tag | "
              f"Spend:€{r.spend_eur:.2f} | {r.action[:30]} | {r.name[:35]}")
        if r.new_budget_eur != r.old_budget_eur:
            changed += 1
    print(f"\n{len(results)} Kampagnen geprüft, {changed} Budget-Änderungen")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    asyncio.run(main())
