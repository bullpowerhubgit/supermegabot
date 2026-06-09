#!/usr/bin/env python3
"""
SuperMegaBot — API Builder & Manager
=====================================
• Katalog aller konfigurierten APIs aus .env
• Live-Test jeder API-Verbindung
• Automatische Generierung neuer API-Client-Module
• Ersetzen/Tauschen von APIs in bestehenden Modulen
• Telegram-Befehle: /api_liste, /api_test, /api_neu, /api_ersetze, /api_info
"""

import asyncio
import aiohttp
import base64
import importlib
import os
import re
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).parent.parent
MODULES_DIR = BASE_DIR / "modules"
DATA_DIR  = BASE_DIR / "data"

# .env beim Import laden
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(BASE_DIR / ".env", override=True)
except ImportError:
    pass

# ═══════════════════════════════════════════════════════════════════════════════
# API-Katalog: alle bekannten APIs mit Test-Endpunkt & Env-Keys
# ═══════════════════════════════════════════════════════════════════════════════

def _e(key: str, default: str = "") -> str:
    return os.getenv(key, default)

KNOWN_APIS: Dict[str, Dict] = {
    # ── Lokale KI ──────────────────────────────────────────────────────────────
    "ollama": {
        "name": "Ollama (lokal)",
        "category": "KI",
        "base_url": lambda: _e("OLLAMA_HOST", "http://localhost:11434"),
        "headers":  lambda: {},
        "test_path": "/api/tags",
        "test_method": "GET",
        "env_keys": ["OLLAMA_HOST", "OLLAMA_MODEL"],
        "module_file": None,
        "docs": "https://ollama.com/library",
    },
    "openclaw": {
        "name": "OpenClaw Gateway",
        "category": "KI",
        "base_url": lambda: _e("OPENCLAW_URL", "http://127.0.0.1:18789"),
        "headers":  lambda: {"Authorization": f"Bearer {_e('OPENCLAW_TOKEN')}"},
        "test_path": "/health",
        "test_method": "GET",
        "env_keys": ["OPENCLAW_URL", "OPENCLAW_TOKEN"],
        "module_file": None,
        "docs": None,
    },
    # ── Cloud KI ───────────────────────────────────────────────────────────────
    "openai": {
        "name": "OpenAI",
        "category": "KI",
        "base_url": lambda: "https://api.openai.com/v1",
        "headers":  lambda: {"Authorization": f"Bearer {_e('OPENAI_API_KEY')}"},
        "test_path": "/models",
        "test_method": "GET",
        "env_keys": ["OPENAI_API_KEY"],
        "module_file": None,
        "docs": "https://platform.openai.com/docs",
    },
    "anthropic": {
        "name": "Anthropic (Claude)",
        "category": "KI",
        "base_url": lambda: "https://api.anthropic.com/v1",
        "headers":  lambda: {
            "x-api-key": _e("ANTHROPIC_API_KEY"),
            "anthropic-version": "2023-06-01",
        },
        "test_path": "/models",
        "test_method": "GET",
        "env_keys": ["ANTHROPIC_API_KEY"],
        "module_file": None,
        "docs": "https://docs.anthropic.com",
    },
    "perplexity": {
        "name": "Perplexity (Web-Suche)",
        "category": "KI",
        "base_url": lambda: "https://api.perplexity.ai",
        "headers":  lambda: {"Authorization": f"Bearer {_e('PERPLEXITY_API_KEY')}"},
        "test_path": None,           # kein einfacher GET-Test
        "test_method": "POST",
        "env_keys": ["PERPLEXITY_API_KEY"],
        "module_file": None,
        "docs": "https://docs.perplexity.ai",
    },
    # ── E-Commerce ─────────────────────────────────────────────────────────────
    "shopify": {
        "name": "Shopify Admin",
        "category": "E-Commerce",
        "base_url": lambda: f"{_e('SHOPIFY_STORE_URL', '').rstrip('/')}/admin/api/2024-10",
        "headers":  lambda: {"X-Shopify-Access-Token": _e("SHOPIFY_ACCESS_TOKEN")},
        "test_path": "/shop.json",
        "test_method": "GET",
        "env_keys": ["SHOPIFY_STORE_URL", "SHOPIFY_ACCESS_TOKEN"],
        "module_file": "modules/shopify_client.py",
        "docs": "https://shopify.dev/docs/api/admin-rest",
    },
    "shopify_storefront": {
        "name": "Shopify Storefront",
        "category": "E-Commerce",
        "base_url": lambda: f"{_e('SHOPIFY_STORE_URL', '').rstrip('/')}/api/2024-10/graphql.json",
        "headers":  lambda: {
            "X-Shopify-Storefront-Access-Token": _e("SHOPIFY_STOREFRONT_TOKEN"),
            "Content-Type": "application/json",
        },
        "test_path": None,
        "test_method": "POST",
        "env_keys": ["SHOPIFY_STORE_URL", "SHOPIFY_STOREFRONT_TOKEN"],
        "module_file": None,
        "docs": "https://shopify.dev/docs/api/storefront",
    },
    "printify": {
        "name": "Printify",
        "category": "E-Commerce",
        "base_url": lambda: "https://api.printify.com/v1",
        "headers":  lambda: {"Authorization": f"Bearer {_e('PRINTIFY_TOKEN')}"},
        "test_path": "/shops.json",
        "test_method": "GET",
        "env_keys": ["PRINTIFY_TOKEN"],
        "module_file": None,
        "docs": "https://developers.printify.com",
    },
    "etsy": {
        "name": "Etsy",
        "category": "E-Commerce",
        "base_url": lambda: "https://openapi.etsy.com/v3",
        "headers":  lambda: {"x-api-key": _e("ETSY_API_KEY")},
        "test_path": "/application/openapi-ping",
        "test_method": "GET",
        "env_keys": ["ETSY_API_KEY"],
        "module_file": None,
        "docs": "https://developers.etsy.com",
    },
    "gumroad": {
        "name": "Gumroad",
        "category": "E-Commerce",
        "base_url": lambda: "https://api.gumroad.com/v2",
        "headers":  lambda: {},
        "test_path": f"/user?access_token={_e('GUMROAD_TOKEN')}",
        "test_method": "GET",
        "env_keys": ["GUMROAD_TOKEN"],
        "module_file": None,
        "docs": "https://gumroad.com/api",
    },
    "digistore24": {
        "name": "Digistore24",
        "category": "E-Commerce",
        "base_url": lambda: "https://www.digistore24.com/api/call",
        "headers":  lambda: {"X-DS24-API-Key": _e("DIGISTORE24_API_KEY")},
        "test_path": None,
        "test_method": "GET",
        "env_keys": ["DIGISTORE24_API_KEY"],
        "module_file": None,
        "docs": "https://www.digistore24.com/page/api-docs",
    },
    # ── Marketing ──────────────────────────────────────────────────────────────
    "klaviyo": {
        "name": "Klaviyo",
        "category": "Marketing",
        "base_url": lambda: "https://a.klaviyo.com/api",
        "headers":  lambda: {
            "Authorization": f"Klaviyo-API-Key {_e('KLAVIYO_API_KEY')}",
            "revision": "2024-02-15",
        },
        "test_path": "/accounts/",
        "test_method": "GET",
        "env_keys": ["KLAVIYO_API_KEY"],
        "module_file": None,
        "docs": "https://developers.klaviyo.com",
    },
    "mailchimp": {
        "name": "Mailchimp",
        "category": "Marketing",
        "base_url": lambda: f"https://{_e('MAILCHIMP_SERVER_PREFIX','us1')}.api.mailchimp.com/3.0",
        "headers":  lambda: {
            "Authorization": "Basic " + base64.b64encode(
                f"any:{_e('MAILCHIMP_API_KEY')}".encode()
            ).decode()
        },
        "test_path": "/ping",
        "test_method": "GET",
        "env_keys": ["MAILCHIMP_API_KEY", "MAILCHIMP_SERVER_PREFIX"],
        "module_file": None,
        "docs": "https://mailchimp.com/developer",
    },
    "windsor": {
        "name": "Windsor.ai (Analytics)",
        "category": "Marketing",
        "base_url": lambda: "https://connectors.windsor.ai",
        "headers":  lambda: {},
        "test_path": f"/all?api_key={_e('WINDSOR_API_KEY')}&fields=source&date_from=today",
        "test_method": "GET",
        "env_keys": ["WINDSOR_API_KEY"],
        "module_file": None,
        "docs": "https://windsor.ai/api-fields",
    },
    # ── Infrastruktur ──────────────────────────────────────────────────────────
    "supabase": {
        "name": "Supabase",
        "category": "Datenbank",
        "base_url": lambda: f"{_e('SUPABASE_URL','').rstrip('/')}/rest/v1",
        "headers":  lambda: {
            "apikey":        _e("SUPABASE_ANON_KEY"),
            "Authorization": f"Bearer {_e('SUPABASE_ANON_KEY')}",
        },
        "test_path": "/",
        "test_method": "GET",
        "env_keys": ["SUPABASE_URL", "SUPABASE_ANON_KEY"],
        "module_file": None,
        "docs": "https://supabase.com/docs",
    },
    "github": {
        "name": "GitHub",
        "category": "DevOps",
        "base_url": lambda: "https://api.github.com",
        "headers":  lambda: {
            "Authorization": f"Bearer {_e('GITHUB_TOKEN')}",
            "Accept": "application/vnd.github.v3+json",
        },
        "test_path": "/user",
        "test_method": "GET",
        "env_keys": ["GITHUB_TOKEN"],
        "module_file": None,
        "docs": "https://docs.github.com/rest",
    },
    "telegram": {
        "name": "Telegram Bot",
        "category": "Kommunikation",
        "base_url": lambda: f"https://api.telegram.org/bot{_e('TELEGRAM_BOT_TOKEN')}",
        "headers":  lambda: {},
        "test_path": "/getMe",
        "test_method": "GET",
        "env_keys": ["TELEGRAM_BOT_TOKEN"],
        "module_file": None,
        "docs": "https://core.telegram.org/bots/api",
    },
    # ── Social / Ads ───────────────────────────────────────────────────────────
    "facebook": {
        "name": "Facebook/Meta Graph",
        "category": "Social",
        "base_url": lambda: "https://graph.facebook.com/v19.0",
        "headers":  lambda: {},
        "test_path": f"/me?access_token={_e('FACEBOOK_APP_ID')}|{_e('FACEBOOK_APP_SECRET')}",
        "test_method": "GET",
        "env_keys": ["FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET"],
        "module_file": None,
        "docs": "https://developers.facebook.com/docs/graph-api",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# APITester — Live-Verbindungstest
# ═══════════════════════════════════════════════════════════════════════════════

class APITester:
    async def test(self, api_id: str) -> Dict:
        cfg = KNOWN_APIS.get(api_id.lower())
        if not cfg:
            return {"ok": False, "error": f"Unbekannte API: {api_id}"}

        # Prüfe ob Env-Keys gesetzt sind
        missing = [k for k in cfg["env_keys"] if not _e(k)]
        if missing:
            return {"ok": False, "error": f"Fehlende Env-Keys: {', '.join(missing)}"}

        test_path = cfg.get("test_path")
        if not test_path:
            return {"ok": None, "info": "Kein GET-Test verfügbar (POST-only API)"}

        base_url = cfg["base_url"]()
        headers  = cfg["headers"]()
        url      = f"{base_url}{test_path}"

        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(url, headers=headers) as r:
                    status = r.status
                    body   = (await r.text())[:200]
                    ok     = status < 400
                    return {
                        "ok":     ok,
                        "status": status,
                        "body":   body if not ok else "✓",
                    }
        except asyncio.TimeoutError:
            return {"ok": False, "error": "Timeout (8s)"}
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}

    async def test_all(self) -> Dict[str, Dict]:
        tasks = {api_id: self.test(api_id) for api_id in KNOWN_APIS}
        results = {}
        for api_id, coro in tasks.items():
            results[api_id] = await coro
        return results


# ═══════════════════════════════════════════════════════════════════════════════
# APIBuilder — generiert neuen Python API-Client
# ═══════════════════════════════════════════════════════════════════════════════

_CLIENT_TEMPLATE = '''\
#!/usr/bin/env python3
"""
{name} API Client
Auto-generiert von SuperMegaBot API Builder am {created_at}
Base URL: {base_url}
Docs: {docs}
"""

import os
import aiohttp
from typing import Any, Dict, List, Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

BASE_URL = "{base_url}"
{env_setup}


class {class_name}Client:
    """Auto-generierter API-Client für {name}."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    def _headers(self) -> Dict[str, str]:
        return {header_dict}

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def get(self, endpoint: str, params: Dict = None) -> Any:
        s = await self._session_get()
        url = f"{{self.base_url}}{{endpoint}}"
        async with s.get(url, params=params or {{}}) as r:
            r.raise_for_status()
            ct = r.headers.get("Content-Type", "")
            return await r.json() if "json" in ct else await r.text()

    async def post(self, endpoint: str, json: Dict = None, data: Dict = None) -> Any:
        s = await self._session_get()
        url = f"{{self.base_url}}{{endpoint}}"
        async with s.post(url, json=json, data=data) as r:
            r.raise_for_status()
            ct = r.headers.get("Content-Type", "")
            return await r.json() if "json" in ct else await r.text()

    async def put(self, endpoint: str, json: Dict = None) -> Any:
        s = await self._session_get()
        url = f"{{self.base_url}}{{endpoint}}"
        async with s.put(url, json=json) as r:
            r.raise_for_status()
            return await r.json()

    async def delete(self, endpoint: str) -> Any:
        s = await self._session_get()
        url = f"{{self.base_url}}{{endpoint}}"
        async with s.delete(url) as r:
            r.raise_for_status()
            return await r.json()

    async def test_connection(self) -> bool:
        """Schnell-Test der Verbindung."""
        try:
            await self.get("{test_path}")
            return True
        except Exception:
            return False

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ── Benutzerdefinierte Methoden ────────────────────────────────────────────
{custom_methods}
'''


class APIBuilder:
    """Generiert neue API-Client-Module als .py-Dateien."""

    # Vorgefertigte Methoden für bekannte API-Typen
    PRESET_METHODS: Dict[str, str] = {
        "shopify": textwrap.dedent("""\
            async def get_products(self, limit: int = 50) -> List[Dict]:
                return (await self.get(f"/products.json?limit={limit}")).get("products", [])

            async def get_orders(self, limit: int = 50) -> List[Dict]:
                return (await self.get(f"/orders.json?limit={limit}")).get("orders", [])

            async def create_product(self, product: Dict) -> Dict:
                return (await self.post("/products.json", json={"product": product})).get("product", {})

            async def update_product(self, product_id: int, data: Dict) -> Dict:
                return (await self.put(f"/products/{product_id}.json", json={"product": data})).get("product", {})
        """),
        "openai": textwrap.dedent("""\
            async def chat(self, messages: List[Dict], model: str = "gpt-4o") -> str:
                resp = await self.post("/chat/completions", json={
                    "model": model, "messages": messages
                })
                return resp.get("choices", [{}])[0].get("message", {}).get("content", "")

            async def list_models(self) -> List[str]:
                resp = await self.get("/models")
                return [m["id"] for m in resp.get("data", [])]
        """),
        "anthropic": textwrap.dedent("""\
            async def chat(self, messages: List[Dict], model: str = "claude-opus-4-5",
                           max_tokens: int = 1024) -> str:
                resp = await self.post("/messages", json={
                    "model": model, "max_tokens": max_tokens, "messages": messages
                })
                return resp.get("content", [{}])[0].get("text", "")
        """),
        "supabase": textwrap.dedent("""\
            async def select(self, table: str, select: str = "*", filters: Dict = None) -> List[Dict]:
                params = {"select": select}
                if filters:
                    params.update(filters)
                return await self.get(f"/{table}", params=params)

            async def insert(self, table: str, data: Dict) -> Dict:
                return await self.post(f"/{table}", json=data)

            async def upsert(self, table: str, data: Dict) -> Dict:
                s = await self._session_get()
                url = f"{self.base_url}/{table}"
                async with s.post(url, json=data, headers={"Prefer": "resolution=merge-duplicates"}) as r:
                    r.raise_for_status()
                    return await r.json()
        """),
        "telegram": textwrap.dedent("""\
            async def send_message(self, chat_id: str, text: str,
                                   parse_mode: str = "HTML") -> Dict:
                return await self.post("/sendMessage", json={
                    "chat_id": chat_id, "text": text, "parse_mode": parse_mode
                })

            async def get_me(self) -> Dict:
                return await self.get("/getMe")
        """),
        "github": textwrap.dedent("""\
            async def get_repos(self, per_page: int = 30) -> List[Dict]:
                return await self.get(f"/user/repos?per_page={per_page}")

            async def create_issue(self, owner: str, repo: str,
                                   title: str, body: str = "") -> Dict:
                return await self.post(f"/repos/{owner}/{repo}/issues",
                                       json={"title": title, "body": body})

            async def get_user(self) -> Dict:
                return await self.get("/user")
        """),
    }

    def build(
        self,
        api_id: str,
        name: str,
        base_url: str,
        auth_type: str,          # "bearer", "apikey_header", "basic", "query", "none"
        auth_env_key: str = "",  # Name des Env-Keys
        auth_header_name: str = "Authorization",
        test_path: str = "/",
        docs: str = "",
        preset: str = "",        # key aus PRESET_METHODS
        save: bool = True,
    ) -> Dict:
        """Generiert einen API-Client und speichert ihn optional als .py-Datei."""

        class_name = "".join(w.capitalize() for w in re.sub(r"[^a-z0-9]", " ", api_id.lower()).split())

        # Auth-Header
        env_setup_lines = []
        header_dict_str = "{}"
        if auth_type == "bearer" and auth_env_key:
            env_setup_lines.append(f'{auth_env_key} = os.getenv("{auth_env_key}", "")')
            header_dict_str = f'{{"{auth_header_name}": f"Bearer {{{auth_env_key}}}"}}'
        elif auth_type == "apikey_header" and auth_env_key:
            env_setup_lines.append(f'{auth_env_key} = os.getenv("{auth_env_key}", "")')
            header_dict_str = f'{{"{auth_header_name}": {auth_env_key}}}'
        elif auth_type == "basic" and auth_env_key:
            env_setup_lines.append(f'{auth_env_key} = os.getenv("{auth_env_key}", "")')
            header_dict_str = (
                f'{{"{auth_header_name}": "Basic " + __import__("base64")'
                f'.b64encode(f"user:{{{auth_env_key}}}".encode()).decode()}}'
            )
        elif auth_type == "none":
            header_dict_str = "{}"

        env_setup = "\n".join(env_setup_lines) if env_setup_lines else "# keine Env-Vars nötig"

        custom_methods_raw = self.PRESET_METHODS.get(preset or api_id.lower(), "")
        if custom_methods_raw:
            custom_methods = textwrap.indent(custom_methods_raw.rstrip(), "    ")
        else:
            custom_methods = "    # Eigene Methoden hier hinzufügen\n    pass"

        code = _CLIENT_TEMPLATE.format(
            name         = name,
            created_at   = datetime.now().strftime("%Y-%m-%d %H:%M"),
            base_url     = base_url,
            docs         = docs or "–",
            class_name   = class_name,
            env_setup    = env_setup,
            header_dict  = header_dict_str,
            test_path    = test_path,
            custom_methods = custom_methods,
        )

        out_path = MODULES_DIR / f"{api_id}_client.py"
        result = {
            "ok":        True,
            "api_id":    api_id,
            "class_name": f"{class_name}Client",
            "file":      str(out_path),
            "code_preview": code[:300] + "…",
        }

        if save:
            MODULES_DIR.mkdir(exist_ok=True)
            out_path.write_text(code)
            result["saved"] = True

        return result

    def register_in_env(self, env_key: str, env_value: str = "") -> bool:
        """Fügt einen neuen Env-Key in .env ein (wenn noch nicht vorhanden)."""
        env_path = BASE_DIR / ".env"
        if not env_path.exists():
            return False
        content = env_path.read_text()
        if env_key in content:
            return False  # bereits vorhanden
        content += f"\n# Auto-hinzugefügt von API Builder\n{env_key}={env_value}\n"
        env_path.write_text(content)
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# APIReplacer — tauscht APIs in bestehenden Modulen aus
# ═══════════════════════════════════════════════════════════════════════════════

# Ersetzungsregeln: (old_api, new_api) → [(regex, replacement, beschreibung), ...]
REPLACEMENT_RULES: Dict[Tuple[str, str], List[Tuple[str, str, str]]] = {
    ("openai", "anthropic"): [
        (r"import openai", "import anthropic", "import openai → import anthropic"),
        (r"openai\.api_key\s*=\s*[^\n]+", "# ANTHROPIC_API_KEY wird aus .env geladen", "API-Key Initialisierung"),
        (r"openai\.ChatCompletion\.create\(", "anthropic.Anthropic().messages.create(", "ChatCompletion → messages"),
        (r'"gpt-4[^"]*"', '"claude-opus-4-5"', "GPT-4 → Claude Opus"),
        (r'"gpt-3\.5[^"]*"', '"claude-haiku-3-5"', "GPT-3.5 → Claude Haiku"),
        (r"openai\.OpenAI\(\)", "anthropic.Anthropic()", "OpenAI() → Anthropic()"),
    ],
    ("openai", "ollama"): [
        (r"import openai", "import aiohttp  # Ollama (lokal, kostenlos)", "openai → aiohttp"),
        (r"openai\.api_key\s*=\s*[^\n]+", "OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')", "API-Key → Ollama Host"),
        (r'"gpt-4[^"]*"', '"llama3.2:latest"', "GPT-4 → Llama3"),
        (r'"gpt-3\.5[^"]*"', '"llama3.2:latest"', "GPT-3.5 → Llama3"),
        (r"client\.chat\.completions\.create\(", "# Ollama-Aufruf — siehe modules/ollama_client.py", "Client-Aufruf"),
    ],
    ("anthropic", "openai"): [
        (r"import anthropic", "import openai", "import anthropic → import openai"),
        (r'"claude-opus[^"]*"',   '"gpt-4o"',       "Claude Opus → GPT-4o"),
        (r'"claude-sonnet[^"]*"', '"gpt-4o-mini"',   "Claude Sonnet → GPT-4o-mini"),
        (r'"claude-haiku[^"]*"',  '"gpt-3.5-turbo"', "Claude Haiku → GPT-3.5"),
        (r"anthropic\.Anthropic\(\)", "openai.OpenAI()", "Anthropic() → OpenAI()"),
    ],
    ("anthropic", "ollama"): [
        (r"import anthropic", "import aiohttp  # Ollama lokal", "import anthropic → aiohttp"),
        (r'"claude-[^"]*"', '"llama3.2:latest"', "Claude → Llama3"),
    ],
    ("requests", "aiohttp"): [
        (r"import requests", "import aiohttp", "requests → aiohttp"),
        (r"requests\.get\(([^)]+)\)", r"await session.get(\1)", "requests.get → aiohttp"),
        (r"requests\.post\(([^)]+)\)", r"await session.post(\1)", "requests.post → aiohttp"),
        (r"\.json\(\)", ".json() # await hinzufügen falls async", "json()"),
    ],
    ("shopify_admin", "shopify_suite"): [
        (r"SHOPIFY_ACCESS_TOKEN", "SHOPIFY_SUITE_ACCESS_TOKEN", "Token-Wechsel"),
        (r"SHOPIFY_STORE_URL", "SHOPIFY_SUITE_URL", "Store-URL-Wechsel"),
    ],
}


class APIReplacer:
    def replace(self, file_path: str, old_api: str, new_api: str) -> Dict:
        path = Path(file_path)
        if not path.exists():
            # Suche relativ zu BASE_DIR
            path = BASE_DIR / file_path
        if not path.exists():
            return {"ok": False, "error": f"Datei nicht gefunden: {file_path}"}

        rules_key = (old_api.lower(), new_api.lower())
        rules = REPLACEMENT_RULES.get(rules_key)
        if not rules:
            return {
                "ok": False,
                "error": (
                    f"Keine Ersetzungsregeln für {old_api} → {new_api}.\n"
                    f"Verfügbar: {', '.join(f'{a}→{b}' for a, b in REPLACEMENT_RULES)}"
                ),
            }

        original = path.read_text()
        content  = original
        applied  = []

        for pattern, replacement, description in rules:
            new_content = re.sub(pattern, replacement, content)
            if new_content != content:
                applied.append(description)
                content = new_content

        if content == original:
            return {"ok": True, "changes": [], "message": "Keine Änderungen nötig."}

        # Backup anlegen
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(f".bak_{ts}{path.suffix}")
        backup.write_text(original)

        path.write_text(content)
        return {
            "ok":      True,
            "file":    str(path),
            "backup":  str(backup),
            "changes": applied,
        }

    def list_rules(self) -> List[str]:
        return [f"{a} → {b}" for a, b in REPLACEMENT_RULES]


# ═══════════════════════════════════════════════════════════════════════════════
# APIManager — Haupt-Entry-Point für Telegram-Commands
# ═══════════════════════════════════════════════════════════════════════════════

class APIManager:
    def __init__(self):
        self.tester   = APITester()
        self.builder  = APIBuilder()
        self.replacer = APIReplacer()

    # ── /api_liste ─────────────────────────────────────────────────────────────
    def cmd_liste(self) -> str:
        lines = ["📋 <b>Konfigurierte APIs</b>\n"]
        by_cat: Dict[str, List] = {}
        for api_id, cfg in KNOWN_APIS.items():
            cat = cfg.get("category", "Sonstiges")
            by_cat.setdefault(cat, []).append((api_id, cfg))

        for cat, apis in sorted(by_cat.items()):
            lines.append(f"<b>{cat}:</b>")
            for api_id, cfg in apis:
                keys_ok = all(_e(k) for k in cfg["env_keys"])
                icon = "✅" if keys_ok else "⚠️"
                lines.append(f"  {icon} <code>{api_id}</code> — {cfg['name']}")
            lines.append("")

        lines.append("Befehle: /api_test &lt;name&gt; | /api_info &lt;name&gt;")
        lines.append("/api_neu &lt;id&gt; &lt;base_url&gt; &lt;auth_type&gt; [env_key]")
        lines.append("/api_ersetze &lt;datei&gt; &lt;alt&gt; &lt;neu&gt;")
        return "\n".join(lines)

    # ── /api_test <name> ───────────────────────────────────────────────────────
    async def cmd_test(self, args: str) -> str:
        api_id = args.strip().lower()
        if not api_id:
            return "Verwendung: /api_test &lt;api-name&gt;\nBeispiel: /api_test shopify"

        result = await self.tester.test(api_id)
        name   = KNOWN_APIS.get(api_id, {}).get("name", api_id)

        if result.get("ok") is None:
            return f"ℹ️ <b>{name}</b>\n{result.get('info','–')}"
        elif result["ok"]:
            return f"✅ <b>{name}</b> — Verbindung OK (HTTP {result.get('status',200)})"
        else:
            err = result.get("error") or f"HTTP {result.get('status','?')}: {result.get('body','')}"
            return f"❌ <b>{name}</b>\n{err}"

    # ── /api_test_alle ─────────────────────────────────────────────────────────
    async def cmd_test_alle(self) -> str:
        results = await self.tester.test_all()
        ok_list, fail_list, skip_list = [], [], []
        for api_id, r in results.items():
            name = KNOWN_APIS[api_id]["name"]
            if r.get("ok") is True:
                ok_list.append(f"✅ {name}")
            elif r.get("ok") is None:
                skip_list.append(f"ℹ️ {name} (kein GET-Test)")
            else:
                fail_list.append(f"❌ {name}: {r.get('error','?')[:60]}")

        lines = [f"<b>API Gesamt-Test ({len(KNOWN_APIS)} APIs)</b>\n"]
        if ok_list:   lines += ok_list
        if fail_list: lines += [""] + fail_list
        if skip_list: lines += [""] + skip_list
        return "\n".join(lines)

    # ── /api_info <name> ───────────────────────────────────────────────────────
    def cmd_info(self, args: str) -> str:
        api_id = args.strip().lower()
        cfg = KNOWN_APIS.get(api_id)
        if not cfg:
            avail = ", ".join(KNOWN_APIS)
            return f"Unbekannte API: <code>{api_id}</code>\nVerfügbar: {avail}"

        keys_status = []
        for k in cfg["env_keys"]:
            val = _e(k)
            keys_status.append(f"  {'✅' if val else '❌'} {k}: {'***' + val[-4:] if val else 'nicht gesetzt'}")

        lines = [
            f"<b>{cfg['name']}</b>",
            f"ID: <code>{api_id}</code>",
            f"Kategorie: {cfg.get('category','–')}",
            f"Base URL: <code>{cfg['base_url']()[:60]}</code>",
            f"Test-Pfad: {cfg.get('test_path') or '(keiner)'}",
            f"Modul: {cfg.get('module_file') or '–'}",
            f"Docs: {cfg.get('docs') or '–'}",
            "",
            "<b>Env-Keys:</b>",
        ] + keys_status

        return "\n".join(lines)

    # ── /api_neu <id> <base_url> <auth_type> [env_key] ────────────────────────
    def cmd_neu(self, args: str) -> str:
        """
        Erstellt einen neuen API-Client.
        Syntax: /api_neu <id> <base_url> <auth_type> [env_key]
        auth_type: bearer | apikey_header | basic | none
        Beispiel: /api_neu stripe https://api.stripe.com/v1 bearer STRIPE_API_KEY
        """
        parts = args.strip().split()
        if len(parts) < 3:
            return (
                "Verwendung:\n"
                "<code>/api_neu &lt;id&gt; &lt;base_url&gt; &lt;auth_type&gt; [env_key]</code>\n\n"
                "auth_type: bearer | apikey_header | basic | none\n\n"
                "Beispiel:\n"
                "<code>/api_neu stripe https://api.stripe.com/v1 bearer STRIPE_SECRET_KEY</code>"
            )

        api_id    = parts[0].lower()
        base_url  = parts[1]
        auth_type = parts[2].lower()
        env_key   = parts[3] if len(parts) > 3 else ""

        if auth_type not in ("bearer", "apikey_header", "basic", "query", "none"):
            return f"Ungültiger auth_type: {auth_type}\nErlaubt: bearer | apikey_header | basic | none"

        result = self.builder.build(
            api_id    = api_id,
            name      = api_id.replace("_", " ").title(),
            base_url  = base_url,
            auth_type = auth_type,
            auth_env_key = env_key.upper() if env_key else "",
            test_path = "/",
            save      = True,
        )

        if env_key:
            added = self.builder.register_in_env(env_key.upper())
            env_note = f"\n{'✅ Env-Key in .env eingetragen: ' if added else 'ℹ️ Env-Key existiert bereits: '}<code>{env_key.upper()}</code>"
        else:
            env_note = ""

        return (
            f"✅ <b>API-Client erstellt!</b>\n"
            f"Datei: <code>{result['file']}</code>\n"
            f"Klasse: <code>{result['class_name']}</code>{env_note}\n\n"
            f"Import:\n"
            f"<code>from modules.{api_id}_client import {result['class_name']}</code>"
        )

    # ── /api_ersetze <datei> <alt_api> <neu_api> ──────────────────────────────
    def cmd_ersetze(self, args: str) -> str:
        """
        Ersetzt eine API durch eine andere in einer Datei.
        Syntax: /api_ersetze <datei> <alt_api> <neu_api>
        Beispiel: /api_ersetze modules/geheimwaffe.py openai anthropic
        """
        parts = args.strip().split()
        if len(parts) < 3:
            avail = "\n".join(f"  • {r}" for r in self.replacer.list_rules())
            return (
                "Verwendung:\n"
                "<code>/api_ersetze &lt;datei&gt; &lt;alt_api&gt; &lt;neu_api&gt;</code>\n\n"
                f"Verfügbare Regeln:\n{avail}"
            )

        file_path, old_api, new_api = parts[0], parts[1], parts[2]
        result = self.replacer.replace(file_path, old_api, new_api)

        if not result["ok"]:
            return f"❌ Fehler: {result['error']}"

        if not result.get("changes"):
            return f"ℹ️ Keine Änderungen in <code>{file_path}</code> nötig."

        changes_str = "\n".join(f"  • {c}" for c in result["changes"])
        return (
            f"✅ <b>API ersetzt!</b>\n"
            f"Datei: <code>{result['file']}</code>\n"
            f"Backup: <code>{result['backup']}</code>\n\n"
            f"Änderungen:\n{changes_str}"
        )

    # ── /api_regeln ────────────────────────────────────────────────────────────
    def cmd_regeln(self) -> str:
        rules = self.replacer.list_rules()
        lines = ["<b>Verfügbare Ersetzungs-Regeln:</b>", ""]
        lines += [f"  <code>{r}</code>" for r in rules]
        lines += ["", "Verwendung: /api_ersetze &lt;datei&gt; &lt;alt&gt; &lt;neu&gt;"]
        return "\n".join(lines)

    # ── Dispatcher für CommandRouter ───────────────────────────────────────────
    async def dispatch(self, text: str) -> str:
        text = text.strip()
        lower = text.lower()

        if lower in ("/api_liste", "api liste", "api list"):
            return self.cmd_liste()
        if lower in ("/api_test_alle", "api test alle"):
            return await self.cmd_test_alle()
        if lower.startswith("/api_test"):
            return await self.cmd_test(text[len("/api_test"):].strip())
        if lower.startswith("/api_info"):
            return self.cmd_info(text[len("/api_info"):].strip())
        if lower.startswith("/api_neu"):
            return self.cmd_neu(text[len("/api_neu"):].strip())
        if lower.startswith("/api_ersetze"):
            return self.cmd_ersetze(text[len("/api_ersetze"):].strip())
        if lower in ("/api_regeln", "api regeln"):
            return self.cmd_regeln()
        if lower in ("/api_hilfe", "/api_help", "api hilfe"):
            return self.cmd_help()

        return self.cmd_help()

    def cmd_help(self) -> str:
        return (
            "<b>API Builder — Befehle:</b>\n\n"
            "/api_liste — alle konfigurierten APIs\n"
            "/api_test &lt;name&gt; — API testen\n"
            "/api_test_alle — alle APIs testen\n"
            "/api_info &lt;name&gt; — API-Details & Keys\n\n"
            "/api_neu &lt;id&gt; &lt;url&gt; &lt;auth&gt; [key] — neuen Client generieren\n"
            "/api_ersetze &lt;datei&gt; &lt;alt&gt; &lt;neu&gt; — API tauschen\n"
            "/api_regeln — verfügbare Ersetzungsregeln\n\n"
            "Beispiele:\n"
            "<code>/api_test shopify</code>\n"
            "<code>/api_neu stripe https://api.stripe.com/v1 bearer STRIPE_KEY</code>\n"
            "<code>/api_ersetze modules/geheimwaffe.py openai anthropic</code>"
        )


# ── Singleton ──────────────────────────────────────────────────────────────────
_manager: Optional[APIManager] = None

def get_manager() -> APIManager:
    global _manager
    if _manager is None:
        _manager = APIManager()
    return _manager


# ── Direktaufruf zum Testen ───────────────────────────────────────────────────
if __name__ == "__main__":
    async def _main():
        mgr = get_manager()
        print(mgr.cmd_liste())
        print("\n--- Test Shopify ---")
        print(await mgr.cmd_test("shopify"))
        print("\n--- Test Telegram ---")
        print(await mgr.cmd_test("telegram"))

    asyncio.run(_main())
