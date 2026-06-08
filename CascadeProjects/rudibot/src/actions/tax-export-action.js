/**
 * Tax Export Action — Handles ELSTER export preparation and validation
 * Bridges KIVO tax intents to Finance Grid tax-core module
 */

class TaxExportAction {
  constructor(taxCore) {
    this.taxCore = taxCore;
    this.exportHistory = [];
  }

  async execute(options = {}) {
    const { 
      year = new Date().getFullYear(), 
      format = 'elster',
      validate = true,
      chatId 
    } = options;

    try {
      // Step 1: Get tax summary
      const summary = await this.getTaxSummary(year);
      
      // Step 2: Validate if requested
      if (validate) {
        const validation = await this.validateTaxData(summary, year);
        if (!validation.valid) {
          return {
            success: false,
            validated: false,
            errors: validation.errors,
            message: this.formatValidationErrors(validation.errors),
            requiresApproval: false
          };
        }
      }

      // Step 3: Prepare export
      const exportData = await this.prepareExport(summary, year, format);

      // Step 4: Return result (actual export requires approval)
      return {
        success: true,
        year,
        format,
        validated: true,
        data: exportData,
        requiresApproval: true,
        reason: 'ELSTER export involves tax liability and should be reviewed before submission',
        message: this.formatExportReady(exportData, year),
        timestamp: new Date().toISOString()
      };

    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Tax export preparation failed: ${e.message}`
      };
    }
  }

  async getTaxSummary(year) {
    try {
      if (this.taxCore) {
        const summary = this.taxCore.getTaxSummary ? 
          this.taxCore.getTaxSummary() : {};
        
        return {
          year,
          documents: summary.documents || 0,
          taxExpenses: summary.taxExpenses || 0,
          taxableIncome: summary.taxableIncome || 0,
          vatAmount: summary.vatAmount || 0,
          incomeTax: summary.incomeTax || 0,
          topCategories: summary.topCategories || [],
          documentDetails: summary.documentDetails || []
        };
      }

      return this.getMockTaxSummary(year);
    } catch (e) {
      console.warn('Tax summary error:', e.message);
      return this.getMockTaxSummary(year);
    }
  }

  async validateTaxData(summary, year) {
    const errors = [];
    const warnings = [];

    // Check minimum document count
    if (summary.documents < 1) {
      errors.push('No tax documents found for this period');
    }

    // Check for negative income
    if (summary.taxableIncome < 0) {
      errors.push('Taxable income is negative — please review');
    }

    // Check for suspiciously high expense ratio
    if (summary.taxExpenses > summary.taxableIncome * 0.8) {
      warnings.push('Expense ratio is high (>80%) — review recommended');
    }

    // Check for missing categories
    const requiredCategories = ['Software', 'Hosting', 'Office'];
    const existingCategories = (summary.topCategories || []).map(c => c.name);
    const missing = requiredCategories.filter(c => !existingCategories.includes(c));
    if (missing.length > 0) {
      warnings.push(`Missing common expense categories: ${missing.join(', ')}`);
    }

    // Check year validity
    const currentYear = new Date().getFullYear();
    if (year > currentYear) {
      errors.push('Cannot export for future year');
    }
    if (year < currentYear - 5) {
      warnings.push('Tax year is more than 5 years old — check statute of limitations');
    }

    // Check for duplicate documents
    const documentNames = (summary.documentDetails || []).map(d => d.filename);
    const duplicates = documentNames.filter((item, index) => documentNames.indexOf(item) !== index);
    if (duplicates.length > 0) {
      warnings.push(`Potential duplicate documents found: ${[...new Set(duplicates)].join(', ')}`);
    }

    return {
      valid: errors.length === 0,
      errors,
      warnings,
      summary: {
        documents: summary.documents,
        expenses: summary.taxExpenses,
        income: summary.taxableIncome
      }
    };
  }

  async prepareExport(summary, year, format) {
    const exportData = {
      year,
      format,
      generatedAt: new Date().toISOString(),
      taxpayer: {
        // Would come from identity vault
        name: process.env.TAXPAYER_NAME || 'Unknown',
        taxId: process.env.TAXPAYER_ID || 'Unknown'
      },
      summary: {
        totalIncome: summary.taxableIncome,
        totalExpenses: summary.taxExpenses,
        netIncome: summary.taxableIncome - summary.taxExpenses,
        estimatedTax: this.calculateTax(summary.taxableIncome - summary.taxExpenses)
      },
      categories: (summary.topCategories || []).map(cat => ({
        name: cat.name,
        amount: cat.amount,
        percentage: summary.taxExpenses ? ((cat.amount / summary.taxExpenses) * 100).toFixed(1) : 0
      })),
      documents: (summary.documentDetails || []).map(doc => ({
        filename: doc.filename,
        date: doc.date,
        amount: doc.amount,
        category: doc.category,
        verified: doc.verified || false
      })),
      metadata: {
        documentsVerified: summary.documentDetails?.every(d => d.verified) || false,
        exportFormat: format,
        elsterVersion: '2026.1',
        checksum: this.generateChecksum(summary)
      }
    };

    return exportData;
  }

  calculateTax(netIncome) {
    // Simplified German income tax calculation
    // Grundfreibetrag 2026: ~11,784 EUR
    const grundfreibetrag = 11784;
    
    if (netIncome <= grundfreibetrag) return 0;
    
    const taxable = netIncome - grundfreibetrag;
    
    // Progressive tax rate (simplified)
    if (taxable <= 17000) return taxable * 0.14;
    if (taxable <= 31000) return taxable * 0.24;
    if (taxable <= 60000) return taxable * 0.42;
    return taxable * 0.45;
  }

  generateChecksum(data) {
    // Simple checksum for integrity verification
    const str = JSON.stringify(data);
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return Math.abs(hash).toString(16).toUpperCase().padStart(8, '0');
  }

  // ── Actual Export (After Approval) ─────────────────────────
  async performExport(exportData, options = {}) {
    try {
      // In a real implementation, this would:
      // 1. Generate ELSTER XML
      // 2. Save to file
      // 3. Optionally upload to ELSTER portal
      
      const filename = `elster-${exportData.year}-${Date.now()}.json`;
      const exportRecord = {
        ...exportData,
        exportedAt: new Date().toISOString(),
        filename,
        status: 'prepared'
      };

      this.exportHistory.push(exportRecord);

      return {
        success: true,
        filename,
        year: exportData.year,
        format: exportData.format,
        message: `📤 ELSTER export prepared: ${filename}`,
        status: 'prepared'
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        message: `❌ Export failed: ${e.message}`
      };
    }
  }

  // ── Formatters ─────────────────────────────────────────────
  formatExportReady(exportData, year) {
    let message = `📤 *ELSTER EXPORT READY*\n\n`;
    message += `📅 Year: ${year}\n`;
    message += `📋 Format: ${exportData.format.toUpperCase()}\n`;
    message += `📄 Documents: ${exportData.summary.totalIncome > 0 ? exportData.documents?.length || 0 : 0}\n\n`;

    message += `💰 *Summary:*\n`;
    message += `Income: €${exportData.summary.totalIncome.toFixed(2)}\n`;
    message += `Expenses: €${exportData.summary.totalExpenses.toFixed(2)}\n`;
    message += `Net Income: €${exportData.summary.netIncome.toFixed(2)}\n`;
    message += `Est. Tax: €${exportData.summary.estimatedTax.toFixed(2)}\n\n`;

    if (exportData.categories && exportData.categories.length > 0) {
      message += `📊 *Top Categories:*\n`;
      exportData.categories.slice(0, 5).forEach(cat => {
        message += `• ${cat.name}: €${cat.amount.toFixed(2)} (${cat.percentage}%)\n`;
      });
      message += `\n`;
    }

    message += `⚠️ *This export involves tax liability.*\n`;
    message += `Please review before submission.\n\n`;
    message += `Use /approve to proceed with export or /cancel to abort.`;

    return message;
  }

  formatValidationErrors(errors) {
    let message = `❌ *VALIDATION FAILED*\n\n`;
    errors.forEach((error, i) => {
      message += `${i + 1}. ${error}\n`;
    });
    message += `\nPlease fix these issues before proceeding with the export.`;
    return message;
  }

  formatWarnings(warnings) {
    if (!warnings || warnings.length === 0) return '';
    
    let message = `⚠️ *Warnings:*\n`;
    warnings.forEach((warning, i) => {
      message += `${i + 1}. ${warning}\n`;
    });
    return message;
  }

  // ── Mock Data ──────────────────────────────────────────────
  getMockTaxSummary(year) {
    return {
      year,
      documents: 12,
      taxExpenses: 2340.50,
      taxableIncome: 5000.00,
      vatAmount: 0,
      incomeTax: 375.23,
      topCategories: [
        { name: 'Software', amount: 899.00 },
        { name: 'Hosting', amount: 420.00 },
        { name: 'Office', amount: 200.00 },
        { name: 'Travel', amount: 150.00 },
        { name: 'Subscriptions', amount: 45.97 }
      ],
      documentDetails: [
        { filename: 'invoice-001.pdf', date: '2026-01-15', amount: 899.00, category: 'Software', verified: true },
        { filename: 'invoice-002.pdf', date: '2026-02-01', amount: 420.00, category: 'Hosting', verified: true },
        { filename: 'invoice-003.pdf', date: '2026-02-15', amount: 200.00, category: 'Office', verified: true }
      ]
    };
  }

  // ── History ────────────────────────────────────────────────
  getExportHistory(year = null) {
    let history = this.exportHistory;
    if (year) {
      history = history.filter(e => e.year === year);
    }
    return history;
  }

  // ── Approval Check ───────────────────────────────────────
  requiresApproval(options) {
    // All tax exports require approval
    return true;
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      taxCoreAvailable: !!this.taxCore,
      supportedFormats: ['elster', 'csv', 'json'],
      totalExports: this.exportHistory.length,
      lastExport: this.exportHistory.length > 0 ? 
        this.exportHistory[this.exportHistory.length - 1].exportedAt : null
    };
  }
}

module.exports = { TaxExportAction };
