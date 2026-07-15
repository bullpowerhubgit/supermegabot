"""
Upwork Proposal Auto-Generator.
Kein offizielles Upwork-API nötig: generiert täglich KI-Proposals
für Shopify/Automation Jobs und sendet sie per Telegram an Rudolf.
Copy-Paste-fertig — kein manuelles Schreiben.
"""
import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("UpworkProposal")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
TELEGRAM_CHAT  = _TG_CHANNEL or ""

DATA_DIR      = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
PROPOSALS_FILE = DATA_DIR / "upwork_proposals.json"

JOB_TYPES = [
    {"niche": "Shopify Store Setup & Automation",    "budget": "€200–€800", "url": "https://www.upwork.com/search/jobs/?q=shopify+automation"},
    {"niche": "AI Chatbot & Telegram Bot Development","budget": "€150–€500", "url": "https://www.upwork.com/search/jobs/?q=telegram+bot+python"},
    {"niche": "Digistore24 Funnel Setup",             "budget": "€100–€400", "url": "https://www.upwork.com/search/jobs/?q=digistore24"},
    {"niche": "E-Commerce Automation Python",         "budget": "€300–€1000","url": "https://www.upwork.com/search/jobs/?q=ecommerce+automation+python"},
    {"niche": "SEO Automation & Content Generator",   "budget": "€100–€350", "url": "https://www.upwork.com/search/jobs/?q=seo+automation"},
]


def _load_proposals() -> list:
    try:
        return json.loads(PROPOSALS_FILE.read_text())
    except Exception:
        return []


def _save_proposals(data: list):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROPOSALS_FILE.write_text(json.dumps(data[-20:], ensure_ascii=False, indent=2))


async def _generate_proposal(job: dict) -> str:
    from modules.ai_client import ai_complete
    prompt = (
        f"Schreibe ein professionelles Upwork-Angebot auf Deutsch (max 150 Wörter) "
        f"für diesen Job-Typ: '{job['niche']}'. Budget-Range: {job['budget']}. "
        f"Absender: Rudolf Sarkany, Experte für KI-Automation, Shopify, Python. "
        f"Überzeugend, konkret, kein Marketing-Bla. Ende mit 'Gerne in 15 Min. besprechen.'"
    )
    try:
        text = await ai_complete(prompt, max_tokens=350)
        if text:
            return text
    except Exception as e:
        log.warning("Proposal gen error: %s", e)
    return (
        f"Hallo,\n\n"
        f"ich bin Rudolf Sarkany, Spezialist für {job['niche']}. "
        f"Mit meinem SuperMegaBot-System habe ich bereits mehreren Kunden "
        f"geholfen, ihre {job['niche'].split('&')[0].strip()}-Prozesse zu automatisieren. "
        f"Mein Angebot liegt bei {job['budget']} je nach Umfang.\n\n"
        f"Gerne bespreche ich Details in einem kurzen Call.\n\nBeste Grüße\nRudolf"
    )


async def _send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text[:4096], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json()
        return d.get("ok", False)
    except Exception:
        return False


async def run_upwork_proposal_generation() -> dict:
    proposals = []
    for job in JOB_TYPES:
        proposal_text = await _generate_proposal(job)
        entry = {
            "niche": job["niche"],
            "budget": job["budget"],
            "search_url": job["url"],
            "proposal": proposal_text,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        proposals.append(entry)

        msg = (
            f"📋 *Upwork Proposal fertig:*\n"
            f"🎯 {job['niche']}\n"
            f"💰 Budget: {job['budget']}\n"
            f"🔗 Jobs suchen: {job['url']}\n\n"
            f"*Text zum Copy-Paste:*\n```\n{proposal_text[:800]}\n```"
        )
        await _send_telegram(msg)

    existing = _load_proposals()
    _save_proposals(existing + proposals)
    log.info("Upwork: %d proposals generated & sent", len(proposals))
    return {"ok": True, "proposals_generated": len(proposals), "ts": datetime.now(timezone.utc).isoformat()}


def get_recent_proposals(limit: int = 5) -> list:
    return _load_proposals()[-limit:]
