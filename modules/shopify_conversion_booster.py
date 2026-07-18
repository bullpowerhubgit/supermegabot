#!/usr/bin/env python3
"""
Shopify Conversion Booster
===========================
Injiziert automatisch Conversion-Elemente in den Shopify Store:
  - Trust-Badges (SSL, Returns, Versand)
  - Urgency-Banner ("Nur noch X verfügbar")
  - Social-Proof ("X Personen sehen das gerade")
  - Free-Shipping-Bar
  - Exit-Intent Discount Popup
  - Sticky ATC Button (mobil)
  - Discount Code via Shopify API

Run: python3 modules/shopify_conversion_booster.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from pathlib import Path
from typing import Dict, Optional

import aiohttp

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

log = logging.getLogger("ConversionBooster")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

def _admin_domain() -> str:
    domain = os.getenv("SHOPIFY_MYSHOPIFY_DOMAIN", "") or os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    if domain and ".myshopify.com" in domain:
        return domain
    store_url = os.getenv("SHOPIFY_STORE_URL", "")
    match = re.search(r"([\w-]+\.myshopify\.com)", store_url)
    return match.group(1) if match else domain


DOMAIN  = _admin_domain()
TOKEN   = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")
BASE    = f"https://{DOMAIN}/admin/api/{VERSION}"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}


# ── Shopify API Helper ────────────────────────────────────────────────────────

async def _get(session: aiohttp.ClientSession, path: str) -> Dict:
    async with session.get(f"{BASE}{path}", headers=HEADERS) as r:
        return await r.json()


async def _post(session: aiohttp.ClientSession, path: str, data: Dict) -> Dict:
    async with session.post(f"{BASE}{path}", headers=HEADERS, json=data) as r:
        return await r.json()


async def _put(session: aiohttp.ClientSession, path: str, data: Dict) -> Dict:
    async with session.put(f"{BASE}{path}", headers=HEADERS, json=data) as r:
        return await r.json()


# ── Discount Code erstellen ───────────────────────────────────────────────────

async def create_discount_codes(session: aiohttp.ClientSession) -> Dict:
    """Erstellt 3 Discount-Codes für verschiedene Conversion-Szenarien."""
    codes = [
        {"title": "WELCOME10", "value": "-10.0", "value_type": "percentage",
         "target_type": "line_item", "target_selection": "all",
         "allocation_method": "across", "customer_selection": "all",
         "starts_at": "2026-01-01T00:00:00Z", "usage_limit": 1000},
        {"title": "SAVE15", "value": "-15.0", "value_type": "percentage",
         "target_type": "line_item", "target_selection": "all",
         "allocation_method": "across", "customer_selection": "all",
         "starts_at": "2026-01-01T00:00:00Z", "usage_limit": 500},
        {"title": "RESCUE10", "value": "-10.0", "value_type": "percentage",
         "target_type": "line_item", "target_selection": "all",
         "allocation_method": "across", "customer_selection": "all",
         "starts_at": "2026-01-01T00:00:00Z", "usage_limit": 999},
    ]
    created = []
    for code_data in codes:
        try:
            r = await _post(session, "/price_rules.json",
                           {"price_rule": code_data})
            rule_id = r.get("price_rule", {}).get("id")
            if rule_id:
                dc = await _post(session, f"/price_rules/{rule_id}/discount_codes.json",
                                {"discount_code": {"code": code_data["title"]}})
                created.append(code_data["title"])
                log.info("Discount Code erstellt: %s", code_data["title"])
        except Exception as e:
            log.warning("Discount Code Fehler (%s): %s", code_data["title"], e)
    return {"created": created}


# ── Script Tag für Conversion-Elemente ───────────────────────────────────────

CONVERSION_SCRIPT = """
(function() {
  'use strict';

  // ─── Config ────────────────────────────────────────────────────────────────
  var CONFIG = {
    freeShippingThreshold: 49,
    currency: 'EUR',
    urgencyMin: 3,
    urgencyMax: 12,
    socialProofMin: 8,
    socialProofMax: 47,
    exitDiscount: 'WELCOME10',
    colors: {
      primary: '#2563eb',
      success: '#16a34a',
      urgent: '#dc2626',
      warning: '#d97706'
    }
  };

  // ─── Free Shipping Bar ──────────────────────────────────────────────────────
  function addFreeShippingBar() {
    if (document.getElementById('bp-shipping-bar')) return;
    var bar = document.createElement('div');
    bar.id = 'bp-shipping-bar';
    bar.style.cssText = [
      'background:' + CONFIG.colors.success,
      'color:#fff',
      'text-align:center',
      'padding:8px 16px',
      'font-size:13px',
      'font-weight:600',
      'position:sticky',
      'top:0',
      'z-index:9999',
      'letter-spacing:.02em'
    ].join(';');
    bar.innerHTML = '🚚 KOSTENLOSER VERSAND ab ' + CONFIG.freeShippingThreshold + ' ' + CONFIG.currency + ' &nbsp;|&nbsp; ✅ 30-Tage Rückgabe &nbsp;|&nbsp; 🔒 SSL-Gesichert';
    document.body.prepend(bar);
  }

  // ─── Trust Badges ──────────────────────────────────────────────────────────
  function addTrustBadges() {
    var forms = document.querySelectorAll('form[action*="/cart"], .product-form, [data-product-form]');
    forms.forEach(function(form) {
      if (form.querySelector('.bp-trust')) return;
      var badges = document.createElement('div');
      badges.className = 'bp-trust';
      badges.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;margin:12px 0;padding:10px 0;border-top:1px solid #e5e7eb;border-bottom:1px solid #e5e7eb';
      var items = [
        { icon: '🔒', text: 'SSL-Verschlüsselt' },
        { icon: '🔄', text: '30 Tage Rückgabe' },
        { icon: '🚚', text: 'Schneller Versand' },
        { icon: '⭐', text: '4.8/5 Bewertung' },
        { icon: '💳', text: 'Sichere Zahlung' }
      ];
      items.forEach(function(item) {
        var badge = document.createElement('div');
        badge.style.cssText = 'display:flex;align-items:center;gap:4px;font-size:11px;color:#374151;background:#f9fafb;border:1px solid #e5e7eb;border-radius:20px;padding:4px 10px';
        badge.innerHTML = '<span>' + item.icon + '</span><span>' + item.text + '</span>';
        badges.appendChild(badge);
      });
      form.appendChild(badges);
    });
  }

  // ─── Urgency Counter ────────────────────────────────────────────────────────
  function addUrgencyCounter() {
    var atcButtons = document.querySelectorAll('.product-form__submit, [name="add"], button[type="submit"]');
    atcButtons.forEach(function(btn) {
      if (btn.closest('.bp-urgency')) return;
      var count = Math.floor(Math.random() * (CONFIG.urgencyMax - CONFIG.urgencyMin + 1)) + CONFIG.urgencyMin;
      var urgency = document.createElement('div');
      urgency.className = 'bp-urgency';
      urgency.style.cssText = 'display:flex;align-items:center;gap:6px;margin:8px 0;font-size:12px;font-weight:600;color:' + CONFIG.colors.urgent;
      urgency.innerHTML = '<span style="animation:blink 1s infinite">🔴</span><span>Nur noch ' + count + ' auf Lager — jetzt sichern!</span>';
      btn.parentNode.insertBefore(urgency, btn);
    });
  }

  // ─── Social Proof Notification ──────────────────────────────────────────────
  function showSocialProof() {
    var existing = document.getElementById('bp-social-proof');
    if (existing) existing.remove();
    var cities = ['Berlin', 'Hamburg', 'München', 'Wien', 'Zürich', 'Frankfurt', 'Köln', 'Stuttgart'];
    var actions = ['sieht sich das gerade an', 'hat das gerade gekauft', 'hat es in den Warenkorb gelegt'];
    var count = Math.floor(Math.random() * (CONFIG.socialProofMax - CONFIG.socialProofMin + 1)) + CONFIG.socialProofMin;
    var city = cities[Math.floor(Math.random() * cities.length)];
    var action = actions[Math.floor(Math.random() * actions.length)];
    var popup = document.createElement('div');
    popup.id = 'bp-social-proof';
    popup.style.cssText = [
      'position:fixed',
      'bottom:20px',
      'left:20px',
      'background:#fff',
      'border:1px solid #e5e7eb',
      'border-radius:12px',
      'padding:12px 16px',
      'box-shadow:0 4px 20px rgba(0,0,0,.15)',
      'z-index:9998',
      'max-width:280px',
      'font-size:12px',
      'display:flex',
      'align-items:center',
      'gap:10px',
      'animation:slideIn .3s ease'
    ].join(';');
    popup.innerHTML = '<span style="font-size:24px">🛍️</span><div><strong>' + count + ' Personen</strong> aus ' + city + '<br><span style="color:#6b7280">' + action + '</span></div>';
    document.body.appendChild(popup);
    setTimeout(function() {
      if (popup.parentNode) popup.remove();
    }, 5000);
  }

  // ─── Exit Intent Popup ──────────────────────────────────────────────────────
  var DISMISS_KEY = 'bp_discount_dismissed';
  function isDiscountDismissed() {
    if (document.cookie.indexOf('bp_discount_dismissed=1') > -1) return true;
    try {
      return window.localStorage && localStorage.getItem(DISMISS_KEY) === '1';
    } catch (e) {
      return false;
    }
  }
  function dismissDiscountPopup(days) {
    var maxAge = (days || 30) * 86400;
    document.cookie = 'bp_discount_dismissed=1;max-age=' + maxAge + ';path=/;SameSite=Lax';
    try {
      if (window.localStorage) localStorage.setItem(DISMISS_KEY, '1');
    } catch (e) {}
  }
  function bindDiscountDismissWatchers() {
    document.addEventListener('click', function(e) {
      var target = e.target;
      if (!target || !target.closest) return;
      var closeTrigger = target.closest('[aria-label="Close"], [aria-label="close"], .klaviyo-close-form, .needsclick.klaviyo-close-form, button[data-testid="close-form-button"]');
      if (closeTrigger) dismissDiscountPopup(30);
    }, true);
    document.addEventListener('submit', function(e) {
      var form = e.target;
      if (!form || !form.matches) return;
      if (form.matches('form.klaviyo-form, form[action*="manage.kmail-lists.com"], form[action*="klaviyo"]')) {
        dismissDiscountPopup(30);
      }
    }, true);
  }
  function hideDismissedDiscountForms() {
    if (!isDiscountDismissed()) return;
    [
      '.klaviyo-form',
      '[class*="klaviyo-form"]',
      'form[action*="manage.kmail-lists.com"]'
    ].forEach(function(selector) {
      document.querySelectorAll(selector).forEach(function(node) {
        var popup = node.closest('[style*="position: fixed"], [class*="modal"], [class*="popup"]') || node;
        if (popup && popup.style) popup.style.display = 'none';
      });
    });
  }
  function suppressLegacyKlaviyoPopup() {
    try {
      localStorage.setItem('kl_popup_shown', JSON.stringify({ts: Date.now(), subscribed: true}));
    } catch (e) {}
    ['kl-popup-overlay', 'kl-popup'].forEach(function(id) {
      var node = document.getElementById(id);
      if (node && node.parentNode) node.parentNode.removeChild(node);
    });
    document.querySelectorAll(
      'script[src*="static.klaviyo.com/onsite/js/"], iframe[src*="klaviyo"], [class*="klaviyo"], [id*="klaviyo"], [data-testid*="klaviyo"]'
    ).forEach(function(node) {
      if (node && node.parentNode) node.parentNode.removeChild(node);
    });
    document.querySelectorAll('div, section, aside, form').forEach(function(node) {
      if (!node || !node.textContent) return;
      var text = node.textContent.toLowerCase();
      var looksLikePopup =
        text.includes('smarter einkaufen') ||
        text.includes('mehr sparen') ||
        text.includes('jetzt 10% sichern') ||
        text.includes('ich bezahle lieber vollen preis') ||
        text.includes('exklusives angebot');
      if (!looksLikePopup) return;
      var popup = node.closest('[style*="position: fixed"], [style*="position:fixed"], [class*="modal"], [class*="popup"], [role="dialog"]') || node;
      if (popup && popup.parentNode) popup.parentNode.removeChild(popup);
    });
  }
  function startLegacyKlaviyoPopupSuppression() {
    suppressLegacyKlaviyoPopup();
    var observer = new MutationObserver(function() {
      suppressLegacyKlaviyoPopup();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    setTimeout(function() { observer.disconnect(); }, 120000);
    window.addEventListener('pageshow', suppressLegacyKlaviyoPopup);
    window.addEventListener('load', suppressLegacyKlaviyoPopup);
    setInterval(suppressLegacyKlaviyoPopup, 1500);
  }
  var exitShown = isDiscountDismissed();
  function showExitIntent() {
    if (exitShown || isDiscountDismissed()) return;
    exitShown = true;
    var overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = '<div style="background:#fff;border-radius:16px;padding:32px;max-width:400px;text-align:center;position:relative">' +
      '<button onclick="window.bpDismissDiscountPopup && window.bpDismissDiscountPopup(); this.closest(\'div\').parentNode.remove()" style="position:absolute;top:12px;right:12px;background:none;border:none;font-size:20px;cursor:pointer;color:#9ca3af">✕</button>' +
      '<div style="font-size:40px;margin-bottom:12px">🎁</div>' +
      '<h2 style="font-size:20px;font-weight:800;margin-bottom:8px">Warte! Hier ist dein Geschenk</h2>' +
      '<p style="color:#6b7280;margin-bottom:16px">Erhalte <strong style="color:#dc2626">10% Rabatt</strong> auf deine erste Bestellung</p>' +
      '<div style="background:#f3f4f6;border-radius:8px;padding:12px;font-size:18px;font-weight:900;letter-spacing:.1em;margin-bottom:16px">' + CONFIG.exitDiscount + '</div>' +
      '<button onclick="navigator.clipboard && navigator.clipboard.writeText(\'' + CONFIG.exitDiscount + '\'); window.bpDismissDiscountPopup && window.bpDismissDiscountPopup(); this.textContent=\'✓ Kopiert!\'" style="background:#2563eb;color:#fff;border:none;border-radius:8px;padding:12px 24px;font-size:14px;font-weight:700;cursor:pointer;width:100%">Code kopieren</button>' +
      '<p style="font-size:11px;color:#9ca3af;margin-top:12px">Gilt für alle Produkte · 30-Tage Rückgabe</p>' +
      '</div>';
    document.body.appendChild(overlay);
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) {
        dismissDiscountPopup(30);
        overlay.remove();
      }
    });
  }

  // ─── Sticky Add-to-Cart (Mobile) ───────────────────────────────────────────
  function addStickyATC() {
    if (window.innerWidth > 768) return;
    if (document.getElementById('bp-sticky-atc')) return;
    var productTitle = document.querySelector('h1, .product__title, [data-product-title]');
    if (!productTitle) return;
    var sticky = document.createElement('div');
    sticky.id = 'bp-sticky-atc';
    sticky.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #e5e7eb;padding:12px 16px;z-index:9997;display:flex;gap:10px;align-items:center;box-shadow:0 -4px 12px rgba(0,0,0,.1)';
    sticky.innerHTML = '<div style="flex:1;font-size:12px;font-weight:600;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">' + (productTitle.textContent.trim().substring(0, 40)) + '</div>' +
      '<button onclick="document.querySelector(\'[name=add], .product-form__submit, button[type=submit]\').click()" style="background:#2563eb;color:#fff;border:none;border-radius:8px;padding:10px 20px;font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap">In den Warenkorb</button>';
    document.body.appendChild(sticky);
  }

  // ─── CSS Animations ─────────────────────────────────────────────────────────
  var style = document.createElement('style');
  style.textContent = '@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}@keyframes slideIn{from{transform:translateX(-100%);opacity:0}to{transform:translateX(0);opacity:1}}';
  document.head.appendChild(style);

  // ─── Init ────────────────────────────────────────────────────────────────────
  function init() {
    window.bpDismissDiscountPopup = function() { dismissDiscountPopup(30); };
    bindDiscountDismissWatchers();
    hideDismissedDiscountForms();
    startLegacyKlaviyoPopupSuppression();
    addFreeShippingBar();
    addTrustBadges();
    addUrgencyCounter();
    addStickyATC();

    // Social Proof alle 8 Sekunden
    setTimeout(showSocialProof, 4000);
    setInterval(showSocialProof, 12000);

    // Exit Intent
    document.addEventListener('mouseleave', function(e) {
      if (e.clientY < 10) showExitIntent();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""


async def inject_conversion_script(session: aiohttp.ClientSession) -> Dict:
    """Injiziert das Conversion-Script via Shopify ScriptTag API."""
    # Bestehende bp-Scripte entfernen
    existing = await _get(session, "/script_tags.json")
    for st in existing.get("script_tags", []):
        src = st.get("src", "")
        if "bp-conversion" in src or "conversion_booster" in src:
            async with session.delete(f"{BASE}/script_tags/{st['id']}.json", headers=HEADERS):
                pass

    # Neues Script via data-URL (Shopify erlaubt keine inline-Scripts)
    # Stattdessen: Theme-Asset hochladen + ScriptTag auf Asset-URL
    return await inject_via_theme_asset(session)


async def inject_via_theme_asset(session: aiohttp.ClientSession) -> Dict:
    """Upload Script als Theme-Asset und registriere ScriptTag."""
    import base64

    # Aktives Theme holen
    themes = await _get(session, "/themes.json")
    active_theme = next((t for t in themes.get("themes", []) if t.get("role") == "main"), None)
    if not active_theme:
        return {"error": "Kein aktives Theme gefunden"}

    theme_id = active_theme["id"]
    theme_name = active_theme.get("name", "?")

    # Script als Asset hochladen
    encoded = base64.b64encode(CONVERSION_SCRIPT.encode()).decode()
    asset_data = {
        "asset": {
            "key": "assets/bp-conversion-booster.js",
            "attachment": encoded,
        }
    }
    put_r = await _put(session, f"/themes/{theme_id}/assets.json", asset_data)

    if "asset" not in put_r:
        return {"error": f"Asset Upload fehlgeschlagen: {put_r}"}

    asset_url = put_r["asset"].get("public_url", "")
    log.info("Asset hochgeladen: %s", asset_url)

    # Prüfe ob ScriptTag schon existiert
    existing = await _get(session, "/script_tags.json?limit=250")
    for st in existing.get("script_tags", []):
        if "bp-conversion-booster" in st.get("src", ""):
            tag_id = st["id"]
            if st.get("src") != asset_url:
                tag_r = await _put(session, f"/script_tags/{tag_id}.json", {
                    "script_tag": {
                        "id": tag_id,
                        "src": asset_url,
                        "event": "onload",
                        "display_scope": "online_store",
                    }
                })
                log.info("ScriptTag aktualisiert: ID %s", tag_id)
                return {"ok": True, "action": "updated", "theme": theme_name, "tag_id": tag_id, "src": asset_url, "result": tag_r}
            log.info("ScriptTag bereits vorhanden — aktuell")
            return {"ok": True, "action": "already_exists", "theme": theme_name, "tag_id": tag_id, "src": asset_url}

    # ScriptTag registrieren
    tag_r = await _post(session, "/script_tags.json", {
        "script_tag": {
            "event": "onload",
            "src": asset_url,
            "display_scope": "online_store",
        }
    })

    if "script_tag" in tag_r:
        tag_id = tag_r["script_tag"]["id"]
        log.info("ScriptTag registriert: ID %s", tag_id)
        return {
            "ok": True,
            "action": "injected",
            "theme": theme_name,
            "tag_id": tag_id,
            "asset_url": asset_url,
            "features": ["free_shipping_bar", "trust_badges", "urgency_counter",
                         "social_proof", "exit_intent_popup", "sticky_atc_mobile"]
        }
    else:
        return {"error": f"ScriptTag Fehler: {tag_r}"}


# ── Abandoned Cart Discount hinzufügen ────────────────────────────────────────

async def ensure_rescue_discount(session: aiohttp.ClientSession) -> Dict:
    """Stellt sicher dass RESCUE10 Discount-Code existiert."""
    existing = await _get(session, "/price_rules.json?title=RESCUE10")
    if existing.get("price_rules"):
        return {"ok": True, "existing": True, "code": "RESCUE10"}

    r = await _post(session, "/price_rules.json", {
        "price_rule": {
            "title": "RESCUE10",
            "value_type": "percentage",
            "value": "-10.0",
            "target_type": "line_item",
            "target_selection": "all",
            "allocation_method": "across",
            "customer_selection": "all",
            "starts_at": "2026-01-01T00:00:00Z",
            "usage_limit": 9999,
        }
    })
    rule_id = r.get("price_rule", {}).get("id")
    if rule_id:
        dc = await _post(session, f"/price_rules/{rule_id}/discount_codes.json",
                        {"discount_code": {"code": "RESCUE10"}})
        return {"ok": True, "created": True, "code": "RESCUE10", "rule_id": rule_id}
    return {"error": str(r)}


# ── Main Runner ────────────────────────────────────────────────────────────────

async def run_conversion_boost() -> Dict:
    if not DOMAIN or not TOKEN:
        return {"error": "SHOPIFY_SHOP_DOMAIN oder SHOPIFY_ADMIN_API_TOKEN fehlt"}

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        results = {}

        # 1. Conversion Script injizieren
        log.info("Injiziere Conversion Script...")
        results["script"] = await inject_via_theme_asset(session)

        # 2. Discount Codes sicherstellen
        log.info("Discount Codes prüfen...")
        results["rescue_discount"] = await ensure_rescue_discount(session)

        log.info("Conversion Boost fertig: %s", results)
        return results


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    r = asyncio.run(run_conversion_boost())
    print(json.dumps(r, indent=2, ensure_ascii=False))
