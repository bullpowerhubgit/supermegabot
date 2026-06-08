/**
 * Deepscan Action — Executes security deep scan
 * Bridges KIVO intent to Rudibot security system
 */

class DeepscanAction {
  constructor(validatorScanner) {
    this.scanner = validatorScanner;
  }

  async execute(options = {}) {
    const { scope = 'full', chatId } = options;
    
    try {
      // Start deep scan
      console.log(`[DEEPSCAN] Starting ${scope} scan for chat ${chatId}`);
      
      // Execute scan based on scope
      let result;
      switch (scope) {
        case 'quick':
          result = await this.quickScan();
          break;
        case 'full':
          result = await this.fullScan();
          break;
        case 'targeted':
          result = await this.targetedScan(options.target);
          break;
        default:
          result = await this.fullScan();
      }

      return {
        success: true,
        scope,
        result,
        message: this.formatResult(result),
        timestamp: new Date().toISOString()
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Deepscan failed: ${e.message}`
      };
    }
  }

  async quickScan() {
    // Scan only critical files and directories
    const criticalPaths = [
      '.env*',
      '**/*.key',
      '**/*.pem',
      '**/config/**',
      'rudibot/',
      'windsurf-api-gateway/'
    ];

    const results = [];
    for (const path of criticalPaths) {
      const scan = await this.scanner.scanDirectory(path, { recursive: true });
      results.push(scan);
    }

    return this.aggregateResults(results, 'quick');
  }

  async fullScan() {
    // Comprehensive scan of entire project
    const scan = await this.scanner.scanDirectory('.', { 
      recursive: true, 
      maxDepth: 5,
      includeGitIgnore: false 
    });

    return scan;
  }

  async targetedScan(target) {
    // Scan specific directory or file
    const scan = await this.scanner.scanDirectory(target, { 
      recursive: true 
    });

    return scan;
  }

  aggregateResults(results, scanType) {
    const aggregated = {
      scanType,
      totalFiles: 0,
      totalSecrets: 0,
      highRisk: 0,
      mediumRisk: 0,
      lowRisk: 0,
      findings: []
    };

    for (const result of results) {
      aggregated.totalFiles += result.filesScanned || 0;
      aggregated.totalSecrets += result.secretsFound || 0;
      aggregated.highRisk += result.highRisk || 0;
      aggregated.mediumRisk += result.mediumRisk || 0;
      aggregated.lowRisk += result.lowRisk || 0;
      
      if (result.findings) {
        aggregated.findings.push(...result.findings);
      }
    }

    return aggregated;
  }

  formatResult(result) {
    let message = `🔍 *DEEPSCAN RESULTS*\n\n`;
    
    if (result.scanType) {
      message += `📊 Scan Type: ${result.scanType.toUpperCase()}\n`;
    }
    
    message += `📁 Files Scanned: ${result.filesScanned || result.totalFiles || 0}\n`;
    message += `🔑 Secrets Found: ${result.secretsFound || result.totalSecrets || 0}\n`;
    
    if (result.highRisk !== undefined) {
      message += `🚨 High Risk: ${result.highRisk}\n`;
      message += `⚠️ Medium Risk: ${result.mediumRisk || 0}\n`;
      message += `ℹ️ Low Risk: ${result.lowRisk || 0}\n`;
    }
    
    if (result.findings && result.findings.length > 0) {
      message += `\n📋 *Top Findings:*\n`;
      result.findings.slice(0, 5).forEach((finding, i) => {
        message += `${i + 1}. ${finding.file || finding.path} — ${finding.type || 'Unknown'}\n`;
      });
      
      if (result.findings.length > 5) {
        message += `... and ${result.findings.length - 5} more\n`;
      }
    }
    
    if ((result.secretsFound || result.totalSecrets || 0) === 0) {
      message += `\n✅ *No critical secrets detected*\n`;
    } else {
      message += `\n⚠️ *Secrets detected — review required*\n`;
    }
    
    return message;
  }

  // ── Approval Check ───────────────────────────────────────
  requiresApproval(scope) {
    // Full scans always require approval
    if (scope === 'full') return true;
    
    // Targeted scans on sensitive areas require approval
    const sensitiveTargets = [
      'config',
      'secrets',
      'keys',
      '.env'
    ];
    
    return sensitiveTargets.some(target => 
      (scope && scope.toLowerCase().includes(target))
    );
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      scannerAvailable: !!this.scanner,
      supportedScopes: ['quick', 'full', 'targeted'],
      lastScan: this.lastScan || null
    };
  }
}

module.exports = { DeepscanAction };
