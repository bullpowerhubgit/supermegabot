#!/usr/bin/env python3
"""
Inject Case Studies + Sales-Call-Prozess into ALL netlify-deploy landings,
marketing copy, and ensure dual CTAs (Trial + Book Call).

Idempotent: skips if data-smb-sales="1" already present.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.sales_call_process import (  # noqa: E402
    CASE_STUDIES,
    PROCESS_STEPS,
    SALES_CALL_URL,
    STRIPE_STARTER,
    html_sections,
    cta_block,
)

DEPLOY = ROOT / "netlify-deploy"
MARKER = 'data-smb-sales="1"'

# folder → display name
NAMES = {
    "bullpower-hub": "BullPower Hub",
    "bullpower-ai": "BullPower AI",
    "launcher": "BullPower Launcher",
    "lead-capture": "Lead Capture Pro",
    "steuercockpit": "SteuercockPit Pro",
    "shopify-brutal-tuning": "Shopify Brutal Tuning",
    "shopify-acquisition-engine": "Shopify Acquisition Engine",
    "shopify-suite": "Shopify Suite",
    "telegram-bot": "Telegram Marketing Bot",
    "autoincome-ai": "AutoIncome AI",
    "creatorai-ultra": "CreatorAI Ultra",
    "creatorstudio-pro": "CreatorStudio Pro",
    "cognitive-symphony": "Cognitive Symphony",
    "digistore24-suite": "Digistore24 Suite",
    "gumroad-discord": "Gumroad Discord Bot",
    "icomeauto": "iComeAuto",
    "master-dashboard": "MEGA Dashboard",
    "demo-hub": "Demo Hub",
    "aiitec-pinterest-portal": "AIITEC / rodibot",
    "aiitec-all": "AIITEC",
}


def inject_html(path: Path, product: str) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if MARKER in text:
        return False
    block = html_sections(product_name=product)
    # insert before </body> or append
    if re.search(r"</body>", text, re.I):
        text = re.sub(r"</body>", block + "\n</body>", text, count=1, flags=re.I)
    else:
        text = text.rstrip() + "\n" + block + "\n"
    path.write_text(text, encoding="utf-8")
    return True


def patch_hero_ctas(path: Path) -> bool:
    """Add secondary Book Call CTA near existing Stripe CTAs if missing."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "Strategy Call" in text or "Strategy-Call" in text or SALES_CALL_URL in text:
        # still ok if only in new block
        pass
    changed = False
    # common hero-ctas container
    if "hero-ctas" in text and SALES_CALL_URL not in text.split("hero-ctas")[1][:800]:
        extra = (
            f'\n      <a class="btn-secondary" href="{SALES_CALL_URL}" target="_blank" rel="noopener" '
            f'style="display:inline-block;padding:.75rem 1.4rem;border-radius:10px;border:1px solid #6c63ff;'
            f'color:#c4b5fd;text-decoration:none;font-weight:700;margin-left:.5rem">15-Min Strategy Call →</a>'
        )
        text2 = re.sub(
            r'(class="hero-ctas"[^>]*>)',
            r"\1" + extra,
            text,
            count=1,
        )
        if text2 != text:
            text = text2
            changed = True
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def update_marketing_md() -> None:
    cta = cta_block("en")
    cases = "\n".join(
        f"- **{c['title']}** ({c['persona']}): {c['result']} in {c['duration']} — {c['quote']}"
        for c in CASE_STUDIES
    )
    steps = "\n".join(f"{s['n']}. **{s['title']}** — {s['desc']}" for s in PROCESS_STEPS)
    block = f"""

---

## Case Studies
{cases}

## Sales Call Process (15–30 min)
{steps}

## CTAs
- **Primary:** [{cta['primary_label']}]({cta['primary_url']})
- **Secondary:** [{cta['secondary_label']}]({cta['secondary_url']})
- **Demo:** [{cta['demo_url']}]({cta['demo_url']})
"""
    for name in ("landingpage_copy_en.md",):
        p = ROOT / "marketing" / name
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        if "## Case Studies" in t and "Sales Call Process" in t:
            # replace old section from ## Case Studies to end or next ---
            t = re.sub(
                r"\n---\n\n## Case Studies[\s\S]*$",
                block.rstrip() + "\n",
                t,
            )
            if "## Case Studies" not in t.split("Sales Call")[0][-50:]:
                # append if replace failed
                if "Sales Call Process (15–30 min)" not in t:
                    t = t.rstrip() + block
        else:
            t = t.rstrip() + block
        p.write_text(t, encoding="utf-8")

    # DE landing copy
    de = ROOT / "marketing" / "landingpage_copy_de.md"
    de_block = f"""# SuperMegaBot — Landing Copy (DE)

## Hero
**Shopify + Telegram mit KI automatisieren.**  
Mehr Umsatz, weniger Support — live in unter 30 Minuten.

**Primary CTA:** [7 Tage kostenlos testen]({STRIPE_STARTER})  
**Secondary CTA:** [15-Min Strategy Call]({SALES_CALL_URL})

## Case Studies
{chr(10).join(f"- **{c['title']}**: {c['result']} ({c['duration']}) — {c['quote']}" for c in CASE_STUDIES)}

## Sales-Call Prozess
{steps}

## Pricing
- Starter €49/mo · Growth €99/mo · Scale €299/mo
- 7-Tage Trial · Strategy Call für High-Touch

## Final CTA
Trial: {STRIPE_STARTER}  
Call: {SALES_CALL_URL}
"""
    de.write_text(de_block, encoding="utf-8")


def update_dm_sheet() -> None:
    p = ROOT / "marketing" / "telegram_dm_sheet_30.md"
    if not p.exists():
        return
    t = p.read_text(encoding="utf-8")
    add = f"""

---

## Sales-Call + Case Study Snippets

### Book Call
Perfekt — 15-Min Strategy Call. Schreib: 1) Shopify/DS24/Agency 2) größter Schmerz 3) Ziel in 30 Tagen.
Trial direkt: {STRIPE_STARTER} · Bot: {SALES_CALL_URL}

### After Case (Shopify)
Ähnlich wie Shopify Solo: −40% Support-Zeit + Recovery-Umsatz in 45 Tagen.
→ Trial: {STRIPE_STARTER} · Call: {SALES_CALL_URL}

### After Case (Agency)
Ähnlich wie Multi-Shop Agency: 1 Hub statt 12 Tools, Team wieder auf Closing.
→ Trial: {STRIPE_STARTER} · Call: {SALES_CALL_URL}

### Close
Option A: 7-Tage Trial (€49) — {STRIPE_STARTER}
Option B: Strategy Call — {SALES_CALL_URL}
"""
    if "Sales-Call + Case Study Snippets" not in t:
        p.write_text(t.rstrip() + add, encoding="utf-8")


def main() -> None:
    injected = 0
    skipped = 0
    # all index.html under netlify-deploy (depth 2-3)
    htmls = list(DEPLOY.glob("*/index.html")) + list(DEPLOY.glob("*/*/index.html"))
    # de-dupe
    seen = set()
    for path in htmls:
        if path.resolve() in seen:
            continue
        seen.add(path.resolve())
        # product name from folder
        rel = path.relative_to(DEPLOY)
        folder = rel.parts[0]
        product = NAMES.get(folder, folder.replace("-", " ").title())
        if inject_html(path, product):
            injected += 1
            print(f"INJECT {path.relative_to(ROOT)}")
        else:
            skipped += 1
        patch_hero_ctas(path)

    update_marketing_md()
    update_dm_sheet()
    print(f"\nDone: injected={injected} skipped_already={skipped} total={injected+skipped}")
    print(f"Stripe trial: {STRIPE_STARTER}")
    print(f"Sales call:  {SALES_CALL_URL}")


if __name__ == "__main__":
    main()
