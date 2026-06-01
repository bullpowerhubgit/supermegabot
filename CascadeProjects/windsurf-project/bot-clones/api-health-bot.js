/**
 * SuperMegaBot API Health Bot - API-Überwachung & Reparatur
 * Zuständig: API-Status, Fehlererkennung, Auto-Reparatur
 */

import axios from 'axios';
import fs from 'fs';
import { exec } from 'child_process';

class APIHealthBot {
  constructor() {
    this.name = 'APIHealthBot';
    this.interval = 60000; // 1 Minute
    this.apis = [
      {
        name: 'Claude API',
        url: 'http://localhost:4001/api/claude',
        method: 'POST',
        testPayload: {
          model: 'claude-sonnet-4-20250514',
          max_tokens: 10,
          messages: [{ role: 'user', content: 'ping' }]
        },
        critical: true
      },
      {
        name: 'QuickCash API',
        url: 'http://localhost:3001/health',
        method: 'GET',
        critical: true
      },
      {
        name: 'My-Shop API',
        url: 'http://localhost:4000/api/health',
        method: 'GET',
        critical: true
      }
    ];
    this.failedAttempts = {};
    this.isRunning = false;
  }

  async start() {
    console.log(`🤖 ${this.name} starting...`);
    this.isRunning = true;
    
    // API Health Check Loop
    this.healthCheckInterval = setInterval(async () => {
      if (!this.isRunning) return;
      
      await this.checkAllAPIs();
    }, this.interval);
    
    console.log(`✅ ${this.name} started - Checking APIs every ${this.interval/1000}s`);
  }

  async checkAllAPIs() {
    const results = {};
    
    for (const api of this.apis) {
      try {
        const result = await this.checkAPI(api);
        results[api.name] = result;
        
        // Reset failed attempts on success
        if (result.status === 'healthy') {
          this.failedAttempts[api.name] = 0;
        }
      } catch (error) {
        results[api.name] = {
          status: 'error',
          error: error.message,
          timestamp: new Date().toISOString()
        };
        
        await this.handleAPIFailure(api, error);
      }
    }
    
    this.logAPIHealth(results);
    return results;
  }

  async checkAPI(api) {
    const startTime = Date.now();
    
    try {
      const config = {
        timeout: 10000,
        headers: api.headers || {}
      };
      
      let response;
      if (api.method === 'POST') {
        response = await axios.post(api.url, api.testPayload, config);
      } else {
        response = await axios.get(api.url, config);
      }
      
      const responseTime = Date.now() - startTime;
      
      return {
        status: 'healthy',
        responseTime: `${responseTime}ms`,
        statusCode: response.status,
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      const responseTime = Date.now() - startTime;
      
      return {
        status: 'unhealthy',
        error: error.message,
        responseTime: `${responseTime}ms`,
        statusCode: error.response?.status || 'N/A',
        timestamp: new Date().toISOString()
      };
    }
  }

  async handleAPIFailure(api, error) {
    const apiName = api.name;
    this.failedAttempts[apiName] = (this.failedAttempts[apiName] || 0) + 1;
    
    console.log(`🚨 API Failure: ${apiName} - Attempt ${this.failedAttempts[apiName]}`);
    
    // Auto-Reparatur Versuche
    if (this.failedAttempts[apiName] === 1) {
      await this.attemptBasicRepair(api);
    } else if (this.failedAttempts[apiName] === 2) {
      await this.attemptAdvancedRepair(api);
    } else if (this.failedAttempts[apiName] >= 3 && api.critical) {
      await this.attemptFullRestart(api);
    }
  }

  async attemptBasicRepair(api) {
    console.log(`🔧 Basic repair attempt for ${api.name}`);
    
    try {
      // Port prüfen und ggf. Prozess neustarten
      const port = this.extractPortFromURL(api.url);
      if (port) {
        const isRunning = await this.checkPort(port);
        if (!isRunning) {
          await this.restartServer(port);
        }
      }
    } catch (error) {
      console.error(`Basic repair failed for ${api.name}:`, error.message);
    }
  }

  async attemptAdvancedRepair(api) {
    console.log(`🔧 Advanced repair attempt for ${api.name}`);
    
    try {
      // Konfiguration prüfen
      await this.checkConfiguration(api);
      
      // Dependencies prüfen
      await this.checkDependencies();
      
      // Logs prüfen auf spezifische Fehler
      await this.analyzeLogs(api.name);
    } catch (error) {
      console.error(`Advanced repair failed for ${api.name}:`, error.message);
    }
  }

  async attemptFullRestart(api) {
    console.log(`🔄 Full restart attempt for ${api.name}`);
    
    try {
      const port = this.extractPortFromURL(api.url);
      if (port) {
        // Prozess beenden
        await this.killProcessOnPort(port);
        
        // Warten und neu starten
        await new Promise(resolve => setTimeout(resolve, 2000));
        await this.restartServer(port);
      }
    } catch (error) {
      console.error(`Full restart failed for ${api.name}:`, error.message);
      await this.sendCriticalAlert(api.name, 'Full restart failed', error.message);
    }
  }

  extractPortFromURL(url) {
    const match = url.match(/:(\d+)/);
    return match ? parseInt(match[1]) : null;
  }

  async checkPort(port) {
    return new Promise((resolve) => {
      exec(`lsof -i:${port}`, (error, stdout) => {
        resolve(!error && stdout.length > 0);
      });
    });
  }

  async killProcessOnPort(port) {
    return new Promise((resolve, reject) => {
      exec(`lsof -ti:${port} | xargs kill -9`, (error) => {
        if (error) {
          reject(error);
        } else {
          resolve();
        }
      });
    });
  }

  async restartServer(port) {
    const serverCommands = {
      4001: 'cd /Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/my-shop/backend && npm run dev',
      3001: 'cd /Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project && node quickcash-backend.js',
      4000: 'cd /Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/my-shop/backend && npm run dev'
    };
    
    const command = serverCommands[port];
    if (command) {
      console.log(`🔄 Restarting server on port ${port}`);
      exec(command, { detached: true }, (error) => {
        if (error) {
          console.error(`Failed to restart server on port ${port}:`, error.message);
        } else {
          console.log(`✅ Server restart initiated on port ${port}`);
        }
      });
    }
  }

  async checkConfiguration(api) {
    // API Konfiguration prüfen
    const configFiles = [
      './.env',
      './api-config.json',
      './package.json'
    ];
    
    for (const file of configFiles) {
      if (fs.existsSync(file)) {
        console.log(`✅ Config file exists: ${file}`);
      } else {
        console.log(`❌ Missing config file: ${file}`);
      }
    }
  }

  async checkDependencies() {
    // Wichtige Dependencies prüfen
    const criticalDeps = ['express', 'axios', 'cors', 'dotenv'];
    
    try {
      const packageJson = JSON.parse(fs.readFileSync('./package.json', 'utf8'));
      const installedDeps = Object.keys(packageJson.dependencies || {});
      
      for (const dep of criticalDeps) {
        if (installedDeps.includes(dep)) {
          console.log(`✅ Dependency installed: ${dep}`);
        } else {
          console.log(`❌ Missing dependency: ${dep}`);
          await this.installDependency(dep);
        }
      }
    } catch (error) {
      console.error('Failed to check dependencies:', error.message);
    }
  }

  async installDependency(dep) {
    console.log(`📦 Installing missing dependency: ${dep}`);
    exec(`npm install ${dep}`, (error, stdout, stderr) => {
      if (error) {
        console.error(`Failed to install ${dep}:`, error.message);
      } else {
        console.log(`✅ Successfully installed ${dep}`);
      }
    });
  }

  async analyzeLogs(apiName) {
    const logFiles = [
      './logs/monitoring.log',
      './logs/alerts.log',
      './logs/api-errors.log'
    ];
    
    for (const logFile of logFiles) {
      if (fs.existsSync(logFile)) {
        const logs = fs.readFileSync(logFile, 'utf8');
        const recentLogs = logs.split('\n').slice(-10); // Letzte 10 Einträge
        
        const apiErrors = recentLogs.filter(log => 
          log.toLowerCase().includes(apiName.toLowerCase()) && 
          log.toLowerCase().includes('error')
        );
        
        if (apiErrors.length > 0) {
          console.log(`🔍 Found ${apiErrors.length} recent errors for ${apiName}`);
          apiErrors.forEach(log => console.log(`   ${log}`));
        }
      }
    }
  }

  async sendCriticalAlert(apiName, action, error) {
    const alert = {
      title: `🚨 CRITICAL: ${apiName} API Failure`,
      action: action,
      error: error,
      timestamp: new Date().toISOString(),
      bot: this.name
    };
    
    console.log(`🚨 CRITICAL ALERT: ${JSON.stringify(alert)}`);
    
    // In Logs schreiben
    fs.appendFileSync('./logs/critical-alerts.log', JSON.stringify(alert) + '\n');
    
    // Hier könnten weitere Alert-Methoden implementiert werden
  }

  logAPIHealth(results) {
    const logEntry = {
      results,
      bot: this.name,
      timestamp: new Date().toISOString()
    };
    
    fs.appendFileSync('./logs/api-health.log', JSON.stringify(logEntry) + '\n');
  }

  async stop() {
    console.log(`🛑 ${this.name} stopping...`);
    this.isRunning = false;
    clearInterval(this.healthCheckInterval);
    console.log(`✅ ${this.name} stopped`);
  }

  getStatus() {
    return {
      name: this.name,
      isRunning: this.isRunning,
      interval: this.interval,
      monitoredAPIs: this.apis.length,
      failedAttempts: this.failedAttempts,
      uptime: process.uptime()
    };
  }
}

// Auto-start wenn direkt ausgeführt
if (import.meta.url === `file://${process.argv[1]}`) {
  const bot = new APIHealthBot();
  bot.start();
  
  // Graceful shutdown
  process.on('SIGINT', async () => {
    await bot.stop();
    process.exit(0);
  });
}

export default APIHealthBot;
