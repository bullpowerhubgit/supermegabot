#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');
const readline = require('readline');
const https = require('https');

const DATA_DIR = path.join(os.homedir(), '.keyring');
const DATA_FILE = path.join(DATA_DIR, 'keys.enc');
const SALT_FILE = path.join(DATA_DIR, 'salt');
const ROTATION_FILE = path.join(DATA_DIR, 'rotation-log.json');

const ALGO = 'aes-256-gcm';
const KEYLEN = 32;
const IVLEN = 16;
const TAGLEN = 16;
const PBKDF2_ITER = 100_000;

// -- helpers ---------------------------------------------

function prompt(q) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise(resolve => rl.question(q, a => { rl.close(); resolve(a); }));
}

function promptHidden(q) {
  return new Promise(resolve => {
    const stdin = process.stdin;
    const stdout = process.stdout;

    if (!stdin.isTTY) {
      const rl = readline.createInterface({ input: stdin, output: stdout });
      rl.question(q, a => { rl.close(); resolve(a); });
      return;
    }

    stdout.write(q);
    stdin.setRawMode(true);
    stdin.resume();
    stdin.setEncoding('utf8');
    let val = '';
    stdin.on('data', ch => {
      const char = ch.toString();
      switch (char) {
        case '\n':
        case '\r':
        case '\u0004':
          stdin.setRawMode(false);
          stdin.pause();
          stdout.write('\n');
          resolve(val);
          break;
        case '\u0003':
          process.exit(1);
          break;
        case '\u007f': // backspace
        case '\b':
          if (val.length > 0) {
            val = val.slice(0, -1);
            stdout.write('\b \b');
          }
          break;
        default:
          val += char;
          stdout.write('*');
          break;
      }
    });
  });
}

function deriveKey(password, salt) {
  return crypto.pbkdf2Sync(password, salt, PBKDF2_ITER, KEYLEN, 'sha256');
}

function encrypt(text, password, salt) {
  const key = deriveKey(password, salt);
  const iv = crypto.randomBytes(IVLEN);
  const cipher = crypto.createCipheriv(ALGO, key, iv);
  const enc = Buffer.concat([cipher.update(text, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, enc]);
}

function decrypt(buffer, password, salt) {
  const key = deriveKey(password, salt);
  const iv = buffer.slice(0, IVLEN);
  const tag = buffer.slice(IVLEN, IVLEN + TAGLEN);
  const enc = buffer.slice(IVLEN + TAGLEN);
  const decipher = crypto.createDecipheriv(ALGO, key, iv);
  decipher.setAuthTag(tag);
  const dec = Buffer.concat([decipher.update(enc), decipher.final()]);
  return dec.toString('utf8');
}

function ensureDir() {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { mode: 0o700 });
}

function getSalt() {
  ensureDir();
  if (!fs.existsSync(SALT_FILE)) {
    const salt = crypto.randomBytes(32);
    fs.writeFileSync(SALT_FILE, salt, { mode: 0o600 });
    return salt;
  }
  return fs.readFileSync(SALT_FILE);
}

async function loadData(password) {
  const salt = getSalt();
  if (!fs.existsSync(DATA_FILE)) return { keys: [], projects: [] };
  const buf = fs.readFileSync(DATA_FILE);
  try {
    const json = decrypt(buf, password, salt);
    return JSON.parse(json);
  } catch {
    console.error('Fehler: Falsches Passwort oder beschädigte Daten.');
    process.exit(1);
  }
}

async function saveData(data, password) {
  const salt = getSalt();
  const buf = encrypt(JSON.stringify(data, null, 2), password, salt);
  fs.writeFileSync(DATA_FILE, buf, { mode: 0o600 });
}

function generateRandomKey(length = 48) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*';
  let out = '';
  const rnd = crypto.randomBytes(length);
  for (let i = 0; i < length; i++) {
    out += chars[rnd[i] % chars.length];
  }
  return out;
}

function mask(value) {
  if (value.length <= 8) return '****';
  return value.slice(0, 4) + '****' + value.slice(-4);
}

// -- validation -------------------------------------------

function validateKeyFormat(name, value, provider) {
  const patterns = {
    'OPENAI_API_KEY': /^sk-[A-Za-z0-9]{48}$/,
    'ANTHROPIC_API_KEY': /^sk-ant-api03-[A-Za-z0-9_-]{95}$/,
    'GOOGLE_API_KEY': /^[A-Za-z0-9_-]{39}$/,
    'VERCEL_TOKEN': /^vct_[A-Za-z0-9]{24}$/,
    'GITHUB_TOKEN': /^ghp_[A-Za-z0-9]{36}$/,
    'SLACK_BOT_TOKEN': /^xoxb-[0-9]{13}-[0-9]{13}-[A-Za-z0-9]{24}$/,
    'DISCORD_BOT_TOKEN': /^[A-Za-z0-9_-]{59}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27}$/,
    'STRIPE_SECRET_KEY': /^sk_test_[A-Za-z0-9]{24}$/,
    'STRIPE_LIVE_KEY': /^sk_live_[A-Za-z0-9]{24}$/,
    'TWILIO_AUTH_TOKEN': /^[A-Za-z0-9]{32}$/,
    'AWS_ACCESS_KEY_ID': /^[A-Z0-9]{20}$/,
    'AWS_SECRET_ACCESS_KEY': /^[A-Za-z0-9+/]{40}$/,
    'AZURE_OPENAI_KEY': /^[A-Za-z0-9]{32}$/,
    'HUGGINGFACE_TOKEN': /^hf_[A-Za-z0-9]{34}$/,
    'RESEND_API_KEY': /^re_[A-Za-z0-9]{32}$/,
    'SENDGRID_API_KEY': /^SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}$/,
    'NOTION_SECRET': /^secret_[A-Za-z0-9]{32}$/,
    'AIRTABLE_API_KEY': /^key[A-Za-z0-9]{17}$/,
    'MONGODB_API_KEY': /^[A-Za-z0-9_-]{64}$/
  };

  const pattern = patterns[name] || patterns[provider?.toUpperCase()];
  if (pattern && !pattern.test(value)) {
    return { valid: false, error: `Format stimmt nicht für ${name}` };
  }

  // Basic checks
  if (value.length < 8) {
    return { valid: false, error: 'Key zu kurz (mindestens 8 Zeichen)' };
  }

  if (value.includes(' ') || value.includes('\n')) {
    return { valid: false, error: 'Key enthält ungültige Zeichen' };
  }

  return { valid: true };
}

async function testApiKey(name, value, provider) {
  const testUrl = getTestUrl(name, provider);
  if (!testUrl) {
    return { status: 'unknown', message: 'Kein Test für diesen Provider verfügbar' };
  }

  return new Promise((resolve) => {
    const url = new URL(testUrl.url);
    const options = {
      hostname: url.hostname,
      port: url.port || 443,
      path: url.pathname + url.search,
      method: testUrl.method || 'GET',
      headers: testUrl.headers ? testUrl.headers(value) : {},
      timeout: 10000
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        const success = testUrl.validate ? testUrl.validate(res.statusCode, data) : res.statusCode < 400;
        resolve({
          status: success ? 'valid' : 'invalid',
          statusCode: res.statusCode,
          message: success ? 'Key funktioniert' : `HTTP ${res.statusCode}: ${data.slice(0, 100)}`
        });
      });
    });

    req.on('error', (err) => {
      resolve({ status: 'error', message: err.message });
    });

    req.on('timeout', () => {
      req.destroy();
      resolve({ status: 'timeout', message: 'Zeitüberschreitung' });
    });

    req.end();
  });
}

function getTestUrl(name, provider) {
  const tests = {
    'OPENAI_API_KEY': {
      url: 'https://api.openai.com/v1/models',
      method: 'GET',
      headers: (key) => ({ 'Authorization': `Bearer ${key}` }),
      validate: (status) => status === 200
    },
    'ANTHROPIC_API_KEY': {
      url: 'https://api.anthropic.com/v1/messages',
      method: 'POST',
      headers: (key) => ({ 
        'Authorization': `Bearer ${key}`,
        'Content-Type': 'application/json'
      }),
      validate: (status, data) => status === 400 || status === 200 // 400 = valid format, wrong body
    },
    'GOOGLE_API_KEY': {
      url: 'https://www.googleapis.com/customsearch/v1?key=TEST&cx=TEST&q=test',
      method: 'GET',
      validate: (status) => status !== 403
    },
    'GITHUB_TOKEN': {
      url: 'https://api.github.com/user',
      method: 'GET',
      headers: (key) => ({ 'Authorization': `Bearer ${key}` }),
      validate: (status) => status === 200
    },
    'VERCEL_TOKEN': {
      url: 'https://api.vercel.com/v9/user',
      method: 'GET',
      headers: (key) => ({ 'Authorization': `Bearer ${key}` }),
      validate: (status) => status === 200
    },
    'SLACK_BOT_TOKEN': {
      url: 'https://slack.com/api/auth.test',
      method: 'POST',
      headers: (key) => ({ 'Authorization': `Bearer ${key}` }),
      validate: (status, data) => {
        try {
          const result = JSON.parse(data);
          return result.ok === true;
        } catch {
          return false;
        }
      }
    },
    'DISCORD_BOT_TOKEN': {
      url: 'https://discord.com/api/v10/users/@me',
      method: 'GET',
      headers: (key) => ({ 'Authorization': `Bot ${key}` }),
      validate: (status) => status === 200
    },
    'STRIPE_SECRET_KEY': {
      url: 'https://api.stripe.com/v1/balance',
      method: 'GET',
      headers: (key) => ({ 'Authorization': `Bearer ${key}` }),
      validate: (status) => status === 200
    },
    'TWILIO_AUTH_TOKEN': {
      url: 'https://api.twilio.com/2010-04-01/Accounts.json',
      method: 'GET',
      headers: (key, sid) => ({ 'Authorization': `Basic ${Buffer.from(`${sid}:${key}`).toString('base64')}` }),
      validate: (status) => status === 200
    },
    'HUGGINGFACE_TOKEN': {
      url: 'https://huggingface.co/api/whoami',
      method: 'GET',
      headers: (key) => ({ 'Authorization': `Bearer ${key}` }),
      validate: (status) => status === 200
    },
    'RESEND_API_KEY': {
      url: 'https://api.resend.com/domains',
      method: 'GET',
      headers: (key) => ({ 'Authorization': `Bearer ${key}` }),
      validate: (status) => status === 200
    },
    'SENDGRID_API_KEY': {
      url: 'https://api.sendgrid.com/v3/user/account',
      method: 'GET',
      headers: (key) => ({ 'Authorization': `Bearer ${key}` }),
      validate: (status) => status === 200
    },
    'NOTION_SECRET': {
      url: 'https://api.notion.com/v1/users/me',
      method: 'GET',
      headers: (key) => ({ 
        'Authorization': `Bearer ${key}`,
        'Notion-Version': '2022-06-28'
      }),
      validate: (status) => status === 200
    },
    'AIRTABLE_API_KEY': {
      url: 'https://api.airtable.com/v0/meta/bases',
      method: 'GET',
      headers: (key) => ({ 'Authorization': `Bearer ${key}` }),
      validate: (status) => status === 200
    }
  };

  return tests[name] || tests[provider?.toUpperCase()] || null;
}

async function validateSingleKey(key) {
  const results = [];

  // Format validation
  const formatCheck = validateKeyFormat(key.name, key.value, key.provider);
  results.push({
    type: 'format',
    status: formatCheck.valid ? 'pass' : 'fail',
    message: formatCheck.error || 'Format gültig'
  });

  // API test (if available)
  if (formatCheck.valid) {
    const apiTest = await testApiKey(key.name, key.value, key.provider);
    results.push({
      type: 'api',
      status: apiTest.status === 'valid' ? 'pass' : apiTest.status === 'unknown' ? 'skip' : 'fail',
      message: apiTest.message
    });
  }

  return results;
}

// -- commands --------------------------------------------

async function init() {
  ensureDir();
  const pw1 = await promptHidden('Master-Passwort festlegen: ');
  process.stdout.write('\n');
  const pw2 = await promptHidden('Master-Passwort wiederholen: ');
  process.stdout.write('\n');
  if (pw1 !== pw2) {
    console.error('Fehler: Passwörter stimmen nicht überein.');
    process.exit(1);
  }
  if (!pw1 || pw1.length < 6) {
    console.error('Fehler: Passwort muss mindestens 6 Zeichen haben.');
    process.exit(1);
  }
  const salt = getSalt();
  const data = { keys: [], projects: [] };
  saveData(data, pw1);
  console.log('Keyring initialisiert. Deine API-Keys werden in ' + DATA_FILE + ' verschlüsselt gespeichert.');
}

async function add() {
  const password = await promptHidden('Master-Passwort: ');
  process.stdout.write('\n');
  const data = await loadData(password);

  const name = await prompt('Name des Keys (z.B. OPENAI_API_KEY): ');
  const value = await promptHidden('API-Key-Wert: ');
  process.stdout.write('\n');
  const provider = await prompt('Provider/Service (optional, z.B. OpenAI): ');
  const project = await prompt('Projekt zuordnen (optional): ');

  const existing = data.keys.find(k => k.name === name);
  if (existing) {
    const overwrite = await prompt('Key existiert bereits. Überschreiben? (j/n): ');
    if (overwrite.toLowerCase() !== 'j') return;
    existing.value = value;
    existing.provider = provider || existing.provider;
    existing.project = project || existing.project;
    existing.updatedAt = new Date().toISOString();
    existing.history = existing.history || [];
    existing.history.push({ value: existing.value, rotatedAt: existing.updatedAt });
  } else {
    data.keys.push({
      name,
      value,
      provider: provider || '',
      project: project || '',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      history: []
    });
  }

  await saveData(data, password);
  console.log(`Key "${name}" gespeichert.`);
}

async function list() {
  const password = await promptHidden('Master-Passwort: ');
  process.stdout.write('\n');
  const data = await loadData(password);

  if (data.keys.length === 0) {
    console.log('Keine Keys gespeichert.');
    return;
  }

  console.log('\n' + '-'.repeat(60));
  console.log('Gespeicherte API-Keys');
  console.log('-'.repeat(60));

  for (const k of data.keys) {
    const proj = k.project ? ` [Projekt: ${k.project}]` : '';
    const prov = k.provider ? ` (${k.provider})` : '';
    console.log(`  ${k.name}${prov}${proj}`);
    console.log(`    Wert: ${mask(k.value)}`);
    console.log(`    Erstellt: ${k.createdAt.slice(0, 10)} | Aktualisiert: ${k.updatedAt.slice(0, 10)}`);
    if (k.history && k.history.length) {
      console.log(`    Rotierungen: ${k.history.length}`);
    }
    console.log();
  }
  console.log('-'.repeat(60));
}

async function show() {
  const name = process.argv[3];
  if (!name) { console.error('Usage: keyring show <name>'); process.exit(1); }

  const password = await promptHidden('Master-Passwort: ');
  process.stdout.write('\n');
  const data = await loadData(password);
  const key = data.keys.find(k => k.name === name);
  if (!key) { console.error('Key nicht gefunden.'); process.exit(1); }

  console.log(`\n${key.name}=${key.value}`);
}

async function remove() {
  const name = process.argv[3];
  if (!name) { console.error('Usage: keyring remove <name>'); process.exit(1); }

  const password = await promptHidden('Master-Passwort: ');
  process.stdout.write('\n');
  const data = await loadData(password);
  const idx = data.keys.findIndex(k => k.name === name);
  if (idx === -1) { console.error('Key nicht gefunden.'); process.exit(1); }

  const confirm = await prompt(`Key "${name}" wirklich löschen? (j/n): `);
  if (confirm.toLowerCase() !== 'j') return;

  data.keys.splice(idx, 1);
  await saveData(data, password);
  console.log(`Key "${name}" gelöscht.`);
}

async function rotate() {
  const name = process.argv[3];
  if (!name) { console.error('Usage: keyring rotate <name>'); process.exit(1); }

  const password = await promptHidden('Master-Passwort: ');
  process.stdout.write('\n');
  const data = await loadData(password);
  const key = data.keys.find(k => k.name === name);
  if (!key) { console.error('Key nicht gefunden.'); process.exit(1); }

  console.log(`\nAktueller Wert: ${mask(key.value)}`);
  const useAuto = await prompt('Neuen Key automatisch generieren? (j/n): ');
  let newValue;
  if (useAuto.toLowerCase() === 'j') {
    newValue = generateRandomKey();
    console.log(`Neuer Key generiert: ${mask(newValue)}`);
  } else {
    newValue = await promptHidden('Neuer API-Key-Wert: ');
    process.stdout.write('\n');
  }

  key.history = key.history || [];
  key.history.push({ value: key.value, rotatedAt: key.updatedAt });
  key.value = newValue;
  key.updatedAt = new Date().toISOString();

  await saveData(data, password);
  console.log(`Key "${name}" rotiert.`);

  // rotation log
  const logEntry = {
    name,
    rotatedAt: key.updatedAt,
    provider: key.provider,
    project: key.project,
    note: 'Bitte neuen Key im Provider-Dashboard aktivieren und alten deaktivieren.'
  };
  const existingLog = fs.existsSync(ROTATION_FILE) ? JSON.parse(fs.readFileSync(ROTATION_FILE, 'utf8')) : [];
  existingLog.push(logEntry);
  fs.writeFileSync(ROTATION_FILE, JSON.stringify(existingLog, null, 2));
}

async function rotateAll() {
  const password = await promptHidden('Master-Passwort: ');
  process.stdout.write('\n');
  const data = await loadData(password);

  if (data.keys.length === 0) {
    console.log('Keine Keys zum Rotieren vorhanden.');
    return;
  }

  const confirm = await prompt(`\nWARNUNG: ${data.keys.length} Key(s) werden rotiert. Fortfahren? (j/n): `);
  if (confirm.toLowerCase() !== 'j') return;

  const rotated = [];
  for (const key of data.keys) {
    key.history = key.history || [];
    key.history.push({ value: key.value, rotatedAt: key.updatedAt });
    key.value = generateRandomKey();
    key.updatedAt = new Date().toISOString();
    rotated.push({ name: key.name, provider: key.provider, project: key.project });
  }

  await saveData(data, password);

  const logEntry = {
    rotatedAt: new Date().toISOString(),
    keys: rotated,
    note: 'Alle Keys rotiert. Bitte jeweils im Provider-Dashboard aktualisieren.'
  };
  const existingLog = fs.existsSync(ROTATION_FILE) ? JSON.parse(fs.readFileSync(ROTATION_FILE, 'utf8')) : [];
  existingLog.push(logEntry);
  fs.writeFileSync(ROTATION_FILE, JSON.stringify(existingLog, null, 2));

  console.log('\n✅ Alle Keys rotiert!');
  console.log('\nZusammenfassung:');
  for (const r of rotated) {
    const prov = r.provider ? ` (${r.provider})` : '';
    const proj = r.project ? ` [${r.project}]` : '';
    console.log(`  - ${r.name}${prov}${proj}`);
  }
  console.log(`\nWICHTIG: Die neu generierten Keys sind PLATZHALTER.`);
  console.log(`Gehe zu den jeweiligen Provider-Dashboards und erstelle echte neue Keys.`);
  console.log(`Speichere die echten Keys dann mit "keyring add <name>".`);
}

async function exportEnv() {
  const projectName = process.argv[3];
  const outFile = process.argv[4] || '.env';

  const password = await promptHidden('Master-Passwort: ');
  process.stdout.write('\n');
  const data = await loadData(password);

  let keys = data.keys;
  if (projectName) {
    keys = keys.filter(k => k.project === projectName);
    if (keys.length === 0) {
      console.log(`Keine Keys für Projekt "${projectName}" gefunden.`);
      return;
    }
  }

  let env = '# Exported from Keyring\n';
  env += `# Exportiert am: ${new Date().toISOString()}\n`;
  if (projectName) env += `# Projekt: ${projectName}\n`;
  env += '\n';
  for (const k of keys) {
    const prov = k.provider ? ` # ${k.provider}` : '';
    env += `${k.name}=${k.value}${prov}\n`;
  }

  fs.writeFileSync(outFile, env);
  console.log(`${keys.length} Key(s) nach "${outFile}" exportiert.`);
}

async function generateEnv() {
  const password = await promptHidden('Master-Passwort: ');
  process.stdout.write('\n');
  const data = await loadData(password);

  if (data.keys.length === 0) {
    console.log('Keine Keys gespeichert.');
    return;
  }

  console.log('\n# Kopiere das in deine .env Datei:\n');
  for (const k of data.keys) {
    console.log(`${k.name}=${k.value}`);
  }
}

async function importEnv() {
  const filePath = process.argv[3];
  if (!filePath) { console.error('Usage: keyring import <.env-file>'); process.exit(1); }
  if (!fs.existsSync(filePath)) { console.error('Datei nicht gefunden.'); process.exit(1); }

  const password = await promptHidden('Master-Passwort: ');
  process.stdout.write('\n');
  const data = await loadData(password);

  const lines = fs.readFileSync(filePath, 'utf8').split('\n');
  let added = 0;
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const name = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1).trim();
    if (!name || !value) continue;

    const existing = data.keys.find(k => k.name === name);
    if (existing) {
      existing.value = value;
      existing.updatedAt = new Date().toISOString();
    } else {
      data.keys.push({
        name,
        value,
        provider: '',
        project: '',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        history: []
      });
    }
    added++;
  }

  await saveData(data, password);
  console.log(`${added} Key(s) aus "${filePath}" importiert.`);
}

async function validate() {
  const keyName = process.argv[3];
  const password = await promptHidden('Master-Passwort: ');
  process.stdout.write('\n');
  const data = await loadData(password);

  if (keyName) {
    // Validate single key
    const key = data.keys.find(k => k.name === keyName);
    if (!key) {
      console.error(`Key "${keyName}" nicht gefunden.`);
      process.exit(1);
    }

    console.log(`\nValidiere: ${key.name} (${key.provider || 'unbekannt'})`);
    console.log('-'.repeat(40));

    const results = await validateSingleKey(key);
    for (const result of results) {
      const icon = result.status === 'pass' ? '✅' : result.status === 'skip' ? '⏭️' : '❌';
      console.log(`${icon} ${result.type.toUpperCase()}: ${result.message}`);
    }
  } else {
    // Validate all keys
    if (data.keys.length === 0) {
      console.log('Keine Keys zum Validieren vorhanden.');
      return;
    }

    console.log('\nValidiere alle Keys...');
    console.log('-'.repeat(60));

    let total = 0;
    let passed = 0;
    let failed = 0;

    for (const key of data.keys) {
      console.log(`\n🔑 ${key.name} (${key.provider || 'unbekannt'})`);
      const results = await validateSingleKey(key);
      
      for (const result of results) {
        total++;
        if (result.status === 'pass') passed++;
        else if (result.status === 'fail') failed++;

        const icon = result.status === 'pass' ? '✅' : result.status === 'skip' ? '⏭️' : '❌';
        console.log(`  ${icon} ${result.type.toUpperCase()}: ${result.message}`);
      }
    }

    console.log('\n' + '='.repeat(60));
    console.log(`Zusammenfassung: ${passed}/${total} Tests bestanden, ${failed} fehlgeschlagen`);
    
    if (failed > 0) {
      console.log('\n⚠️  Einige Keys funktionieren nicht. Überprüfe die fehlerhaften Keys.');
    }
  }
}

async function health() {
  const password = await promptHidden('Master-Passwort: ');
  process.stdout.write('\n');
  const data = await loadData(password);

  if (data.keys.length === 0) {
    console.log('Keine Keys für Health-Check vorhanden.');
    return;
  }

  console.log('\nHealth-Check für alle API-Keys');
  console.log('-'.repeat(60));

  const results = [];
  for (const key of data.keys) {
    process.stdout.write(`Testing ${key.name}... `);
    
    const keyResults = await validateSingleKey(key);
    const apiTest = keyResults.find(r => r.type === 'api');
    
    let status = 'unknown';
    if (apiTest) {
      status = apiTest.status === 'pass' ? 'healthy' : apiTest.status === 'fail' ? 'unhealthy' : 'unknown';
    }

    results.push({
      name: key.name,
      provider: key.provider || 'unbekannt',
      project: key.project || '',
      status,
      lastChecked: new Date().toISOString(),
      details: keyResults
    });

    const icon = status === 'healthy' ? '✅' : status === 'unhealthy' ? '❌' : '❓';
    console.log(`${icon} ${status}`);
  }

  // Save health report
  const healthFile = path.join(DATA_DIR, 'health-report.json');
  fs.writeFileSync(healthFile, JSON.stringify(results, null, 2));

  console.log('\n' + '='.repeat(60));
  const healthy = results.filter(r => r.status === 'healthy').length;
  const unhealthy = results.filter(r => r.status === 'unhealthy').length;
  const unknown = results.filter(r => r.status === 'unknown').length;

  console.log(`Gesund: ${healthy} | Ungesund: ${unhealthy} | Unbekannt: ${unknown}`);
  console.log(`\nDetails gespeichert in: ${healthFile}`);
}

async function showLog() {
  if (!fs.existsSync(ROTATION_FILE)) {
    console.log('Kein Rotations-Log vorhanden.');
    return;
  }
  const log = JSON.parse(fs.readFileSync(ROTATION_FILE, 'utf8'));
  console.log('\n' + '-'.repeat(60));
  console.log('Rotations-Log');
  console.log('-'.repeat(60));
  for (const entry of log) {
    if (entry.keys) {
      console.log(`\n[${entry.rotatedAt}] MASSENROTATION:`);
      for (const k of entry.keys) {
        console.log(`  - ${k.name} (${k.provider || 'unbekannt'})`);
      }
    } else {
      console.log(`\n[${entry.rotatedAt}] ${entry.name} (${entry.provider || 'unbekannt'})`);
    }
    console.log(`  -> ${entry.note}`);
  }
}

function printHelp() {
  console.log(`
Keyring CLI – API-Key Verwaltung & Rotation

Usage: keyring <command> [options]

Commands:
  init                          Initialisiert den verschlüsselten Speicher
  add                           Neuen API-Key hinzufügen
  list                          Alle Keys auflisten (maskiert)
  show <name>                   Einen Key im Klartext anzeigen
  remove <name>                 Einen Key löschen
  rotate <name>                 Einen einzelnen Key rotieren
  rotate-all                    ALLE Keys auf einmal rotieren
  validate [name]               Key(s) auf Gültigkeit testen
  health                        Health-Check für alle Keys
  export [project] [file]       .env Datei erstellen (default: .env)
  generate                      Alle Keys als .env Format ausgeben
  import <file>                 API-Keys aus .env Datei importieren
  log                           Rotations-Log anzeigen
  help                          Diese Hilfe anzeigen

Beispiele:
  keyring add                   # Fügt OPENAI_API_KEY, ANTHROPIC_API_KEY etc. hinzu
  keyring validate              # Validiert alle Keys
  keyring validate OPENAI_API_KEY # Validiert einen bestimmten Key
  keyring health                # Health-Check für alle Keys
  keyring export myapp .env     # Exportiert Keys für Projekt "myapp" nach .env
  keyring rotate-all            # Rotiert ALLE gespeicherten Keys

Unterstützte Provider für Tests:
  OpenAI, Anthropic, Google, GitHub, Vercel, Slack, Discord,
  Stripe, Twilio, HuggingFace, Resend, SendGrid, Notion, Airtable

Daten werden verschlüsselt gespeichert in: ~/.keyring/
`);
}

// -- main ------------------------------------------------

async function main() {
  const cmd = process.argv[2];

  switch (cmd) {
    case 'init':      await init(); break;
    case 'add':       await add(); break;
    case 'list':      await list(); break;
    case 'show':      await show(); break;
    case 'remove':    await remove(); break;
    case 'rotate':    await rotate(); break;
    case 'rotate-all':await rotateAll(); break;
    case 'validate':  await validate(); break;
    case 'health':    await health(); break;
    case 'export':    await exportEnv(); break;
    case 'generate':  await generateEnv(); break;
    case 'import':    await importEnv(); break;
    case 'log':       await showLog(); break;
    case 'help':
    case '--help':
    case '-h':
    default:          printHelp(); break;
  }
}

main().catch(e => { console.error(e); process.exit(1); });
