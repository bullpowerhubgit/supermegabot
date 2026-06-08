// PM2 Ecosystem Configuration
// Rudolf Sarkany - Master System Orchestrator
// Usage: pm2 start ecosystem.config.js

module.exports = {
  apps: [
    // 🌐 API Gateway (Central Hub)
    {
      name: 'windsurf-api-gateway',
      cwd: './windsurf-api-gateway',
      script: 'server.js',
      instances: 1,
      exec_mode: 'fork',
      env: {
        NODE_ENV: 'production',
        PORT: 8080
      },
      log_file: './logs/api-gateway.log',
      out_file: './logs/api-gateway-out.log',
      error_file: './logs/api-gateway-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
      max_memory_restart: '500M',
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '10s',
      watch: false,
      // Auto-restart on failure
      autorestart: true,
      // Health check
      health_check_grace_period: 30000,
      // Kill timeout
      kill_timeout: 5000,
      // Listen timeout
      listen_timeout: 10000
    },

    // 🤖 SuperMegaBot Dashboard
    {
      name: 'supermegabot-dashboard',
      cwd: './supermegabot',
      script: 'dashboard/server.py',
      interpreter: 'python3',
      instances: 1,
      exec_mode: 'fork',
      env: {
        DASHBOARD_PORT: 8888,
        PYTHONPATH: '.'
      },
      log_file: './logs/supermegabot.log',
      out_file: './logs/supermegabot-out.log',
      error_file: './logs/supermegabot-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
      max_memory_restart: '1G',
      restart_delay: 5000,
      max_restarts: 10,
      min_uptime: '10s',
      watch: false,
      autorestart: true
    },

    // 🤖 SuperMegaBot Telegram Bridge
    {
      name: 'telegram-hub-bridge',
      cwd: './supermegabot',
      script: 'telegram_hub_bridge.py',
      interpreter: 'python3',
      instances: 1,
      exec_mode: 'fork',
      env: {
        PYTHONPATH: '.'
      },
      log_file: './logs/telegram-bridge.log',
      out_file: './logs/telegram-bridge-out.log',
      error_file: './logs/telegram-bridge-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
      max_memory_restart: '500M',
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '10s',
      watch: false,
      autorestart: true
    },

    // 🛒 Shopify Automation API
    {
      name: 'shopify-automation-api',
      cwd: './shopify-automation-api/backend',
      script: 'dist/index.js',
      instances: 1,
      exec_mode: 'fork',
      env: {
        NODE_ENV: 'production',
        PORT: 3000
      },
      log_file: './logs/shopify-api.log',
      out_file: './logs/shopify-api-out.log',
      error_file: './logs/shopify-api-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
      max_memory_restart: '500M',
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '10s',
      watch: false,
      autorestart: true
    },

    // 📱 Windsurf Telegram Bot
    {
      name: 'windsurf-telegram-bot',
      cwd: './windsurf-telegram-bot',
      script: 'index.js',
      instances: 1,
      exec_mode: 'fork',
      env: {
        NODE_ENV: 'production',
        PORT: 8003
      },
      log_file: './logs/telegram-bot.log',
      out_file: './logs/telegram-bot-out.log',
      error_file: './logs/telegram-bot-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
      max_memory_restart: '500M',
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '10s',
      watch: false,
      autorestart: true
    },

    // 🎯 Acquisition Engine
    {
      name: 'shopify-acquisition-engine',
      cwd: './shopify-acquisition-engine',
      script: 'server.js',
      instances: 1,
      exec_mode: 'fork',
      env: {
        NODE_ENV: 'production',
        PORT: 3003
      },
      log_file: './logs/acquisition.log',
      out_file: './logs/acquisition-out.log',
      error_file: './logs/acquisition-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
      max_memory_restart: '500M',
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '10s',
      watch: false,
      autorestart: true
    },

    // 🛍️ Shopify Brutal Tuning
    {
      name: 'shopify-brutal-tuning',
      cwd: './shopify-automation-brutal-tuning',
      script: 'server.js',
      instances: 1,
      exec_mode: 'fork',
      env: {
        NODE_ENV: 'production',
        PORT: 3004
      },
      log_file: './logs/brutal-tuning.log',
      out_file: './logs/brutal-tuning-out.log',
      error_file: './logs/brutal-tuning-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
      max_memory_restart: '500M',
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '10s',
      watch: false,
      autorestart: true
    },

    // 💰 AutoIncome AI
    {
      name: 'autoincome-ai',
      cwd: './autoincome-ai',
      script: 'server.js',
      instances: 1,
      exec_mode: 'fork',
      env: {
        NODE_ENV: 'production',
        PORT: 3005
      },
      log_file: './logs/autoincome.log',
      out_file: './logs/autoincome-out.log',
      error_file: './logs/autoincome-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
      max_memory_restart: '500M',
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '10s',
      watch: false,
      autorestart: true
    }
  ],

  // Deployment configuration (optional)
  deploy: {
    production: {
      user: 'deploy',
      host: 'your-server.com',
      ref: 'origin/main',
      repo: 'https://github.com/bullpowerhubgit/supermegabot.git',
      path: '/var/www/rudibot',
      'post-deploy': 'npm install && pm2 reload ecosystem.config.js --env production'
    }
  }
};
