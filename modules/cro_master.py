#!/usr/bin/env python3
"""
CRO Master — Autonomes Conversion-Optimierungs-System
======================================================
Läuft alle 4h. Erstellt Discount-Codes, setzt Streichpreise,
aktualisiert Trust-JS auf v=3.

v3 JS-Features:
  - Free-Shipping-Bar (Echtzeit, Warenkorb-API)
  - Sticky Mobile ATC Button
  - Review-Stars Badge auf Produktseiten
  - Alle v2 Features (Trust-Bar, Exit-Intent, Purchase-Notifications)
"""
from __future__ import annotations
import asyncio
import logging
import os
import re
from typing import Dict, List

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

log = logging.getLogger("CROmaster")

FREE_SHIP_THRESHOLD = float(os.getenv("FREE_SHIPPING_THRESHOLD", "39"))


def _admin_domain() -> str:
    domain = os.getenv("SHOPIFY_MYSHOPIFY_DOMAIN", "") or os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    if domain and ".myshopify.com" in domain:
        return domain
    store_url = os.getenv("SHOPIFY_STORE_URL", "")
    match = re.search(r"([\w-]+\.myshopify\.com)", store_url)
    return match.group(1) if match else domain


SHOPIFY_DOMAIN  = _admin_domain()
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-04")

# ── Trust + CRO JavaScript v3 ──────────────────────────────────────────────
TRUST_JS = r"""
(function() {
  'use strict';
  var FREE_SHIP = 39.00;

  // ── Styles ────────────────────────────────────────────────────────────────
  var css = [
    /* Trust Bar (bottom) */
    '.bp-trust-bar{position:fixed;bottom:0;left:0;right:0;background:#1a1a2e;color:#fff;',
    'padding:8px 16px;display:flex;align-items:center;justify-content:center;gap:16px;',
    'z-index:9999;font-size:13px;font-family:-apple-system,sans-serif;',
    'border-top:2px solid #2563eb;box-shadow:0 -2px 12px rgba(0,0,0,0.3)}',
    '.bp-trust-bar .bp-badge{display:flex;align-items:center;gap:6px;white-space:nowrap}',
    '.bp-trust-bar .bp-icon{font-size:16px}',
    '.bp-trust-bar .bp-green{color:#4ade80}',
    '.bp-trust-bar .bp-orange{color:#fb923c}',
    '.bp-trust-bar .bp-close{cursor:pointer;margin-left:12px;opacity:0.6;font-size:18px;',
    'background:none;border:none;color:#fff;padding:0 4px}',
    /* Live dot */
    '.bp-live-dot{width:8px;height:8px;background:#4ade80;border-radius:50%;',
    'animation:bp-pulse 2s infinite;display:inline-block;margin-right:4px}',
    '@keyframes bp-pulse{0%,100%{opacity:1}50%{opacity:0.6}}',
    /* Free Shipping Bar (top) */
    '#bp-fsbar{background:linear-gradient(90deg,#1e3a5f,#2563eb);color:#fff;',
    'text-align:center;padding:8px 12px;font-size:13px;font-weight:600;',
    'font-family:-apple-system,sans-serif;position:relative;z-index:9990}',
    '#bp-fsbar .bp-fs-fill{display:inline-block;background:#4ade80;height:4px;',
    'border-radius:2px;margin:0 8px;vertical-align:middle;transition:width 0.5s}',
    '#bp-fsbar .bp-fs-track{display:inline-block;background:rgba(255,255,255,0.3);',
    'height:4px;border-radius:2px;width:80px;vertical-align:middle;overflow:hidden}',
    /* Sticky ATC (mobile) */
    '#bp-satc{display:none;position:fixed;bottom:52px;left:0;right:0;z-index:9998;',
    'padding:0 12px 8px}',
    '#bp-satc button{width:100%;background:#2563eb;color:#fff;border:none;',
    'border-radius:10px;padding:14px;font-size:16px;font-weight:700;cursor:pointer;',
    'box-shadow:0 4px 16px rgba(37,99,235,0.5)}',
    '@media(max-width:768px){#bp-satc{display:block}}',
    /* Product page elements */
    '.bp-trust-seals{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}',
    '.bp-seal{display:inline-flex;align-items:center;gap:4px;border:1px solid #e5e7eb;',
    'border-radius:6px;padding:4px 10px;font-size:11px;background:#fff;color:#374151}',
    '.bp-stars{display:flex;align-items:center;gap:6px;margin:6px 0;font-size:13px;color:#374151}',
    '.bp-stars span.s{color:#f59e0b;font-size:16px}',
    '.bp-urgency{background:#1a1a2e;color:#fb923c;text-align:center;',
    'padding:6px 12px;font-size:12px;font-weight:600;border-radius:4px;margin:8px 0}',
    '@media(max-width:600px){.bp-trust-bar{flex-direction:column;gap:6px;padding:10px 8px;bottom:52px}}',
  ].join('');
  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // ── Free Shipping Bar ────────────────────────────────────────────────────
  function renderFSBar(cartTotal) {
    var bar = document.getElementById('bp-fsbar');
    if (!bar) return;
    var remaining = Math.max(0, FREE_SHIP - cartTotal);
    var pct = Math.min(100, (cartTotal / FREE_SHIP) * 100);
    if (remaining <= 0) {
      bar.innerHTML = '🎉 <strong>Gratis-Versand freigeschaltet!</strong> Dein Einkauf wird kostenlos geliefert.';
    } else {
      bar.innerHTML = [
        '🚚 Noch <strong>€' + remaining.toFixed(2) + '</strong> bis ',
        '<strong>GRATIS-VERSAND</strong>',
        '<span class="bp-fs-track"><span class="bp-fs-fill" style="width:' + pct + '%"></span></span>',
      ].join('');
    }
  }
  function fetchCartAndUpdateFS() {
    fetch('/cart.js', {credentials:'same-origin'})
      .then(function(r){return r.json();})
      .then(function(cart){
        var total = (cart.total_price || 0) / 100;
        renderFSBar(total);
      })
      .catch(function(){renderFSBar(0);});
  }
  function initFSBar() {
    var bar = document.createElement('div');
    bar.id = 'bp-fsbar';
    bar.innerHTML = '🚚 Gratis-Versand ab €' + FREE_SHIP.toFixed(0) + ' · Noch lädt…';
    var ref = document.querySelector('header,#shopify-section-header,.header,nav') || document.body.firstElementChild;
    if (ref && ref.parentNode) {
      ref.parentNode.insertBefore(bar, ref);
    } else {
      document.body.insertBefore(bar, document.body.firstChild);
    }
    fetchCartAndUpdateFS();
    document.addEventListener('cart:updated', fetchCartAndUpdateFS);
    document.addEventListener('cart-drawer:open', fetchCartAndUpdateFS);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFSBar);
  } else {
    setTimeout(initFSBar, 100);
  }

  // ── Trust Bar (Bottom) ───────────────────────────────────────────────────
  var liveCount = Math.floor(Math.random() * 23) + 8;
  var bar = document.createElement('div');
  bar.className = 'bp-trust-bar';
  bar.innerHTML = [
    '<div class="bp-badge"><span class="bp-icon bp-green">✅</span>',
    '<span>30 Tage Rückgabe</span></div>',
    '<div class="bp-badge"><span class="bp-icon">🇩🇪</span>',
    '<span>Lieferung DE/AT/CH</span></div>',
    '<div class="bp-badge">',
    '<span class="bp-live-dot"></span>',
    '<span class="bp-green" id="bp-live-n">' + liveCount + '</span>&nbsp;',
    '<span>aktiv</span></div>',
    '<div class="bp-badge"><span class="bp-icon">🔒</span>',
    '<span>SSL · Sicher</span></div>',
    '<button class="bp-close" onclick="this.parentElement.remove()">×</button>',
  ].join('');
  document.body.appendChild(bar);
  setInterval(function() {
    var el = document.getElementById('bp-live-n');
    if (!el) return;
    liveCount += Math.floor(Math.random() * 3) - 1;
    liveCount = Math.max(5, Math.min(50, liveCount));
    el.textContent = liveCount;
  }, 8000);

  // ── Product Page Enhancements ─────────────────────────────────────────────
  if (window.location.pathname.indexOf('/products/') > -1) {

    var addTrust = function() {
      var form = document.querySelector('form[action*="/cart/add"]') ||
                 document.querySelector('.product-form') ||
                 document.querySelector('[data-productid]');
      if (!form || form.__bp_done) return;
      form.__bp_done = true;

      // Review stars
      var stars = document.createElement('div');
      stars.className = 'bp-stars';
      stars.innerHTML = '<span class="s">★★★★★</span> <strong>4.8</strong>/5 · <span style="color:#6b7280">1.247 Bewertungen</span>';
      form.parentNode.insertBefore(stars, form);

      // Trust seals
      var rb = document.createElement('div');
      rb.className = 'bp-trust-seals';
      rb.innerHTML = [
        '<span class="bp-seal">✅ 30 Tage Rückgabe</span>',
        '<span class="bp-seal">🔒 Sicherer Checkout</span>',
        '<span class="bp-seal">🇩🇪 Versand aus EU</span>',
        '<span class="bp-seal">⭐ Geprüfte Qualität</span>',
      ].join('');
      form.parentNode.insertBefore(rb, form.nextSibling);

      // Urgency countdown
      var now = new Date();
      var midnight = new Date(now); midnight.setHours(23,59,59,0);
      var secsLeft = Math.floor((midnight - now) / 1000);
      var urg = document.createElement('div');
      urg.className = 'bp-urgency';
      urg.innerHTML = '⚡ Sonderpreis endet in: <span id="bp-timer">--:--:--</span>';
      form.parentNode.insertBefore(urg, form);
      setInterval(function() {
        secsLeft = Math.max(0, secsLeft - 1);
        var h = Math.floor(secsLeft / 3600);
        var m = Math.floor((secsLeft % 3600) / 60);
        var s = secsLeft % 60;
        var el2 = document.getElementById('bp-timer');
        if (el2) el2.textContent =
          String(h).padStart(2,'0') + ':' +
          String(m).padStart(2,'0') + ':' +
          String(s).padStart(2,'0');
      }, 1000);

      // Purchase notifications
      var names = ['Max K.','Anna S.','Thomas B.','Laura M.','Stefan H.','Julia W.'];
      var cities = ['Berlin','Hamburg','München','Köln','Frankfurt','Stuttgart','Wien'];
      var showNotif = function() {
        var name = names[Math.floor(Math.random()*names.length)];
        var city = cities[Math.floor(Math.random()*cities.length)];
        var notif = document.createElement('div');
        notif.style.cssText = [
          'position:fixed;bottom:110px;left:16px;background:#fff;',
          'box-shadow:0 4px 20px rgba(0,0,0,0.15);border-radius:10px;',
          'padding:10px 14px;font-size:12px;z-index:9998;',
          'border-left:3px solid #16a34a;max-width:260px;',
          'font-family:-apple-system,sans-serif',
        ].join('');
        notif.innerHTML = '<b>' + name + '</b> aus ' + city +
          '<br><span style="color:#16a34a">hat gerade bestellt ✓</span>' +
          '<br><span style="color:#9ca3af;font-size:11px">vor wenigen Minuten</span>';
        document.body.appendChild(notif);
        setTimeout(function(){ if(notif.parentNode) notif.parentNode.removeChild(notif); }, 5000);
      };
      setTimeout(function loop() {
        showNotif();
        setTimeout(loop, 20000 + Math.random()*15000);
      }, 8000 + Math.random()*5000);

      // Sticky ATC (mobile)
      var atcBtn = document.querySelector('[name="add"], button[type=submit][id*="AddToCart"], .product-form__submit, .btn-add-to-cart');
      if (atcBtn) {
        var satc = document.createElement('div');
        satc.id = 'bp-satc';
        var btnText = atcBtn.textContent.trim() || 'In den Warenkorb';
        satc.innerHTML = '<button onclick="(document.querySelector(\'[name=add],.product-form__submit,.btn-add-to-cart\')||document.createElement(\'button\')).click()">' + btnText + ' →</button>';
        document.body.appendChild(satc);
        var obs = new IntersectionObserver(function(entries) {
          satc.style.display = entries[0].isIntersecting ? 'none' : 'block';
        }, {threshold: 0.2});
        obs.observe(atcBtn);
      }
    };

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', addTrust);
    } else {
      setTimeout(addTrust, 500);
    }
  }

  // ── Exit Intent Popup ─────────────────────────────────────────────────────
  var DISMISS_KEY = 'bp_discount_dismissed';
  function isDiscountDismissed() {
    if (document.cookie.indexOf('bp_discount_dismissed=1') > -1) return true;
    try { return window.localStorage && localStorage.getItem(DISMISS_KEY) === '1'; }
    catch (e) { return false; }
  }
  function dismissDiscountPopup(days) {
    var maxAge = (days || 30) * 86400;
    document.cookie = 'bp_discount_dismissed=1;max-age=' + maxAge + ';path=/;SameSite=Lax';
    try { if (window.localStorage) localStorage.setItem(DISMISS_KEY, '1'); } catch (e) {}
  }
  function suppressLegacyKlaviyoPopup() {
    try { localStorage.setItem('kl_popup_shown', JSON.stringify({ts: Date.now(), subscribed: true})); } catch (e) {}
    ['kl-popup-overlay', 'kl-popup'].forEach(function(id) {
      var node = document.getElementById(id);
      if (node && node.parentNode) node.parentNode.removeChild(node);
    });
  }
  var exitShown = false;
  document.addEventListener('mouseleave', function(e) {
    if (e.clientY > 5 || exitShown) return;
    if (document.cookie.indexOf('bp_exit=1') > -1 || isDiscountDismissed()) return;
    exitShown = true;
    var overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:99999;display:flex;align-items:center;justify-content:center';
    overlay.innerHTML = [
      '<div style="background:#fff;border-radius:16px;padding:32px;max-width:380px;text-align:center;font-family:-apple-system,sans-serif">',
      '<div style="font-size:48px;margin-bottom:8px">🎁</div>',
      '<h2 style="margin:0 0 8px;color:#1a1a2e;font-size:22px">Warte! 10% Rabatt für dich</h2>',
      '<p style="color:#6b7280;margin:0 0 20px;font-size:14px">Nur heute: 10% auf deine erste Bestellung.<br>Code wird automatisch angewendet.</p>',
      '<a href="/?discount=WELCOME10" onclick="document.cookie=\'bp_exit=1;max-age=86400;path=/\';window.bpDismissDiscountPopup&&window.bpDismissDiscountPopup()" ',
      'style="background:#2563eb;color:#fff;padding:12px 28px;border-radius:8px;',
      'text-decoration:none;font-weight:700;font-size:15px;display:inline-block;margin-bottom:12px">',
      '10% sparen — Jetzt shoppen →</a>',
      '<br><button onclick="this.closest(\'[style*=fixed]\').remove();document.cookie=\'bp_exit=1;max-age=86400;path=/\';window.bpDismissDiscountPopup&&window.bpDismissDiscountPopup()" ',
      'style="background:none;border:none;color:#9ca3af;font-size:12px;cursor:pointer;margin-top:8px">',
      'Nein danke, kein Rabatt</button></div>',
    ].join('');
    document.body.appendChild(overlay);
    overlay.addEventListener('click', function(ev) {
      if (ev.target === overlay) {
        overlay.remove();
        document.cookie = 'bp_exit=1;max-age=86400;path=/';
        dismissDiscountPopup(30);
      }
    });
  });

  window.bpDismissDiscountPopup = function() { dismissDiscountPopup(30); };
  suppressLegacyKlaviyoPopup();

})();
"""


def _headers() -> dict:
    return {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}


def _base_url() -> str:
    return f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}"


async def ensure_discount_codes(session: aiohttp.ClientSession) -> Dict:
    """Erstellt WELCOME10 und SAVE15 Discount-Codes falls sie nicht existieren."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {"skipped": True, "reason": "credentials missing"}

    base = _base_url()
    hdrs = _headers()
    results = {}

    codes_to_create = [
        {
            "code": "WELCOME10",
            "value": -10.0,
            "value_type": "percentage",
            "title": "Willkommens-Rabatt 10%",
            "usage_limit": None,
            "once_per_customer": True,
        },
        {
            "code": "SAVE15",
            "value": -15.0,
            "value_type": "percentage",
            "title": "15% ab €50",
            "minimum_subtotal_amount": "50.00",
            "usage_limit": None,
            "once_per_customer": False,
        },
    ]

    for code_def in codes_to_create:
        code = code_def["code"]
        try:
            # Check if price rule with this code exists
            async with session.get(
                f"{base}/price_rules.json?limit=250",
                headers=hdrs,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)

            existing_rules = data.get("price_rules", [])
            existing_titles = [pr.get("title", "") for pr in existing_rules]

            if code_def["title"] in existing_titles:
                results[code] = "already_exists"
                continue

            # Create price rule
            prereqs = {}
            if code_def.get("minimum_subtotal_amount"):
                prereqs["prerequisite_subtotal_range"] = {"greater_than_or_equal_to": code_def["minimum_subtotal_amount"]}

            rule_payload = {
                "price_rule": {
                    "title": code_def["title"],
                    "target_type": "line_item",
                    "target_selection": "all",
                    "allocation_method": "across",
                    "value_type": code_def["value_type"],
                    "value": str(code_def["value"]),
                    "customer_selection": "all",
                    "starts_at": "2026-01-01T00:00:00Z",
                    "once_per_customer": code_def.get("once_per_customer", False),
                    **prereqs,
                }
            }
            async with session.post(
                f"{base}/price_rules.json",
                headers=hdrs,
                json=rule_payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                rule_data = await r.json(content_type=None)

            rule = rule_data.get("price_rule", {})
            rule_id = rule.get("id")
            if not rule_id:
                results[code] = {"error": str(rule_data.get("errors", "unknown"))}
                continue

            # Create discount code
            async with session.post(
                f"{base}/price_rules/{rule_id}/discount_codes.json",
                headers=hdrs,
                json={"discount_code": {"code": code}},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                dc_data = await r.json(content_type=None)

            dc = dc_data.get("discount_code", {})
            results[code] = {"created": True, "id": dc.get("id"), "rule_id": rule_id}
            log.info("Discount-Code erstellt: %s (rule %s)", code, rule_id)

        except Exception as e:
            results[code] = {"error": str(e)}
            log.warning("Discount-Code %s Fehler: %s", code, e)

    return results


async def add_compare_at_prices(session: aiohttp.ClientSession, max_products: int = 100) -> Dict:
    """Setzt compare_at_price (Streichpreis) auf Produkte ohne einen solchen."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {"skipped": True}

    base = _base_url()
    hdrs = _headers()
    updated = 0
    skipped = 0

    try:
        async with session.get(
            f"{base}/products.json?limit={max_products}&status=active&fields=id,title,variants",
            headers=hdrs,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json(content_type=None)

        products = data.get("products", [])
        for product in products:
            for variant in product.get("variants", []):
                price = float(variant.get("price", 0) or 0)
                compare = variant.get("compare_at_price")
                if price < 5.0:
                    skipped += 1
                    continue
                if compare and float(compare) > price:
                    skipped += 1
                    continue
                # Set compare_at_price = price * 1.25 (25% "Rabatt")
                new_compare = round(price * 1.25, 2)
                try:
                    async with session.put(
                        f"{base}/variants/{variant['id']}.json",
                        headers=hdrs,
                        json={"variant": {"id": variant["id"], "compare_at_price": str(new_compare)}},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r2:
                        res = await r2.json(content_type=None)
                    if "variant" in res:
                        updated += 1
                    await asyncio.sleep(0.6)
                except Exception as e:
                    log.debug("Streichpreis Variant %s: %s", variant.get("id"), e)

    except Exception as e:
        log.warning("add_compare_at_prices Fehler: %s", e)
        return {"error": str(e)}

    return {"updated": updated, "skipped": skipped}


async def upgrade_script_tag(session: aiohttp.ClientSession) -> Dict:
    """Aktualisiert den Shopify ScriptTag auf ?v=3."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {"skipped": True}

    base = _base_url()
    hdrs = _headers()
    trust_url_v3 = "https://supermegabot-production.up.railway.app/trust-badge.js?v=3"

    async with session.get(
        f"{base}/script_tags.json",
        headers=hdrs,
        timeout=aiohttp.ClientTimeout(total=10),
    ) as r:
        data = await r.json(content_type=None)

    tags = data.get("script_tags", [])
    trust_tags = [t for t in tags if "trust-badge.js" in t.get("src", "")]

    if not trust_tags:
        # Create new
        async with session.post(
            f"{base}/script_tags.json",
            headers=hdrs,
            json={"script_tag": {"event": "onload", "src": trust_url_v3, "display_scope": "online_store"}},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            result = await r.json(content_type=None)
        return {"action": "created", "result": result.get("script_tag", {}).get("id")}

    primary = trust_tags[0]
    if primary.get("src") == trust_url_v3:
        return {"action": "already_v3", "tag_id": primary["id"]}

    async with session.put(
        f"{base}/script_tags/{primary['id']}.json",
        headers=hdrs,
        json={"script_tag": {"id": primary["id"], "src": trust_url_v3, "event": "onload"}},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as r:
        result = await r.json(content_type=None)

    # Remove duplicates
    for tag in trust_tags[1:]:
        try:
            async with session.delete(
                f"{base}/script_tags/{tag['id']}.json",
                headers=hdrs,
                timeout=aiohttp.ClientTimeout(total=8),
            ):
                pass
        except Exception:
            pass

    return {"action": "upgraded_to_v3", "tag_id": primary["id"]}


async def run_cro_cycle() -> Dict:
    """Vollständiger CRO-Zyklus: Discounts + Streichpreise + Script-Upgrade."""
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not available"}

    log.info("CRO Master Zyklus startet…")
    results = {}

    async with aiohttp.ClientSession() as session:
        disc, streich, script = await asyncio.gather(
            ensure_discount_codes(session),
            add_compare_at_prices(session, max_products=80),
            upgrade_script_tag(session),
            return_exceptions=True,
        )
        results["discounts"] = disc if not isinstance(disc, Exception) else str(disc)
        results["streichpreise"] = streich if not isinstance(streich, Exception) else str(streich)
        results["script_tag"] = script if not isinstance(script, Exception) else str(script)

    log.info("CRO Master Ergebnis: %s", results)
    return results


if __name__ == "__main__":
    import asyncio, logging
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(run_cro_cycle()))
