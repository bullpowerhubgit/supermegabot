"""
Amazon Associates Integration — bullpowerhub-21
Generiert Affiliate-Links, optional PAAPI v5 Produktsuche.
"""

import os
import hmac
import hashlib
import json
import logging
import asyncio
import aiohttp
from datetime import datetime, timezone
from urllib.parse import urlencode, quote

logger = logging.getLogger(__name__)

TRACKING_ID  = os.getenv('AMAZON_TRACKING_ID', 'bullpowerhub-21')
PAAPI_KEY    = os.getenv('AMAZON_PAAPI_KEY', '')
PAAPI_SECRET = os.getenv('AMAZON_PAAPI_SECRET', '')
PAAPI_HOST   = 'webservices.amazon.de'
PAAPI_REGION = 'eu-west-1'
BASE_URL     = 'https://www.amazon.de'


def build_affiliate_link(asin_or_keyword: str) -> str:
    """Einfacher Affiliate-Link für ASIN oder Suchbegriff."""
    clean = asin_or_keyword.strip()
    if len(clean) == 10 and clean.isalnum() and clean.isupper():
        return f'{BASE_URL}/dp/{clean}?tag={TRACKING_ID}'
    return f'{BASE_URL}/s?k={quote(clean)}&tag={TRACKING_ID}'


def _hmac(key: bytes, data: str) -> bytes:
    return hmac.new(key, data.encode('utf-8'), hashlib.sha256).digest()


async def search_products(keywords: str, category: str = 'All', count: int = 10) -> dict:
    """Produktsuche via PAAPI v5 (braucht KEY+SECRET nach 3 Verkäufen)."""
    if not PAAPI_KEY or not PAAPI_SECRET:
        logger.warning('AMAZON_PAAPI_KEY fehlt — Fallback auf Affiliate-Link')
        return {
            'error': 'PAAPI noch nicht verfügbar (3 qualifizierte Verkäufe nötig)',
            'fallback_link': build_affiliate_link(keywords),
            'tracking_id': TRACKING_ID,
        }

    payload = json.dumps({
        'Keywords': keywords,
        'Resources': [
            'Images.Primary.Medium',
            'ItemInfo.Title',
            'Offers.Listings.Price',
            'ItemInfo.Features',
        ],
        'SearchIndex': category,
        'ItemCount': min(count, 10),
        'PartnerTag': TRACKING_ID,
        'PartnerType': 'Associates',
        'Marketplace': 'www.amazon.de',
    })

    now = datetime.now(timezone.utc)
    amz_date = now.strftime('%Y%m%dT%H%M%SZ')
    date_stamp = now.strftime('%Y%m%d')
    target = 'com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems'

    headers_str = (
        f'content-encoding:amz-1.0\n'
        f'content-type:application/json; charset=UTF-8\n'
        f'host:{PAAPI_HOST}\n'
        f'x-amz-date:{amz_date}\n'
        f'x-amz-target:{target}'
    )
    signed_headers = 'content-encoding;content-type;host;x-amz-date;x-amz-target'
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()

    canonical = '\n'.join(['POST', '/paapi5/searchitems', '', headers_str, '', signed_headers, payload_hash])
    cred_scope = f'{date_stamp}/{PAAPI_REGION}/ProductAdvertisingAPI/aws4_request'
    str_to_sign = f'AWS4-HMAC-SHA256\n{amz_date}\n{cred_scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}'

    sig_key = _hmac(_hmac(_hmac(_hmac(f'AWS4{PAAPI_SECRET}'.encode(), date_stamp), PAAPI_REGION), 'ProductAdvertisingAPI'), 'aws4_request')
    sig = hmac.new(sig_key, str_to_sign.encode(), hashlib.sha256).hexdigest()

    auth = (f'AWS4-HMAC-SHA256 Credential={PAAPI_KEY}/{cred_scope}, '
            f'SignedHeaders={signed_headers}, Signature={sig}')

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f'https://{PAAPI_HOST}/paapi5/searchitems',
            data=payload,
            headers={
                'content-encoding': 'amz-1.0',
                'content-type': 'application/json; charset=UTF-8',
                'host': PAAPI_HOST,
                'x-amz-date': amz_date,
                'x-amz-target': target,
                'Authorization': auth,
            },
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            data = await resp.json(content_type=None)

    items = []
    for item in data.get('SearchResult', {}).get('Items', []):
        items.append({
            'asin':      item.get('ASIN'),
            'title':     item.get('ItemInfo', {}).get('Title', {}).get('DisplayValue'),
            'price':     item.get('Offers', {}).get('Listings', [{}])[0].get('Price', {}).get('DisplayAmount'),
            'image':     item.get('Images', {}).get('Primary', {}).get('Medium', {}).get('URL'),
            'affiliate': build_affiliate_link(item.get('ASIN', '')),
        })

    logger.info(f'Amazon Suche "{keywords}": {len(items)} Produkte')
    return {'total': len(items), 'keyword': keywords, 'items': items}


async def generate_product_links(keywords_list: list) -> list:
    """Für eine Liste von Keywords Affiliate-Links generieren."""
    results = []
    for kw in keywords_list:
        link = build_affiliate_link(kw)
        results.append({'keyword': kw, 'link': link, 'tag': TRACKING_ID})
        logger.info(f'Amazon Link: {link}')
    return results


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    async def main():
        print(f'=== Amazon Associates ({TRACKING_ID}) ===')
        # Test Links
        for term in ['Werkzeugset', 'B0CZ588F76', 'Laptop Stativ']:
            print(f'  {term}: {build_affiliate_link(term)}')

        # PAAPI Test (gibt Fallback-Link wenn noch kein Zugang)
        result = await search_products('Werkzeug')
        print(f'\nSuche: {json.dumps(result, indent=2, ensure_ascii=False)[:300]}')

    asyncio.run(main())
