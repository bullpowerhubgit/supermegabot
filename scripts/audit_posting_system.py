#!/usr/bin/env python3
"""End-to-end audit of posting quality guards. Exit 0 only if all critical checks pass."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from modules.post_guardian import validate_post as guardian_validate
    from modules import http_guard

    fails: list[str] = []

    bad_samples = [
        ("twitter", "Hallo None, kauf jetzt [PLACEHOLDER]!"),
        ("facebook", "Vancouver PD website features Quick Escape button"),
        ("instagram", "3D Modellierung Einsteiger — Blender von 0 — Smarter wohnen ab €37"),
        ("linkedin", "Check https://autopilot-store-suite-fmbka.myshopify.com/products/x"),
        ("twitter", "TODO: insert product link here"),
        ("facebook", "Show HN: my new app that wipes history"),
        ("linkedin", "Als KI-Sprachmodell kann ich dir helfen"),
    ]
    for plat, text in bad_samples:
        ok, errs = guardian_validate(text, plat)
        status = "BLOCK" if not ok else "LEAK"
        print(f"{status:5} [{plat}] {text[:55]!r} → {str(errs)[:80]}")
        if ok:
            fails.append(f"LEAKED bad post on {plat}: {text[:40]}")

    good = (
        "Shopify Automation mit SuperMegaBot: Spare 10h/Woche und steigere "
        "deinen E-Commerce Umsatz. Smart Home Gadgets auf ineedit.com.co 🚀"
    )
    ok, errs = guardian_validate(good, "linkedin")
    print(f"{'PASS' if ok else 'FAIL':5} [linkedin] good content → {errs}")
    if not ok:
        fails.append(f"blocked good post: {errs}")

    src = inspect.getsource(http_guard._intercepted_request)
    if "request_info=None" in src:
        fails.append("HttpGuard still raises ClientResponseError(None)")
        print("FAIL  HttpGuard still uses broken ClientResponseError(None)")
    else:
        print("PASS  HttpGuard uses safe ClientError")

    sched = (ROOT / "core" / "automation_scheduler.py").read_text()
    if '\n    ("product_hub"' in sched or '\n\t("product_hub"' in sched:
        fails.append("product_hub still scheduled")
        print("FAIL  product_hub still active")
    else:
        print("PASS  product_hub disabled")

    # post_gateway must ban myshopify
    from modules import post_gateway
    gw_src = inspect.getsource(post_gateway)
    if "myshopify" not in gw_src:
        fails.append("post_gateway missing myshopify ban")
        print("FAIL  post_gateway missing myshopify ban")
    else:
        print("PASS  post_gateway bans myshopify")

    # NEVER-TWICE engine + wiring across all posting paths
    try:
        from modules.post_never_twice import (
            check_never_twice,
            import_legacy_blocks,
            remember_block,
            self_check,
            stats,
        )
        import_legacy_blocks()
        nt = self_check()
        print(f"{'PASS' if nt.get('ok') else 'FAIL'}  NeverTwice self_check → {nt}")
        if not nt.get("ok"):
            fails.append(f"NeverTwice self_check failed: {nt}")
        # same content twice
        bad = "NEVER TWICE SAMPLE [PLACEHOLDER] myshopify.com Hallo None"
        remember_block(bad, "facebook", ["placeholder", "myshopify"], source_module="audit")
        ok2, e2 = check_never_twice(bad, "facebook")
        print(f"{'PASS' if not ok2 else 'FAIL'}  same content blocked again → {e2[:1]}")
        if ok2:
            fails.append("NeverTwice allowed previously blocked content")

        # Wiring must exist in all critical modules
        for mod_name, needle in (
            ("modules/post_gateway.py", "check_never_twice"),
            ("modules/post_guardian.py", "check_never_twice"),
            ("modules/post_guard.py", "check_never_twice"),
            ("modules/post_validator.py", "check_never_twice"),
            ("modules/post_watchdog.py", "check_never_twice"),
            ("modules/http_guard.py", "check_never_twice"),
            ("modules/twitter_auto_poster.py", "check_never_twice"),
            ("modules/twitter_autoposter.py", "check_never_twice"),
        ):
            src = (ROOT / mod_name).read_text()
            if needle not in src:
                fails.append(f"{mod_name} missing {needle}")
                print(f"FAIL  {mod_name} missing {needle}")
            else:
                print(f"PASS  {mod_name} wired")

        st = stats()
        print(f"INFO  NeverTwice stats: {st}")
    except Exception as e:
        fails.append(f"NeverTwice import/run failed: {e}")
        print(f"FAIL  NeverTwice: {e}")

    print("---")
    if fails:
        print(f"AUDIT FAILED: {len(fails)} issues")
        for f in fails:
            print(" -", f)
        return 1
    print("AUDIT OK — posting guards + never-twice block faulty content")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
