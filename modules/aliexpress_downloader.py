"""
AliExpress Product Downloader — Python
Nutzt ae_sdk-kompatible Signierung (HMAC-SHA256) direkt gegen die AliExpress TOP API.
Lädt Produkte herunter und importiert sie optional in Shopify.
"""

import os
import time
import hmac
import hashlib
import json
import logging
import asyncio
import aiohttp
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

APP_KEY    = os.getenv('ALIEXPRESS_APP_KEY', '537346')
APP_SECRET = os.getenv('ALIEXPRESS_APP_SECRET', 'cnTeBUGhazNSsBVwLBiXqz3s8XTmT1hI')
ACCESS_TOKEN = os.getenv('ALIEXPRESS_ACCESS_TOKEN', '')
API_BASE   = os.getenv('ALIEXPRESS_API_ENDPOINT', 'https://api-sg.aliexpress.com')


def _sign(params: dict, secret: str) -> str:
    sorted_keys = sorted(params.keys())
    sign_str = secret + ''.join(f'{k}{params[k]}' for k in sorted_keys) + secret
    return hmac.new(secret.encode(), sign_str.encode(), hashlib.sha256).hexdigest().upper()


def _build_params(method: str, extra: dict) -> dict:
    params = {
        'app_key':     APP_KEY,
        'timestamp':   str(int(time.time() * 1000)),
        'sign_method': 'sha256',
        'format':      'json',
        'v':           '2.0',
        'method':      method,
        **extra,
    }
    if ACCESS_TOKEN:
        params['session'] = ACCESS_TOKEN
    params['sign'] = _sign(params, APP_SECRET)
    return params


async def search_products(keywords: str = 'trending', page_size: int = 20,
                          category_ids: str = '', sort: str = 'SALE_PRICE_ASC') -> list:
    """Produkte über Affiliate API suchen."""
    extra = {
        'keywords':   keywords,
        'page_no':    '1',
        'page_size':  str(min(page_size, 50)),
        'sort':       sort,
        'fields':     'product_id,product_title,sale_price,original_price,'
                      'product_main_image_url,product_detail_url,discount,evaluate_rate',
    }
    if category_ids:
        extra['category_ids'] = category_ids

    params = _build_params('aliexpress.affiliate.product.query', extra)
    url = f'{API_BASE}/sync?{urlencode(params)}'

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json(content_type=None)

    result = (data
              .get('aliexpress_affiliate_product_query_response', {})
              .get('resp_result', {})
              .get('result', {}))
    raw = result.get('products', {})
    products = raw.get('product', []) if isinstance(raw, dict) else raw
    logger.info(f'AliExpress Suche "{keywords}": {len(products)} Produkte gefunden')
    return products


async def get_product_details(product_id: str) -> dict:
    """Produktdetails via Affiliate API."""
    params = _build_params('aliexpress.affiliate.product.detail.get', {
        'product_id': str(product_id),
        'fields':     'product_id,product_title,sale_price,original_price,'
                      'product_main_image_url,product_small_image_urls,product_detail_url,'
                      'discount,evaluate_rate,product_video_url,hot_product_commission_rate',
    })
    url = f'{API_BASE}/sync?{urlencode(params)}'
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json(content_type=None)
    return (data
            .get('aliexpress_affiliate_product_detail_get_response', {})
            .get('resp_result', {})
            .get('result', {}))


async def generate_affiliate_link(product_url: str, tracking_id: str = 'supermegabot') -> str:
    """Affiliate-Link für eine Produkt-URL generieren."""
    params = _build_params('aliexpress.affiliate.link.generate', {
        'promotion_link_type': '0',
        'source_values':       product_url,
        'tracking_id':         tracking_id,
    })
    url = f'{API_BASE}/sync?{urlencode(params)}'
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json(content_type=None)
    links = (data
             .get('aliexpress_affiliate_link_generate_response', {})
             .get('resp_result', {})
             .get('result', {})
             .get('promotion_links', {})
             .get('promotion_link', []))
    return links[0].get('promotion_link', product_url) if links else product_url


async def import_to_shopify(products: list, markup: float = 2.5,
                             shopify_domain: str = '', shopify_token: str = '',
                             anthropic_key: str = '') -> list:
    """AliExpress-Produkte mit KI-Texten in Shopify importieren."""
    if not shopify_domain:
        shopify_domain = os.getenv('SHOPIFY_SHOP_DOMAIN', '')
    if not shopify_token:
        shopify_token = os.getenv('SHOPIFY_ADMIN_API_TOKEN', '')
    if not anthropic_key:
        anthropic_key = os.getenv('ANTHROPIC_API_KEY', '')

    if not shopify_domain or not shopify_token:
        raise ValueError('SHOPIFY_SHOP_DOMAIN und SHOPIFY_ADMIN_API_TOKEN erforderlich')

    api_ver = os.getenv('SHOPIFY_API_VERSION', '2024-10')
    shop_base = f'https://{shopify_domain}/admin/api/{api_ver}'
    headers = {'X-Shopify-Access-Token': shopify_token, 'Content-Type': 'application/json'}
    imported = []

    async with aiohttp.ClientSession() as session:
        for p in products:
            raw_price = float(str(p.get('sale_price', '10')).replace('US $', '').strip() or '10')
            title = p.get('product_title', 'AliExpress Produkt')[:200]
            description = f'<p>{title}</p>'

            try:
                    from modules.ai_client import ai_complete
                    import re
                    ai_prompt = (
                        f'Shopify-Produkt auf Deutsch:\n"{title[:150]}"\n'
                        f'JSON: {{"title":"...(DE, max 70 Zeichen)","description":"...(HTML <p>+<ul>, 100-200 Wörter, keine AliExpress-Begriffe)"}}'
                    )
                    txt = await ai_complete(ai_prompt, max_tokens=400)
                    if txt:
                        m = re.search(r'\{[\s\S]+\}', txt)
                        if m:
                            parsed = json.loads(m.group())
                            if parsed.get('title'):
                                title = parsed['title']
                            if parsed.get('description'):
                                description = parsed['description']
            except Exception as e:
                    logger.warning(f'AI Fehler: {e}')

            sell_price = round(raw_price * markup, 2)
            product_data = {
                'title': title,
                'body_html': description,
                'vendor': 'AliExpress',
                'product_type': 'Import',
                'tags': 'aliexpress,dropshipping,import',
                'variants': [{'price': str(sell_price),
                              'compare_at_price': str(round(sell_price * 1.3, 2)),
                              'inventory_quantity': 100,
                              'inventory_management': 'shopify'}],
            }
            img = p.get('product_main_image_url', '')
            if img:
                product_data['images'] = [{'src': img}]

            try:
                async with session.post(
                    f'{shop_base}/products.json',
                    json={'product': product_data},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as r:
                    result = await r.json()
                    created = result.get('product', {})
                    imported.append({
                        'ok': bool(created.get('id')),
                        'id': created.get('id'),
                        'title': created.get('title', title),
                        'price': f'€{sell_price}',
                        'ali_id': p.get('product_id'),
                    })
            except Exception as e:
                imported.append({'ok': False, 'error': str(e), 'ali_id': p.get('product_id')})

    ok_count = sum(1 for i in imported if i['ok'])
    logger.info(f'AliExpress → Shopify: {ok_count}/{len(products)} importiert')
    return imported


async def run_auto_download(keywords: list = None, count: int = 10, markup: float = 2.5) -> dict:
    """Vollautomatischer Download + Shopify-Import."""
    if not keywords:
        keywords = ['home gadgets', 'phone accessories', 'fitness equipment']

    all_imported = []
    for kw in keywords:
        try:
            products = await search_products(kw, page_size=count)
            if products:
                results = await import_to_shopify(products[:count], markup=markup)
                all_imported.extend(results)
                logger.info(f'Keyword "{kw}": {len(results)} Produkte verarbeitet')
        except Exception as e:
            logger.error(f'Fehler bei Keyword "{kw}": {e}')

    ok = sum(1 for i in all_imported if i.get('ok'))

    # BrutusCore: neue AliExpress Produkte auf allen Kanälen promoten
    if ok > 0:
        try:
            from modules.brutus_core import fire as brutus_fire
            top = [p for p in all_imported if p.get('ok')][:2]
            for item in top:
                name = item.get('title', 'Trending Produkt')[:50]
                await brutus_fire(
                    title=f"🛒 Neu: {name}",
                    body=f"Gerade im Shop verfügbar: {name} — direkt aus dem Trend importiert.",
                    link="https://ineedit.com.co/collections/trending-now",
                    niche="dropshipping trending gadgets",
                    tags=["neu", "aliexpress", "trending", "dropshipping"]
                )
        except Exception:
            pass

    return {'total_tried': len(all_imported), 'imported': ok, 'products': all_imported}


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    async def main():
        print('=== AliExpress Produkte herunterladen ===')
        products = await search_products('home gadgets', page_size=5)
        print(f'{len(products)} Produkte gefunden:')
        for p in products[:3]:
            print(f'  - {p.get("product_title", "?")[:60]} | {p.get("sale_price", "?")}')

    asyncio.run(main())
