// ecosystem.config.js — PM2 Production Setup
module.exports = {
  apps: [
    {
      name: 'autopilot-server',
      script: 'mega-dashboard.js',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env_production: {
        NODE_ENV: 'production',
        PORT: 8888
      },
      error_file: 'logs/server-error.log',
      out_file: 'logs/server-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      min_uptime: '5s',
      max_restarts: 10,
      restart_delay: 3000,
      exp_backoff_restart_delay: 100
    },
    {
      name: 'autopilot-bot-public',
      script: 'bots/public-bot.js',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '300M',
      env_production: {
        NODE_ENV: 'production'
      },
      error_file: 'logs/bot-public-error.log',
      out_file: 'logs/bot-public-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      min_uptime: '10s',
      max_restarts: 20,
      restart_delay: 5000,
      pre_start: 'rm -f .bot*.lock'
    },
    {
      name: 'autopilot-bot-control',
      script: 'bots/control-bot.js',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '300M',
      env_production: {
        NODE_ENV: 'production'
      },
      error_file: 'logs/bot-control-error.log',
      out_file: 'logs/bot-control-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      min_uptime: '10s',
      max_restarts: 20,
      restart_delay: 5000,
      pre_start: 'rm -f .bot*.lock'
    },
    {
      name: 'ecommerce-orchestrator',
      script: 'ecommerce-master-orchestrator.js',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '400M',
      env_production: {
        NODE_ENV: 'production'
      },
      error_file: 'logs/ecommerce-error.log',
      out_file: 'logs/ecommerce-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss'
    }
  ]
};
