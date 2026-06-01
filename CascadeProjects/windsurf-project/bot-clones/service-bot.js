#!/usr/bin/env node

/**
 * ServiceBot - Überwacht und verwaltet System-Services
 * n8n, Netdata, PM2, Docker Services Manager
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import https from 'https';
import http from 'http';

const execAsync = promisify(exec);

class ServiceBot {
    constructor() {
        this.name = 'ServiceBot';
        this.status = 'active';
        this.services = {
            n8n: { port: 5678, status: 'unknown', process: null },
            netdata: { port: 19999, status: 'unknown', process: null },
            pm2: { status: 'unknown', processes: [] },
            docker: { status: 'unknown', containers: [] }
        };
        this.restarts = 0;
        this.lastCheck = null;
    }

    async checkServiceStatus(serviceName, port) {
        return new Promise((resolve) => {
            const protocol = port === 443 ? https : http;
            
            const req = protocol.request({
                hostname: 'localhost',
                port: port,
                path: '/',
                timeout: 3000
            }, (res) => {
                resolve(res.statusCode === 200 ? 'running' : 'error');
            });

            req.on('error', () => resolve('down'));
            req.on('timeout', () => {
                req.destroy();
                resolve('timeout');
            });

            req.end();
        });
    }

    async checkN8N() {
        try {
            const status = await this.checkServiceStatus('n8n', 5678);
            this.services.n8n.status = status;
            
            if (status === 'down') {
                console.log('🔧 n8n is down, attempting to restart...');
                await this.startN8N();
                this.restarts++;
            }
            
            return status;
        } catch (error) {
            console.warn('Failed to check n8n status:', error.message);
            return 'error';
        }
    }

    async checkNetdata() {
        try {
            const status = await this.checkServiceStatus('netdata', 19999);
            this.services.netdata.status = status;
            
            if (status === 'down') {
                console.log('🔧 Netdata is down, attempting to restart...');
                await this.startNetdata();
                this.restarts++;
            }
            
            return status;
        } catch (error) {
            console.warn('Failed to check Netdata status:', error.message);
            return 'error';
        }
    }

    async checkPM2() {
        try {
            const { stdout } = await execAsync('pm2 list 2>/dev/null || echo "PM2_NOT_INSTALLED"');
            
            if (stdout.includes('PM2_NOT_INSTALLED')) {
                this.services.pm2.status = 'not_installed';
                return 'not_installed';
            }
            
            const lines = stdout.trim().split('\n');
            const processes = [];
            
            for (let i = 2; i < lines.length; i++) {
                const line = lines[i].trim();
                if (line) {
                    const parts = line.split(/\s+/);
                    processes.push({
                        name: parts[2],
                        status: parts[3],
                        cpu: parseFloat(parts[4]) || 0,
                        memory: parts[5],
                        pid: parts[0] !== '┌' ? parts[0] : null
                    });
                }
            }
            
            this.services.pm2.processes = processes;
            this.services.pm2.status = processes.length > 0 ? 'running' : 'no_processes';
            
            return this.services.pm2.status;
        } catch (error) {
            console.warn('Failed to check PM2 status:', error.message);
            return 'error';
        }
    }

    async checkDocker() {
        try {
            const { stdout } = await execAsync('docker ps 2>/dev/null || echo "DOCKER_NOT_INSTALLED"');
            
            if (stdout.includes('DOCKER_NOT_INSTALLED')) {
                this.services.docker.status = 'not_installed';
                return 'not_installed';
            }
            
            const lines = stdout.trim().split('\n');
            const containers = [];
            
            for (let i = 1; i < lines.length; i++) {
                const line = lines[i].trim();
                if (line) {
                    const parts = line.split(/\s{2,}/);
                    containers.push({
                        id: parts[0],
                        image: parts[1],
                        status: parts[2],
                        ports: parts[3] || ''
                    });
                }
            }
            
            this.services.docker.containers = containers;
            this.services.docker.status = containers.length > 0 ? 'running' : 'no_containers';
            
            return this.services.docker.status;
        } catch (error) {
            console.warn('Failed to check Docker status:', error.message);
            return 'error';
        }
    }

    async startN8N() {
        try {
            console.log('🚀 Starting n8n...');
            
            // Check if n8n is installed
            const { stdout } = await execAsync('which n8n');
            if (!stdout.trim()) {
                console.log('📦 Installing n8n...');
                await execAsync('npm install -g n8n');
            }
            
            // Start n8n in background
            await execAsync('nohup n8n start > /tmp/n8n.log 2>&1 &');
            
            // Wait a bit and check status
            await new Promise(resolve => setTimeout(resolve, 5000));
            const status = await this.checkServiceStatus('n8n', 5678);
            
            if (status === 'running') {
                console.log('✅ n8n started successfully');
                this.services.n8n.status = 'running';
            } else {
                console.log('❌ n8n failed to start');
                this.services.n8n.status = 'failed';
            }
            
            return status;
        } catch (error) {
            console.error('Failed to start n8n:', error.message);
            this.services.n8n.status = 'error';
            return 'error';
        }
    }

    async startNetdata() {
        try {
            console.log('🚀 Starting Netdata...');
            
            // Try to start with brew services first
            try {
                await execAsync('brew services start netdata');
                console.log('✅ Netdata started via brew services');
                this.services.netdata.status = 'running';
                return 'running';
            } catch (brewError) {
                console.log('🔄 Brew services failed, trying direct start...');
                
                // Fallback: direct start
                await execAsync('nohup netdata > /tmp/netdata.log 2>&1 &');
                
                await new Promise(resolve => setTimeout(resolve, 3000));
                const status = await this.checkServiceStatus('netdata', 19999);
                
                if (status === 'running') {
                    console.log('✅ Netdata started directly');
                    this.services.netdata.status = 'running';
                } else {
                    console.log('❌ Netdata failed to start');
                    this.services.netdata.status = 'failed';
                }
                
                return status;
            }
        } catch (error) {
            console.error('Failed to start Netdata:', error.message);
            this.services.netdata.status = 'error';
            return 'error';
        }
    }

    async restartPM2Service(serviceName) {
        try {
            console.log(`🔄 Restarting PM2 service: ${serviceName}`);
            await execAsync(`pm2 restart ${serviceName}`);
            console.log(`✅ PM2 service ${serviceName} restarted`);
            return true;
        } catch (error) {
            console.error(`Failed to restart PM2 service ${serviceName}:`, error.message);
            return false;
        }
    }

    async restartDockerContainer(containerId) {
        try {
            console.log(`🔄 Restarting Docker container: ${containerId}`);
            await execAsync(`docker restart ${containerId}`);
            console.log(`✅ Docker container ${containerId} restarted`);
            return true;
        } catch (error) {
            console.error(`Failed to restart Docker container ${containerId}:`, error.message);
            return false;
        }
    }

    async getAllServiceStatus() {
        await Promise.all([
            this.checkN8N(),
            this.checkNetdata(),
            this.checkPM2(),
            this.checkDocker()
        ]);
        
        this.lastCheck = new Date();
        return this.services;
    }

    async generateReport() {
        const report = {
            timestamp: new Date(),
            bot: this.name,
            status: this.status,
            services: this.services,
            restarts: this.restarts,
            lastCheck: this.lastCheck,
            summary: {
                totalServices: Object.keys(this.services).length,
                runningServices: Object.values(this.services).filter(s => s.status === 'running').length,
                downServices: Object.values(this.services).filter(s => s.status === 'down').length,
                issues: Object.values(this.services).filter(s => ['down', 'error', 'failed'].includes(s.status))
            },
            recommendations: this.getRecommendations()
        };
        
        const reportPath = 'reports/service-report.json';
        fs.mkdirSync('reports', { recursive: true });
        fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
        
        console.log(`📄 Service report saved to ${reportPath}`);
        return report;
    }

    getRecommendations() {
        const recommendations = [];
        
        if (this.services.n8n.status === 'down') {
            recommendations.push('Install and configure n8n for workflow automation');
        }
        
        if (this.services.netdata.status === 'down') {
            recommendations.push('Install Netdata for system monitoring');
        }
        
        if (this.services.pm2.status === 'not_installed') {
            recommendations.push('Install PM2 for process management');
        }
        
        if (this.restarts > 5) {
            recommendations.push('Consider investigating why services are frequently restarting');
        }
        
        return recommendations;
    }

    async startMonitoring() {
        console.log(`🤖 ${this.name} starting service monitoring...`);
        
        // Monitor every 60 seconds
        setInterval(async () => {
            await this.getAllServiceStatus();
            await this.generateReport();
        }, 60 * 1000);
        
        // Initial monitoring
        await this.getAllServiceStatus();
        await this.generateReport();
    }
}

// Start ServiceBot
if (import.meta.url === `file://${process.argv[1]}`) {
    const bot = new ServiceBot();
    bot.startMonitoring().catch(console.error);
}

export default ServiceBot;
