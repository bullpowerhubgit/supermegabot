module.exports = {
  apps: [
    {
      name: 'autopilot-server',
      script: 'server.js',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env_production: { NODE_ENV: 'production', PORT: 3200 },
      error_file: 'logs/server-error.log',
      out_file: 'logs/server-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      min_uptime: '5s',
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: 'monitoring',
      script: 'windsurf-monitoring.js',
      instances: 1,
      autorestart: true,
      env_production: { NODE_ENV: 'production', MONITORING_PORT: 9001 },
      error_file: 'logs/monitor-error.log',
      out_file: 'logs/monitor-out.log',
    }
  ]
};
