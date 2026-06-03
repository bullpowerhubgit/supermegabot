const app = require('./index.js');
const http = require('http');

const PORT = 3997;
const server = app.listen(PORT, async () => {
  console.log('✅ Server listening on port', PORT);

  const tests = [
    { path: '/api/health', method: 'GET', expect: 200 },
    { path: '/api/status', method: 'GET', expect: 200 },
    { path: '/webhook/telegram', method: 'GET', expect: 200 },
    { path: '/webhook/control', method: 'GET', expect: 200 },
    { path: '/webhook/klaviyo', method: 'GET', expect: 200 },
    { path: '/', method: 'GET', expect: 200 },
  ];

  for (const test of tests) {
    try {
      const res = await fetch(`http://localhost:${PORT}${test.path}`, { method: test.method });
      const body = await res.text();
      const ok = res.status === test.expect ? '✅' : '❌';
      console.log(`${ok} ${test.method} ${test.path} -> ${res.status} (${body.slice(0, 40)})`);
    } catch (err) {
      console.log(`❌ ${test.method} ${test.path} -> ERROR: ${err.message}`);
    }
  }

  console.log('\n✅ All routes tested');
  server.close();
  process.exit(0);
});

setTimeout(() => {
  console.log('⏱️ Timeout');
  server.close();
  process.exit(1);
}, 10000);
