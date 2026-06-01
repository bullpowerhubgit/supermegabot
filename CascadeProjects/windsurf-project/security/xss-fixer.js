#!/usr/bin/env node

/**
 * XSS Security Fixer
 * Replaces dangerous innerHTML with safe DOM manipulation
 */

import fs from 'fs';
import path from 'path';

const XSS_PATTERNS = [
    // Basic innerHTML assignments with string literals
    {
        pattern: /(\w+)\.innerHTML\s*=\s*['"`]([^'"`]*)['"`]/g,
        replacement: (match, varName, content) => {
            // If content contains HTML tags, use sanitization
            if (/<[^>]+>/.test(content)) {
                return `${varName}.innerHTML = DOMHelper.sanitizeHTML('${content.replace(/'/g, "\\'")}')`;
            }
            return `${varName}.textContent = '${content.replace(/'/g, "\\'")}'`;
        },
        description: 'innerHTML -> textContent/sanitized'
    },
    // innerHTML with template literals
    {
        pattern: /(\.w+)\.innerHTML\s*=\s*`([^`]*)`/g,
        replacement: (match, varName, content) => {
            if (/<[^>]+>/.test(content)) {
                return `${varName}.innerHTML = DOMHelper.sanitizeHTML(\`${content}\`)`;
            }
            return `${varName}.textContent = \`${content}\``;
        },
        description: 'innerHTML template literal -> safe'
    },
    // innerHTML with concatenation
    {
        pattern: /(\.w+)\.innerHTML\s*\+=\s*(.+?)(?:;|$)/g,
        replacement: (match, varName, content) => {
            return `${varName}.textContent += ${content}`;
        },
        description: 'innerHTML += -> textContent +='
    },
    // resultDiv.innerHTML patterns
    {
        pattern: /resultDiv\.innerHTML\s*=\s*(.+?)(?:;|$)/g,
        replacement: (match, content) => {
            return `resultDiv.textContent = ${content}`;
        },
        description: 'resultDiv.innerHTML -> resultDiv.textContent'
    }
];

const FILES_TO_FIX = [
    'super-server.js',
    'mega-dashboard.js',
    'mega-dashboard-backend.js',
    'monitor-dashboard.js',
    'orchestrator-dashboard.js',
    'adaptive-deepscan-system.js',
    'bots/specialized/monitoring-bot.js',
    'bots/specialized/maintenance-bot.js',
    'bots/specialized/error-detection-bot.js',
    'bots/webapp/control-bot.js',
    'bots/webapp/maintenance-bot.js',
    'professional-desktop-monitor.js',
    'utils/DOMHelper.js'
];

function fixXSSInFile(filePath) {
    if (!fs.existsSync(filePath)) {
        console.log(`⚠️  File not found: ${filePath}`);
        return false;
    }

    let content = fs.readFileSync(filePath, 'utf8');
    let modified = false;

    XSS_PATTERNS.forEach(({ pattern, replacement, description }) => {
        const matches = content.match(pattern);
        if (matches) {
            content = content.replace(pattern, replacement);
            modified = true;
            console.log(`🔧 Fixed ${description} in ${filePath} (${matches.length} occurrences)`);
        }
    });

    if (modified) {
        fs.writeFileSync(filePath, content);
        console.log(`✅ Secured: ${filePath}`);
        return true;
    } else {
        console.log(`ℹ️  No XSS issues found in: ${filePath}`);
        return false;
    }
}

function main() {
    console.log('🛡️  XSS Security Fixer - Starting...\n');
    
    let totalFixed = 0;
    
    FILES_TO_FIX.forEach(file => {
        if (fixXSSInFile(file)) {
            totalFixed++;
        }
    });

    console.log(`\n📊 Summary: ${totalFixed} files secured`);
    console.log('🎯 Recommendation: Add DOMPurify for complex HTML content');
}

if (import.meta.url === `file://${process.argv[1]}`) {
    main();
}

export { fixXSSInFile, XSS_PATTERNS };
