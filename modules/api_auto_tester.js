#!/usr/bin/env node
/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║  API Auto-Tester — Jede API wird VOR Einbau getestet            ║
 * ║  Blockiert Integration bei Fehlern · Cache · Retry-Logik        ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

const https = require('https');
const http = require('http');
const fs = require('fs').promises;
const path = require('path');

const CACHE_DIR = path.join(__dirname, '..', '.api_test_cache');
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 Minuten Cache

// API-Registrierung: Alle APIs die vor Einbau getestet werden müssen
const API_REGISTRY = {
    // Shopify
    shopify: {
        name: 'Shopify Admin API',
        baseUrl: process.env.SHOPIFY_SHOP_URL,
        testEndpoint: '/admin/api/2024-04/shop.json',
        headers: () => ({
            'X-Shopify-Access-Token': process.env.SHOPIFY_ACCESS_TOKEN,
        }),
        requiredEnv: ['SHOPIFY_SHOP_URL', 'SHOPIFY_ACCESS_TOKEN'],
        timeout: 10000,
    },
    // Telegram Bot API
    telegram: {
        name: 'Telegram Bot API',
        baseUrl: 'https://api.telegram.org',
        testEndpoint: (token) => `/bot${token}/getMe`,
        requiredEnv: ['TELEGRAM_BOT_TOKEN'],
        timeout: 8000,
    },
    // OpenAI
    openai: {
        name: 'OpenAI API',
        baseUrl: 'https://api.openai.com',
        testEndpoint: '/v1/models',
        headers: () => ({
            'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
        }),
        requiredEnv: ['OPENAI_API_KEY'],
        timeout: 10000,
    },
    // Ollama (lokal)
    ollama: {
        name: 'Ollama LLM',
        baseUrl: process.env.OLLAMA_HOST || 'http://localhost:11434',
        testEndpoint: '/api/tags',
        requiredEnv: [], // Optional, lokal
        timeout: 5000,
    },
    // Supabase
    supabase: {
        name: 'Supabase REST API',
        baseUrl: `${process.env.SUPABASE_URL}/rest/v1`,
        testEndpoint: '',
        headers: () => ({
            'apikey': process.env.SUPABASE_ANON_KEY,
            'Authorization': `Bearer ${process.env.SUPABASE_ANON_KEY}`,
        }),
        requiredEnv: ['SUPABASE_URL', 'SUPABASE_ANON_KEY'],
        timeout: 8000,
    },
    // Anthropic / Claude
    anthropic: {
        name: 'Anthropic Claude API',
        baseUrl: 'https://api.anthropic.com',
        testEndpoint: '/v1/models',
        headers: () => ({
            'x-api-key': process.env.ANTHROPIC_API_KEY,
            'anthropic-version': '2023-06-01',
        }),
        requiredEnv: ['ANTHROPIC_API_KEY'],
        timeout: 10000,
    },
    // Guardian API (intern)
    guardian: {
        name: 'RudiBot Guardian API',
        baseUrl: `http://${process.env.GUARDIAN_API_HOST || 'localhost'}:${process.env.GUARDIAN_API_PORT || 3201}`,
        testEndpoint: '/health',
        headers: () => ({
            'X-API-Key': process.env.GUARDIAN_API_SECRET,
        }),
        requiredEnv: ['GUARDIAN_API_SECRET'],
        timeout: 5000,
    },
};

/**
 * Cache-Key generieren
 */
function cacheKey(apiKey) {
    return path.join(CACHE_DIR, `${apiKey}_test.json`);
}

/**
 * Cache lesen (wenn noch gültig)
 */
async function readCache(apiKey) {
    try {
        const cacheFile = cacheKey(apiKey);
        const data = JSON.parse(await fs.readFile(cacheFile, 'utf-8'));
        const age = Date.now() - data.timestamp;
        if (age < CACHE_TTL_MS) {
            return data.result;
        }
    } catch (e) {
        // Cache miss oder ungültig
    }
    return null;
}

/**
 * Cache schreiben
 */
async function writeCache(apiKey, result) {
    try {
        await fs.mkdir(CACHE_DIR, { recursive: true });
        await fs.writeFile(
            cacheKey(apiKey),
            JSON.stringify({ timestamp: Date.now(), result }, null, 2)
        );
    } catch (e) {
        console.warn(`[API-Tester] Cache write failed: ${e.message}`);
    }
}

/**
 * Umgebungsvariablen prüfen
 */
function checkEnv(apiConfig) {
    const missing = [];
    for (const envVar of apiConfig.requiredEnv) {
        if (!process.env[envVar]) {
            missing.push(envVar);
        }
    }
    if (missing.length > 0) {
        return {
            ok: false,
            error: `Fehlende Env-Vars: ${missing.join(', ')}`,
        };
    }
    return { ok: true };
}

/**
 * Einzelne API testen
 */
async function testApi(apiKey, apiConfig) {
    // 1. Cache check
    const cached = await readCache(apiKey);
    if (cached) {
        console.log(`  [${apiConfig.name}] ✅ Cache-Hit`);
        return cached;
    }

    // 2. Env-Check
    const envCheck = checkEnv(apiConfig);
    if (!envCheck.ok) {
        const result = {
            api: apiKey,
            name: apiConfig.name,
            status: 'SKIP',
            ok: false,
            error: envCheck.error,
            latency: 0,
            timestamp: new Date().toISOString(),
        };
        await writeCache(apiKey, result);
        return result;
    }

    // 3. HTTP-Test
    const start = Date.now();
    try {
        let testUrl;
        if (typeof apiConfig.testEndpoint === 'function') {
            testUrl = `${apiConfig.baseUrl}${apiConfig.testEndpoint(process.env[apiConfig.requiredEnv[0]])}`;
        } else {
            testUrl = `${apiConfig.baseUrl}${apiConfig.testEndpoint}`;
        }

        const headers = apiConfig.headers ? apiConfig.headers() : {};

        // Built-in HTTP(S) request (zero dependencies)
        const urlObj = new URL(testUrl);
        const client = urlObj.protocol === 'https:' ? https : http;
        const requestOptions = {
            hostname: urlObj.hostname,
            port: urlObj.port || (urlObj.protocol === 'https:' ? 443 : 80),
            path: urlObj.pathname + urlObj.search,
            method: 'GET',
            headers: { ...headers, 'User-Agent': 'RudiBot-API-Tester/1.0' },
            timeout: apiConfig.timeout,
        };

        const response = await new Promise((resolve, reject) => {
            const req = client.request(requestOptions, (res) => {
                resolve({ status: res.statusCode, headers: res.headers });
            });
            req.on('error', reject);
            req.on('timeout', () => { req.destroy(); reject(new Error('TIMEOUT')); });
            req.end();
        });

        const latency = Date.now() - start;
        const status = response.status || 0;
        const reachable = status < 500 && status > 0;
        const authenticated = status !== 401 && status !== 403;

        const result = {
            api: apiKey,
            name: apiConfig.name,
            status: reachable ? 'OK' : 'FAIL',
            ok: reachable && authenticated,
            httpStatus: status,
            latency,
            error: reachable && authenticated ? null : `HTTP ${status}`,
            timestamp: new Date().toISOString(),
        };

        await writeCache(apiKey, result);
        return result;

    } catch (error) {
        const latency = Date.now() - start;
        const result = {
            api: apiKey,
            name: apiConfig.name,
            status: 'ERROR',
            ok: false,
            httpStatus: 0,
            latency,
            error: error.code || error.message,
            timestamp: new Date().toISOString(),
        };
        await writeCache(apiKey, result);
        return result;
    }
}

/**
 * ALLE APIs testen (Full Suite)
 */
async function testAllApis() {
    console.log('\n╔═══════════════════════════════════════════════════════════╗');
    console.log('║  🧪 API Auto-Tester — Vor-Einbau Prüfung                  ║');
    console.log('╚═══════════════════════════════════════════════════════════╝\n');

    const results = [];
    for (const [apiKey, apiConfig] of Object.entries(API_REGISTRY)) {
        const result = await testApi(apiKey, apiConfig);
        results.push(result);

        const icon = result.ok ? '✅' : (result.status === 'SKIP' ? '⏭️' : '❌');
        const statusStr = result.httpStatus > 0 ? `HTTP ${result.httpStatus}` : result.error;
        console.log(`  ${icon} ${result.name.padEnd(25)} ${result.status.padEnd(6)} ${result.latency.toString().padStart(5)}ms  ${statusStr}`);
    }

    // Zusammenfassung
    const passed = results.filter(r => r.ok).length;
    const skipped = results.filter(r => r.status === 'SKIP').length;
    const failed = results.filter(r => !r.ok && r.status !== 'SKIP').length;
    const total = results.length;

    console.log('\n' + '─'.repeat(65));
    console.log(`Ergebnis: ${passed} OK | ${skipped} SKIP (Env fehlt) | ${failed} FAIL | ${total} Total`);

    if (failed > 0) {
        console.log('\n❌ BLOCKIERT: Diese APIs dürfen NICHT eingebaut werden bis sie repariert sind:');
        for (const r of results.filter(r => !r.ok && r.status !== 'SKIP')) {
            console.log(`   - ${r.name}: ${r.error}`);
        }
    } else {
        console.log('\n✅ ALLE APIs OK — Integration erlaubt!');
    }

    return { results, passed, skipped, failed, total };
}

/**
 * API vor Einbau testen — ERZWINGT Blockade bei Fehler
 */
async function requireApiBeforeIntegration(apiKey, context = '') {
    const config = API_REGISTRY[apiKey];
    if (!config) {
        throw new Error(`Unbekannte API: ${apiKey}`);
    }

    console.log(`\n🔒 Pre-Integration Check: ${config.name} (${context})`);
    const result = await testApi(apiKey, config);

    if (!result.ok) {
        const err = new Error(
            `API "${config.name}" INTEGRIERT SICH NICHT: ${result.error}\n` +
            `Fix erforderlich bevor ${context} startet.`
        );
        err.apiResult = result;
        err.isApiBlocked = true;
        throw err;
    }

    console.log(`   ✅ ${config.name} freigegeben für Integration.`);
    return result;
}

/**
 * CLI-Aufruf
 */
if (require.main === module) {
    testAllApis().then(({ failed }) => {
        process.exit(failed > 0 ? 1 : 0);
    }).catch(err => {
        console.error('API Auto-Tester Fehler:', err.message);
        process.exit(1);
    });
}

module.exports = {
    testAllApis,
    testApi,
    requireApiBeforeIntegration,
    API_REGISTRY,
};
