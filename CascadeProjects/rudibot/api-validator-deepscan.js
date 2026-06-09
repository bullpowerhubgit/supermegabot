#!/usr/bin/env node

// 🔐 API KEY VALIDATOR + DEEP SCAN SYSTEM
// Rudolf Sarkany · Integrated Security & Validation System
// ===================================================

'use strict';
require('dotenv').config();

const crypto = require('crypto');
const fs = require('fs').promises;
const path = require('path');
const axios = require('axios');

// ── VALIDATOR CONFIGURATION ─────────────────────────────────────
const VALIDATOR_CONFIG = {
    // API Key Patterns
    patterns: {
        shopify: /^shpat_[a-f0-9]{32,}$/i,
        telegram: /^[0-9]{8,10}:[a-zA-Z0-9_-]{35,}$/,
        stripe: /^sk_live_[a-zA-Z0-9]{24,}$/,
        openai: /^sk-[a-zA-Z0-9]{48,}$/,
        supabase: /^eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+$/,
        github: /^ghp_[a-zA-Z0-9]{36,}$/,
        vercel: /^vca_[a-zA-Z0-9]{32,}$/
    },
    
    // Security Rules
    securityRules: {
        minLength: 8,
        maxLength: 500,
        noCommonPatterns: true,
        checkEntropy: true,
        validateFormat: true
    },
    
    // Deep Scan Configuration
    deepScan: {
        maxDepth: 5,
        fileTypes: ['.js', '.ts', '.json', '.env', '.env.example', '.yml', '.yaml', '.toml'],
        excludeDirs: ['node_modules', '.git', 'dist', 'build', 'coverage'],
        sensitivePatterns: [
            /password/i,
            /secret/i,
            /key/i,
            /token/i,
            /auth/i,
            /credential/i
        ]
    }
};

// ── API KEY VALIDATOR CLASS ─────────────────────────────────────
class ApiKeyValidator {
    constructor() {
        this.results = [];
        this.scanStartTime = null;
    }

    // Validate single API key
    validateApiKey(key, type, context = {}) {
        const result = {
            key: this.maskApiKey(key),
            type: type,
            valid: false,
            issues: [],
            securityScore: 0,
            context: context,
            timestamp: new Date().toISOString()
        };

        try {
            // 1. Pattern Validation
            if (!this.validatePattern(key, type)) {
                result.issues.push('Invalid format pattern');
            }

            // 2. Security Validation
            const securityIssues = this.validateSecurity(key);
            result.issues.push(...securityIssues);

            // 3. Entropy Check
            const entropy = this.calculateEntropy(key);
            if (entropy < 3.0) {
                result.issues.push('Low entropy - weak key');
            }

            // 4. Length Validation
            if (key.length < VALIDATOR_CONFIG.securityRules.minLength) {
                result.issues.push('Key too short');
            }
            if (key.length > VALIDATOR_CONFIG.securityRules.maxLength) {
                result.issues.push('Key too long');
            }

            // Calculate security score
            result.securityScore = this.calculateSecurityScore(key, result.issues);
            result.valid = result.issues.length === 0 && result.securityScore >= 70;

        } catch (error) {
            result.issues.push(`Validation error: ${error.message}`);
            result.valid = false;
        }

        return result;
    }

    // Validate pattern
    validatePattern(key, type) {
        const pattern = VALIDATOR_CONFIG.patterns[type];
        if (!pattern) {
            return false; // Unknown type
        }
        return pattern.test(key);
    }

    // Validate security rules
    validateSecurity(key) {
        const issues = [];
        
        // Check for common patterns
        if (VALIDATOR_CONFIG.securityRules.noCommonPatterns) {
            const commonPatterns = ['test', 'demo', 'sample', 'example', 'dev', 'staging'];
            for (const pattern of commonPatterns) {
                if (key.toLowerCase().includes(pattern)) {
                    issues.push(`Contains common pattern: ${pattern}`);
                }
            }
        }

        // Check for sequential characters
        if (this.hasSequentialChars(key)) {
            issues.push('Contains sequential characters');
        }

        // Check for repeated characters
        if (this.hasRepeatedChars(key)) {
            issues.push('Contains repeated characters');
        }

        return issues;
    }

    // Calculate entropy
    calculateEntropy(key) {
        const freq = {};
        for (const char of key) {
            freq[char] = (freq[char] || 0) + 1;
        }
        
        let entropy = 0;
        const len = key.length;
        for (const count of Object.values(freq)) {
            const p = count / len;
            entropy -= p * Math.log2(p);
        }
        
        return entropy;
    }

    // Check for sequential characters
    hasSequentialChars(key) {
        for (let i = 0; i < key.length - 2; i++) {
            const char1 = key.charCodeAt(i);
            const char2 = key.charCodeAt(i + 1);
            const char3 = key.charCodeAt(i + 2);
            
            if (char2 === char1 + 1 && char3 === char2 + 1) {
                return true;
            }
        }
        return false;
    }

    // Check for repeated characters
    hasRepeatedChars(key) {
        for (let i = 0; i < key.length - 2; i++) {
            if (key[i] === key[i + 1] && key[i + 1] === key[i + 2]) {
                return true;
            }
        }
        return false;
    }

    // Calculate security score
    calculateSecurityScore(key, issues) {
        let score = 100;
        
        // Deduct points for issues
        score -= issues.length * 15;
        
        // Bonus for length
        if (key.length > 20) score += 10;
        if (key.length > 30) score += 10;
        
        // Bonus for entropy
        const entropy = this.calculateEntropy(key);
        if (entropy > 4.0) score += 10;
        if (entropy > 5.0) score += 10;
        
        // Bonus for mixed characters
        if (/[a-z]/.test(key) && /[A-Z]/.test(key)) score += 5;
        if (/[a-zA-Z]/.test(key) && /[0-9]/.test(key)) score += 5;
        if (/[a-zA-Z0-9]/.test(key) && /[^a-zA-Z0-9]/.test(key)) score += 5;
        
        return Math.max(0, Math.min(100, score));
    }

    // Mask API key for display
    maskApiKey(key) {
        if (!key || key.length < 8) return '***';
        return key.substring(0, 4) + '***' + key.substring(key.length - 4);
    }
}

// ── DEEP SCAN SYSTEM CLASS ───────────────────────────────────────
class DeepScanSystem {
    constructor() {
        this.validator = new ApiKeyValidator();
        this.scanResults = [];
        this.scanProgress = 0;
    }

    // Perform deep scan of directory
    async deepScan(directory = process.cwd()) {
        console.log('🔍 Starting deep scan...');
        this.scanStartTime = Date.now();
        this.scanResults = [];
        
        try {
            await this.scanDirectory(directory, 0);
            this.generateReport();
            return this.scanResults;
        } catch (error) {
            console.error('❌ Deep scan error:', error.message);
            throw error;
        }
    }

    // Scan directory recursively
    async scanDirectory(dir, depth) {
        if (depth > VALIDATOR_CONFIG.deepScan.maxDepth) return;
        
        try {
            const entries = await fs.readdir(dir, { withFileTypes: true });
            
            for (const entry of entries) {
                const fullPath = path.join(dir, entry.name);
                
                // Skip excluded directories
                if (entry.isDirectory() && VALIDATOR_CONFIG.deepScan.excludeDirs.includes(entry.name)) {
                    continue;
                }
                
                if (entry.isDirectory()) {
                    await this.scanDirectory(fullPath, depth + 1);
                } else if (entry.isFile()) {
                    await this.scanFile(fullPath);
                }
                
                // Update progress
                this.scanProgress = Math.min(99, this.scanProgress + 1);
            }
        } catch (error) {
            console.warn(`⚠️  Error scanning directory ${dir}:`, error.message);
        }
    }

    // Scan individual file
    async scanFile(filePath) {
        const ext = path.extname(filePath);
        
        // Only scan relevant file types
        if (!VALIDATOR_CONFIG.deepScan.fileTypes.includes(ext)) {
            return;
        }
        
        try {
            const content = await fs.readFile(filePath, 'utf8');
            const relativePath = path.relative(process.cwd(), filePath);
            
            // Find potential API keys
            const potentialKeys = this.extractPotentialKeys(content);
            
            for (const { key, type, line } of potentialKeys) {
                const validation = this.validator.validateApiKey(key, type, {
                    file: relativePath,
                    line: line,
                    context: this.extractContext(content, line)
                });
                
                this.scanResults.push({
                    ...validation,
                    file: relativePath,
                    line: line,
                    severity: this.determineSeverity(validation),
                    recommendation: this.generateRecommendation(validation)
                });
            }
            
            // Check for sensitive patterns
            const sensitiveMatches = this.findSensitivePatterns(content);
            for (const match of sensitiveMatches) {
                this.scanResults.push({
                    type: 'sensitive_pattern',
                    pattern: match.pattern,
                    file: relativePath,
                    line: match.line,
                    severity: 'medium',
                    recommendation: 'Review and secure sensitive information',
                    context: this.extractContext(content, match.line)
                });
            }
            
        } catch (error) {
            console.warn(`⚠️  Error scanning file ${filePath}:`, error.message);
        }
    }

    // Extract potential API keys from content
    extractPotentialKeys(content) {
        const keys = [];
        const lines = content.split('\n');
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            
            // Check each pattern type
            for (const [type, pattern] of Object.entries(VALIDATOR_CONFIG.patterns)) {
                const matches = line.match(pattern);
                if (matches) {
                    for (const match of matches) {
                        keys.push({
                            key: match,
                            type: type,
                            line: i + 1
                        });
                    }
                }
            }
        }
        
        return keys;
    }

    // Find sensitive patterns
    findSensitivePatterns(content) {
        const matches = [];
        const lines = content.split('\n');
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            
            for (const pattern of VALIDATOR_CONFIG.deepScan.sensitivePatterns) {
                if (pattern.test(line)) {
                    matches.push({
                        pattern: pattern.toString(),
                        line: i + 1
                    });
                }
            }
        }
        
        return matches;
    }

    // Extract context around a line
    extractContext(content, lineNumber, contextLines = 2) {
        const lines = content.split('\n');
        const start = Math.max(0, lineNumber - contextLines - 1);
        const end = Math.min(lines.length, lineNumber + contextLines);
        
        return lines.slice(start, end).map((line, index) => ({
            lineNumber: start + index + 1,
            content: line.trim(),
            isTarget: start + index === lineNumber - 1
        }));
    }

    // Determine severity of issue
    determineSeverity(validation) {
        if (!validation.valid) {
            if (validation.securityScore < 30) return 'critical';
            if (validation.securityScore < 60) return 'high';
            return 'medium';
        }
        return 'low';
    }

    // Generate recommendation
    generateRecommendation(validation) {
        if (!validation.valid) {
            if (validation.issues.includes('Invalid format pattern')) {
                return 'Check API key format and regenerate if necessary';
            }
            if (validation.issues.includes('Low entropy')) {
                return 'Regenerate API key with higher entropy';
            }
            if (validation.issues.includes('Key too short')) {
                return 'Use longer API key if possible';
            }
            return 'Review and fix security issues';
        }
        return 'API key appears secure';
    }

    // Generate comprehensive report
    generateReport() {
        const scanTime = Date.now() - this.scanStartTime;
        
        const summary = {
            totalIssues: this.scanResults.length,
            criticalIssues: this.scanResults.filter(r => r.severity === 'critical').length,
            highIssues: this.scanResults.filter(r => r.severity === 'high').length,
            mediumIssues: this.scanResults.filter(r => r.severity === 'medium').length,
            lowIssues: this.scanResults.filter(r => r.severity === 'low').length,
            scanTime: scanTime,
            filesScanned: [...new Set(this.scanResults.map(r => r.file))].length
        };
        
        console.log('\n📊 DEEP SCAN REPORT');
        console.log('='.repeat(50));
        console.log(`⏱️  Scan Time: ${scanTime}ms`);
        console.log(`📁 Files Scanned: ${summary.filesScanned}`);
        console.log(`🔍 Total Issues: ${summary.totalIssues}`);
        console.log(`🚨 Critical: ${summary.criticalIssues}`);
        console.log(`⚠️  High: ${summary.highIssues}`);
        console.log(`📋 Medium: ${summary.mediumIssues}`);
        console.log(`ℹ️  Low: ${summary.lowIssues}`);
        
        // Show top issues
        const topIssues = this.scanResults
            .filter(r => r.severity === 'critical' || r.severity === 'high')
            .slice(0, 10);
            
        if (topIssues.length > 0) {
            console.log('\n🚨 TOP PRIORITY ISSUES:');
            topIssues.forEach((issue, index) => {
                console.log(`${index + 1}. ${issue.file}:${issue.line} - ${issue.type}`);
                console.log(`   Severity: ${issue.severity}`);
                console.log(`   Recommendation: ${issue.recommendation}`);
            });
        }
        
        return summary;
    }

    // Get scan progress
    getProgress() {
        return {
            progress: this.scanProgress,
            issuesFound: this.scanResults.length,
            scanTime: this.scanStartTime ? Date.now() - this.scanStartTime : 0
        };
    }
}

// ── INTEGRATED SYSTEM ───────────────────────────────────────────────
class IntegratedValidatorScanner {
    constructor() {
        this.validator = new ApiKeyValidator();
        this.scanner = new DeepScanSystem();
        this.isScanning = false;
    }

    // Quick validation of specific API key
    validateKey(key, type, context = {}) {
        return this.validator.validateApiKey(key, type, context);
    }

    // Start deep scan
    async startDeepScan(directory = process.cwd()) {
        if (this.isScanning) {
            throw new Error('Scan already in progress');
        }
        
        this.isScanning = true;
        try {
            const results = await this.scanner.deepScan(directory);
            return results;
        } finally {
            this.isScanning = false;
        }
    }

    // Get scan status
    getScanStatus() {
        return {
            isScanning: this.isScanning,
            progress: this.scanner.getProgress(),
            results: this.scanner.scanResults
        };
    }

    // Generate security summary
    generateSecuritySummary() {
        const results = this.scanner.scanResults;
        
        const summary = {
            overallSecurity: 'good',
            totalIssues: results.length,
            criticalIssues: results.filter(r => r.severity === 'critical').length,
            recommendations: []
        };
        
        if (summary.criticalIssues > 0) {
            summary.overallSecurity = 'critical';
            summary.recommendations.push('Address critical security issues immediately');
        } else if (summary.totalIssues > 5) {
            summary.overallSecurity = 'warning';
            summary.recommendations.push('Review and fix security issues');
        }
        
        return summary;
    }
}

// ── EXPORTS ───────────────────────────────────────────────────────
module.exports = {
    ApiKeyValidator,
    DeepScanSystem,
    IntegratedValidatorScanner,
    VALIDATOR_CONFIG
};

// ── CLI USAGE ───────────────────────────────────────────────────────
if (require.main === module) {
    const scanner = new IntegratedValidatorScanner();
    
    // Example usage
    console.log('🔐 API Key Validator + Deep Scan System');
    console.log('='.repeat(50));
    
    // Quick validation example
    const testKey = 'shpat_1234567890abcdef1234567890abcdef';
    const validation = scanner.validateKey(testKey, 'shopify');
    console.log('Validation Result:', validation);
    
    // Start deep scan
    scanner.startDeepScan().then(results => {
        console.log(`\n✅ Deep scan completed with ${results.length} issues found`);
    }).catch(error => {
        console.error('❌ Deep scan failed:', error.message);
    });
}
