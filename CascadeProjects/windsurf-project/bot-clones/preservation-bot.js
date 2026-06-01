#!/usr/bin/env node

/**
 * Preservation Bot (Instandhaltungs-Bot)
 * Langfristige Stabilität und Technical Debt Management
 * Dokumentation, Refactoring-Planung, Best Practices
 */

import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

class PreservationBot {
  constructor(options = {}) {
    this.interval = (options.interval || 600) * 1000;
    this.logFile = options.logFile || path.join(process.cwd(), 'logs', 'preservation-bot.log');
    this.maxLogSize = options.maxLogSize || 5 * 1024 * 1024;
    this.maxLogFiles = options.maxLogFiles || 3;
    this.running = false;
    this.timer = null;
    this.technicalDebt = [];
    this.documentationStatus = {};
    
    this.ensureLogDir();
  }

  ensureLogDir() {
    const logDir = path.dirname(this.logFile);
    if (!fs.existsSync(logDir)) {
      fs.mkdirSync(logDir, { recursive: true });
    }
  }

  checkLogRotation() {
    try {
      if (fs.existsSync(this.logFile)) {
        const stats = fs.statSync(this.logFile);
        if (stats.size > this.maxLogSize) {
          const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
          const backupFile = `${this.logFile}.${timestamp}.backup`;
          fs.renameSync(this.logFile, backupFile);
          this.cleanOldBackups();
        }
      }
    } catch (error) {
      console.error('Log rotation error:', error.message);
    }
  }

  cleanOldBackups() {
    try {
      const dir = path.dirname(this.logFile);
      const basename = path.basename(this.logFile);
      const files = fs.readdirSync(dir)
        .filter(f => f.startsWith(basename) && f.endsWith('.backup'))
        .map(f => ({
          name: f,
          path: path.join(dir, f),
          time: fs.statSync(path.join(dir, f)).mtime.getTime()
        }))
        .sort((a, b) => b.time - a.time);
      
      if (files.length > this.maxLogFiles) {
        files.slice(this.maxLogFiles).forEach(f => {
          fs.unlinkSync(f.path);
        });
      }
    } catch (error) {
      console.error('Backup cleanup error:', error.message);
    }
  }

  log(level, message) {
    this.checkLogRotation();
    const timestamp = new Date().toISOString();
    const line = `[${timestamp}] [${level.toUpperCase()}] ${message}\n`;
    fs.appendFileSync(this.logFile, line);
  }

  recordDebt(type, description, severity) {
    this.technicalDebt.push({
      timestamp: new Date().toISOString(),
      type,
      description,
      severity
    });
  }

  async checkDocumentation() {
    try {
      this.log('info', '📚 Prüfe Dokumentation...');
      
      const requiredDocs = [
        'README.md',
        'API_SETUP_GUIDE.md',
        'PROJECT_PRIORITIZATION_ANALYSIS.md',
        'DEPLOYMENT_READY_SYSTEMS.md'
      ];

      let missing = 0;
      for (const doc of requiredDocs) {
        const docPath = path.join(process.cwd(), doc);
        if (!fs.existsSync(docPath)) {
          this.log('warn', `⚠️ Fehlende Dokumentation: ${doc}`);
          missing++;
        } else {
          const stats = fs.statSync(docPath);
          const age = (Date.now() - stats.mtime.getTime()) / (24 * 60 * 60 * 1000);
          
          if (age > 30) {
            this.log('warn', `⚠️ Dokumentation veraltet: ${doc} (${Math.round(age)} Tage)`);
            this.recordDebt('documentation', `${doc} ist ${Math.round(age)} Tage alt`, 'medium');
          } else {
            this.log('info', `✅ ${doc}: OK (${Math.round(age)} Tage alt)`);
          }
        }
      }

      if (missing > 0) {
        this.log('warn', `⚠️ ${missing} Dokumente fehlen`);
        this.recordDebt('documentation', `${missing} wichtige Dokumente fehlen`, 'high');
      }

    } catch (error) {
      this.log('error', `❌ Dokumentations-Prüfung fehlgeschlagen: ${error.message}`);
    }
  }

  async checkCodeConsistency() {
    try {
      this.log('info', '🔍 Prüfe Code-Konsistenz...');
      
      const criticalFiles = [
        'components/quick-cash/AutoShopSuite.tsx',
        'components/quick-cash/QuickCashSystem.tsx',
        'api-config.json',
        'watchdog.js'
      ];

      for (const file of criticalFiles) {
        const filePath = path.join(process.cwd(), file);
        if (fs.existsSync(filePath)) {
          const content = fs.readFileSync(filePath, 'utf8');
          const lines = content.split('\n');
          
          // Check for consistent formatting
          const mixedQuotes = lines.some(l => l.includes('"') && l.includes("'"));
          if (mixedQuotes) {
            this.log('warn', `⚠️ ${file}: Gemischte Quote-Stile gefunden`);
            this.recordDebt('style', `${file} hat gemischte Quote-Stile`, 'low');
          }
          
          // Check for very long lines
          const longLines = lines.filter(l => l.length > 120);
          if (longLines.length > 0) {
            this.log('warn', `⚠️ ${file}: ${longLines.length} Zeilen > 120 Zeichen`);
            this.recordDebt('style', `${file} hat ${longLines.length} zu lange Zeilen`, 'low');
          }
        }
      }

    } catch (error) {
      this.log('error', `❌ Code-Konsistenz Prüfung fehlgeschlagen: ${error.message}`);
    }
  }

  async generateRefactoringPlan() {
    try {
      this.log('info', '📋 Generiere Refactoring-Plan...');
      
      if (this.technicalDebt.length === 0) {
        this.log('info', '✅ Kein Technical Debt - Refactoring nicht nötig');
        return;
      }

      const highSeverity = this.technicalDebt.filter(d => d.severity === 'high');
      const mediumSeverity = this.technicalDebt.filter(d => d.severity === 'medium');
      const lowSeverity = this.technicalDebt.filter(d => d.severity === 'low');

      this.log('info', `📊 Technical Debt Übersicht:`);
      this.log('info', `  🔴 Hoch: ${highSeverity.length}`);
      this.log('info', `  🟡 Mittel: ${mediumSeverity.length}`);
      this.log('info', `  🟢 Niedrig: ${lowSeverity.length}`);

      if (highSeverity.length > 0) {
        this.log('warn', `⚠️ ${highSeverity.length} kritische Punkte erfordern sofortige Aufmerksamkeit`);
      }

      // Generate refactoring report
      const reportPath = path.join(process.cwd(), 'logs', 'refactoring-plan.md');
      const report = `# Refactoring Plan

Generated: ${new Date().toISOString()}

## Technical Debt Summary

- **High Priority**: ${highSeverity.length}
- **Medium Priority**: ${mediumSeverity.length}
- **Low Priority**: ${lowSeverity.length}

## High Priority Items

${highSeverity.map(d => `- [ ] ${d.type}: ${d.description} (${d.timestamp})`).join('\n')}

## Medium Priority Items

${mediumSeverity.map(d => `- [ ] ${d.type}: ${d.description} (${d.timestamp})`).join('\n')}

## Low Priority Items

${lowSeverity.map(d => `- [ ] ${d.type}: ${d.description} (${d.timestamp})`).join('\n')}

## Recommended Actions

1. Address high priority items first
2. Schedule medium priority items for next sprint
3. Include low priority items in regular maintenance
`;

      fs.writeFileSync(reportPath, report);
      this.log('info', `✅ Refactoring-Plan erstellt: ${reportPath}`);

    } catch (error) {
      this.log('error', `❌ Refactoring-Plan Generierung fehlgeschlagen: ${error.message}`);
    }
  }

  async checkBestPractices() {
    try {
      this.log('info', '✅ Prüfe Best Practices...');
      
      // Check for .env.example
      const envExamplePath = path.join(process.cwd(), '.env.example');
      if (!fs.existsSync(envExamplePath)) {
        this.log('warn', `⚠️ .env.example fehlt - Erstelle Template`);
        this.recordDebt('config', '.env.example fehlt', 'medium');
      }

      // Check for .gitignore
      const gitignorePath = path.join(process.cwd(), '.gitignore');
      if (fs.existsSync(gitignorePath)) {
        const content = fs.readFileSync(gitignorePath, 'utf8');
        const requiredIgnores = ['node_modules', '.env', 'logs/*.backup'];
        
        for (const ignore of requiredIgnores) {
          if (!content.includes(ignore)) {
            this.log('warn', `⚠️ .gitignore fehlt: ${ignore}`);
            this.recordDebt('config', `.gitignore fehlt: ${ignore}`, 'low');
          }
        }
      }

      // Check for consistent file structure
      const expectedDirs = ['components', 'services', 'utils', 'logs'];
      for (const dir of expectedDirs) {
        const dirPath = path.join(process.cwd(), dir);
        if (!fs.existsSync(dirPath)) {
          this.log('warn', `⚠️ Verzeichnis fehlt: ${dir}`);
          this.recordDebt('structure', `Verzeichnis fehlt: ${dir}`, 'low');
        }
      }

    } catch (error) {
      this.log('error', `❌ Best Practices Prüfung fehlgeschlagen: ${error.message}`);
    }
  }

  async tick() {
    try {
      this.log('info', '🏛️ Preservation Bot Tick gestartet');

      await this.checkDocumentation();
      await this.checkCodeConsistency();
      await this.checkBestPractices();
      
      // Generate refactoring plan every 5 ticks
      if (!this.planCounter) this.planCounter = 0;
      this.planCounter++;
      if (this.planCounter >= 5) {
        this.planCounter = 0;
        await this.generateRefactoringPlan();
      }

      this.log('info', '✅ Preservation Bot Tick abgeschlossen');
    } catch (error) {
      this.log('error', `Preservation Bot Fehler: ${error.message}`);
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.log('info', '🏛️ Preservation Bot gestartet');
    this.tick();
    this.timer = setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.log('info', '🛑 Preservation Bot gestoppt');
  }
}

// Konfiguration
const bot = new PreservationBot({
  interval: 600
});

process.on('SIGINT', () => bot.stop());
process.on('SIGTERM', () => bot.stop());

bot.start();
