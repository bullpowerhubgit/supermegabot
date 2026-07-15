/**
 * PM2 Ecosystem — SuperMegaBot
 * Verwendet __dirname für portable Pfade, kein Hardcoding von /Users/...
 */
const path = require("path");
const HOME = process.env.HOME || require("os").homedir();

// Projekt-Root = Verzeichnis dieser Datei
const MEGA_DIR = __dirname;

// Externe Projekte aus Umgebungsvariablen oder Standard-Pfaden
const BOT_DIR     = process.env.TELEGRAM_BOT_DIR   || path.join(HOME, "telegram-automation-bot");
const SHOPIFY_DIR = process.env.SHOPIFY_SUITE_DIR  || path.join(HOME, "windsurf-shopify-suite");
const PASS_DIR    = process.env.PASSWORD_SYNC_DIR  || path.join(HOME, "password-sync-suite", "web-app");
const HEAL_DIR    = process.env.AUTO_HEAL_DIR      || path.join(HOME, "windsurf-auto-heal");
const GW_DIR      = process.env.API_GATEWAY_DIR    || path.join(HOME, "windsurf-api-gateway");
const WS_BOT_DIR  = process.env.WS_TELEGRAM_DIR   || path.join(HOME, "windsurf-telegram-bot");
const ETERNAL_DIR = process.env.ETERNAL_BOT_DIR   || path.join(HOME, "rudibot-eternal");

module.exports = {
  apps: [
    // ── Kern-Services ────────────────────────────────────────────────────────
    {
      name: "supermegabot",
      script: "python3",
      args: "dashboard/server.py",
      cwd: MEGA_DIR,
      interpreter: "none",
      env: { PORT: 8888 },
      restart_delay: 5000,
      kill_timeout: 5000,
      max_restarts: 10,
      log_file: "/tmp/supermegabot.log",
    },
    {
      name: "mega-orchestrator",
      script: "python3",
      args: "core/mega_orchestrator.py",
      cwd: MEGA_DIR,
      interpreter: "none",
      restart_delay: 5000,
      kill_timeout: 5000,
      max_restarts: 99,
      autorestart: true,
      log_file: "/tmp/mega-orchestrator-pm2.log",
    },
    {
      name: "rudibot-army",
      script: "python3",
      args: "rudibot-army/army_commander.py",
      cwd: MEGA_DIR,
      interpreter: "none",
      restart_delay: 8000,
      kill_timeout: 5000,
      max_restarts: 20,
      autorestart: true,
      log_file: "/tmp/rudibot-army.log",
    },
    {
      // LOCAL POLLING ONLY — niemals in Railway starten!
      // Railway setzt Webhook via dashboard/server.py (/api/telegram/setup → setWebhook).
      // Telegram erlaubt NICHT gleichzeitig Webhook + getUpdates (→ 409 Conflict, CPU-Spin).
      // Beim PM2-Start wird der Webhook zuerst per deleteWebhook entfernt, danach startet Polling.
      // Manuell starten: pm2 start ecosystem.config.cjs --only tg-hub-bridge
      name: "tg-hub-bridge",
      script: "bash",
      args: ["-c", `python3 -c 'import os,urllib.request; t=os.getenv("TELEGRAM_BOT_TOKEN",""); urllib.request.urlopen("https://api.telegram.org/bot"+t+"/deleteWebhook") if t else None' 2>/dev/null; exec python3 telegram_hub_bridge.py`],
      cwd: MEGA_DIR,
      interpreter: "none",
      autorestart: false,
      restart_delay: 10000,
      kill_timeout: 5000,
      max_restarts: 5,
      log_file: "/tmp/tg-hub-bridge.log",
    },

    // ── Windsurf Integration Services ────────────────────────────────────────
    /* DISABLED: requires npm install axios ws + Linux portability fixes
    {
      name: "windsurf-watchdog",
      script: "node",
      args: "core/watchdog/watchdog-v2.js",
      cwd: MEGA_DIR,
      restart_delay: 10000,
      kill_timeout: 5000,
      max_restarts: 20,
      autorestart: true,
      log_file: "/tmp/windsurf-watchdog.log",
    },
    {
      name: "windsurf-watchdog-monitor",
      script: "node",
      args: "core/watchdog/watchdog-monitor-server.js",
      cwd: MEGA_DIR,
      env: { PORT: 9003 },
      restart_delay: 10000,
      kill_timeout: 5000,
      max_restarts: 10,
      autorestart: true,
      log_file: "/tmp/windsurf-watchdog-monitor.log",
    },
    {
      name: "windsurf-dashboard",
      script: "node",
      args: "dashboard/server_windsurf.js",
      cwd: MEGA_DIR,
      env: { PORT: 9002 },
      restart_delay: 5000,
      kill_timeout: 5000,
      max_restarts: 10,
      autorestart: true,
      log_file: "/tmp/windsurf-dashboard.log",
    },
    {
      name: "windsurf-ecommerce",
      script: "node",
      args: "modules/ecommerce_orchestrator.js",
      cwd: MEGA_DIR,
      restart_delay: 8000,
      kill_timeout: 5000,
      max_restarts: 10,
      autorestart: true,
      log_file: "/tmp/windsurf-ecommerce.log",
    },
    {
      name: "windsurf-marketing",
      script: "node",
      args: "modules/marketing_engine.js",
      cwd: MEGA_DIR,
      restart_delay: 8000,
      kill_timeout: 5000,
      max_restarts: 10,
      autorestart: true,
      log_file: "/tmp/windsurf-marketing.log",
    },
    {
      name: "windsurf-agenten-hub",
      script: "node",
      args: "core/agenten_hub.js",
      cwd: MEGA_DIR,
      env: { PORT: 9998 },
      restart_delay: 8000,
      kill_timeout: 5000,
      max_restarts: 10,
      autorestart: true,
      log_file: "/tmp/windsurf-agenten-hub.log",
    },
    */

    // ── Optionale externe Services ────────────────────────────────────────────
    // autorestart: false — PM2 startet diese Services nicht neu wenn das Repo
    // lokal nicht existiert. Manuell starten mit: pm2 start ecosystem.config.js --only <name>
    {
      name: "telegram-bot",
      script: "node",
      args: "server.js",
      cwd: BOT_DIR,
      kill_timeout: 5000,
      max_restarts: 5,
      autorestart: false,
      log_file: "/tmp/telegram-bot-pm2.log",
    },
    {
      name: "password-sync",
      script: "npm",
      args: "start",
      cwd: PASS_DIR,
      interpreter: "none",
      env: { PORT: 3005 },
      kill_timeout: 5000,
      max_restarts: 5,
      autorestart: false,
      log_file: "/tmp/password-sync-pm2.log",
    },
    {
      name: "windsurf-shopify",
      script: "npm",
      args: "start",
      cwd: SHOPIFY_DIR,
      interpreter: "none",
      env: { PORT: 3001 },
      kill_timeout: 5000,
      max_restarts: 5,
      autorestart: false,
      log_file: "/tmp/windsurf-shopify-pm2.log",
    },
    {
      name: "windsurf-autoheal",
      script: "npm",
      args: "start",
      cwd: HEAL_DIR,
      interpreter: "none",
      env: { AUTO_HEAL_PORT: 9000 },
      kill_timeout: 5000,
      max_restarts: 5,
      autorestart: false,
      log_file: "/tmp/windsurf-autoheal-pm2.log",
    },
    {
      name: "windsurf-api-gateway",
      script: "node",
      args: "src/index.js",
      cwd: GW_DIR,
      env: { PORT: 8080 },
      kill_timeout: 5000,
      max_restarts: 5,
      autorestart: false,
      log_file: "/tmp/windsurf-api-gateway-pm2.log",
    },
    {
      name: "windsurf-telegram-bot",
      script: "npm",
      args: "start",
      cwd: WS_BOT_DIR,
      interpreter: "none",
      env: { PORT: 8000 },
      kill_timeout: 5000,
      max_restarts: 5,
      autorestart: false,
      log_file: "/tmp/windsurf-telegram-bot-pm2.log",
    },
    {
      name: "rudibot-eternal",
      script: "python3",
      args: "eternal_immortal_bot.py",
      cwd: ETERNAL_DIR,
      interpreter: "none",
      exp_backoff_restart_delay: 100,
      kill_timeout: 5000,
      max_restarts: 99,
      autorestart: true,
      log_file: "/tmp/rudibot-eternal-pm2.log",
    },
  ],
};
