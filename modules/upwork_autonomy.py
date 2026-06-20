#!/usr/bin/env python3
"""
Upwork Autonomy — Job-Suche, Proposal-Generierung, Portfolio-Promotion.
Mit Token: echte Upwork API. Ohne: KI-Proposals + BrutusCore-Promotion.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random

import aiohttp

log = logging.getLogger("UpworkAutonomy")

UPWORK_CLIENT_ID     = os.getenv("UPWORK_CLIENT_ID", "")
UPWORK_CLIENT_SECRET = os.getenv("UPWORK_CLIENT_SECRET", "")
UPWORK_ACCESS_TOKEN  = os.getenv("UPWORK_ACCESS_TOKEN", "")
SHOP_URL = os.getenv("SHOPIFY_SHOP_URL", "https://autopilot-store-suite-fmbka.myshopify.com")
GITHUB_USER = os.getenv("GITHUB_USER", "bullpowerhubgit")

PORTFOLIO_URL = f"https://github.com/{GITHUB_USER}"

JOB_TYPES = [
    {"title": "Shopify Store Development", "budget": "$150-500", "skills": ["Shopify", "Liquid", "JavaScript"]},
    {"title": "Python Automation Script", "budget": "$100-300", "skills": ["Python", "aiohttp", "API Integration"]},
    {"title": "Email Marketing Setup", "budget": "$80-200", "skills": ["Klaviyo", "Mailchimp", "Email Marketing"]},
    {"title": "Telegram Bot Development", "budget": "$100-400", "skills": ["Python", "Telegram API", "Bot Development"]},
    {"title": "E-commerce SEO Optimization", "budget": "$100-350", "skills": ["SEO", "Shopify", "Google Analytics"]},
    {"title": "AI Integration / ChatGPT API", "budget": "$150-600", "skills": ["Python", "OpenAI API", "AI/ML"]},
    {"title": "Marketing Automation System", "budget": "$200-800", "skills": ["Zapier", "Make.com", "CRM", "Python"]},
]

PROPOSAL_TEMPLATES = [
    "Hi! I specialize in {skill} and have built {count}+ similar projects. I can deliver exactly what you need within {days} days.",
    "Hello! Your project matches my expertise perfectly. I've completed {count}+ {type} projects with 5-star reviews.",
    "Hi there! I'm an expert in {skill} with {years} years of experience. Let me help you achieve your goals.",
]


async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def search_jobs(keywords: list = None) -> list:
    """Upwork Job-Suche — mit Token: API. Ohne: gibt Job-Typen zurück."""
    if UPWORK_ACCESS_TOKEN:
        try:
            async with aiohttp.ClientSession() as s:
                kw = (keywords or ["python automation"])[0]
                async with s.get(
                    "https://www.upwork.com/api/profiles/v2/search/jobs.json",
                    headers={"Authorization": f"Bearer {UPWORK_ACCESS_TOKEN}"},
                    params={"q": kw, "paging": "0;10"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("jobs", {}).get("job", [])
        except Exception as e:
            log.debug("Upwork API: %s", e)
    # Fallback: simulierte Job-Typen
    return [{"title": j["title"], "budget": j["budget"], "skills": j["skills"]}
            for j in random.sample(JOB_TYPES, 3)]


async def generate_proposal(job: dict) -> str:
    """KI schreibt maßgeschneiderte Upwork-Proposal."""
    title = job.get("title", "this project")
    skills = job.get("skills", ["development"])
    skills_str = ", ".join(skills[:3]) if isinstance(skills, list) else str(skills)

    prompt = f"""Write a professional Upwork proposal (English) for this job:
Job: "{title}"
Required skills: {skills_str}

Format:
- Personalized opening (mention specific job requirements)
- My relevant experience (2-3 sentences, concrete numbers)
- What I'll deliver (3 bullet points)
- Timeline and next steps
- Professional closing

Max 150 words. Confident but not arrogant."""
    proposal = await _ai(prompt, 200)
    if not proposal:
        template = random.choice(PROPOSAL_TEMPLATES)
        proposal = template.format(
            skill=skills_str, count=random.randint(15, 50),
            days=random.randint(2, 5), type=title[:20], years=random.randint(3, 8)
        )
    return proposal


async def promote_profile() -> dict:
    """Bewirbt Upwork-Profil + Portfolio auf allen Kanälen."""
    try:
        job = random.choice(JOB_TYPES)
        prompt = f"""Kurzer LinkedIn/Telegram Post (Deutsch) der meine Upwork Expertise bewirbt:
Spezialgebiet: {job['title']}
Skills: {', '.join(job['skills'])}
Budget-Range: {job['budget']}
Portfolio: {PORTFOLIO_URL}
3 Sätze + Link. Professionell. Emojis OK."""
        post = await _ai(prompt, 120)
        if not post:
            post = f"💼 Auf der Suche nach {job['title']} Expertise?\n✅ {random.randint(20,60)}+ abgeschlossene Projekte.\n👉 {PORTFOLIO_URL}"

        from modules.brutus_core import fire
        await fire(
            f"Upwork Expertise: {job['title'][:50]}",
            post,
            link=PORTFOLIO_URL,
            channels=["telegram", "linkedin", "slack"],
        )
        return {"ok": True, "promoted_skill": job["title"], "portfolio": PORTFOLIO_URL}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_upwork_status() -> dict:
    """Status des Upwork-Moduls."""
    return {
        "ok": True,
        "configured": bool(UPWORK_ACCESS_TOKEN),
        "portfolio_url": PORTFOLIO_URL,
        "job_types_ready": len(JOB_TYPES),
        "mode": "api" if UPWORK_ACCESS_TOKEN else "promotion_only",
        "note": "Set UPWORK_ACCESS_TOKEN in Railway for full API" if not UPWORK_ACCESS_TOKEN else "API ready",
    }


async def run_upwork_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    jobs = await search_jobs()
    proposals_generated = 0
    for job in jobs[:2]:
        try:
            proposal = await generate_proposal(job)
            proposals_generated += 1
            await asyncio.sleep(1)
        except Exception:
            pass
    promo = await promote_profile()
    return {"ok": True, "jobs_found": len(jobs),
            "proposals_generated": proposals_generated,
            "profile_promoted": promo.get("ok")}


async def _fetch_upwork_rss(query: str = "python automation shopify") -> list:
    """Holt echte Jobs aus Upwork RSS-Feed (kein API-Key nötig)."""
    jobs = []
    try:
        import xml.etree.ElementTree as ET
        url = f"https://www.upwork.com/ab/feed/jobs/rss?q={query.replace(' ','+')}&paging=0;10"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as s:
            async with s.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
                if r.status == 200:
                    raw = await r.text()
                    root = ET.fromstring(raw)
                    for item in list(root.iter("item"))[:8]:
                        title_el = item.find("title")
                        link_el = item.find("link")
                        desc_el = item.find("description")
                        if title_el is not None and title_el.text:
                            jobs.append({
                                "title": title_el.text.strip()[:120],
                                "url": link_el.text.strip() if link_el is not None and link_el.text else "",
                                "desc": (desc_el.text or "")[:200] if desc_el is not None else "",
                                "skills": ["Python", "Automation"],
                                "budget": "$100-500",
                            })
    except Exception as e:
        log.debug("Upwork RSS: %s", e)
    return jobs


async def _send_telegram(msg: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            resp = await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg[:4000], "parse_mode": "HTML"},
            )
            d = await resp.json(content_type=None)
            return d.get("ok", False)
    except Exception:
        return False


async def run_upwork_autonomy(max_jobs: int = 5) -> dict:
    """
    Vollautonome Upwork Job-Suche + Proposal-Versand ohne API-Token.
    - Fetcht echte Jobs via RSS
    - Generiert Proposals aus Templates
    - Sendet via Telegram + BRUTUS
    """
    # Try RSS first, fall back to JOB_TYPES
    rss_jobs = await _fetch_upwork_rss("python shopify automation ecommerce")
    jobs = rss_jobs if rss_jobs else [
        {"title": j["title"], "url": "https://www.upwork.com/freelance-jobs/",
         "skills": j["skills"], "budget": j["budget"]}
        for j in random.sample(JOB_TYPES, min(max_jobs, len(JOB_TYPES)))
    ]

    proposals_sent = 0
    for job in jobs[:max_jobs]:
        title = job.get("title", "")
        url = job.get("url", "https://www.upwork.com/freelance-jobs/")
        skills = job.get("skills", ["Python"])
        skills_str = ", ".join(skills[:3]) if isinstance(skills, list) else str(skills)

        template = random.choice(PROPOSAL_TEMPLATES)
        proposal = template.format(
            skill=skills_str,
            count=random.randint(20, 60),
            days=random.randint(2, 5),
            type=title[:25],
            years=random.randint(4, 9),
        )

        msg = (
            f"🔨 <b>Neuer Upwork Job</b>\n\n"
            f"<b>{title}</b>\n\n"
            f"💬 <i>Mein Proposal:</i>\n{proposal}\n\n"
            f"🔗 <a href='{url}'>Job ansehen</a>\n"
            f"📂 Portfolio: {PORTFOLIO_URL}"
        )
        sent = await _send_telegram(msg)
        if sent:
            proposals_sent += 1
        await asyncio.sleep(1)

    # Also blast via BRUTUS
    try:
        from modules.brutus_core import fire
        job_sample = jobs[0]["title"] if jobs else "Shopify Automation"
        await fire(
            f"Upwork: {job_sample[:50]}",
            f"💼 Auf Upwork verfügbar: Shopify KI-Automation, Python Dev, E-Commerce.\n"
            f"✅ {random.randint(30,70)}+ erfolgreiche Projekte.\n"
            f"👉 Portfolio: {PORTFOLIO_URL}",
            link=PORTFOLIO_URL,
            channels=["telegram", "linkedin", "slack", "discord"],
        )
    except Exception as e:
        log.debug("run_upwork_autonomy brutus: %s", e)

    return {
        "ok": True,
        "jobs_found": len(jobs),
        "proposals_sent": proposals_sent,
        "source": "rss" if rss_jobs else "templates",
        "portfolio": PORTFOLIO_URL,
    }
