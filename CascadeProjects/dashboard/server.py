#!/usr/bin/env python3
"""
SuperMegaBot Dashboard Server
- Railway deployment ready
- Telegram webhook endpoints
- Auto-registration on startup
"""

import os
import sys
import json
import asyncio
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import aiohttp
from aiohttp import web
from dotenv import load_dotenv

# ── Configuration ────────────────────────────────────────────────────────────
PORT = int(os.getenv("PORT", 8080))
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()

# ── Telegram Handlers ─────────────────────────────────────────────────────────
async def handle_telegram_webhook(request: web.Request) -> web.Response:
    """Handle incoming Telegram webhook messages"""
    try:
        data = await request.json()
        log.info("📨 Telegram webhook received: %s", json.dumps(data, indent=2))
        
        # Extract message info
        if "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            user = message.get("from", {})
            
            log.info("💬 Message from %s (%s): %s", 
                    user.get("first_name", "Unknown"), 
                    chat_id, 
                    text)
            
            # Process message with Claude Haiku
            response_text = await process_with_claude(text, user)
            
            # Send response back to Telegram
            await send_telegram_message(chat_id, response_text)
            
        elif "edited_message" in data:
            message = data["edited_message"]
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            log.info("✏️ Edited message in chat %s: %s", chat_id, text)
        
        return web.json_response({"status": "ok"})
        
    except Exception as e:
        log.error("❌ Telegram webhook error: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def process_with_claude(text: str, user: Dict[str, Any]) -> str:
    """Process message with Claude Haiku AI"""
    try:
        # Get Claude API key
        claude_api_key = os.getenv("CLAUDE_API_KEY")
        if not claude_api_key:
            return "🤖 Claude API key not configured"
        
        # Prepare prompt with user context
        user_name = user.get("first_name", "User")
        prompt = f"""
You are a helpful AI assistant. User {user_name} sent: "{text}"

Respond concisely and helpfully in German or English based on the language used.
"""
        
        # Call Claude Haiku API
        async with aiohttp.ClientSession() as session:
            headers = {
                "x-api-key": claude_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            
            payload = {
                "model": "claude-3-haiku-20240307",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            }
            
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["content"][0]["text"]
                else:
                    log.error("Claude API error: %s", await response.text())
                    return "🤖 Sorry, I'm having trouble processing your message right now."
                    
    except Exception as e:
        log.error("Claude processing error: %s", e)
        return "🤖 Sorry, something went wrong while processing your message."


async def send_telegram_message(chat_id: int, text: str) -> None:
    """Send message back to Telegram chat"""
    try:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_2")
        if not bot_token:
            log.warning("No Telegram bot token configured")
            return
        
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            
            async with session.post(url, json=payload) as response:
                result = await response.json()
                if response.status == 200:
                    log.info("✅ Message sent successfully")
                else:
                    log.error("❌ Failed to send message: %s", result)
                    
    except Exception as e:
        log.error("Error sending Telegram message: %s", e)


# ── Additional API Endpoints ───────────────────────────────────────────────────
async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint"""
    return web.json_response({
        "status": "healthy",
        "service": "SuperMegaBot Dashboard",
        "version": "2.0.0"
    })


async def handle_status(request: web.Request) -> web.Response:
    """Status endpoint with service info"""
    return web.json_response({
        "telegram_webhook": "active" if os.getenv("TELEGRAM_BOT_TOKEN") else "inactive",
        "claude_api": "active" if os.getenv("CLAUDE_API_KEY") else "inactive",
        "railway_url": os.getenv("RAILWAY_STATIC_URL", "not_set")
    })


# ── Application Setup ───────────────────────────────────────────────────────────
async def create_app() -> web.Application:
    """Create and configure the aiohttp application"""
    app = web.Application()
    
    # Add routes
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/status", handle_status)
    
    # Telegram webhook endpoints (both for compatibility)
    app.router.add_post("/webhook/telegram", handle_telegram_webhook)
    app.router.add_post("/api/webhook/telegram", handle_telegram_webhook)
    
    log.info("🚀 SuperMegaBot Dashboard configured")
    log.info("📡 Telegram webhook: /webhook/telegram and /api/webhook/telegram")
    
    return app


def _free_port(port: int) -> None:
    """Kill whatever holds the port (macOS + Linux)."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            try:
                os.kill(int(pid), 9)
                print(f"  Killed PID {pid} on port {port}")
            except Exception:
                pass
    except Exception:
        pass


# ── Main Application ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def _main():
        print(f"\n🔍 Prüfe Port {PORT}...")
        _free_port(PORT)
        await asyncio.sleep(0.5)   # kurz warten damit OS den Port freigibt

        app = await create_app()
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT, reuse_address=True, reuse_port=True)
        await site.start()
        print(f"\n{'='*50}\n  SuperMegaBot Dashboard\n  http://localhost:{PORT}\n{'='*50}\n")

        # Auto-register Telegram webhook on Railway
        railway_url = os.getenv("RAILWAY_STATIC_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        if railway_url:
            base = f"https://{railway_url}" if not railway_url.startswith("http") else railway_url
            for token_env in ("TELEGRAM_BOT_TOKEN_2", "TELEGRAM_BOT_TOKEN"):
                tok = os.getenv(token_env)
                if tok:
                    try:
                        async with aiohttp.ClientSession() as session:
                            wh_url = f"{base}/webhook/telegram"
                            r = await session.post(
                                f"https://api.telegram.org/bot{tok}/setWebhook",
                                json={"url": wh_url, "allowed_updates": ["message", "edited_message"]}
                            )
                            result = await r.json()
                            log.info("Telegram webhook set (%s): %s → %s", 
                                   token_env, wh_url, result.get("description",""))
                    except Exception as e:
                        log.warning("Telegram webhook setup failed: %s", e)

        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    asyncio.run(_main())
