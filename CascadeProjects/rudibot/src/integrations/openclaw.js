/**
 * OpenClaw Integration — Legal automation and compliance checks
 * Bridges KIVO to OpenLaw and legal automation systems
 */

class OpenClawIntegration {
  constructor(config) {
    this.config = {
      baseUrl: config.baseUrl || process.env.OPENCLAW_URL || 'http://localhost:3001',
      token: config.token || process.env.OPENCLAW_TOKEN,
      timeout: config.timeout || 10000,
      ...config
    };
  }

  async checkCompliance(type, data) {
    try {
      switch (type) {
        case 'gdpr':
          return await this.checkGDPR(data);
        case 'agb':
          return await this.checkAGB(data);
        case 'impressum':
          return await this.checkImpressum(data);
        case 'nda':
          return await this.checkNDA(data);
        default:
          return { success: false, error: `Unknown compliance type: ${type}` };
      }
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  async checkGDPR(data) {
    const checks = [
      { name: 'Privacy Policy', required: true, present: !!data.privacyPolicy },
      { name: 'Consent Mechanism', required: true, present: !!data.consentMechanism },
      { name: 'Data Processing Records', required: true, present: !!data.processingRecords },
      { name: 'Right to Deletion', required: true, present: !!data.rightToDeletion },
      { name: 'Data Transfer Safeguards', required: data.transfersData, present: !!data.transferSafeguards },
      { name: 'DPO Contact', required: data.requiresDPO, present: !!data.dpoContact }
    ];

    const passed = checks.filter(c => !c.required || c.present);
    const failed = checks.filter(c => c.required && !c.present);

    return {
      success: failed.length === 0,
      type: 'gdpr',
      score: Math.round((passed.length / checks.length) * 100),
      checks,
      passed: passed.length,
      failed: failed.length,
      message: this.formatComplianceResult('GDPR', passed.length, failed.length, checks.length)
    };
  }

  async checkAGB(data) {
    const checks = [
      { name: 'AGB Present', required: true, present: !!data.termsPresent },
      { name: 'Withdrawal Policy', required: true, present: !!data.withdrawalPolicy },
      { name: 'Payment Terms', required: true, present: !!data.paymentTerms },
      { name: 'Liability Clause', required: true, present: !!data.liabilityClause },
      { name: 'Jurisdiction', required: true, present: !!data.jurisdiction }
    ];

    const passed = checks.filter(c => !c.required || c.present);
    const failed = checks.filter(c => c.required && !c.present);

    return {
      success: failed.length === 0,
      type: 'agb',
      score: Math.round((passed.length / checks.length) * 100),
      checks,
      passed: passed.length,
      failed: failed.length,
      message: this.formatComplianceResult('AGB', passed.length, failed.length, checks.length)
    };
  }

  async checkImpressum(data) {
    const checks = [
      { name: 'Company Name', required: true, present: !!data.companyName },
      { name: 'Address', required: true, present: !!data.address },
      { name: 'Contact Email', required: true, present: !!data.email },
      { name: 'Registration Number', required: data.isCompany, present: !!data.registrationNumber },
      { name: 'VAT ID', required: data.isCompany, present: !!data.vatId },
      { name: 'Managing Director', required: data.isCompany, present: !!data.managingDirector }
    ];

    const passed = checks.filter(c => !c.required || c.present);
    const failed = checks.filter(c => c.required && !c.present);

    return {
      success: failed.length === 0,
      type: 'impressum',
      score: Math.round((passed.length / checks.length) * 100),
      checks,
      passed: passed.length,
      failed: failed.length,
      message: this.formatComplianceResult('Impressum', passed.length, failed.length, checks.length)
    };
  }

  async checkNDA(data) {
    const checks = [
      { name: 'Confidentiality Definition', required: true, present: !!data.confidentialityDefinition },
      { name: 'Duration', required: true, present: !!data.duration },
      { name: 'Return Policy', required: true, present: !!data.returnPolicy },
      { name: 'Breach Consequences', required: true, present: !!data.breachConsequences },
      { name: 'Governing Law', required: true, present: !!data.governingLaw }
    ];

    const passed = checks.filter(c => !c.required || c.present);
    const failed = checks.filter(c => c.required && !c.present);

    return {
      success: failed.length === 0,
      type: 'nda',
      score: Math.round((passed.length / checks.length) * 100),
      checks,
      passed: passed.length,
      failed: failed.length,
      message: this.formatComplianceResult('NDA', passed.length, failed.length, checks.length)
    };
  }

  formatComplianceResult(type, passed, failed, total) {
    const score = Math.round((passed / total) * 100);
    const status = failed === 0 ? '✅ PASSED' : failed <= 2 ? '⚠️ PARTIAL' : '❌ FAILED';
    
    let message = `⚖️ *${type} COMPLIANCE*\n\n`;
    message += `${status} (${score}%)\n`;
    message += `✅ Passed: ${passed}/${total}\n`;
    if (failed > 0) {
      message += `❌ Failed: ${failed}/${total}\n`;
    }
    
    return message;
  }

  // ── Document Generation ───────────────────────────────────
  async generateDocument(type, data) {
    try {
      switch (type) {
        case 'gdpr-privacy':
          return await this.generatePrivacyPolicy(data);
        case 'agb':
          return await this.generateAGB(data);
        case 'impressum':
          return await this.generateImpressum(data);
        case 'nda':
          return await this.generateNDA(data);
        default:
          return { success: false, error: `Unknown document type: ${type}` };
      }
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  async generatePrivacyPolicy(data) {
    const template = this.getPrivacyPolicyTemplate(data);
    return {
      success: true,
      type: 'gdpr-privacy',
      content: template,
      message: '📄 Privacy Policy generated successfully'
    };
  }

  async generateAGB(data) {
    const template = this.getAGBTemplate(data);
    return {
      success: true,
      type: 'agb',
      content: template,
      message: '📄 AGB generated successfully'
    };
  }

  async generateImpressum(data) {
    const template = this.getImpressumTemplate(data);
    return {
      success: true,
      type: 'impressum',
      content: template,
      message: '📄 Impressum generated successfully'
    };
  }

  async generateNDA(data) {
    const template = this.getNDATemplate(data);
    return {
      success: true,
      type: 'nda',
      content: template,
      message: '📄 NDA generated successfully'
    };
  }

  // ── Templates ─────────────────────────────────────────────
  getPrivacyPolicyTemplate(data) {
    return `Privacy Policy for ${data.companyName || 'Company'}\n\n` +
      `1. Data Controller\n` +
      `${data.companyName}\n` +
      `${data.address}\n\n` +
      `2. Data We Collect\n` +
      `${data.dataCollected || 'Contact information, usage data'}\n\n` +
      `3. Your Rights\n` +
      `Right to access, rectification, erasure, portability\n\n` +
      `4. Contact\n` +
      `Email: ${data.email || 'privacy@example.com'}`;
  }

  getAGBTemplate(data) {
    return `Terms of Service for ${data.companyName || 'Company'}\n\n` +
      `1. Scope\n` +
      `These terms apply to all services.\n\n` +
      `2. Payment\n` +
      `${data.paymentTerms || 'Payment due within 14 days'}\n\n` +
      `3. Withdrawal\n` +
      `${data.withdrawalPolicy || '14-day withdrawal period'}\n\n` +
      `4. Liability\n` +
      `${data.liabilityClause || 'Limited liability as per statutory provisions'}`;
  }

  getImpressumTemplate(data) {
    return `Impressum\n\n` +
      `${data.companyName}\n` +
      `${data.address}\n\n` +
      `Contact:\n` +
      `Email: ${data.email}\n` +
      (data.phone ? `Phone: ${data.phone}\n` : '') +
      (data.vatId ? `VAT ID: ${data.vatId}\n` : '') +
      (data.registrationNumber ? `Registration: ${data.registrationNumber}\n` : '');
  }

  getNDATemplate(data) {
    return `Non-Disclosure Agreement\n\n` +
      `Between: ${data.partyA || 'Party A'}\n` +
      `And: ${data.partyB || 'Party B'}\n\n` +
      `1. Confidential Information\n` +
      `${data.confidentialityDefinition || 'All non-public information'}\n\n` +
      `2. Duration\n` +
      `${data.duration || '3 years from signing'}\n\n` +
      `3. Return\n` +
      `${data.returnPolicy || 'Return within 30 days of request'}\n\n` +
      `4. Breach\n` +
      `${data.breachConsequences || 'Injunctive relief and damages'}`;
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      configured: !!this.config.token,
      baseUrl: this.config.baseUrl,
      supportedChecks: ['gdpr', 'agb', 'impressum', 'nda'],
      supportedDocuments: ['gdpr-privacy', 'agb', 'impressum', 'nda']
    };
  }
}

module.exports = { OpenClawIntegration };
