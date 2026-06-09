#!/usr/bin/env python3
"""Mac System Controller - Full macOS control via AppleScript + subprocess"""

import asyncio
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _run(cmd: str, timeout: int = 30) -> dict:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout.strip(), "stderr": r.stderr.strip(), "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Timeout", "returncode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}


def _applescript(script: str) -> str:
    r = _run(f"osascript -e '{script}'")
    return r["stdout"]


class MacController:
    # ---------- Screenshots ----------

    async def take_screenshot(self, save_path: str = None) -> str:
        if not save_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = str(SCREENSHOTS_DIR / f"screenshot_{ts}.png")
        _run(f"screencapture -x {save_path}")
        return save_path

    async def take_window_screenshot(self, app_name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = str(SCREENSHOTS_DIR / f"{app_name}_{ts}.png")
        _run(f"screencapture -l $(osascript -e 'tell app \"{app_name}\" to id of window 1') {path}")
        return path

    # ---------- App Control ----------

    async def open_app(self, app_name: str) -> str:
        r = _run(f"open -a '{app_name}'")
        return f"Opened {app_name}" if r["returncode"] == 0 else f"Error: {r['stderr']}"

    async def quit_app(self, app_name: str) -> str:
        _applescript(f'tell application "{app_name}" to quit')
        return f"Quit {app_name}"

    async def list_running_apps(self) -> list:
        out = _run("osascript -e 'tell app \"System Events\" to get name of every process where background only is false'")
        return [a.strip() for a in out["stdout"].split(",") if a.strip()]

    async def focus_app(self, app_name: str) -> str:
        _applescript(f'tell application "{app_name}" to activate')
        return f"Focused {app_name}"

    # ---------- Keyboard / Mouse ----------

    async def type_text(self, text: str) -> str:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
        _applescript(f'tell application "System Events" to keystroke "{escaped}"')
        return f"Typed: {text[:40]}"

    async def press_key(self, key: str) -> str:
        _applescript(f'tell application "System Events" to key code {key}')
        return f"Pressed key: {key}"

    async def hotkey(self, *keys) -> str:
        modifiers = []
        main_key = keys[-1]
        mod_map = {"cmd": "command", "shift": "shift", "opt": "option", "ctrl": "control"}
        for k in keys[:-1]:
            modifiers.append(mod_map.get(k, k))
        mod_str = " & ".join([f'"{m} down"' for m in modifiers])
        if mod_str:
            script = f'tell application "System Events" to keystroke "{main_key}" using {{{mod_str}}}'
        else:
            script = f'tell application "System Events" to keystroke "{main_key}"'
        _applescript(script)
        return f"Hotkey: {'+'.join(keys)}"

    async def click_at(self, x: int, y: int) -> str:
        script = f'''
tell application "System Events"
    click at {{{x}, {y}}}
end tell'''
        _run(f"osascript -e '{script}'")
        return f"Clicked at ({x}, {y})"

    # ---------- Volume & Display ----------

    async def set_volume(self, level: int) -> str:
        level = max(0, min(100, level))
        _applescript(f"set volume output volume {level}")
        return f"Volume set to {level}%"

    async def mute(self) -> str:
        _applescript("set volume output muted true")
        return "Muted"

    async def unmute(self) -> str:
        _applescript("set volume output muted false")
        return "Unmuted"

    async def set_brightness(self, level: float) -> str:
        level = max(0.0, min(1.0, level))
        _run(f"brightness {level}")
        return f"Brightness set to {int(level*100)}%"

    # ---------- Notifications ----------

    async def notify(self, title: str, message: str, sound: str = "default") -> str:
        script = f'display notification "{message}" with title "{title}" sound name "{sound}"'
        _applescript(script)
        return f"Notification sent: {title}"

    # ---------- Clipboard ----------

    async def get_clipboard(self) -> str:
        r = _run("pbpaste")
        return r["stdout"]

    async def set_clipboard(self, text: str) -> str:
        _run(f"echo '{text}' | pbcopy")
        return "Clipboard set"

    # ---------- System Info ----------

    async def get_battery(self) -> dict:
        r = _run("pmset -g batt")
        return {"raw": r["stdout"]}

    async def get_wifi_info(self) -> dict:
        r = _run("networksetup -getairportnetwork en0")
        return {"raw": r["stdout"]}

    async def get_system_info(self) -> dict:
        try:
            import psutil
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.5),
                "memory_used_gb": round(mem.used / 1024**3, 1),
                "memory_total_gb": round(mem.total / 1024**3, 1),
                "memory_percent": mem.percent,
                "disk_used_gb": round(disk.used / 1024**3, 1),
                "disk_free_gb": round(disk.free / 1024**3, 1),
                "disk_percent": disk.percent,
            }
        except ImportError:
            r = _run("sysctl -n hw.memsize")
            return {"raw_memory": r["stdout"]}

    # ---------- Browser Control ----------

    async def open_url_safari(self, url: str) -> str:
        _run(f"open -a Safari '{url}'")
        await asyncio.sleep(1)
        return f"Safari opened: {url}"

    async def open_url_chrome(self, url: str) -> str:
        _run(f"open -a 'Google Chrome' '{url}'")
        return f"Chrome opened: {url}"

    async def safari_current_url(self) -> str:
        return _applescript('tell application "Safari" to get URL of current tab of window 1')

    async def safari_execute_js(self, js: str) -> str:
        escaped = js.replace("'", "\\'")
        return _applescript(f"tell application \"Safari\" to do JavaScript '{escaped}' in current tab of window 1")

    # ---------- File Operations ----------

    async def open_file(self, path: str) -> str:
        _run(f"open '{path}'")
        return f"Opened: {path}"

    async def reveal_in_finder(self, path: str) -> str:
        _run(f"open -R '{path}'")
        return f"Revealed in Finder: {path}"

    # ---------- Subscription Management ----------

    async def list_subscriptions(self) -> str:
        r = _run("open 'https://appleid.apple.com/account/manage/section/subscriptions'")
        return (
            "Apple Subscriptions geöffnet in Browser.\n\n"
            "Für automatische Kündigung: Tippe 'abo kündigen <service>'\n"
            "Unterstützte Services: Netflix, Spotify, Amazon, Apple One"
        )

    async def cancel_subscription(self, service: str) -> str:
        service_lower = service.lower()
        urls = {
            "netflix": "https://www.netflix.com/cancelplan",
            "spotify": "https://www.spotify.com/account/subscription/",
            "amazon": "https://www.amazon.de/mc/pipelines/membership",
            "apple": "https://appleid.apple.com/account/manage/section/subscriptions",
        }
        for name, url in urls.items():
            if name in service_lower:
                _run(f"open '{url}'")
                return f"{service} Kündigungsseite geöffnet. Bitte manuell bestätigen."
        return f"Service '{service}' nicht gefunden. Verfügbar: {', '.join(urls.keys())}"

    # ---------- Power Management ----------

    async def sleep_display(self) -> str:
        _run("pmset displaysleepnow")
        return "Display sleeping"

    async def lock_screen(self) -> str:
        _run("/System/Library/CoreServices/Menu\\ Extras/User.menu/Contents/Resources/CGSession -suspend")
        return "Screen locked"

    async def empty_trash(self) -> str:
        _applescript('tell application "Finder" to empty trash')
        return "Trash emptied"

    # ---------- Terminal Commands ----------

    async def run_terminal_command(self, cmd: str, timeout: int = 30) -> dict:
        return _run(cmd, timeout=timeout)

    async def run_in_new_terminal(self, cmd: str) -> str:
        script = f'tell application "Terminal" to do script "{cmd}"'
        _applescript(script)
        return f"Running in Terminal: {cmd[:60]}"
