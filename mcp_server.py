#!/usr/bin/env python3
"""
SuperMegaBot MCP Server
Provides Claude Desktop access to the SuperMegaBot API (localhost:8888)
"""

import asyncio
import json
import sys
import urllib.request
import urllib.error
import hashlib
import os

BASE_URL = "http://localhost:8888"
GUARDIAN_URL = "http://localhost:3201"

# Guardian API Key aus Umgebung laden
GUARDIAN_SECRET = os.getenv('GUARDIAN_API_SECRET', '')
GUARDIAN_API_KEY = hashlib.sha256(GUARDIAN_SECRET.encode()).hexdigest()[:32] if GUARDIAN_SECRET else ''

def guardian_api_call(method, path, body=None):
    """Call Guardian API with authentication"""
    url = GUARDIAN_URL + path
    headers = {"Content-Type": "application/json", "X-API-Key": GUARDIAN_API_KEY}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e), "guardian": "unavailable"}


def api_call(method, path, body=None):
    url = BASE_URL + path
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e)}


def send_tools_list():
    tools = [
        {
            "name": "get_services",
            "description": "List all services and their online/offline status",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "service_action",
            "description": "Start, stop, or restart a service by ID",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Service ID"},
                    "action": {"type": "string", "enum": ["start", "stop", "restart"]}
                },
                "required": ["id", "action"]
            }
        },
        {
            "name": "get_system_status",
            "description": "Get CPU, RAM, disk usage and process count",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "get_processes",
            "description": "List top processes by CPU usage",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "send_chat",
            "description": "Send a message to the AI chat and get a response",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Message text"},
                    "model": {"type": "string", "default": "gemma4"}
                },
                "required": ["text"]
            }
        },
        {
            "name": "run_autopilot",
            "description": "Run an AutoPilot agent with a goal",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "Mission goal / task description"},
                    "agent_id": {"type": "string", "description": "Optional agent ID"}
                },
                "required": ["goal"]
            }
        },
        {
            "name": "get_trading_prices",
            "description": "Get current crypto/trading prices",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "get_logs",
            "description": "Get recent system logs",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "mac_action",
            "description": "Execute a Mac control action (screenshot, lock, sleep, notify, etc.)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["screenshot", "lock", "sleep", "notification", "empty_trash", "open_finder", "open_terminal"]}
                },
                "required": ["action"]
            }
        },
        {
            "name": "set_volume",
            "description": "Set system volume (0-100)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "level": {"type": "integer", "minimum": 0, "maximum": 100}
                },
                "required": ["level"]
            }
        },
        {
            "name": "run_geheimwaffe",
            "description": "Run the GEHEIMWAFFE niche research tool",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "niche": {"type": "string", "description": "Niche or market to research"}
                },
                "required": ["niche"]
            }
        },
        {
            "name": "get_shopify_status",
            "description": "Get Shopify store status and product counts",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "run_backup",
            "description": "Trigger a system backup",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "guardian_health",
            "description": "Check Guardian API health status",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "guardian_status",
            "description": "Get full Guardian system status with all services",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "guardian_services",
            "description": "List all services monitored by Guardian",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "guardian_heal",
            "description": "Heal/restart a service via Guardian",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name to heal (e.g., rudibot_main, ollama)"}
                },
                "required": ["service"]
            }
        },
        {
            "name": "guardian_agents",
            "description": "List all registered Guardian agents",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "guardian_notify",
            "description": "Send notification via Guardian to all channels",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to send"},
                    "priority": {"type": "string", "enum": ["normal", "high", "critical"], "default": "normal"}
                },
                "required": ["message"]
            }
        },
        {
            "name": "guardian_brain",
            "description": "Get Guardian brain statistics (learned patterns)",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "guardian_backup",
            "description": "Trigger manual backup of all projects",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "guardian_backups_list",
            "description": "List all available backup dates",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "guardian_restore",
            "description": "Restore project from backup",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name (e.g., supermegabot, telegram-automation-bot)"},
                    "date": {"type": "string", "description": "Backup date YYYY-MM-DD (optional, uses latest if not specified)"}
                },
                "required": ["project"]
            }
        }
    ]
    send_message({"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}})


def handle_tool_call(name, args):
    if name == "get_services":
        return api_call("GET", "/api/services/status")
    elif name == "service_action":
        return api_call("POST", "/api/services/action", {"id": args["id"], "action": args["action"]})
    elif name == "get_system_status":
        return api_call("GET", "/api/system")
    elif name == "get_processes":
        return api_call("GET", "/api/processes")
    elif name == "send_chat":
        return api_call("POST", "/api/chat", {"text": args["text"], "session_id": "claude_mcp", "model": args.get("model", "gemma4")})
    elif name == "run_autopilot":
        return api_call("POST", "/api/autopilot/run", {"goal": args["goal"], "agent_id": args.get("agent_id", "")})
    elif name == "get_trading_prices":
        return api_call("GET", "/api/trading/prices")
    elif name == "get_logs":
        return api_call("GET", "/api/logs")
    elif name == "mac_action":
        return api_call("POST", "/api/mac/action", {"action": args["action"]})
    elif name == "set_volume":
        return api_call("POST", "/api/mac/action", {"action": "volume", "level": args["level"]})
    elif name == "run_geheimwaffe":
        return api_call("POST", "/api/geheimwaffe/run", {"niche": args["niche"]})
    elif name == "get_shopify_status":
        return api_call("GET", "/api/shopify/status")
    elif name == "run_backup":
        return api_call("POST", "/api/backup/run")
    # Guardian Tools
    elif name == "guardian_health":
        return guardian_api_call("GET", "/api/v1/health")
    elif name == "guardian_status":
        return guardian_api_call("GET", "/api/v1/status")
    elif name == "guardian_services":
        status = guardian_api_call("GET", "/api/v1/status")
        return {"services": status.get("services", []), "overall": status.get("overall_health")}
    elif name == "guardian_heal":
        return guardian_api_call("POST", "/api/v1/services/heal", {"service": args["service"]})
    elif name == "guardian_agents":
        return guardian_api_call("GET", "/api/v1/agents")
    elif name == "guardian_notify":
        return guardian_api_call("POST", "/api/v1/notify", {
            "message": args["message"],
            "priority": args.get("priority", "normal")
        })
    elif name == "guardian_brain":
        return guardian_api_call("GET", "/api/v1/brain/summary")
    elif name == "guardian_backup":
        return guardian_api_call("POST", "/api/v1/backup")
    elif name == "guardian_backups_list":
        return guardian_api_call("GET", "/api/v1/backups")
    elif name == "guardian_restore":
        return guardian_api_call("POST", "/api/v1/restore", {
            "project": args["project"],
            "date": args.get("date")
        })
    return {"error": "Unknown tool"}


def send_message(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


async def main():
    global req_id
    while True:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("method") == "initialize":
            send_message({
                "jsonrpc": "2.0", "id": msg["id"],
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "supermegabot-mcp-guardian", "version": "1.1.0"}
                }
            })
        elif msg.get("method") == "tools/list":
            req_id = msg["id"]
            send_tools_list()
        elif msg.get("method") == "tools/call":
            params = msg.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            result = handle_tool_call(name, args)
            send_message({
                "jsonrpc": "2.0", "id": msg["id"],
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}]}
            })


if __name__ == "__main__":
    asyncio.run(main())
