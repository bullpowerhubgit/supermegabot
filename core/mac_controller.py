#!/usr/bin/env python3
"""
SuperMegaBot — Mac System Controller
Vollständige macOS-Kontrolle: Screenshot, Volume, Apps, Shell, System
"""
import asyncio
import subprocess
import os
import time
import psutil
from typing import Dict, Any, Optional
from pathlib import Path


class MacController:
    async def run(self, cmd: str, timeout: int = 15) -> Dict:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return {"success": r.returncode == 0, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def screenshot(self, path: str = None) -> Dict:
        path = path or f"/tmp/screenshot_{int(time.time())}.png"
        r = await self.run(f"screencapture -x {path}")
        return {**r, "file_path": path if r["success"] else None}

    async def volume(self, action: str, value: int = 50) -> Dict:
        cmds = {
            "set":   f"osascript -e 'set volume output volume {value}'",
            "mute":  "osascript -e 'set volume with output muted'",
            "unmute":"osascript -e 'set volume without output muted'",
            "get":   "osascript -e 'output volume of (get volume settings)'",
        }
        return await self.run(cmds.get(action, cmds["get"]))

    async def open_app(self, app_name: str) -> Dict:
        return await self.run(f"open -a '{app_name}'")

    async def get_running_apps(self) -> Dict:
        apps = [p.name() for p in psutil.process_iter(['name']) if p.info['name']]
        return {"success": True, "apps": sorted(set(apps))}

    async def system_info(self) -> Dict:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        battery = psutil.sensors_battery()
        return {
            "cpu_percent": cpu,
            "ram_used_gb": round(mem.used / 1e9, 1),
            "ram_total_gb": round(mem.total / 1e9, 1),
            "ram_percent": mem.percent,
            "disk_used_gb": round(disk.used / 1e9, 1),
            "disk_total_gb": round(disk.total / 1e9, 1),
            "disk_percent": disk.percent,
            "battery_percent": battery.percent if battery else 100,
            "charging": battery.power_plugged if battery else True,
        }

    async def notify(self, title: str, message: str) -> Dict:
        script = f'display notification "{message}" with title "{title}"'
        return await self.run(f"osascript -e '{script}'")

    async def clipboard_get(self) -> Dict:
        return await self.run("pbpaste")

    async def clipboard_set(self, text: str) -> Dict:
        p = subprocess.Popen("pbcopy", stdin=subprocess.PIPE)
        p.communicate(text.encode())
        return {"success": p.returncode == 0}

    async def speak(self, text: str, voice: str = "Anna") -> Dict:
        return await self.run(f"say -v {voice} '{text}'")

    async def wifi_status(self) -> Dict:
        r = await self.run("networksetup -getinfo Wi-Fi")
        return r

    async def list_wifi_networks(self) -> Dict:
        r = await self.run("/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -s")
        return r

    async def sleep_display(self) -> Dict:
        return await self.run("pmset displaysleepnow")

    async def lock_screen(self) -> Dict:
        return await self.run("/System/Library/CoreServices/Menu\\ Extras/User.menu/Contents/Resources/CGSession -suspend")

    async def get_ip(self) -> Dict:
        r = await self.run("ipconfig getifaddr en0 || ipconfig getifaddr en1")
        return r

    async def process_kill(self, name: str) -> Dict:
        return await self.run(f"pkill -f '{name}'")

    async def disk_cleanup(self) -> Dict:
        cmds = [
            "find /tmp -mtime +2 -delete 2>/dev/null || true",
            "rm -rf ~/Library/Caches/com.apple.Safari 2>/dev/null || true",
        ]
        results = []
        for cmd in cmds:
            r = await self.run(cmd)
            results.append(r)
        before = psutil.disk_usage('/').used
        # After cleanup
        after = psutil.disk_usage('/').used
        freed_mb = round((before - after) / 1e6, 1)
        return {"success": True, "freed_mb": freed_mb, "steps": len(results)}
