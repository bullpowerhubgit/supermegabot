/**
 * SuperMegaBot Optimizer Bot - Performance & Cost Optimization
 * Zuständig: Performance-Optimierung, Cost-Optimierung (API Usage), Caching-Strategien, Resource Management
 */

import os from 'os';
import fs from 'fs';
import { exec } from 'child_process';
import path from 'path';

class OptimizerBot {
  constructor() {
    this.name = 'OptimizerBot';
    this.interval = 120000; // 2 Minuten
    this.isRunning = false;
    this.optimizations = [];
    this.metrics = {
      memory: [],
      cpu: [],
      apiCalls: [],
      costs: []
    };
  }

  async start() {
    console.log(`🤖 ${this.name} starting...`);
    this.isRunning = true;
    
    // Haupt-Optimierung Loop
    this.optimizationInterval = setInterval(async () => {
      if (!this.isRunning) return;
      
      await this.optimize();
    }, this.interval);
    
    console.log(`✅ ${this.name} started - Optimizing every ${this.interval/1000}s`);
  }

  async optimize() {
    console.log(`⚡ ${this.name}: Running optimizations...`);
    
    // 1. Memory Optimization
    await this.optimizeMemory();
    
    // 2. CPU Optimization
    await this.optimizeCPU();
    
    // 3. API Cost Optimization
    await this.optimizeAPIUsage();
    
    // 4. Caching Strategy
    await this.optimizeCaching();
    
    // 5. Resource Management
    await this.optimizeResources();
    
    this.collectMetrics();
  }

  async optimizeMemory() {
    const memUsage = process.memoryUsage();
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    const memPercentage = ((totalMem - freeMem) / totalMem * 100).toFixed(2);
    
    console.log(`💾 Memory Usage: ${memPercentage}%`);
    
    // Auto-Garbage Collection bei hohem Speicherverbrauch
    if (parseFloat(memPercentage) > 80) {
      console.log(`🧹 ${this.name}: High memory usage detected, running GC...`);
      
      if (global.gc) {
        global.gc();
        this.optimizations.push({
          type: 'memory',
          action: 'garbage_collection',
          timestamp: new Date().toISOString(),
          before: memPercentage
        });
      }
      
      // Clear unnecessary caches
      await this.clearCaches();
    }
    
    // Optimize Node.js memory limits
    if (memUsage.heapUsed > 500 * 1024 * 1024) { // 500MB
      console.log(`⚠️ ${this.name}: Heap size large, consider increasing --max-old-space-size`);
    }
  }

  async optimizeCPU() {
    const cpus = os.cpus();
    const loadAvg = os.loadavg();
    
    console.log(`🖥️ CPU Load: ${loadAvg[0].toFixed(2)} (1m), ${loadAvg[1].toFixed(2)} (5m), ${loadAvg[2].toFixed(2)} (15m)`);
    
    // Check for CPU-intensive processes
    if (loadAvg[0] > cpus.length * 0.8) {
      console.log(`⚠️ ${this.name}: High CPU load detected`);
      
      // Identify CPU-intensive processes
      try {
        const result = await this.execCommand('ps aux | sort -rk 3 | head -5');
        console.log(`🔍 Top CPU processes:\n${result}`);
      } catch (error) {
        console.error('Failed to get CPU processes:', error.message);
      }
    }
  }

  async optimizeAPIUsage() {
    console.log(`💰 ${this.name}: Optimizing API usage...`);
    
    // Check API call logs
    const apiLogPath = path.join(process.cwd(), 'logs', 'api-usage.log');
    if (fs.existsSync(apiLogPath)) {
      const apiLogs = fs.readFileSync(apiLogPath, 'utf-8');
      const calls = apiLogs.split('\n').filter(line => line.trim());
      
      console.log(`📊 Total API calls: ${calls.length}`);
      
      // Analyze API usage patterns
      const apiUsage = this.analyzeAPIUsage(calls);
      
      // Suggest optimizations
      if (apiUsage.highFrequencyCalls > 100) {
        console.log(`💡 ${this.name}: High frequency API calls detected - consider caching`);
        this.optimizations.push({
          type: 'api',
          action: 'suggest_caching',
          timestamp: new Date().toISOString(),
          details: 'High frequency API calls detected'
        });
      }
      
      // Calculate estimated costs
      const estimatedCost = this.calculateAPICosts(apiUsage);
      console.log(`💰 Estimated API costs: $${estimatedCost.toFixed(2)}`);
      
      this.metrics.costs.push({
        timestamp: new Date().toISOString(),
        cost: estimatedCost
      });
    }
  }

  analyzeAPIUsage(calls) {
    const usage = {
      totalCalls: calls.length,
      byEndpoint: {},
      highFrequencyCalls: 0
    };
    
    for (const call of calls) {
      try {
        const data = JSON.parse(call);
        const endpoint = data.endpoint || 'unknown';
        
        if (!usage.byEndpoint[endpoint]) {
          usage.byEndpoint[endpoint] = 0;
        }
        usage.byEndpoint[endpoint]++;
        
        if (usage.byEndpoint[endpoint] > 100) {
          usage.highFrequencyCalls++;
        }
      } catch (error) {
        // Invalid log entry - skip
      }
    }
    
    return usage;
  }

  calculateAPICosts(usage) {
    // Estimated costs based on typical API pricing
    const claudeCostPer1kTokens = 0.003; // Claude Sonnet
    const openAICostPer1kTokens = 0.002; // GPT-4
    
    let totalCost = 0;
    
    // This is a simplified calculation - real implementation would use actual token counts
    for (const endpoint in usage.byEndpoint) {
      const callCount = usage.byEndpoint[endpoint];
      const avgTokensPerCall = 1000; // Estimate
      
      if (endpoint.includes('claude') || endpoint.includes('anthropic')) {
        totalCost += (callCount * avgTokensPerCall / 1000) * claudeCostPer1kTokens;
      } else if (endpoint.includes('openai') || endpoint.includes('gpt')) {
        totalCost += (callCount * avgTokensPerCall / 1000) * openAICostPer1kTokens;
      }
    }
    
    return totalCost;
  }

  async optimizeCaching() {
    console.log(`🗄️ ${this.name}: Optimizing caching strategies...`);
    
    // Check for cache directories
    const cacheDirs = [
      path.join(process.cwd(), '.cache'),
      path.join(process.cwd(), 'node_modules', '.cache'),
      path.join(os.tmpdir(), 'supermegabot-cache')
    ];
    
    for (const cacheDir of cacheDirs) {
      if (fs.existsSync(cacheDir)) {
        const stats = fs.statSync(cacheDir);
        const sizeInMB = stats.size / (1024 * 1024);
        
        console.log(`📦 Cache size: ${sizeInMB.toFixed(2)} MB`);
        
        // Clear old cache if too large
        if (sizeInMB > 500) {
          console.log(`🧹 ${this.name}: Clearing large cache...`);
          await this.clearDirectory(cacheDir);
          
          this.optimizations.push({
            type: 'cache',
            action: 'clear_large_cache',
            timestamp: new Date().toISOString(),
            size: sizeInMB
          });
        }
      }
    }
    
    // Suggest caching for frequently accessed data
    console.log(`💡 ${this.name}: Consider implementing Redis for distributed caching`);
  }

  async optimizeResources() {
    console.log(`🔧 ${this.name}: Optimizing resources...`);
    
    // Check for unused ports
    try {
      const result = await this.execCommand('lsof -i -P -n | grep LISTEN');
      const ports = result.split('\n').filter(line => line.trim());
      
      console.log(`🌐 Active ports: ${ports.length}`);
      
      // Identify long-running processes
      for (const line of ports) {
        const parts = line.split(/\s+/);
        if (parts.length > 1) {
          const pid = parts[1];
          const command = parts[0];
          
          // Check process age
          try {
            const psResult = await this.execCommand(`ps -p ${pid} -o etime=`);
            const runtime = psResult.trim();
            
            // Suggest restart for very long-running processes
            if (runtime.includes('-')) { // Days
              console.log(`⚠️ ${this.name}: Long-running process detected: ${command} (PID: ${pid}, Runtime: ${runtime})`);
            }
          } catch (error) {
            // Process check failed - skip
          }
        }
      }
    } catch (error) {
      console.error('Failed to check ports:', error.message);
    }
    
    // Optimize file system
    await this.optimizeFileSystem();
  }

  async optimizeFileSystem() {
    console.log(`📁 ${this.name}: Optimizing file system...`);
    
    // Check disk usage
    try {
      const result = await this.execCommand('df -h');
      console.log(`💾 Disk usage:\n${result}`);
      
      // Clean up temporary files
      const tempDirs = [
        path.join(os.tmpdir(), 'supermegabot-*'),
        path.join(process.cwd(), 'tmp'),
        path.join(process.cwd(), '.tmp')
      ];
      
      for (const tempDir of tempDirs) {
        try {
          await this.execCommand(`rm -rf ${tempDir}`);
          console.log(`🧹 ${this.name}: Cleaned ${tempDir}`);
        } catch (error) {
          // Directory doesn't exist or can't be removed - skip
        }
      }
    } catch (error) {
      console.error('Failed to optimize file system:', error.message);
    }
  }

  async clearCaches() {
    const cacheDirs = [
      path.join(os.tmpdir(), 'supermegabot-cache'),
      path.join(process.cwd(), '.cache')
    ];
    
    for (const cacheDir of cacheDirs) {
      if (fs.existsSync(cacheDir)) {
        await this.clearDirectory(cacheDir);
      }
    }
  }

  async clearDirectory(dir) {
    return new Promise((resolve, reject) => {
      exec(`rm -rf ${dir}/*`, (error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }

  async execCommand(command) {
    return new Promise((resolve, reject) => {
      exec(command, (error, stdout, stderr) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(stdout);
      });
    });
  }

  collectMetrics() {
    const memUsage = process.memoryUsage();
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    
    this.metrics.memory.push({
      timestamp: new Date().toISOString(),
      heapUsed: memUsage.heapUsed,
      heapTotal: memUsage.heapTotal,
      external: memUsage.external,
      percentage: ((totalMem - freeMem) / totalMem * 100).toFixed(2)
    });
    
    // Keep only last 100 data points
    if (this.metrics.memory.length > 100) {
      this.metrics.memory.shift();
    }
  }

  async stop() {
    console.log(`🛑 ${this.name} stopping...`);
    this.isRunning = false;
    clearInterval(this.optimizationInterval);
    console.log(`✅ ${this.name} stopped`);
  }

  getStatus() {
    return {
      name: this.name,
      isRunning: this.isRunning,
      interval: this.interval,
      optimizationsApplied: this.optimizations.length,
      metrics: {
        memorySamples: this.metrics.memory.length,
        costSamples: this.metrics.costs.length
      }
    };
  }

  getOptimizationReport() {
    return {
      totalOptimizations: this.optimizations.length,
      optimizationsByType: this.groupOptimizationsByType(),
      recentOptimizations: this.optimizations.slice(-10),
      metrics: this.metrics
    };
  }

  groupOptimizationsByType() {
    const grouped = {};
    for (const opt of this.optimizations) {
      if (!grouped[opt.type]) {
        grouped[opt.type] = 0;
      }
      grouped[opt.type]++;
    }
    return grouped;
  }
}

// Auto-start wenn direkt ausgeführt
if (import.meta.url === `file://${process.argv[1]}`) {
  const bot = new OptimizerBot();
  bot.start();
  
  // Graceful shutdown
  process.on('SIGINT', async () => {
    await bot.stop();
    process.exit(0);
  });
}

export default OptimizerBot;
