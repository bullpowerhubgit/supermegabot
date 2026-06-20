#!/usr/bin/env python3
"""
Brutus Injector — fügt BrutusCore-fire() in alle Revenue-Module ein.
Jedes Modul bekommt einen _brutus_fire() Helper + Calls nach Revenue-Events.
"""
import subprocess
import sys

BRUTUS_HELPER = '''

async def _brutus_fire(message: str, channels: list = None):
    """BrutusCore: verteilt Revenue-Events auf alle Kanäle."""
    try:
        from modules.brutus_core import BrutusCore
        b = BrutusCore()
        await b.fire(message, channels=channels or ["telegram", "shopify_blog", "linkedin", "mailchimp", "klaviyo"])
    except Exception as _be:
        import logging
        logging.getLogger(__name__).debug("Brutus fire skip: %s", _be)

'''

# (filename, injection_target_string, brutus_message_template, channels)
INJECTIONS = [
    # DS24 Auto-Fill — nach run() Erfolg
    ("modules/ds24_auto_fill.py",
     "async def run_ds24_auto_fill():",
     None, None),

    # DS24 Funnel — nach run_sync() Erfolg
    ("modules/ds24_funnel_automation.py",
     "async def run_sync()",
     None, None),

    # Auto Funnel — nach run_auto_funnel()
    ("modules/auto_funnel.py",
     "async def run_auto_funnel()",
     None, None),

    # Growth Engine — nach review requests etc
    ("modules/growth_engine.py",
     None, None, None),

    # Social Scheduler — nach post_to_all_channels
    ("modules/social_scheduler.py",
     None, None, None),

    # SEO Automation
    ("modules/seo_automation.py",
     None, None, None),

    # Backlink Bomber — nach run_backlink_bomber
    ("modules/backlink_bomber.py",
     "async def run_backlink_bomber",
     None, None),

    # AI Content Pipeline
    ("modules/ai_content_pipeline.py",
     None, None, None),

    # B2B Pipeline
    ("modules/b2b_pipeline.py",
     None, None, None),

    # TikTok Research
    ("modules/tiktok_research.py",
     None, None, None),
]


def has_brutus(content: str) -> bool:
    return "brutus_core" in content or "_brutus_fire" in content or "BrutusCore" in content


def add_brutus_helper(content: str, filename: str) -> str:
    """Add _brutus_fire helper after imports block."""
    lines = content.split("\n")
    insert_at = 0
    in_docstring = False
    docstring_char = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Track docstrings
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring_char = stripped[:3]
                if stripped.count(docstring_char) >= 2 and len(stripped) > 3:
                    pass  # single-line docstring
                else:
                    in_docstring = True
                continue
        else:
            if docstring_char in stripped:
                in_docstring = False
            continue

        # After imports + module-level constants
        if (stripped.startswith("import ") or stripped.startswith("from ") or
                stripped.startswith("#") or stripped == "" or
                stripped.startswith("log") or stripped.startswith("LOG") or
                stripped.startswith("logger") or
                (stripped.startswith(tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ_")) and "=" in stripped)):
            insert_at = i + 1
        elif stripped.startswith("async def ") or stripped.startswith("def ") or stripped.startswith("class "):
            break

    lines.insert(insert_at, BRUTUS_HELPER)
    return "\n".join(lines)


def inject_brutus_calls(content: str, filename: str) -> str:
    """Add Brutus fire calls after key revenue actions."""

    # Pattern: after "return {" with "ok": True in revenue functions
    # We'll add a _brutus_fire call before the final return in key functions

    inject_map = {
        "modules/ds24_auto_fill.py": [
            ("return {\"ok\": True", "🔥 DS24 Auto-Fill: Neue Affiliate-Produkte live! Jetzt kaufen → {}", ["telegram", "linkedin", "mailchimp"]),
        ],
        "modules/ds24_funnel_automation.py": [
            ("return {\"synced\":", "💰 DS24 Funnel: Neue Käufer erfasst! Umsatz automatisch verarbeitet. #DigiStore24 #PassivesEinkommen", ["telegram", "mailchimp", "klaviyo"]),
        ],
        "modules/auto_funnel.py": [
            ("return result", "🎯 Auto-Funnel aktiv: Lead → Sale → Upsell Pipeline läuft! Mehr Info: https://bullpower.de #AutoFunnel", ["telegram", "klaviyo"]),
        ],
        "modules/backlink_bomber.py": [
            ("return {\"ok\": True", "🔗 BacklinkBomber: Neue Backlinks generiert! SEO-Power für maximale Sichtbarkeit. #SEO #Backlinks", ["telegram", "linkedin", "shopify_blog"]),
        ],
        "modules/seo_automation.py": [
            ("return {\"ok\": True", "📈 SEO optimiert: Shopify-Produkte mit maximaler SEO-Power ausgestattet! #ShopifySEO #Ecommerce", ["telegram", "shopify_blog", "indexnow"]),
        ],
        "modules/social_scheduler.py": [
            ("return {\"ok\": True", "🚀 Content verteilt: Multi-Channel-Post erfolgreich! #Marketing #SocialMedia", ["telegram"]),
        ],
        "modules/growth_engine.py": [
            ("return {\"ok\": True", "📊 Growth Engine: Neue Wachstums-Aktion abgeschlossen! Umsatz steigt. #GrowthHacking", ["telegram", "linkedin"]),
        ],
        "modules/ai_content_pipeline.py": [
            ("return {\"ok\": True", "✍️ AI Content Pipeline: Neuer Content generiert und verteilt! #ContentMarketing #KI", ["telegram", "shopify_blog", "linkedin"]),
        ],
        "modules/b2b_pipeline.py": [
            ("return {\"ok\": True", "🤝 B2B Pipeline: Neue Business-Leads gefunden und kontaktiert! #B2B #BusinessDevelopment", ["telegram", "linkedin"]),
        ],
        "modules/tiktok_research.py": [
            ("return result", "🎵 TikTok Trend erkannt! Viral-Potenzial analysiert. #TikTok #Viral #Marketing", ["telegram"]),
        ],
    }

    if filename not in inject_map:
        return content

    for (search_str, msg, channels) in inject_map[filename]:
        if search_str in content:
            brutus_call = f'\n        await _brutus_fire("{msg}", channels={channels})\n        '
            content = content.replace(search_str, brutus_call + search_str, 1)

    return content


def process_file(filepath: str) -> bool:
    try:
        with open(filepath, "r") as f:
            original = f.read()
    except FileNotFoundError:
        print(f"  SKIP (not found): {filepath}")
        return False

    if has_brutus(original):
        print(f"  SKIP (already has Brutus): {filepath}")
        return False

    content = add_brutus_helper(original, filepath)
    content = inject_brutus_calls(content, filepath)

    with open(filepath, "w") as f:
        f.write(content)

    # Syntax check
    result = subprocess.run(["python3", "-m", "py_compile", filepath], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  SYNTAX ERROR in {filepath}: {result.stderr}")
        # Rollback
        with open(filepath, "w") as f:
            f.write(original)
        print(f"  ROLLED BACK: {filepath}")
        return False

    print(f"  OK: {filepath}")
    return True


FILES = [
    "modules/ds24_auto_fill.py",
    "modules/ds24_funnel_automation.py",
    "modules/auto_funnel.py",
    "modules/growth_engine.py",
    "modules/social_scheduler.py",
    "modules/seo_automation.py",
    "modules/backlink_bomber.py",
    "modules/ai_content_pipeline.py",
    "modules/b2b_pipeline.py",
    "modules/tiktok_research.py",
]

if __name__ == "__main__":
    fixed = 0
    for f in FILES:
        print(f"Processing {f}...")
        if process_file(f):
            fixed += 1
    print(f"\nDone: {fixed}/{len(FILES)} files processed with BrutusCore")
