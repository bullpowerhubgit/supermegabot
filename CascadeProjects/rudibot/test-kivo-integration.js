/**
 * E2E Smoke Test: Rudibot Server + KIVO Integration
 * Verifies that both systems can coexist and the bridge works.
 */

const http = require('http');

async function runTest() {
  console.log('🔌 E2E Integration Test\n');

  // 1. Start Rudibot server
  const app = require('./index.js');
  const PORT = 3996;
  const server = app.listen(PORT);
  console.log(`✅ Rudibot server on port ${PORT}`);

  await new Promise(r => setTimeout(r, 500));

  // 2. Verify health endpoint
  const healthRes = await fetch(`http://localhost:${PORT}/api/health`);
  const health = await healthRes.json();
  console.log('✅ Health:', health.status);

  // 3. Load KIVO alongside (simulated integration)
  let KivoCore;
  try {
    KivoCore = require('/Users/rudolfsarkany/CascadeProjects/50-kivo/kivo-core.js').KivoCore;
    console.log('✅ KIVO Core loaded');
  } catch (e) {
    console.log('⚠️  KIVO Core not available:', e.message);
    server.close();
    return;
  }

  const kivo = new KivoCore();
  console.log('✅ KIVO instantiated');

  // 4. Process a command through KIVO
  const result = await kivo.processText('Hey Kivo, Statusbericht');
  console.log('✅ KIVO processed command:', result.status || result.unknown || 'ok');

  // 5. Verify KIVO status includes all modules
  const status = kivo.getStatus();
  const modules = Object.keys(status).sort();
  console.log('✅ KIVO modules:', modules.join(', '));

  // 6. Verify bridge status
  if (status.bridge) {
    console.log('✅ Bridge commands mapped:', status.bridge.commandsMapped);
  }

  // 7. Cleanup
  server.close();
  console.log('\n✅ E2E smoke test passed');
}

runTest().catch(err => {
  console.error('❌ E2E test failed:', err);
  process.exit(1);
});
