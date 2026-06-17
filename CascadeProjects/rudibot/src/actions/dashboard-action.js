/**
 * Dashboard Action — Generates and manages dashboard reports
 * Bridges KIVO report intents to dashboard system
 */

class DashboardAction {
  constructor(dashboardConfig) {
    this.config = {
      baseUrl: dashboardConfig.baseUrl || process.env.DASHBOARD_URL || 'http://localhost:3000',
      timeout: dashboardConfig.timeout || 10000
    };
  }

  async execute(action, options = {}) {
    const { scope, format, chatId } = options;
    
    try {
      switch (action) {
        case 'status':
          return await this.getStatusReport(scope);
        case 'metrics':
          return await this.getMetricsReport(scope);
        case 'health':
          return await this.getHealthReport(scope);
        case 'export':
          return await this.exportData(scope, format);
        default:
          return await this.getOverviewReport();
      }
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Dashboard action failed: ${e.message}`
      };
    }
  }

  async getOverviewReport() {
    // Generate comprehensive overview
    const sections = [
      await this.getSystemSection(),
      await this.getFinanceSection(),
      await this.getSecuritySection(),
      await this.getHomeSection()
    ];

    const report = {
      title: '📊 System Overview',
      timestamp: new Date().toISOString(),
      sections,
      summary: this.generateSummary(sections)
    };

    return {
      success: true,
      report,
      message: this.formatReport(report)
    };
  }

  async getStatusReport(scope) {
    let sections = [];

    switch (scope) {
      case 'system':
        sections = [await this.getSystemSection()];
        break;
      case 'finance':
        sections = [await this.getFinanceSection()];
        break;
      case 'security':
        sections = [await this.getSecuritySection()];
        break;
      case 'home':
        sections = [await this.getHomeSection()];
        break;
      default:
        sections = [
          await this.getSystemSection(),
          await this.getFinanceSection(),
          await this.getSecuritySection(),
          await this.getHomeSection()
        ];
    }

    const report = {
      title: `📊 Status Report${scope ? ` - ${scope}` : ''}`,
      timestamp: new Date().toISOString(),
      sections,
      summary: this.generateSummary(sections)
    };

    return {
      success: true,
      report,
      message: this.formatReport(report)
    };
  }

  async getMetricsReport(scope) {
    // Get detailed metrics
    const metrics = {
      system: await this.getSystemMetrics(),
      finance: await this.getFinanceMetrics(),
      security: await this.getSecurityMetrics(),
      home: await this.getHomeMetrics()
    };

    const report = {
      title: `📈 Metrics Report${scope ? ` - ${scope}` : ''}`,
      timestamp: new Date().toISOString(),
      metrics: scope ? { [scope]: metrics[scope] } : metrics
    };

    return {
      success: true,
      report,
      message: this.formatMetricsReport(report)
    };
  }

  async getHealthReport(scope) {
    // Get health status of all components
    const health = {
      rudibot: await this.checkRudibotHealth(),
      gateway: await this.checkGatewayHealth(),
      financeGrid: await this.checkFinanceGridHealth(),
      kivo: await this.checkKivoHealth(),
      homeAssistant: await this.checkHomeAssistantHealth()
    };

    const report = {
      title: `🩺 Health Report${scope ? ` - ${scope}` : ''}`,
      timestamp: new Date().toISOString(),
      health: scope ? { [scope]: health[scope] } : health,
      overall: this.calculateOverallHealth(health)
    };

    return {
      success: true,
      report,
      message: this.formatHealthReport(report)
    };
  }

  async exportData(scope, format = 'json') {
    const data = {
      timestamp: new Date().toISOString(),
      scope: scope || 'all',
      data: {}
    };

    if (!scope || scope === 'system') {
      data.data.system = await this.getSystemMetrics();
    }
    if (!scope || scope === 'finance') {
      data.data.finance = await this.getFinanceMetrics();
    }
    if (!scope || scope === 'security') {
      data.data.security = await this.getSecurityMetrics();
    }
    if (!scope || scope === 'home') {
      data.data.home = await this.getHomeMetrics();
    }

    return {
      success: true,
      export: data,
      filename: `dashboard-export-${scope || 'all'}-${Date.now()}.${format}`,
      message: `📤 Data exported: dashboard-export-${scope || 'all'}-${Date.now()}.${format}`
    };
  }

  // ── Section Generators ─────────────────────────────────────
  async getSystemSection() {
    const health = await this.checkRudibotHealth();
    return {
      title: '🤖 System',
      status: health.status,
      uptime: health.uptime,
      commands: health.commands,
      lastCommand: health.lastCommand,
      message: `Rudibot: ${health.status} (${Math.floor(health.uptime / 60)}m uptime)`
    };
  }

  async getFinanceSection() {
    // Simulate finance data
    return {
      title: '💰 Finance',
      subscriptions: 3,
      monthlyCost: 45.97,
      annualCost: 551.64,
      upcomingRenewals: 2,
      message: `3 active subscriptions, €45.97/month`
    };
  }

  async getSecuritySection() {
    const scan = await this.getLastSecurityScan();
    return {
      title: '🔒 Security',
      lastScan: scan.timestamp || 'Never',
      secretsFound: scan.secretsFound || 0,
      riskLevel: scan.riskLevel || 'unknown',
      message: `${scan.secretsFound || 0} secrets found, risk level: ${scan.riskLevel || 'unknown'}`
    };
  }

  async getHomeSection() {
    const ha = await this.checkHomeAssistantHealth();
    return {
      title: '🏠 Home',
      status: ha.status,
      devices: ha.devices || 0,
      scenes: ha.scenes || 0,
      message: `Home Assistant: ${ha.status}, ${ha.devices || 0} devices`
    };
  }

  // ── Metrics Collectors ───────────────────────────────────────
  async getSystemMetrics() {
    const health = await this.checkRudibotHealth();
    return {
      uptime: health.uptime,
      commandCount: health.commands,
      errorRate: this.calculateErrorRate(),
      responseTime: this.calculateResponseTime()
    };
  }

  async getFinanceMetrics() {
    return {
      totalSubscriptions: 3,
      totalMonthlyCost: 45.97,
      totalAnnualCost: 551.64,
      averageCostPerSubscription: 15.32,
      upcomingRenewals: 2,
      potentialSavings: 35.97
    };
  }

  async getSecurityMetrics() {
    const scan = await this.getLastSecurityScan();
    return {
      scansPerformed: scan.totalScans || 0,
      secretsFound: scan.secretsFound || 0,
      highRiskFindings: scan.highRisk || 0,
      mediumRiskFindings: scan.mediumRisk || 0,
      lowRiskFindings: scan.lowRisk || 0
    };
  }

  async getHomeMetrics() {
    const ha = await this.checkHomeAssistantHealth();
    return {
      totalDevices: ha.devices || 0,
      totalScenes: ha.scenes || 0,
      automations: ha.automations || 0,
      lastActivity: ha.lastActivity || null
    };
  }

  // ── Health Checks ───────────────────────────────────────
  async checkRudibotHealth() {
    try {
      const response = await fetch('http://localhost:3201/bot-health', {
        signal: AbortSignal.timeout(5000)
      });
      const data = await response.json();
      return {
        status: data.status || 'unknown',
        uptime: data.uptime || 0,
        commands: data.commands || 0,
        lastCommand: data.lastCommand || null
      };
    } catch (e) {
      return {
        status: 'offline',
        error: e.message
      };
    }
  }

  async checkGatewayHealth() {
    try {
      const response = await fetch('http://localhost:3000/health', {
        signal: AbortSignal.timeout(5000)
      });
      const data = await response.json();
      return {
        status: data.status || 'unknown',
        services: data.services || []
      };
    } catch (e) {
      return {
        status: 'offline',
        error: e.message
      };
    }
  }

  async checkFinanceGridHealth() {
    // Simulate check
    return {
      status: 'healthy',
      modules: 6,
      lastUpdate: new Date().toISOString()
    };
  }

  async checkKivoHealth() {
    // Simulate check
    return {
      status: 'healthy',
      listening: false,
      sessionActive: false
    };
  }

  async checkHomeAssistantHealth() {
    try {
      const response = await fetch(`${this.config.baseUrl}/api/config`, {
        headers: {
          'Authorization': `Bearer ${process.env.HOME_ASSISTANT_TOKEN}`,
        },
        signal: AbortSignal.timeout(5000)
      });
      
      if (response.ok) {
        const config = await response.json();
        return {
          status: 'online',
          version: config.version,
          location: config.location,
          devices: 12, // Placeholder
          scenes: 5, // Placeholder
          automations: 8 // Placeholder
        };
      }
    } catch (e) {
      // Fallback
    }

    return {
      status: 'offline',
      devices: 0,
      scenes: 0,
      error: 'Not reachable'
    };
  }

  // ── Helper Methods ───────────────────────────────────────
  generateSummary(sections) {
    const statusCounts = sections.reduce((acc, section) => {
      acc[section.status] = (acc[section.status] || 0) + 1;
      return acc;
    }, {});

    return {
      healthy: statusCounts.healthy || 0,
      warning: statusCounts.warning || 0,
      error: statusCounts.error || 0,
      offline: statusCounts.offline || 0
    };
  }

  calculateOverallHealth(health) {
    const statuses = Object.values(health).map(h => h.status);
    const healthy = statuses.filter(s => s === 'online' || s === 'healthy').length;
    const total = statuses.length;
    
    if (healthy === total) return 'excellent';
    if (healthy >= total * 0.8) return 'good';
    if (healthy >= total * 0.5) return 'warning';
    return 'critical';
  }

  calculateErrorRate() {
    // Placeholder
    return 0.02; // 2%
  }

  calculateResponseTime() {
    // Placeholder
    return 150; // 150ms
  }

  getLastSecurityScan() {
    // Simulate last scan data
    return {
      timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2 hours ago
      secretsFound: 0,
      riskLevel: 'low',
      highRisk: 0,
      mediumRisk: 0,
      lowRisk: 0,
      totalScans: 15
    };
  }

  // ── Formatters ───────────────────────────────────────────
  formatReport(report) {
    let message = `${report.title}\n\n`;
    
    for (const section of report.sections) {
      message += `${section.title}: ${section.message}\n`;
    }
    
    if (report.summary) {
      message += `\n📊 Summary: ${report.summary.healthy} healthy, ${report.summary.warning} warnings`;
    }
    
    return message;
  }

  formatMetricsReport(report) {
    let message = `${report.title}\n\n`;
    
    for (const [scope, metrics] of Object.entries(report.metrics)) {
      message += `📈 ${scope.toUpperCase()}:\n`;
      for (const [key, value] of Object.entries(metrics)) {
        message += `  ${key}: ${value}\n`;
      }
      message += '\n';
    }
    
    return message;
  }

  formatHealthReport(report) {
    let message = `${report.title}\n\n`;
    message += `🎯 Overall: ${report.overall.toUpperCase()}\n\n`;
    
    for (const [component, health] of Object.entries(report.health)) {
      message += `${component}: ${health.status}\n`;
      if (health.error) {
        message += `  Error: ${health.error}\n`;
      }
    }
    
    return message;
  }

  // ── Approval Check ───────────────────────────────────────
  requiresApproval(action, options) {
    // Export actions might require approval for data privacy
    if (action === 'export') {
      return true;
    }
    return false;
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      baseUrl: this.config.baseUrl,
      configured: true,
      supportedActions: ['status', 'metrics', 'health', 'export'],
      supportedScopes: ['system', 'finance', 'security', 'home'],
      supportedFormats: ['json', 'csv']
    };
  }
}

module.exports = { DashboardAction };
