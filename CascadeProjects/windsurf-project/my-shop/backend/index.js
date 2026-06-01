/**
 * My-Shop Backend API
 * Verbindet Frontend mit SuperMegaBot E-Commerce System
 */

import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';

import db from './db.js';
import produktRoutes from './routes/produkte.js';
import bestellungRoutes from './routes/bestellungen.js';
import marketingRoutes from './routes/marketing.js';
import analyticsRoutes from './routes/analytics.js';
import systemRoutes from './routes/system.js';
import claudeRoutes from './routes/claude.js';

dotenv.config();

const app = express();
const PORT = process.env.SHOP_BACKEND_PORT || 4001;

app.use(cors());
app.use(express.json());

app.use('/api/produkte', produktRoutes);
app.use('/api/bestellungen', bestellungRoutes);
app.use('/api/marketing', marketingRoutes);
app.use('/api/analytics', analyticsRoutes);
app.use('/api/system', systemRoutes);
app.use('/api/claude', claudeRoutes);

app.get('/api/health', (req, res) => {
  res.json({
    status: 'online',
    zeitstempel: new Date().toISOString(),
    dienste: ['produkte', 'bestellungen', 'marketing', 'analytics', 'system']
  });
});

app.listen(PORT, async () => {
  console.log(`🛒 My-Shop Backend läuft auf Port ${PORT}`);
  console.log(`📡 API Endpunkte:`);
  console.log(`   - /api/health`);
  console.log(`   - /api/produkte`);
  console.log(`   - /api/bestellungen`);
  console.log(`   - /api/marketing`);
  console.log(`   - /api/analytics`);
  console.log(`   - /api/system`);
  
  const dbConnected = await db.connect();
  if (dbConnected) {
    console.log(`✅ Datenbank verbunden`);
  } else {
    console.log(`⚠️  Datenbank nicht verbunden - In-Memory Modus aktiv`);
  }
});
