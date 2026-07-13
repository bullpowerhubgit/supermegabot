module.exports = {
  apps: [
    {
      name: 'agent-orchestrator',
      cwd: __dirname,
      script: 'orchestrator.js',
      interpreter: 'node',
      autorestart: true,
      max_memory_restart: '300M',
      env: { NODE_ENV: 'production' }
    }
  ]
};
