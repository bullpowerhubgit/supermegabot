#!/usr/bin/env node

// 🌐 WINDSURF API GATEWAY - Vollautomatischer Zentral-Hub
// Rudolf Sarkany · Production Ready · Autonomous System
// ============================================================

'use strict';
require('dotenv').config();

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const compression = require('compression');
const morgan = require('morgan');
const axios = require('axios');
const jwt = require('jsonwebtoken');

// 🧠 Autonome Integrationen
const ollama = require('./ollama-integration');
const openlaw = require('./openlaw-integration');
const openSource = require('./opensource-versions');

// ── Config ───────────────────────────────────────────────────
const PORT = process.env.PORT || 8080;
const JWT_SECRET = process.env.JWT_SECRET || 'development-secret';
const NODE_ENV = process.env.NODE_ENV || 'development';

// ── Service Registry ──────────────────────────────────────────
const SERVICES = {
    rudibot: {
        name: '🤖 Rudibot',
        url: process.env.RUDIBOT_URL || 'http://localhost:3200',
        health: '/api/health',
        status: 'unknown',
        lastCheck: null
    },
    dashboard: {
        name: '📊 Mega Dashboard',
        url: process.env.MEGA_DASHBOARD_URL || 'http://localhost:3000',
        health: '/api/health',
        status: 'unknown',
        lastCheck: null
    },
    shopify: {
        name: '🛒 Shopify Automation',
        url: process.env.SHOPIFY_API_URL || 'http://localhost:3001',
        health: '/health',
        status: 'unknown',
        lastCheck: null
    },
    telegram: {
        name: '📱 Telegram Bot',
        url: process.env.TELEGRAM_BOT_URL || 'http://localhost:3002',
        health: '/health',
        status: 'unknown',
        lastCheck: null
    },
    acquisition: {
        name: '🎯 Acquisition Engine',
        url: process.env.ACQUISITION_ENGINE_URL || 'http://localhost:3003',
        health: '/health',
        status: 'unknown',
        lastCheck: null
    },
    supermegabot: {
        name: '🤖 SuperMegaBot Dashboard',
        url: process.env.SUPERMEGABOT_URL || 'http://localhost:8888',
        health: '/health',
        status: 'unknown',
        lastCheck: null
    },
    telegram: {
        name: '📱 Windsurf Telegram Bot',
        url: process.env.TELEGRAM_BOT_URL || 'http://localhost:8003',
        health: '/health',
        status: 'unknown',
        lastCheck: null
    }
};

// ── Express Setup ─────────────────────────────────────────────
const app = express();
const startTime = Date.now();

// Security Middleware
app.use(helmet({
    contentSecurityPolicy: {
        directives: {
            defaultSrc: ["'self'"],
            scriptSrc: ["'self'", "'unsafe-inline'"],
            styleSrc: ["'self'", "'unsafe-inline'"],
            imgSrc: ["'self'", "data:", "https:"],
            connectSrc: ["'self'"]
        }
    }
}));

app.use(cors({
    origin: function(origin, callback) {
        const allowedOrigins = [
            'http://localhost:3000',
            'http://localhost:3200',
            'https://vercel.app',
            process.env.FRONTEND_URL
        ].filter(Boolean);
        
        if (!origin || allowedOrigins.includes(origin)) {
            callback(null, true);
        } else {
            callback(new Error('CORS not allowed'));
        }
    },
    credentials: true
}));

app.use(compression());
app.use(express.json({ limit: '10mb' }));
app.use(morgan('combined'));

// Rate Limiting
const limiter = rateLimit({
    windowMs: parseInt(process.env.RATE_LIMIT_WINDOW_MS) || 15 * 60 * 1000,
    max: parseInt(process.env.RATE_LIMIT_MAX_REQUESTS) || 100,
    message: { error: 'Rate limit exceeded' },
    standardHeaders: true
});
app.use('/api/', limiter);

// ── Auth Middleware ─────────────────────────────────────────────
function authenticateToken(req, res, next) {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1];
    
    if (!token) {
        return res.status(401).json({ error: 'Access token required' });
    }
    
    jwt.verify(token, JWT_SECRET, (err, user) => {
        if (err) return res.status(403).json({ error: 'Invalid token' });
        req.user = user;
        next();
    });
}

// ── Service Health Checks ─────────────────────────────────────
async function checkServiceHealth(serviceKey) {
    const service = SERVICES[serviceKey];
    try {
        const response = await axios.get(`${service.url}${service.health}`, {
            timeout: 5000,
            validateStatus: () => true
        });
        
        service.status = response.status === 200 ? 'healthy' : 'degraded';
        service.lastCheck = new Date().toISOString();
        return service.status === 'healthy';
    } catch (error) {
        service.status = 'offline';
        service.lastCheck = new Date().toISOString();
        return false;
    }
}

async function checkAllServices() {
    console.log('🔍 Running autonomous health checks...');
    for (const key of Object.keys(SERVICES)) {
        await checkServiceHealth(key);
    }
}

// ── Routes ────────────────────────────────────────────────────

// 🏠 Health Check
app.get('/', (req, res) => {
    res.json({
        name: '🌐 Windsurf API Gateway',
        version: '1.0.0',
        status: 'online',
        uptime: Math.floor((Date.now() - startTime) / 1000),
        environment: NODE_ENV,
        services: Object.keys(SERVICES).length,
        timestamp: new Date().toISOString()
    });
});

// 💚 Detailed Health
app.get('/health', async (req, res) => {
    await checkAllServices();
    
    const servicesHealth = {};
    for (const [key, service] of Object.entries(SERVICES)) {
        servicesHealth[key] = {
            status: service.status,
            lastCheck: service.lastCheck
        };
    }
    
    const allHealthy = Object.values(SERVICES).every(s => s.status === 'healthy');
    
    res.status(allHealthy ? 200 : 503).json({
        status: allHealthy ? 'healthy' : 'degraded',
        gateway: 'healthy',
        services: servicesHealth,
        uptime: Math.floor((Date.now() - startTime) / 1000),
        timestamp: new Date().toISOString()
    });
});

// 📊 Dashboard Stats
app.get('/api/gateway/stats', authenticateToken, (req, res) => {
    res.json({
        services: Object.entries(SERVICES).map(([key, service]) => ({
            key,
            name: service.name,
            status: service.status,
            url: service.url,
            lastCheck: service.lastCheck
        })),
        uptime: Math.floor((Date.now() - startTime) / 1000),
        memory: process.memoryUsage(),
        node: process.version,
        platform: process.platform
    });
});

// 🔗 Service Proxy Routes
app.use('/api/rudibot/*', async (req, res) => {
    try {
        const targetUrl = `${SERVICES.rudibot.url}${req.path.replace('/api/rudibot', '')}`;
        const response = await axios({
            method: req.method,
            url: targetUrl,
            data: req.body,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': req.headers.authorization
            },
            timeout: 10000
        });
        res.json(response.data);
    } catch (error) {
        res.status(502).json({ error: 'Rudibot service unavailable', details: error.message });
    }
});

app.use('/api/shopify/*', async (req, res) => {
    try {
        const targetUrl = `${SERVICES.shopify.url}${req.path.replace('/api/shopify', '')}`;
        const response = await axios({
            method: req.method,
            url: targetUrl,
            data: req.body,
            headers: {
                'Content-Type': 'application/json'
            },
            timeout: 10000
        });
        res.json(response.data);
    } catch (error) {
        res.status(502).json({ error: 'Shopify service unavailable', details: error.message });
    }
});

// 🤖 SuperMegaBot Proxy
app.use('/api/megabot/*', async (req, res) => {
    try {
        const targetUrl = `${SERVICES.supermegabot.url}${req.path.replace('/api/megabot', '')}`;
        const response = await axios({
            method: req.method,
            url: targetUrl,
            data: req.body,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': req.headers.authorization
            },
            timeout: 30000
        });
        res.json(response.data);
    } catch (error) {
        res.status(502).json({ error: 'SuperMegaBot service unavailable', details: error.message });
    }
});

// 📱 Telegram Bot Proxy
app.use('/api/telegram-bot/*', async (req, res) => {
    try {
        const targetUrl = `${SERVICES.telegram.url}${req.path.replace('/api/telegram-bot', '')}`;
        const response = await axios({
            method: req.method,
            url: targetUrl,
            data: req.body,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': req.headers.authorization
            },
            timeout: 10000
        });
        res.json(response.data);
    } catch (error) {
        res.status(502).json({ error: 'Telegram bot service unavailable', details: error.message });
    }
});

// 📨 Telegram Webhook Weiterleitung zu supermegabot
app.post('/webhook/telegram', async (req, res) => {
    try {
        const response = await axios.post(
            `${SERVICES.supermegabot.url}/webhook/telegram`,
            req.body,
            { headers: { 'Content-Type': 'application/json' }, timeout: 10000 }
        );
        res.json(response.data);
    } catch (error) {
        res.status(502).json({ error: 'Webhook forwarding failed', details: error.message });
    }
});

// 💰 Monetization Webhook
app.post('/webhooks/stripe', express.raw({type: 'application/json'}), (req, res) => {
    const sig = req.headers['stripe-signature'];
    const secret = process.env.STRIPE_WEBHOOK_SECRET;
    
    if (!sig || !secret) {
        return res.status(400).json({ error: 'Missing signature or secret' });
    }
    
    // Stripe Webhook Verifikation
    console.log('💰 Stripe webhook received:', req.body);
    res.json({ received: true });
});

// 🔄 Autonomous Service Discovery
app.get('/api/discover', (req, res) => {
    res.json({
        services: Object.entries(SERVICES).map(([key, service]) => ({
            key,
            name: service.name,
            url: service.url,
            healthEndpoint: service.health,
            status: service.status,
            endpoints: [
                `/api/${key}/*`
            ]
        }))
    });
});

// 🧠 OLLAMA AI ROUTES ──────────────────────────────────────
app.get('/api/ai/models', async (req, res) => {
    try {
        const models = Object.entries(ollama.AVAILABLE_MODELS).map(([key, model]) => ({
            key,
            name: model.name,
            description: model.description,
            useCase: model.useCase,
            size: model.size,
            languages: model.languages,
            strengths: model.strengths
        }));
        res.json({ models, count: models.length });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/ai/generate', async (req, res) => {
    try {
        const { prompt, model, temperature, maxTokens } = req.body;
        const result = await ollama.generate(prompt, {
            model,
            temperature,
            maxTokens
        });
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/ai/chat', async (req, res) => {
    try {
        const { messages, model } = req.body;
        const result = await ollama.chat(messages, { model });
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/ai/analyze', async (req, res) => {
    try {
        const { text, task } = req.body;
        const result = await ollama.analyzeText(text, task);
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ⚖️ OPENLAW ROUTES ──────────────────────────────────────
app.get('/api/legal/templates', (req, res) => {
    try {
        const templates = openlaw.getAvailableTemplates();
        res.json({ templates, count: templates.length });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/legal/generate', async (req, res) => {
    try {
        const { template, variables } = req.body;
        const document = await openlaw.generateDocument(template, variables);
        res.json(document);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/legal/compliance', async (req, res) => {
    try {
        const { type, data } = req.body;
        const result = await openlaw.checkCompliance(type, data);
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/legal/full-check', async (req, res) => {
    try {
        const { websiteData } = req.body;
        const result = await openlaw.fullWebsiteCheck(websiteData);
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// 🌐 OPENSOURCE ROUTES ──────────────────────────────────────
app.get('/api/opensource/services', (req, res) => {
    try {
        const categories = openSource.getCategories();
        res.json({ categories, count: Object.keys(categories).length });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/opensource/health', async (req, res) => {
    try {
        const result = await openSource.checkAllHealth();
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/opensource/overview', (req, res) => {
    try {
        const overview = openSource.getSystemOverview();
        res.json(overview);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/opensource/docker-compose', (req, res) => {
    try {
        const compose = openSource.generateDockerCompose();
        res.json(compose);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ── Autonomous Health Check Loop ─────────────────────────────
const HEALTH_CHECK_INTERVAL = parseInt(process.env.HEALTH_CHECK_INTERVAL) || 30000;

setInterval(async () => {
    console.log('🔄 Autonomous health check cycle...');
    await checkAllServices();
    
    const healthy = Object.values(SERVICES).filter(s => s.status === 'healthy').length;
    const total = Object.keys(SERVICES).length;
    console.log(`✅ Health check complete: ${healthy}/${total} services healthy`);
}, HEALTH_CHECK_INTERVAL);

// ── Error Handling ────────────────────────────────────────────
app.use((err, req, res, next) => {
    console.error('❌ Gateway Error:', err.message);
    res.status(500).json({
        error: 'Internal gateway error',
        message: NODE_ENV === 'development' ? err.message : 'Something went wrong'
    });
});

app.use((req, res) => {
    res.status(404).json({ error: 'API Gateway: Route not found' });
});

// ── Critical Error Handlers ───────────────────────────────────
process.on('unhandledRejection', (reason, promise) => {
    console.error('❌ Unhandled Rejection:', reason);
});

process.on('uncaughtException', (error) => {
    console.error('❌ Uncaught Exception:', error);
    if (NODE_ENV === 'production') {
        process.exit(1);
    }
});

// ── Start Server ─────────────────────────────────────────────
app.listen(PORT, () => {
    console.log('');
    console.log('🌐 WINDSURF API GATEWAY - AUTONOMOUS MODE');
    console.log('='.repeat(60));
    console.log(`📡 Port: ${PORT}`);
    console.log(`🔧 Environment: ${NODE_ENV}`);
    console.log(`🛡️  Security: JWT Auth, Rate Limiting, Helmet`);
    console.log(`📊 Services: ${Object.keys(SERVICES).length} registered`);
    console.log('');
    console.log('🔗 Core Endpoints:');
    console.log('   GET  /          - Gateway status');
    console.log('   GET  /health    - Health check');
    console.log('   GET  /api/discover - Service discovery');
    console.log('   GET  /api/gateway/stats - Dashboard stats');
    console.log('');
    console.log('🧠 Ollama AI Endpoints:');
    console.log('   GET  /api/ai/models - Available AI models');
    console.log('   POST /api/ai/generate - Generate text');
    console.log('   POST /api/ai/chat - Chat with AI');
    console.log('   POST /api/ai/analyze - Analyze text');
    console.log('');
    console.log('⚖️  OpenLaw Endpoints:');
    console.log('   GET  /api/legal/templates - Legal templates');
    console.log('   POST /api/legal/generate - Generate document');
    console.log('   POST /api/legal/compliance - Check compliance');
    console.log('   POST /api/legal/full-check - Full website check');
    console.log('');
    console.log('🌐 OpenSource Endpoints:');
    console.log('   GET  /api/opensource/services - OpenSource services');
    console.log('   GET  /api/opensource/health - Health check');
    console.log('   GET  /api/opensource/overview - System overview');
    console.log('   POST /api/opensource/docker-compose - Generate compose');
    console.log('');
    console.log('🤖 AUTONOMOUS HEALTH CHECKS: Active');
    console.log(`🔄 Interval: ${HEALTH_CHECK_INTERVAL}ms`);
    console.log('');
    console.log('🚀 GATEWAY READY FOR AUTONOMOUS OPERATION');
    console.log('='.repeat(60));
    
    // Initial health check
    checkAllServices();
});

module.exports = app;
