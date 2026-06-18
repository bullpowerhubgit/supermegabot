"""
Telegram Master Dashboard — steuert alle 19 Railway-Services via Bot
Inline-Keyboard Menü, Polling, Shopify Aktionen, Revenue, SEO, Content
"""
import asyncio
import aiohttp
import logging
import os
import json
from datetime import datetime

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8600739487:AAGhByAoKEpbsfco9swoaRYjU2HI_gSt718')
CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID', '5088771245')
BASE_URL  = f'https://api.telegram.org/bot{BOT_TOKEN}'

# Alle 19 Railway-Services
SERVICES = {
    'supermegabot':      'https://dudirudibot-mega-production.up.railway.app/health',
    'shopify-acq':       'https://shopify-acquisition-engine-production.up.railway.app/health',
    'icomeauto':         'https://icomeauto-saas-production.up.railway.app/health',
    'seo-tools':         'https://seo-turbo-tools-production.up.railway.app/health',
    'tg-bot':            'https://telegram-automation-bot-production.up.railway.app/health',
    'creatorai':         'https://creatorai-ultra-production.up.railway.app/health',
    'digistore24':       'https://digistore24-automation-production.up.railway.app/api/health',
    'cognitive':         'https://cognitive-symphony-production.up.railway.app/health',
    'revenue-hub':       'https://revenue-hub-notifications-production.up.railway.app/health',
    'adposter':          'https://adposter-engine-production.up.railway.app/health',
    'steuercockpit':     'https://steuercockpit-production-44c9.up.railway.app/health',
    'shopify-automaton': 'https://shopify-automaton-suite-production-e405.up.railway.app/api/health',
    'meta-social':       'https://meta-social-engine-production.up.railway.app/health',
    'freelance-gig':     'https://freelance-gig-engine-production.up.railway.app/health',
    'visual-content':    'https://visual-content-engine-production.up.railway.app/health',
    'analytics-mkt':     'https://analytics-marketing-pro-production.up.railway.app/health',
    'shopify-ki':        'https://shopify-ki-suite-production.up.railway.app/health',
    'seo-traffic':       'https://seo-traffic-engine-production.up.railway.app/health',
    'social-traffic':    'https://social-traffic-engine-production.up.railway.app/health',
}

SERVICE_ACTIONS = {
    'shopify-automaton': {
        'base': 'https://shopify-automaton-suite-production-e405.up.railway.app',
        'actions': {
            'seo_audit':    ('GET',  '/api/shopify/seo-audit'),
            'seo_optimize': ('POST', '/api/shopify/seo-optimize'),
            'fix_images':   ('POST', '/api/shopify/fix-images'),
            'fix_text':     ('POST', '/api/shopify/fix-text'),
            'sitemap_ping': ('POST', '/api/shopify/sitemap-ping'),
            'traffic':      ('GET',  '/api/shopify/traffic-report'),
        }
    },
    'adposter': {
        'base': 'https://adposter-engine-production.up.railway.app',
        'actions': {
            'generate_ad': ('POST', '/api/generate'),
        }
    },
    'seo-traffic': {
        'base': 'https://seo-traffic-engine-production.up.railway.app',
        'actions': {
            'generate_article': ('POST', '/api/generate'),
        }
    },
}

SEO_ENGINE_URL = os.getenv('SEO_TRAFFIC_ENGINE_URL', 'https://seo-traffic-engine-production.up.railway.app')


# ── Telegram API helpers ──────────────────────────────────────────────────────

async def tg_api(method: str, data: dict) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(f'{BASE_URL}/{method}', json=data,
                          timeout=aiohttp.ClientTimeout(total=10)) as r:
            return await r.json()


async def send_message(chat_id: str, text: str, reply_markup=None, parse_mode='HTML'):
    payload = {'chat_id': chat_id, 'text': text[:4096], 'parse_mode': parse_mode}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return await tg_api('sendMessage', payload)


async def edit_message(chat_id, message_id, text: str, reply_markup=None):
    payload = {'chat_id': chat_id, 'message_id': message_id,
               'text': text[:4096], 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return await tg_api('editMessageText', payload)


async def answer_callback(callback_id: str, text=''):
    return await tg_api('answerCallbackQuery', {'callback_query_id': callback_id, 'text': text})


# ── Keyboards ────────────────────────────────────────────────────────────────

def main_menu_keyboard():
    return {'inline_keyboard': [
        [{'text': '📊 Dashboard',     'callback_data': 'dashboard'},
         {'text': '🛍️ Shopify',      'callback_data': 'shopify_menu'}],
        [{'text': '💰 Umsatz',        'callback_data': 'revenue'},
         {'text': '📝 Content',       'callback_data': 'content_menu'}],
        [{'text': '🔍 SEO',           'callback_data': 'seo_menu'},
         {'text': '🤖 Automation',    'callback_data': 'auto_menu'}],
        [{'text': '⚡ Alle Services', 'callback_data': 'all_services'},
         {'text': '🆘 Hilfe',         'callback_data': 'help'}],
    ]}


def shopify_keyboard():
    return {'inline_keyboard': [
        [{'text': '📋 SEO Audit',      'callback_data': 'action_shopify-automaton_seo_audit'},
         {'text': '✨ SEO Optimize',   'callback_data': 'action_shopify-automaton_seo_optimize'}],
        [{'text': '🖼️ Bilder fixen',  'callback_data': 'action_shopify-automaton_fix_images'},
         {'text': '✏️ Texte fixen',   'callback_data': 'action_shopify-automaton_fix_text'}],
        [{'text': '📡 Sitemap Ping',   'callback_data': 'action_shopify-automaton_sitemap_ping'},
         {'text': '📈 Traffic',        'callback_data': 'action_shopify-automaton_traffic'}],
        [{'text': '◀️ Zurück',         'callback_data': 'main_menu'}],
    ]}


def seo_keyboard():
    return {'inline_keyboard': [
        [{'text': '📄 Artikel generieren',    'callback_data': 'action_seo-traffic_generate_article'}],
        [{'text': '📊 SEO Audit (Shopify)',   'callback_data': 'action_shopify-automaton_seo_audit'}],
        [{'text': '◀️ Zurück',               'callback_data': 'main_menu'}],
    ]}


def auto_keyboard():
    return {'inline_keyboard': [
        [{'text': '🚀 Content Cycle starten', 'callback_data': 'trigger_content_cycle'}],
        [{'text': '💼 Freelance Cycle',        'callback_data': 'trigger_freelance_cycle'}],
        [{'text': '📣 Ad generieren',          'callback_data': 'action_adposter_generate_ad'}],
        [{'text': '◀️ Zurück',                'callback_data': 'main_menu'}],
    ]}


# ── Dashboard ────────────────────────────────────────────────────────────────

async def check_all_services() -> str:
    timeout = aiohttp.ClientTimeout(total=6)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async def check(name, url):
            try:
                async with s.get(url) as r:
                    data = await r.json(content_type=None)
                    st = data.get('status', 'ok' if r.status < 300 else 'err')
                    icon = '✅' if st in ('ok', 'healthy', 'running') else '⚠️'
                    return f'{icon} <code>{name:<16}</code>'
            except Exception:
                return f'❌ <code>{name:<16}</code>'
        results = await asyncio.gather(*[check(n, u) for n, u in SERVICES.items()])

    online = sum(1 for r in results if r.startswith('✅'))
    header = (f'🖥️ <b>System Dashboard</b>\n'
              f'<code>{datetime.now().strftime("%H:%M:%S")}</code> — {online}/{len(SERVICES)} online\n\n')
    cols = []
    for i in range(0, len(results), 2):
        row = results[i] + ('  ' + results[i + 1] if i + 1 < len(results) else '')
        cols.append(row)
    return header + '\n'.join(cols)


# ── Service actions ───────────────────────────────────────────────────────────

async def run_service_action(service: str, action: str) -> str:
    cfg = SERVICE_ACTIONS.get(service)
    if not cfg:
        return f'Keine Aktionen für {service} konfiguriert.'
    act = cfg['actions'].get(action)
    if not act:
        return f'Aktion {action} für {service} nicht gefunden.'
    method, path = act
    url = cfg['base'] + path
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            if method == 'GET':
                async with s.get(url) as r:
                    data = await r.json(content_type=None)
            else:
                async with s.post(url, json={}, headers={'Content-Type': 'application/json'}) as r:
                    data = await r.json(content_type=None)
        if action == 'seo_audit':
            return (f'🔍 <b>SEO Audit</b>\n'
                    f'📊 Score: <b>{data.get("seo_score", "?")} / 100</b>\n'
                    f'🛍️ Produkte: {data.get("total", "?")}\n'
                    f'⚠️ Probleme: {data.get("issues_count", "?")}')
        elif action == 'seo_optimize':
            return f'✨ <b>SEO Optimize</b>\n{data.get("optimized", 0)} Produkte optimiert'
        elif action == 'fix_images':
            return (f'🖼️ <b>Image Fix</b>\n'
                    f'{data.get("processed_products", 0)} Produkte gescannt\n'
                    f'{data.get("updated_images", 0)} Bilder aktualisiert')
        elif action == 'fix_text':
            return f'✏️ <b>Text Fix</b>\n{data.get("fixed", 0)} Produkttexte korrigiert'
        elif action == 'sitemap_ping':
            lines = [f"{p['engine']}: {p['status']}" for p in data.get('pings', [])]
            return '📡 <b>Sitemap Ping</b>\n' + '\n'.join(lines)
        elif action == 'traffic':
            return (f'📈 <b>Traffic Report</b>\n'
                    f'💶 Umsatz: €{data.get("total_revenue", "0")}\n'
                    f'📦 Bestellungen: {data.get("last_50_orders", 0)}')
        else:
            return f'✅ Ergebnis:\n{json.dumps(data, ensure_ascii=False)[:400]}'
    except Exception as e:
        return f'❌ Fehler bei {service}/{action}:\n{e}'


# ── Revenue ───────────────────────────────────────────────────────────────────

async def get_revenue_summary() -> str:
    stripe_key = os.getenv('STRIPE_SECRET_KEY', '')
    if not stripe_key:
        return '❌ STRIPE_SECRET_KEY nicht gesetzt'
    try:
        import stripe
        client = stripe.StripeClient(stripe_key)
        now = int(datetime.now().timestamp())
        day_start = now - (now % 86400)
        charges = client.charges.list(params={'created': {'gte': day_start}, 'limit': 100})
        total = sum(c.amount for c in charges.data if c.paid) / 100
        count = sum(1 for c in charges.data if c.paid)
        return (f'💰 <b>Heutiger Umsatz</b>\n'
                f'💶 <b>€{total:.2f}</b>\n'
                f'📦 {count} Zahlungen\n'
                f'🕐 Stand: {datetime.now().strftime("%H:%M")}')
    except Exception as e:
        return f'❌ Stripe Fehler: {e}'


# ── Dispatcher ────────────────────────────────────────────────────────────────

async def handle_update(update: dict):
    msg = update.get('message') or {}
    cb  = update.get('callback_query') or {}

    if msg:
        chat_id = str(msg.get('chat', {}).get('id', CHAT_ID))
        text = (msg.get('text') or '').strip()
        if text in ('/start', '/menu', '/hilfe', '/help'):
            await send_message(chat_id,
                '🤖 <b>SuperMegaBot Master Dashboard</b>\n\n'
                '19 Railway-Services auf einen Blick.\nWähle eine Kategorie:',
                reply_markup=main_menu_keyboard())
        elif text in ('/dashboard', '/status'):
            await send_message(chat_id, await check_all_services())
        elif text == '/revenue':
            await send_message(chat_id, await get_revenue_summary())
        elif text.startswith('/seo_push'):
            parts = text.split(None, 1)
            keyword = parts[1].strip() if len(parts) > 1 else 'shopify automation'
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                    async with s.post(f'{SEO_ENGINE_URL}/api/ingest',
                                      json={'keyword': keyword}) as r:
                        d = await r.json(content_type=None)
                await send_message(chat_id,
                    f'✅ SEO Push: <b>{keyword}</b>\n{json.dumps(d, ensure_ascii=False)[:200]}')
            except Exception as e:
                await send_message(chat_id, f'❌ SEO Push Fehler: {e}')
        elif text in ('/agent_status', '/alle_dienste'):
            await send_message(chat_id,
                '🤖 <b>Agenten-Status</b>\n\n'
                '• AdPoster: alle 6h\n'
                '• Revenue Hub: Stripe sofort\n'
                '• SEO Traffic: alle 6h\n'
                '• Social Traffic: alle 8h\n'
                '• Meta Social: alle 4h\n'
                '• Visual Content: alle 5h\n'
                '• Freelance: alle 12h\n'
                '• Content Hub: alle 6h\n\n'
                '⚠️ Facebook Token erneuern!\n'
                '⚠️ Discord Bot einladen!',
                reply_markup=main_menu_keyboard())

    elif cb:
        cb_id   = cb['id']
        chat_id = str(cb.get('message', {}).get('chat', {}).get('id', CHAT_ID))
        msg_id  = cb.get('message', {}).get('message_id')
        data    = cb.get('data', '')

        await answer_callback(cb_id)
        back = {'inline_keyboard': [[{'text': '◀️ Menü', 'callback_data': 'main_menu'}]]}

        if data == 'main_menu':
            await edit_message(chat_id, msg_id,
                '🤖 <b>SuperMegaBot Master Dashboard</b>\nWähle eine Kategorie:',
                reply_markup=main_menu_keyboard())

        elif data in ('dashboard', 'all_services'):
            status = await check_all_services()
            await edit_message(chat_id, msg_id, status, reply_markup={'inline_keyboard': [[
                {'text': '🔄 Refresh', 'callback_data': 'dashboard'},
                {'text': '◀️ Menü',   'callback_data': 'main_menu'},
            ]]})

        elif data == 'shopify_menu':
            await edit_message(chat_id, msg_id,
                '🛍️ <b>Shopify Automaton</b>\nWas soll ich tun?',
                reply_markup=shopify_keyboard())

        elif data == 'seo_menu':
            await edit_message(chat_id, msg_id, '🔍 <b>SEO Werkzeuge</b>',
                               reply_markup=seo_keyboard())

        elif data == 'auto_menu':
            await edit_message(chat_id, msg_id, '🤖 <b>Automation starten</b>',
                               reply_markup=auto_keyboard())

        elif data == 'revenue':
            rev = await get_revenue_summary()
            await edit_message(chat_id, msg_id, rev, reply_markup={'inline_keyboard': [[
                {'text': '🔄 Refresh', 'callback_data': 'revenue'},
                {'text': '◀️ Menü',   'callback_data': 'main_menu'},
            ]]})

        elif data == 'content_menu':
            await edit_message(chat_id, msg_id, '📝 <b>Content</b>', reply_markup={'inline_keyboard': [
                [{'text': '🚀 Content Cycle',  'callback_data': 'trigger_content_cycle'}],
                [{'text': '💼 Freelance Cycle', 'callback_data': 'trigger_freelance_cycle'}],
                [{'text': '◀️ Zurück',          'callback_data': 'main_menu'}],
            ]})

        elif data == 'help':
            await edit_message(chat_id, msg_id,
                '🆘 <b>Befehle</b>\n\n'
                '/start — Hauptmenü\n'
                '/dashboard — Alle Services Status\n'
                '/revenue — Heutiger Umsatz\n'
                '/status — Service Health\n'
                '/seo_push &lt;keyword&gt; — SEO Artikel\n'
                '/agent_status — Agenten-Info\n\n'
                '<b>Inline-Buttons:</b> Shopify, SEO, Automation, Content',
                reply_markup=back)

        elif data.startswith('action_'):
            parts = data.split('_', 2)
            if len(parts) == 3:
                _, service, action = parts
                await send_message(chat_id, f'⏳ <b>{action}</b> wird ausgeführt...')
                result = await run_service_action(service, action)
                await send_message(chat_id, result, reply_markup=back)

        elif data == 'trigger_content_cycle':
            try:
                from modules.content_hub import run_content_cycle
                await send_message(chat_id, '⏳ Content Cycle startet...')
                result = await run_content_cycle()
                await send_message(chat_id, f'✅ Content Cycle abgeschlossen!\n{result[:200]}')
            except Exception as e:
                await send_message(chat_id, f'❌ Fehler: {e}')

        elif data == 'trigger_freelance_cycle':
            try:
                from modules.content_hub import run_freelance_cycle
                await send_message(chat_id, '⏳ Freelance Cycle startet...')
                result = await run_freelance_cycle()
                await send_message(chat_id, f'✅ Freelance Cycle abgeschlossen!\n{result[:200]}')
            except Exception as e:
                await send_message(chat_id, f'❌ Fehler: {e}')


# ── Polling loop ──────────────────────────────────────────────────────────────

async def run_polling():
    """Long-polling loop — läuft parallel zum Scheduler."""
    offset = 0
    logger.info('Telegram Master Dashboard: Polling gestartet')
    try:
        await send_message(CHAT_ID,
            '🚀 <b>SuperMegaBot ist online!</b>\n'
            f'19 Services werden überwacht.\n'
            f'🕐 {datetime.now().strftime("%H:%M:%S")}\n\n'
            'Tippe /menu oder /start für das Dashboard.',
            reply_markup=main_menu_keyboard())
    except Exception as e:
        logger.error(f'Startup message failed: {e}')

    while True:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40)) as s:
                async with s.get(
                    f'{BASE_URL}/getUpdates',
                    params={'offset': offset, 'timeout': 30,
                            'allowed_updates': ['message', 'callback_query']}
                ) as r:
                    resp = await r.json()
            if resp.get('ok') and resp.get('result'):
                for update in resp['result']:
                    offset = update['update_id'] + 1
                    try:
                        await handle_update(update)
                    except Exception as e:
                        logger.error(f'Update handling error: {e}')
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f'Polling error: {e}')
            await asyncio.sleep(5)


async def send_startup_notification():
    """Einmalige Startup-Benachrichtigung (ohne Polling)."""
    try:
        await send_message(CHAT_ID,
            '🚀 <b>SuperMegaBot Dashboard gestartet!</b>\n'
            f'🕐 {datetime.now().strftime("%H:%M:%S")}\n'
            'Tippe /menu für das Dashboard.',
            reply_markup=main_menu_keyboard())
    except Exception as e:
        logger.error(f'send_startup_notification failed: {e}')


# ── Legacy command functions (kept for mega_orchestrator compatibility) ───────

async def cmd_dashboard(text: str = '', session_id: str = '') -> str:
    return await check_all_services()


async def cmd_alle_dienste(text: str = '', session_id: str = '') -> str:
    lines = ['🗺️ <b>ALLE DIENSTE</b>', '']
    for name, url in SERVICES.items():
        lines.append(f'• {name}: {url.rsplit("/health", 1)[0]}')
    return '\n'.join(lines)


async def cmd_revenue(text: str = '', session_id: str = '') -> str:
    return await get_revenue_summary()


async def cmd_seo_push(text: str = '', session_id: str = '') -> str:
    parts = text.strip().split(None, 1)
    keyword = parts[1].strip() if len(parts) > 1 else 'shopify automation'
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(f'{SEO_ENGINE_URL}/api/ingest',
                              json={'keyword': keyword}) as r:
                d = await r.json(content_type=None)
        return f'✅ SEO Push: {keyword}\n{json.dumps(d, ensure_ascii=False)[:200]}'
    except Exception as e:
        return f'❌ SEO Push Fehler: {e}'


async def cmd_agent_status(text: str = '', session_id: str = '') -> str:
    return (
        '🤖 <b>Agenten-Status</b>\n\n'
        '• AdPoster: KI-Ads alle 6h\n'
        '• Revenue Hub: Stripe sofort\n'
        '• SEO Traffic: Artikel alle 6h\n'
        '• Social Traffic: Reddit/LinkedIn alle 8h\n'
        '• Meta Social: Facebook + Instagram alle 4h\n'
        '• Visual Content: TikTok + Pinterest alle 5h\n'
        '• Freelance: Fiverr + Upwork alle 12h\n\n'
        '⚠️ Facebook Token abgelaufen — erneuern!'
    )


async def cmd_deploy_status(text: str = '', session_id: str = '') -> str:
    return await check_all_services()
