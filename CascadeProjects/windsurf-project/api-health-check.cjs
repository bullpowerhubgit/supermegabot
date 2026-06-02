const fs = require('fs');
const axios = require('axios');

const envContent = fs.readFileSync('.env', 'utf8');
const envVars = {};
envContent.split('\n').forEach(line => {
  const [key, ...valueParts] = line.split('=');
  if (key && valueParts.length > 0 && !line.trim().startsWith('#') && !line.trim().startsWith('//')) {
    envVars[key.trim()] = valueParts.join('=').trim();
  }
});

console.log('🔍 API HEALTH CHECK - SuperMegaBot');
console.log('====================================\n');

const apis = [
  { name: 'Stripe', envKey: 'STRIPE_SECRET_KEY', url: 'https://api.stripe.com/v1/account', method: 'GET' },
  { name: 'OpenAI', envKey: 'OPENAI_API_KEY', url: 'https://api.openai.com/v1/models', method: 'GET' },
  { name: 'Anthropic', envKey: 'ANTHROPIC_API_KEY', url: 'https://api.anthropic.com/v1/messages', method: 'POST', body: { model: 'claude-3-haiku-20240307', max_tokens: 10, messages: [{ role: 'user', content: 'test' }] } },
  { name: 'Telegram Bot', envKey: 'TELEGRAM_BOT_TOKEN', url: 'https://api.telegram.org/botTOKEN/getMe', method: 'GET', telegram: true },
  { name: 'GitHub', envKey: 'GITHUB_TOKEN', url: 'https://api.github.com/user', method: 'GET' },
  { name: 'Supabase', envKey: 'SUPABASE_SERVICE_KEY', url: 'https://qyrjeckzacjaazkpvnjk.supabase.co/rest/v1/', method: 'GET', params: { select: '*' } }
];

async function testAPIs() {
  const results = [];
  
  for (const api of apis) {
    if (!envVars[api.envKey]) {
      console.log('⚠️  ' + api.name + ': Key fehlt');
      continue;
    }
    
    try {
      const config = {
        method: api.method,
        timeout: 10000,
        headers: {}
      };
      
      if (api.telegram) {
        config.url = 'https://api.telegram.org/bot' + envVars.TELEGRAM_BOT_TOKEN + '/getMe';
      } else {
        config.url = api.url;
        config.headers['Authorization'] = 'Bearer ' + envVars[api.envKey];
      }
      
      if (api.body) config.data = api.body;
      if (api.params) config.params = api.params;
      
      const response = await axios(config);
      
      results.push({ name: api.name, status: '✅ WORKING', code: response.status });
      console.log('✅ ' + api.name + ': WORKING (HTTP ' + response.status + ')');
      
    } catch (error) {
      const status = error.response ? error.response.status : 'ERR';
      const msg = error.response ? (error.response.data?.error?.message || error.response.statusText) : error.message;
      results.push({ name: api.name, status: '❌ FAILED', code: status, error: msg });
      console.log('❌ ' + api.name + ': FAILED (HTTP ' + status + ' - ' + msg.substring(0, 80) + ')');
    }
    
    await new Promise(r => setTimeout(r, 500));
  }
  
  console.log('\n📊 ZUSAMMENFASSUNG');
  console.log('==================');
  const ok = results.filter(r => r.status.includes('WORKING')).length;
  const fail = results.filter(r => r.status.includes('FAILED')).length;
  console.log('Getestet: ' + results.length);
  console.log('Funktionierend: ' + ok + ' ✅');
  console.log('Fehler: ' + fail + ' ❌');
  console.log('Erfolgsrate: ' + Math.round((ok/results.length)*100) + '%');
  
  fs.writeFileSync('API_HEALTH_CHECK_RESULTS.json', JSON.stringify(results, null, 2));
  console.log('\n💾 Ergebnisse gespeichert in: API_HEALTH_CHECK_RESULTS.json');
}

testAPIs().catch(console.error);
