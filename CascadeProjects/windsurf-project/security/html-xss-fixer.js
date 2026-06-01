#!/usr/bin/env node

/**
 * HTML XSS Security Fixer
 * Fixes innerHTML vulnerabilities in HTML dashboard files
 */

import fs from 'fs';
import path from 'path';

const HTML_XSS_PATTERNS = [
    // Basic innerHTML assignments in HTML files
    {
        pattern: /(\w+)\.innerHTML\s*=\s*['"`]([^'"`]*)['"`]/g,
        replacement: (match, varName, content) => {
            // If content contains HTML tags, use DOMHelper
            if (/<[^>]+>/.test(content)) {
                return `${varName}.innerHTML = DOMHelper.sanitizeHTML('${content.replace(/'/g, "\\'")}')`;
            }
            return `${varName}.textContent = '${content.replace(/'/g, "\\'")}'`;
        },
        description: 'innerHTML -> textContent/sanitized'
    },
    // innerHTML with template literals in HTML
    {
        pattern: /(\w+)\.innerHTML\s*=\s*`([^`]*)`/g,
        replacement: (match, varName, content) => {
            if (/<[^>]+>/.test(content)) {
                return `${varName}.innerHTML = DOMHelper.sanitizeHTML(\`${content}\`)`;
            }
            return `${varName}.textContent = \`${content}\``;
        },
        description: 'innerHTML template literal -> safe'
    },
    // innerHTML = '' patterns
    {
        pattern: /(\w+)\.innerHTML\s*=\s*['"`]\s*['"`]/g,
        replacement: (match, varName) => {
            return `${varName}.textContent = ''`;
        },
        description: 'innerHTML = \'\' -> textContent = \'\''
    }
];

const HTML_FILES_TO_FIX = [
    'mega-dashboard.html',
    'unified-mega-dashboard.html',
    'pro-mega-dashboard.html',
    'bot-monitoring-dashboard.html',
    'watchdog-monitor.html',
    'templates/dashboard.html',
    'AUTOSHOP_FRONTEND.html',
    'QUICKCASH_FRONTEND.html',
    'ultimate-ecommerce-dashboard.html',
    'secure-dashboard-template.html',
    'shopify-dashboard.html'
];

function fixXSSInHTMLFile(filePath) {
    if (!fs.existsSync(filePath)) {
        console.log(`⚠️  File not found: ${filePath}`);
        return false;
    }

    let content = fs.readFileSync(filePath, 'utf8');
    let modified = false;

    HTML_XSS_PATTERNS.forEach(({ pattern, replacement, description }) => {
        const matches = content.match(pattern);
        if (matches) {
            content = content.replace(pattern, replacement);
            modified = true;
            console.log(`🔧 Fixed ${description} in ${filePath} (${matches.length} occurrences)`);
        }
    });

    if (modified) {
        // Add DOMHelper script tag if not present
        if (!content.includes('DOMHelper.js')) {
            const scriptTag = '<script src="utils/DOMHelper.js"></script>';
            if (content.includes('<head>')) {
                content = content.replace('<head>', `<head>\n    ${scriptTag}`);
            } else if (content.includes('<html>')) {
                content = content.replace('<html>', `<html>\n  <head>\n    ${scriptTag}\n  </head>`);
            } else {
                content = `${scriptTag}\n${content}`;
            }
            console.log(`📦 Added DOMHelper script to ${filePath}`);
        }
        
        fs.writeFileSync(filePath, content);
        console.log(`✅ Secured: ${filePath}`);
        return true;
    } else {
        console.log(`ℹ️  No XSS issues found in: ${filePath}`);
        return false;
    }
}

function main() {
    console.log('🛡️  HTML XSS Security Fixer - Starting...\n');
    
    let totalFixed = 0;
    
    HTML_FILES_TO_FIX.forEach(file => {
        if (fixXSSInHTMLFile(file)) {
            totalFixed++;
        }
    });

    console.log(`\n📊 Summary: ${totalFixed} HTML files secured`);
    console.log('🎯 Recommendation: Test all dashboards after fixes');
}

if (import.meta.url === `file://${process.argv[1]}`) {
    main();
}

export { fixXSSInHTMLFile, HTML_XSS_PATTERNS };
