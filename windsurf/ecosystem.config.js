// RudiBot King of Tools - PM2 Ecosystem
// Alle Services unter einem Dach

module.exports = {
  apps: [
    // ── CORE API (King) ──────────────────────────────────────────
    {
      name: 'rudibot-api',
      script: './dist/api/server.js',
      cwd: '/Users/rudolfsarkany/windsurf',
      instances: 1,
      exec_mode: 'fork',
      watch: false,
      max_memory_restart: '1G',
      env: {
        NODE_ENV: 'production',
        PORT: 3001
      },
      log_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-api.log',
      out_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-api-out.log',
      error_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-api-error.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      autorestart: true,
      max_restarts: 5,
      min_uptime: '10s',
      restart_delay: 3000
    },

    // ── ETERNAL GUARDIAN ─────────────────────────────────────────
    {
      name: 'rudibot-eternal',
      script: '/Users/rudolfsarkany/rudibot-eternal/eternal_guardian.py',
      cwd: '/Users/rudolfsarkany/rudibot-eternal',
      instances: 1,
      exec_mode: 'fork',
      interpreter: '/Library/Frameworks/Python.framework/Versions/3.13/bin/python3',
      watch: false,
      env: {
        FLASK_ENV: 'production',
        PORT: 3201
      },
      log_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-eternal.log',
      out_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-eternal-out.log',
      error_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-eternal-error.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      autorestart: true,
      max_restarts: 5,
      min_uptime: '10s',
      restart_delay: 5000
    },

    // ── RUDIBOT MASTER ───────────────────────────────────────────
    {
      name: 'rudibot-master',
      script: '/Users/rudolfsarkany/rudibot-master/server.py',
      cwd: '/Users/rudolfsarkany/rudibot-master',
      instances: 1,
      exec_mode: 'fork',
      interpreter: '/Library/Frameworks/Python.framework/Versions/3.13/bin/python3',
      watch: false,
      env: {
        PORT: 9900
      },
      log_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-master.log',
      out_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-master-out.log',
      error_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-master-error.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      autorestart: true,
      max_restarts: 5,
      min_uptime: '10s',
      restart_delay: 5000
    },

    // ── TELEGRAM BOT ─────────────────────────────────────────────
    {
      name: 'rudibot-telegram',
      script: '/Users/rudolfsarkany/windsurf-telegram-bot/src/index.js',
      cwd: '/Users/rudolfsarkany/windsurf-telegram-bot',
      instances: 1,
      exec_mode: 'fork',
      watch: false,
      env: {
        NODE_ENV: 'production',
        PORT: 3200
      },
      log_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-telegram.log',
      out_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-telegram-out.log',
      error_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-telegram-error.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      autorestart: true,
      max_restarts: 5,
      min_uptime: '10s',
      restart_delay: 3000
    },

    // ── SHOPIFY DASHBOARD ────────────────────────────────────────
    {
      name: 'rudibot-shopify',
      script: '/Users/rudolfsarkany/shopify-dashboard/server.js',
      cwd: '/Users/rudolfsarkany/shopify-dashboard',
      instances: 1,
      exec_mode: 'fork',
      watch: false,
      env: {
        NODE_ENV: 'production',
        PORT: 3000
      },
      log_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-shopify.log',
      out_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-shopify-out.log',
      error_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-shopify-error.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      autorestart: true,
      max_restarts: 5,
      min_uptime: '10s',
      restart_delay: 3000
    },

    // ── UNIFIED DASHBOARD ─────────────────────────────────────────
    {
      name: 'rudibot-dashboard',
      script: '/Users/rudolfsarkany/windsurf/unified-dashboard/server.js',
      cwd: '/Users/rudolfsarkany/windsurf',
      instances: 1,
      exec_mode: 'fork',
      watch: false,
      env: {
        NODE_ENV: 'production',
        PORT: 8080
      },
      log_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-dashboard.log',
      out_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-dashboard-out.log',
      error_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-dashboard-error.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      autorestart: true,
      max_restarts: 5,
      min_uptime: '10s',
      restart_delay: 3000
    },

    // ── SUPERMEBABOT DASHBOARD ───────────────────────────────────
    {
      name: 'rudibot-supermega',
      script: '/Users/rudolfsarkany/supermegabot/dashboard/server.py',
      cwd: '/Users/rudolfsarkany/supermegabot',
      instances: 1,
      exec_mode: 'fork',
      interpreter: '/Library/Frameworks/Python.framework/Versions/3.13/bin/python3',
      watch: false,
      env: {
        PORT: 8888
      },
      log_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-supermega.log',
      out_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-supermega-out.log',
      error_file: '/Users/rudolfsarkany/.pm2/logs/rudibot-supermega-error.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      autorestart: true,
      max_restarts: 5,
      min_uptime: '10s',
      restart_delay: 5000
    }
  ]
};
