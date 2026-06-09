const express = require('express');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const path = require('path');

const statusHandler = require('./api/status');
const controlHandler = require('./api/webhook-control');
const telegramHandler = require('./api/webhook-telegram');
const klaviyoHandler = require('./api/webhook-klaviyo');

const app = express();

// Security Middleware
app.use(helmet());
app.use(rateLimit({
    windowMs: 15 * 60 * 1000, // 15 Minuten
    max: 100 // Limit pro IP
}));
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// API Routes
app.get('/api/status', statusHandler);
app.get('/api/health', statusHandler);

// Webhook Routes
app.post('/webhook/control', controlHandler);
app.post('/webhook/telegram', telegramHandler);
app.post('/webhook/klaviyo', klaviyoHandler);

// GET fallback for webhooks (health checks)
app.get('/webhook/control', (req, res) => res.json({ ok: true }));
app.get('/webhook/telegram', (req, res) => res.json({ ok: true }));
app.get('/webhook/klaviyo', (req, res) => res.json({ ok: true }));

// Root
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

module.exports = app;


// 🔧 KRITISCHE FEHLER-HANDLER
process.on('unhandledRejection', (reason, promise) => {
    console.error('❌ Unhandled Rejection:', reason);
});

process.on('uncaughtException', (error) => {
    console.error('❌ Uncaught Exception:', error);
    if (process.env.NODE_ENV === 'production') {
        process.exit(1);
    }
});
