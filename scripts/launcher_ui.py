#!/usr/bin/env python3
"""
SuperMegaBot — Einmalklick All-Starter
Dark-themed Desktop Launcher
"""
import tkinter as tk
from tkinter import ttk
import subprocess
import threading
import urllib.request
import json
import time
import webbrowser
import os
import sys

BASE_URL = "https://supermegabot-production.up.railway.app"
LOCAL_URL = "http://localhost:8888"

DARK_BG     = "#040407"
CARD_BG     = "#0d0d18"
CARD2_BG    = "#111120"
BORDER      = "#1a1a2e"
CYAN        = "#00d4ff"
GREEN       = "#00ff88"
PURPLE      = "#7b2fff"
RED         = "#ff3366"
ORANGE      = "#ff8c00"
TEXT        = "#dde4ef"
MUTED       = "#5a6478"
FONT_MONO   = ("Menlo", 11)
FONT_MONO_S = ("Menlo", 10)
FONT_TITLE  = ("SF Pro Display", 22, "bold")
FONT_BTN    = ("SF Pro Display", 14, "bold")
FONT_LABEL  = ("SF Pro Display", 11)
FONT_SMALL  = ("SF Pro Display", 10)


def api_call(path: str, method: str = "GET") -> dict:
    try:
        for base in [LOCAL_URL, BASE_URL]:
            try:
                req = urllib.request.Request(
                    f"{base}{path}",
                    method=method,
                    headers={"Content-Type": "application/json", "User-Agent": "SuperMegaBot-Launcher/1.0"}
                )
                with urllib.request.urlopen(req, timeout=8) as r:
                    return {"ok": True, "data": json.loads(r.read()), "url": base}
            except Exception:
                continue
        return {"ok": False, "error": "Kein Server erreichbar"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class LauncherApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("⚡ SuperMegaBot Launcher")
        self.root.geometry("780x640")
        self.root.configure(bg=DARK_BG)
        self.root.resizable(False, False)

        # Center on screen
        self.root.update_idletasks()
        w = self.root.winfo_screenwidth()
        h = self.root.winfo_screenheight()
        self.root.geometry(f"780x640+{(w-780)//2}+{(h-640)//2}")

        self.status_vars = {}
        self.running = True
        self._build_ui()
        self._start_status_loop()

    def _build_ui(self):
        # ── HEADER ──────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=DARK_BG, pady=20)
        header.pack(fill="x", padx=24)

        tk.Label(header, text="⚡ SUPERMEGABOT", font=("Menlo", 20, "bold"),
                 bg=DARK_BG, fg=CYAN).pack(side="left")
        tk.Label(header, text="  ALL-IN-ONE LAUNCHER", font=("SF Pro Display", 14),
                 bg=DARK_BG, fg=MUTED).pack(side="left", pady=4)

        # Server status pill
        self.server_pill = tk.Label(header, text="● CHECKING...", font=FONT_SMALL,
                                     bg=CARD_BG, fg=ORANGE, padx=12, pady=4)
        self.server_pill.pack(side="right")

        # ── START ALL BUTTON ─────────────────────────────────────────────────
        btn_frame = tk.Frame(self.root, bg=DARK_BG)
        btn_frame.pack(fill="x", padx=24, pady=(0, 16))

        start_all = tk.Button(
            btn_frame,
            text="  🚀  START ALL  —  ALLE SYSTEME STARTEN",
            font=("SF Pro Display", 15, "bold"),
            bg=CYAN, fg=DARK_BG,
            activebackground="#00b8d9", activeforeground=DARK_BG,
            relief="flat", padx=24, pady=14,
            cursor="hand2",
            command=self._start_all,
        )
        start_all.pack(fill="x")
        self._pulse_btn(start_all, CYAN, "#00b8d9")

        # ── SERVICE GRID ─────────────────────────────────────────────────────
        grid_frame = tk.Frame(self.root, bg=DARK_BG)
        grid_frame.pack(fill="x", padx=24)

        services = [
            ("🤖", "SuperMegaBot",    "/health",               self._open_dashboard,   CYAN),
            ("⚡", "VORSPRUNG Scan",  "/api/vorsprung/status", self._run_vorsprung,    PURPLE),
            ("🔥", "Viral Scanner",   "/api/viral/status",     self._open_viral,       ORANGE),
            ("🛒", "Shopify Sync",    "/api/shopify/status",   self._run_shopify,      GREEN),
            ("📊", "Scheduler",       "/api/scheduler/tasks",  self._open_scheduler,   "#44aaff"),
            ("📱", "Telegram",        "/api/telegram/status",  self._open_telegram,    "#2AABEE"),
        ]

        for i, (icon, name, endpoint, action, color) in enumerate(services):
            row, col = divmod(i, 3)
            card = tk.Frame(grid_frame, bg=CARD_BG, padx=16, pady=14,
                            highlightbackground=BORDER, highlightthickness=1)
            card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            grid_frame.columnconfigure(col, weight=1)

            top = tk.Frame(card, bg=CARD_BG)
            top.pack(fill="x")
            tk.Label(top, text=icon, font=("SF Pro Display", 22), bg=CARD_BG, fg=color).pack(side="left")

            status_var = tk.StringVar(value="○ Prüfe...")
            status_lbl = tk.Label(top, textvariable=status_var, font=FONT_SMALL,
                                  bg=CARD_BG, fg=MUTED)
            status_lbl.pack(side="right")
            self.status_vars[name] = (status_var, status_lbl, endpoint)

            tk.Label(card, text=name, font=("SF Pro Display", 12, "bold"),
                     bg=CARD_BG, fg=TEXT).pack(anchor="w", pady=(4, 6))

            btn = tk.Button(card, text="▶  Starten", font=FONT_SMALL,
                            bg=CARD2_BG, fg=color, activebackground=BORDER,
                            activeforeground=color, relief="flat", padx=10, pady=5,
                            cursor="hand2", command=action)
            btn.pack(anchor="w")

        # ── LOG AREA ─────────────────────────────────────────────────────────
        log_frame = tk.Frame(self.root, bg=CARD_BG,
                             highlightbackground=BORDER, highlightthickness=1)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(16, 0))

        tk.Label(log_frame, text="LIVE LOG", font=("Menlo", 9, "bold"),
                 bg=CARD_BG, fg=MUTED, padx=12, pady=6).pack(anchor="w")

        self.log_text = tk.Text(
            log_frame, height=6, bg=CARD_BG, fg=GREEN,
            font=FONT_MONO_S, relief="flat", padx=12, pady=4,
            insertbackground=GREEN, wrap="word", state="disabled"
        )
        self.log_text.pack(fill="both", expand=True)

        # ── FOOTER ───────────────────────────────────────────────────────────
        footer = tk.Frame(self.root, bg=DARK_BG)
        footer.pack(fill="x", padx=24, pady=12)

        tk.Button(footer, text="🌐  Dashboard öffnen", font=FONT_SMALL,
                  bg=CARD2_BG, fg=MUTED, relief="flat", padx=12, pady=6,
                  cursor="hand2", command=self._open_dashboard).pack(side="left")
        tk.Button(footer, text="📈  VORSPRUNG Briefing", font=FONT_SMALL,
                  bg=CARD2_BG, fg=PURPLE, relief="flat", padx=12, pady=6,
                  cursor="hand2", command=self._open_briefing).pack(side="left", padx=8)
        tk.Label(footer, text="Railway ● EU West", font=FONT_SMALL,
                 bg=DARK_BG, fg=MUTED).pack(side="right")

    def _log(self, msg: str, color: str = GREEN):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _pulse_btn(self, btn, c1, c2, on=True):
        if not self.running:
            return
        btn.configure(bg=c1 if on else c2)
        self.root.after(900, lambda: self._pulse_btn(btn, c1, c2, not on))

    def _start_all(self):
        self._log("🚀 STARTE ALLE SYSTEME...", CYAN)
        threading.Thread(target=self._start_all_bg, daemon=True).start()

    def _start_all_bg(self):
        # 1. Check / start local server
        self._log("Prüfe lokalen Server...", CYAN)
        result = api_call("/health")
        if result.get("ok"):
            base = result.get("url", LOCAL_URL)
            self._log(f"✅ Server online: {base}", GREEN)
            self.root.after(0, lambda: self.server_pill.configure(text="● ONLINE", fg=GREEN))
        else:
            self._log("Starte lokalen Server...", ORANGE)
            project = os.path.expanduser("~/CascadeProjects/supermegabot")
            subprocess.Popen(
                ["python3", "dashboard/server.py"],
                cwd=project, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(3)

        # 2. VORSPRUNG Scan
        self._log("⚡ Starte VORSPRUNG Intelligence Scan...", PURPLE)
        r = api_call("/api/vorsprung/scan", "POST")
        if r.get("ok"):
            d = r.get("data", {})
            self._log(f"✅ VORSPRUNG: {d.get('signals_collected', '?')} Signale gesammelt", GREEN)
        else:
            self._log(f"⚠ VORSPRUNG: {r.get('error', '?')}", ORANGE)

        # 3. Viral scan
        self._log("🔥 Starte Viral Window Scanner...", ORANGE)
        r = api_call("/api/viral/scan", "POST")
        self._log("✅ Viral Scanner gestartet" if r.get("ok") else f"⚠ Viral: {r.get('error','?')}", GREEN if r.get("ok") else ORANGE)

        # 4. Open dashboard in browser
        self._log("🌐 Öffne Dashboard...", CYAN)
        time.sleep(0.5)
        self.root.after(0, self._open_dashboard)

        self._log("✅ ALLE SYSTEME GESTARTET!", GREEN)

    def _start_status_loop(self):
        threading.Thread(target=self._status_loop, daemon=True).start()

    def _status_loop(self):
        while self.running:
            for name, (var, lbl, endpoint) in self.status_vars.items():
                try:
                    result = api_call(endpoint)
                    if result.get("ok"):
                        self.root.after(0, lambda v=var, l=lbl: (
                            v.set("● LIVE"),
                            l.configure(fg=GREEN)
                        ))
                    else:
                        self.root.after(0, lambda v=var, l=lbl: (
                            v.set("○ Offline"),
                            l.configure(fg=MUTED)
                        ))
                except Exception:
                    pass
            # Check server pill
            r = api_call("/health")
            if r.get("ok"):
                base = r.get("url", "")
                label = "● RAILWAY" if "railway" in base else "● LOKAL"
                self.root.after(0, lambda t=label: self.server_pill.configure(text=t, fg=GREEN))
            else:
                self.root.after(0, lambda: self.server_pill.configure(text="○ OFFLINE", fg=RED))
            time.sleep(30)

    def _open_dashboard(self):
        webbrowser.open(f"{BASE_URL}")
        self._log("🌐 Dashboard geöffnet", CYAN)

    def _open_viral(self):
        webbrowser.open(f"{BASE_URL}/viral")
        self._log("🔥 Viral Scanner geöffnet", ORANGE)

    def _open_scheduler(self):
        webbrowser.open(f"{BASE_URL}/api/scheduler/tasks")
        self._log("📊 Scheduler geöffnet", "#44aaff")

    def _open_telegram(self):
        webbrowser.open("https://t.me/SuperMegaBotBot")
        self._log("📱 Telegram geöffnet", "#2AABEE")

    def _open_briefing(self):
        webbrowser.open(f"{BASE_URL}/api/vorsprung/briefing")
        self._log("📈 VORSPRUNG Briefing geöffnet", PURPLE)

    def _run_vorsprung(self):
        self._log("⚡ VORSPRUNG Scan startet...", PURPLE)
        threading.Thread(target=self._vorsprung_bg, daemon=True).start()

    def _vorsprung_bg(self):
        r = api_call("/api/vorsprung/scan", "POST")
        if r.get("ok"):
            d = r.get("data", {})
            self._log(f"✅ VORSPRUNG: {d.get('signals_collected','?')} Signale | Briefing generiert", GREEN)
        else:
            self._log(f"⚠ VORSPRUNG: {r.get('error','?')}", ORANGE)

    def _run_shopify(self):
        self._log("🛒 Shopify Sync startet...", GREEN)
        threading.Thread(target=lambda: (
            api_call("/api/shopify/import", "POST"),
            self._log("✅ Shopify Sync gestartet", GREEN)
        ), daemon=True).start()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self.running = False
        self.root.destroy()


if __name__ == "__main__":
    app = LauncherApp()
    app.run()
