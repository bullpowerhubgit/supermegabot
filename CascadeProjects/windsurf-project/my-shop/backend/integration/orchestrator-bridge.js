/**
 * Orchestrator Bridge
 * Verbindet My-Shop Backend mit bestehendem SuperMegaBot E-Commerce System
 */

import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const rootDir = join(__dirname, '../../../');

class OrchestratorBridge {
  constructor() {
    this.orchestrator = null;
    this.systeme = {};
  }

  async initialisieren() {
    try {
      const { default: ECommerceMasterOrchestrator } = await import(
        join(rootDir, 'ecommerce-master-orchestrator.js')
      );
      this.orchestrator = new ECommerceMasterOrchestrator();
      console.log('Orchestrator Bridge verbunden');
      return true;
    } catch (fehler) {
      console.warn('Orchestrator nicht direkt verfuegbar:', fehler.message);
      return false;
    }
  }

  async metriken() {
    if (!this.orchestrator) {
      return { status: 'offline', nachricht: 'Orchestrator nicht verbunden' };
    }
    return {
      status: 'online',
      metriken: this.orchestrator.metrics || {},
      laeuft: this.orchestrator.isRunning || false
    };
  }

  async systemStatus() {
    return {
      module: {
        dropshipping: this.orchestrator?.dropshipping ? 'verbunden' : 'nicht verfuegbar',
        marketing: this.orchestrator?.marketing ? 'verbunden' : 'nicht verfuegbar',
        seo: this.orchestrator?.seo ? 'verbunden' : 'nicht verfuegbar'
      },
      umgebung: {
        shopify: process.env.SHOPIFY_STORE_URL ? 'konfiguriert' : 'nicht konfiguriert',
        supabase: process.env.SUPABASE_URL ? 'konfiguriert' : 'nicht konfiguriert',
        telegram: process.env.TELEGRAM_BOT_TOKEN ? 'konfiguriert' : 'nicht konfiguriert',
        openai: process.env.OPENAI_API_KEY ? 'konfiguriert' : 'nicht konfiguriert'
      }
    };
  }
}

export default new OrchestratorBridge();
