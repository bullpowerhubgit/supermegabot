#!/usr/bin/env node

/**
 * PerformanceBot - Überwacht und optimiert System-Performance
 * Load Monitor, Memory Manager, Process Optimizer
 */

import os from 'os';
import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';

const execAsync = promisify(exec);

class PerformanceBot {
    constructor() {
        this.name = 'PerformanceBot';
        this.status = 'active';
        this.metrics = {
            load: [],
            memory: [],
            processes: [],
            uptime: 0
        };
        this.thresholds = {
            loadCritical: 10.0,
            loadWarning: 5.0,
            memoryCritical: 90,
            memoryWarning: 75
        };
        this.optimizations = 0;
    }

    async collectMetrics() {
        // System load
        const loadAvg = os.loadavg();
        this.metrics.load = loadAvg;
        
        // Memory usage
        const totalMem = os.totalmem();
        const freeMem = os.freemem();
        const usedMem = totalMem - freeMem;
        const memoryUsage = (usedMem / totalMem) * 100;
        
        this.metrics.memory = {
            total: Math.round(totalMem / 1024 / 1024 / 1024),
            used: Math.round(usedMem / 1024 / 1024 / 1024),
            free: Math.round(freeMem / 1024 / 1024 / 1024),
            usage: memoryUsage
        };
        
        // Process information
        await this.collectProcessInfo();
        
        // Uptime
        this.metrics.uptime = os.uptime();
        
        return this.metrics;
    }

    async collectProcessInfo() {
        try {
            const { stdout } = await execAsync('ps aux | head -20');
            const lines = stdout.trim().split('\n').slice(1);
            
            this.metrics.processes = lines.map(line => {
                const parts = line.trim().split(/\s+/);
                return {
                    pid: parts[1],
                    cpu: parseFloat(parts[2]),
                    mem: parseFloat(parts[3]),
                    command: parts.slice(10).join(' ').substring(0, 50)
                };
            }).filter(p => p.cpu > 1.0); // Only processes using >1% CPU
        } catch (error) {
            console.warn('Failed to collect process info:', error.message);
        }
    }

    analyzePerformance() {
        const issues = [];
        
        // Check load average
        if (this.metrics.load[0] > this.thresholds.loadCritical) {
            issues.push({
                type: 'load_critical',
                value: this.metrics.load[0],
                message: `CRITICAL: Load average ${this.metrics.load[0].toFixed(2)} exceeds threshold ${this.thresholds.loadCritical}`,
                action: 'kill_high_cpu_processes'
            });
        } else if (this.metrics.load[0] > this.thresholds.loadWarning) {
            issues.push({
                type: 'load_warning',
                value: this.metrics.load[0],
                message: `WARNING: Load average ${this.metrics.load[0].toFixed(2)} exceeds threshold ${this.thresholds.loadWarning}`,
                action: 'monitor_processes'
            });
        }
        
        // Check memory usage
        if (this.metrics.memory.usage > this.thresholds.memoryCritical) {
            issues.push({
                type: 'memory_critical',
                value: this.metrics.memory.usage,
                message: `CRITICAL: Memory usage ${this.metrics.memory.usage.toFixed(1)}% exceeds threshold ${this.thresholds.memoryCritical}`,
                action: 'clear_memory'
            });
        } else if (this.metrics.memory.usage > this.thresholds.memoryWarning) {
            issues.push({
                type: 'memory_warning',
                value: this.metrics.memory.usage,
                message: `WARNING: Memory usage ${this.metrics.memory.usage.toFixed(1)}% exceeds threshold ${this.thresholds.memoryWarning}`,
                action: 'monitor_memory'
            });
        }
        
        return issues;
    }

    async optimizePerformance() {
        console.log('🚀 Optimizing system performance...');
        
        const issues = this.analyzePerformance();
        let optimizations = 0;
        
        for (const issue of issues) {
            switch (issue.action) {
                case 'kill_high_cpu_processes':
                    optimizations += await this.killHighCPUProcesses();
                    break;
                case 'clear_memory':
                    optimizations += await this.clearMemory();
                    break;
                case 'monitor_processes':
                    await this.monitorProcesses();
                    break;
                case 'monitor_memory':
                    await this.monitorMemory();
                    break;
            }
        }
        
        this.optimizations = optimizations;
        console.log(`🔧 Applied ${optimizations} performance optimizations`);
        return optimizations;
    }

    async killHighCPUProcesses() {
        console.log('⚡ Terminating high CPU processes...');
        
        const highCPUProcesses = this.metrics.processes
            .filter(p => p.cpu > 50.0)
            .filter(p => !p.command.includes('Windsurf') && !p.command.includes('SecurityBot'));
        
        let killed = 0;
        
        for (const process of highCPUProcesses) {
            try {
                await execAsync(`kill ${process.pid}`);
                console.log(`🔪 Killed process ${process.pid} (${process.command}) - CPU: ${process.cpu}%`);
                killed++;
            } catch (error) {
                console.warn(`Failed to kill process ${process.pid}:`, error.message);
            }
        }
        
        return killed;
    }

    async clearMemory() {
        console.log('🧹 Clearing system memory...');
        
        try {
            // Clear system caches
            await execAsync('sudo purge');
            console.log('🗑️ System cache cleared');
            
            // Clear npm cache
            await execAsync('npm cache clean --force');
            console.log('🗑️ NPM cache cleared');
            
            // Clear DNS cache
            await execAsync('sudo dscacheutil -flushcache');
            console.log('🗑️ DNS cache cleared');
            
            return 3;
        } catch (error) {
            console.warn('Failed to clear memory:', error.message);
            return 0;
        }
    }

    async monitorProcesses() {
        console.log('👀 Monitoring high CPU processes...');
        
        const highCPUProcesses = this.metrics.processes
            .filter(p => p.cpu > 10.0)
            .slice(0, 5);
        
        if (highCPUProcesses.length > 0) {
            console.log('⚠️ High CPU processes detected:');
            highCPUProcesses.forEach(p => {
                console.log(`   PID ${p.pid}: ${p.command} (${p.cpu.toFixed(1)}% CPU, ${p.mem.toFixed(1)}% MEM)`);
            });
        }
    }

    async monitorMemory() {
        console.log('💾 Memory usage details:');
        console.log(`   Total: ${this.metrics.memory.total}GB`);
        console.log(`   Used: ${this.metrics.memory.used}GB (${this.metrics.memory.usage.toFixed(1)}%)`);
        console.log(`   Free: ${this.metrics.memory.free}GB`);
    }

    async generateReport() {
        const report = {
            timestamp: new Date(),
            bot: this.name,
            status: this.status,
            metrics: this.metrics,
            issues: this.analyzePerformance(),
            optimizations: this.optimizations,
            recommendations: this.getRecommendations()
        };
        
        const reportPath = 'reports/performance-report.json';
        fs.mkdirSync('reports', { recursive: true });
        fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
        
        console.log(`📄 Performance report saved to ${reportPath}`);
        return report;
    }

    getRecommendations() {
        const recommendations = [];
        
        if (this.metrics.load[0] > this.thresholds.loadWarning) {
            recommendations.push('Consider upgrading hardware or optimizing resource-intensive applications');
        }
        
        if (this.metrics.memory.usage > this.thresholds.memoryWarning) {
            recommendations.push('Add more RAM or close memory-intensive applications');
        }
        
        if (this.optimizations > 5) {
            recommendations.push('Consider implementing automated performance monitoring');
        }
        
        return recommendations;
    }

    async startMonitoring() {
        console.log(`🤖 ${this.name} starting performance monitoring...`);
        
        // Monitor every 30 seconds
        setInterval(async () => {
            await this.collectMetrics();
            await this.optimizePerformance();
            await this.generateReport();
        }, 30 * 1000);
        
        // Initial monitoring
        await this.collectMetrics();
        await this.optimizePerformance();
        await this.generateReport();
    }
}

// Start PerformanceBot
if (import.meta.url === `file://${process.argv[1]}`) {
    const bot = new PerformanceBot();
    bot.startMonitoring().catch(console.error);
}

export default PerformanceBot;
