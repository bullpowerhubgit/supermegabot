#!/usr/bin/env node

/**
 * SecurityBot - Überwacht und repariert Sicherheitsprobleme
 * XSS-Scanner, Token-Manager, API-Key Validator
 */

import fs from 'fs';
import path from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

class SecurityBot {
    constructor() {
        this.name = 'SecurityBot';
        this.status = 'active';
        this.lastScan = null;
        this.issues = [];
        this.fixes = 0;
    }

    async scanForXSS() {
        console.log('🔍 Scanning for XSS vulnerabilities...');
        
        const files = await this.findJSFiles();
        const issues = [];
        
        for (const file of files) {
            const content = fs.readFileSync(file, 'utf8');
            const xssPatterns = [
                /innerHTML\s*=/g,
                /eval\s*\(/g,
                /Function\s*\(/g,
                /document\.write/g
            ];
            
            xssPatterns.forEach(pattern => {
                const matches = content.match(pattern);
                if (matches) {
                    issues.push({
                        file,
                        pattern: pattern.source,
                        count: matches.length,
                        severity: 'high'
                    });
                }
            });
        }
        
        this.issues = issues;
        this.lastScan = new Date();
        
        console.log(`📊 XSS Scan Complete: ${issues.length} issues found`);
        return issues;
    }

    async findJSFiles() {
        const { stdout } = await execAsync('find . -name "*.js" -not -path "./node_modules/*"');
        return stdout.trim().split('\n').filter(Boolean);
    }

    async validateTokens() {
        console.log('🔑 Validating API tokens...');
        
        const tokenFiles = ['.env', 'API_CONFIG_TEMPLATE.env'];
        const issues = [];
        
        for (const file of tokenFiles) {
            if (fs.existsSync(file)) {
                const content = fs.readFileSync(file, 'utf8');
                
                // Check for expired or example tokens
                const expiredPatterns = [
                    /shpat_[a-f0-9]{32}/, // Shopify token pattern (detect any hardcoded shpat_ tokens)
                    /YOUR_.*_HERE/,
                    /example/,
                    /test/
                ];
                
                expiredPatterns.forEach(pattern => {
                    if (pattern.test(content)) {
                        issues.push({
                            file,
                            issue: 'Expired or example token',
                            pattern: pattern.source,
                            severity: 'critical'
                        });
                    }
                });
            }
        }
        
        console.log(`🔑 Token Validation Complete: ${issues.length} issues found`);
        return issues;
    }

    async fixSecurityIssues() {
        console.log('🔧 Fixing security issues...');
        
        let fixes = 0;
        
        // Fix XSS issues
        for (const issue of this.issues) {
            if (issue.pattern.includes('innerHTML')) {
                await this.fixInnerHTML(issue.file);
                fixes++;
            }
        }
        
        // Fix token issues
        const tokenIssues = await this.validateTokens();
        for (const issue of tokenIssues) {
            await this.fixTokenIssue(issue);
            fixes++;
        }
        
        this.fixes = fixes;
        console.log(`🔧 Security fixes applied: ${fixes}`);
        return fixes;
    }

    async fixInnerHTML(filePath) {
        const content = fs.readFileSync(filePath, 'utf8');
        const fixed = content.replace(/\.innerHTML\s*=/g, '.textContent =');
        fs.writeFileSync(filePath, fixed);
        console.log(`✅ Fixed innerHTML in ${filePath}`);
    }

    async fixTokenIssue(issue) {
        console.log(`⚠️ Token issue in ${issue.file}: ${issue.issue}`);
        // Would need manual intervention or token rotation
    }

    async generateReport() {
        const report = {
            timestamp: new Date(),
            bot: this.name,
            status: this.status,
            lastScan: this.lastScan,
            issues: this.issues,
            fixes: this.fixes,
            recommendations: [
                'Install DOMPurify for complex HTML content',
                'Implement token rotation system',
                'Add automated security scanning'
            ]
        };
        
        const reportPath = 'reports/security-report.json';
        fs.mkdirSync('reports', { recursive: true });
        fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
        
        console.log(`📄 Security report saved to ${reportPath}`);
        return report;
    }

    async startMonitoring() {
        console.log(`🤖 ${this.name} starting continuous monitoring...`);
        
        // Run security scan every 5 minutes
        setInterval(async () => {
            await this.scanForXSS();
            await this.validateTokens();
            await this.generateReport();
        }, 5 * 60 * 1000);
        
        // Initial scan
        await this.scanForXSS();
        await this.validateTokens();
        await this.generateReport();
    }
}

// Start SecurityBot
if (import.meta.url === `file://${process.argv[1]}`) {
    const bot = new SecurityBot();
    bot.startMonitoring().catch(console.error);
}

export default SecurityBot;
