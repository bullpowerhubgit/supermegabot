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

    // ── Optionale externe Services ────────────────────────────────────────────
    {
      name: "telegram-bot",
      script: "node",
      args: "server.js",
      cwd: BOT_DIR,
      restart_delay: 5000,
      kill_timeout: 5000,
      max_restarts: 10,
      log_file: "/tmp/telegram-bot-pm2.log",
    },
    {
      name: "password-sync",
      script: "npm",
      args: "start",
      cwd: PASS_DIR,
      interpreter: "none",
      env: { PORT: 3005 },
      restart_delay: 5000,
      kill_timeout: 5000,
      max_restarts: 10,
      log_file: "/tmp/password-sync-pm2.log",
    },
    {
      name: "windsurf-shopify",
      script: "npm",
      args: "start",
      cwd: SHOPIFY_DIR,
      interpreter: "none",
      env: { PORT: 3001 },
      restart_delay: 5000,
      kill_timeout: 5000,
      max_restarts: 10,
      log_file: "/tmp/windsurf-shopify-pm2.log",
    },
    {
      name: "windsurf-autoheal",
      script: "npm",
      args: "start",
      cwd: HEAL_DIR,
      interpreter: "none",
      env: { AUTO_HEAL_PORT: 9000 },
      restart_delay: 5000,
      kill_timeout: 5000,
      max_restarts: 10,
      log_file: "/tmp/windsurf-autoheal-pm2.log",
    },
    {
      name: "windsurf-api-gateway",
      script: "node",
      args: "src/index.js",
      cwd: GW_DIR,
      env: { PORT: 8080 },
      restart_delay: 5000,
      kill_timeout: 5000,
      max_restarts: 10,
      log_file: "/tmp/windsurf-api-gateway-pm2.log",
    },
    {
      name: "windsurf-telegram-bot",
      script: "npm",
      args: "start",
      cwd: WS_BOT_DIR,
      interpreter: "none",
      env: { PORT: 8000 },
      restart_delay: 5000,
      kill_timeout: 5000,
      max_restarts: 10,
      log_file: "/tmp/windsurf-telegram-bot-pm2.log",
    },
    {
      name: "rudibot-eternal",
      script: "python3",
      args: "eternal_immortal_bot.py",
      cwd: ETERNAL_DIR,
      interpreter: "none",
      restart_delay: 10000,
      kill_timeout: 5000,
      max_restarts: 99,
      autorestart: true,
      log_file: "/tmp/rudibot-eternal-pm2.log",
    },
  ],
};
