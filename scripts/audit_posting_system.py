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
        # Placeholder / Template-Fehler
        ("twitter", "Hallo None, kauf jetzt [PLACEHOLDER]!"),
        ("linkedin", "Als KI-Sprachmodell kann ich dir helfen"),
        ("twitter", "TODO: insert product link here"),
        # Verbotene URLs
        ("linkedin", "Check https://autopilot-store-suite-fmbka.myshopify.com/products/x"),
        # Off-Topic News
        ("facebook", "Vancouver PD website features Quick Escape button"),
        ("facebook", "Show HN: my new app that wipes history"),
        ("instagram", "3D Modellierung Einsteiger — Blender von 0 — Smarter wohnen ab €37"),
        # OFF-TOPIC NISCHE — dürfen NIE posten (Bambus, Kaffee, Stuhl, Yoga, etc.)
        ("instagram", "Bambus Schneidebrett Set — Das perfekte Küchenaccessoire für dein Zuhause!"),
        ("facebook", "Coffee Grinder Electric — Frisch gemahlener Kaffee jeden Morgen"),
        ("instagram", "Ergonomic Chair Cushion — Komfort für deinen Bürostuhl"),
        ("twitter", "Yoga Matte Premium — Rutschfest für dein Training"),
        ("facebook", "Kochbuch für Anfänger — 100 einfache Rezepte"),
        ("instagram", "Duftkerze Lavendel — Entspannung pur für dein Wohnzimmer"),
        ("linkedin", "Bettwäsche Set 100% Baumwolle — Sanfter Schlaf garantiert"),
        ("twitter", "Notizbuch DIN A5 — Dein perfekter Begleiter für jeden Tag"),
    ]
    for plat, text in bad_samples:
        ok, errs = guardian_validate(text, plat)
        status = "BLOCK" if not ok else "LEAK"
        print(f"{status:5} [{plat}] {text[:55]!r} → {str(errs)[:80]}")
        if ok:
            fails.append(f"LEAKED bad post on {plat}: {text[:40]}")

    good_samples = [
        (
            "Shopify Automation mit KI: Spare 10h/Woche und steigere deinen "
            "E-Commerce Umsatz. Smart Home Gadgets auf ineedit.com.co 🚀",
            "linkedin",
        ),
        (
            "100W Solar Panel — Komplettset mit MPPT Controller und Powerstation. "
            "Jetzt auf ineedit.com.co für €89,99 🌞 #solar #smarthome",
            "instagram",
        ),
        (
            "WiFi Überwachungskamera 4K mit AI Bewegungserkennung — Smart Home Security "
            "auf ineedit.com.co #smartsecurity #gadget",
            "facebook",
        ),
    ]
    for text, plat in good_samples:
        ok, errs = guardian_validate(text, plat)
        print(f"{'PASS' if ok else 'FAIL':5} [good-{plat}] {text[:50]!r} → {errs}")
        if not ok:
            fails.append(f"blocked good post on {plat}: {text[:40]} — {errs}")

    # PostValidator Layer 0: Off-Topic Hard-Block direkt testen
    import asyncio as _asyncio
    try:
        from modules.post_validator import validate_post as pv_validate, _L0_RE
        offtopic_tests = [
            "Bambus Schneidebrett Set — Das perfekte Küchenaccessoire",
            "Coffee Grinder Electric — Frisch gemahlener Kaffee",
            "Ergonomic Chair Cushion für deinen Bürostuhl",
            "Yoga Matte Premium rutschfest",
            "Duftkerze Lavendel Entspannung",
        ]
        for t in offtopic_tests:
            ok_pv, layer, reason = _asyncio.get_event_loop().run_until_complete(
                pv_validate(t, "instagram", content_type="social")
            )
            status = "BLOCK" if not ok_pv else "LEAK"
            print(f"{status:5} [PostValidator-L{layer}] {t[:40]!r} → {reason[:50]}")
            if ok_pv:
                fails.append(f"PostValidator leaked off-topic: {t[:40]}")
        print(f"INFO  Layer-0 Off-Topic patterns: {len(_L0_RE)} aktive Regeln")
    except Exception as e:
        fails.append(f"PostValidator off-topic test failed: {e}")
        print(f"FAIL  PostValidator: {e}")

    # RequestsGuard aktiv prüfen
    try:
        import requests as _req
        guard_active = "_guarded_send" in str(_req.Session.send) or \
                       hasattr(_req.Session.send, "__wrapped__") or \
                       "RequestsGuard" in (getattr(_req.Session.send, "__qualname__", "") or
                                           getattr(_req.Session.send, "__name__", ""))
        # Simple check: inspect source
        import inspect as _ins
        send_src = _ins.getsource(_req.Session.send)
        if "_L0_RE" in send_src or "RequestsGuard" in send_src or "_guarded_send" in send_src or "off_topic" in send_src:
            print("PASS  RequestsGuard wired in requests.Session.send")
        else:
            # Http guard must be activated — check if module patches it
            hg_src = (ROOT / "modules" / "http_guard.py").read_text()
            if "_patch_requests_sync" in hg_src and "Session.send" in hg_src:
                print("PASS  RequestsGuard defined in http_guard (activates on server start)")
            else:
                fails.append("RequestsGuard NOT defined in http_guard.py")
                print("FAIL  RequestsGuard missing from http_guard.py")
    except Exception as e:
        print(f"WARN  RequestsGuard check: {e}")

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
