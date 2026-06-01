/**
 * SuperMegaBot Bot System Starter
 * Startet alle spezialisierten Bots
 */

const { getBotOrchestrator } = require('./bot-orchestrator.cjs');

async function startBotSystem() {
  console.log('🚀 Starting SuperMegaBot Bot System...');
  
  try {
    // Get bot orchestrator
    const orchestrator = getBotOrchestrator();
    
    // Set up event listeners
    orchestrator.on('started', (data) => {
      console.log(`✅ ${data.bot} started at ${data.timestamp}`);
    });
    
    orchestrator.on('stopped', (data) => {
      console.log(`🛑 ${data.bot} stopped at ${data.timestamp}`);
    });
    
    orchestrator.on('systemMetrics', (data) => {
      console.log(`📊 System Metrics: Memory ${data.metrics.memory}%, CPU ${data.metrics.cpu}%`);
    });
    
    orchestrator.on('systemAlerts', (data) => {
      console.log(`🚨 System Alerts: ${data.alerts.length} alerts`);
      data.alerts.forEach(alert => {
        console.log(`  - ${alert.level}: ${alert.message}`);
      });
    });
    
    orchestrator.on('repairStatus', (data) => {
      console.log(`🔧 Repairs: ${data.repairs.fixed} fixed, ${data.repairs.failed} failed`);
    });
    
    orchestrator.on('criticalAlert', (data) => {
      console.log(`🚨 CRITICAL: ${data.type} = ${data.value}`);
    });
    
    orchestrator.on('healthStatus', (metrics) => {
      console.log(`💚 Health: ${metrics.activeBots}/${metrics.totalBots} bots active`);
    });
    
    // Start the orchestrator
    await orchestrator.start();
    
    // Show initial status
    console.log('\n📊 Initial System Status:');
    const status = orchestrator.getSystemStatus();
    console.log(JSON.stringify(status, null, 2));
    
    // Keep the process running
    console.log('\n🎮 Bot System is running... Press Ctrl+C to stop');
    
    // Handle graceful shutdown
    process.on('SIGINT', async () => {
      console.log('\n🛑 Shutting down bot system...');
      await orchestrator.stop();
      process.exit(0);
    });
    
    process.on('SIGTERM', async () => {
      console.log('\n🛑 Shutting down bot system...');
      await orchestrator.stop();
      process.exit(0);
    });
    
  } catch (error) {
    console.error('❌ Failed to start bot system:', error);
    process.exit(1);
  }
}

// Start the bot system
if (require.main === module) {
  startBotSystem();
}

module.exports = { startBotSystem };
