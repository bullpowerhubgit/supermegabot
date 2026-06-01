#!/usr/bin/env node
/**
 * RAM Optimizer - Sofortige RAM-Optimierung
 */

import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

async function optimizeRAM() {
  console.log('🧠 Starting RAM Optimization...');
  
  try {
    // 1. Node.js Prozesse optimieren
    console.log('📊 Checking Node.js processes...');
    const { stdout: nodeProcesses } = await execAsync('ps aux | grep node | grep -v grep');
    const nodeLines = nodeProcesses.split('\n').filter(l => l.trim());
    
    console.log(`Found ${nodeLines.length} Node.js processes`);
    
    // 2. Hohe RAM-Nutzung identifizieren
    const { stdout: highMem } = await execAsync('ps aux | sort -k4 -rn | head -10');
    console.log('Top RAM consumers:');
    console.log(highMem.split('\n').slice(0, 5).join('\n'));
    
    // 3. macOS Memory Pressure reduzieren
    console.log('🧹 Cleaning memory pressure...');
    try {
      await execAsync('sudo purge 2>/dev/null || echo "purge requires sudo"');
    } catch {}
    
    // 4. Cache leeren
    console.log('💾 Clearing caches...');
    try {
      await execAsync('npm cache clean --force 2>/dev/null || echo "npm cache clean failed"');
    } catch {}
    
    // 5. Inaktive Prozesse beenden
    console.log('🔍 Checking for inactive processes...');
    try {
      const { stdout: inactive } = await execAsync("ps -ax -o pid,etime,pcpu,pmem,comm | grep node | grep -v grep | awk '$3 < 0.1 && $4 > 3.0 {print $1}'");
      const inactivePids = inactive.split('\n').filter(l => l.trim());
      
      for (const pid of inactivePids.slice(0, 2)) {
        try {
          process.kill(parseInt(pid), 'SIGTERM');
          console.log(`⚡ Terminated inactive process: ${pid}`);
        } catch {}
      }
    } catch {}
    
    // 6. RAM-Status prüfen
    const totalRAM = require('os').totalmem();
    const freeRAM = require('os').freemem();
    const usedPercent = Math.round(((totalRAM - freeRAM) / totalRAM) * 100);
    
    console.log(`📈 RAM Status: ${usedPercent}% used`);
    console.log(`💾 Free: ${Math.round(freeRAM / 1024 / 1024)} MB`);
    
    if (usedPercent > 80) {
      console.log('⚠️  High RAM usage detected!');
    } else {
      console.log('✅ RAM usage optimized');
    }
    
  } catch (error) {
    console.error('❌ Optimization error:', error.message);
  }
}

// CLI Interface
if (import.meta.url === `file://${process.argv[1]}`) {
  optimizeRAM();
}

export { optimizeRAM };
