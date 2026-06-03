const fs = require('fs');
const path = require('path');

/**
 * Invoice Hunter — Rechnungen aus Mail, Browser und PDF erkennen
 * 
 * Funktionen:
 * - Mail-Rechnungen erkennen (IMAP/Pop3/API)
 * - Browser-Seiten nach Rechnungen scannen
 * - PDF-Rechnungen parsen (Text-Extraktion)
 * - Wiederkehrende Rechnungen identifizieren
 * - Kündigungsfristen extrahieren
 * - Fälligkeitsdaten tracken
 */

class InvoiceHunter {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../../state/invoices');
    this.invoices = [];
    this.detectedContracts = new Map();
    
    this.patterns = {
      amount: /(?:Betrag|Amount|Summe|Total|Gesamt)[:\s]*([\d.,]+)\s*(EUR|€|\$|USD)/i,
      invoiceNumber: /(?:Rechnung|Invoice|Rechnungsnr)[:\s#]*(\S+)/i,
      date: /(?:Datum|Date|Rechnungsdatum)[:\s]*(\d{1,2}[.\/]\d{1,2}[.\/]\d{2,4})/i,
      dueDate: /(?:Fälligkeit|Fällig am|Due Date|Zahlbar bis)[:\s]*(\d{1,2}[.\/]\d{1,2}[.\/]\d{2,4})/i,
      vendor: /(?:Von|From|Absender|Vertragspartner|Dienstleister)[:\s]*([^\n]+)/i,
      contractId: /(?:Vertragsnr|Kundennummer|Contract|Kundennr)[:\s#]*(\S+)/i,
      cancellationPeriod: /(?:Kündigungsfrist|Kündigungszeitraum)[:\s]*([^\n]+)/i,
      recurring: /(?:monatlich|jährlich|quartalsweise|monthly|annual|subscription|abo|wiederkehrend)/i,
      iban: /(?:IBAN)[:\s]*([A-Z]{2}\d{2}[\s]?[A-Z0-9]{4}[\s]?[A-Z0-9]{4}[\s]?[A-Z0-9]{4}[\s]?[A-Z0-9]{4}[\s]?[A-Z0-9]{0,4})/i
    };
    
    this.vendorPatterns = {
      'IONOS': { category: 'hosting', keywords: ['ionos', '1und1'] },
      'Netlify': { category: 'hosting', keywords: ['netlify'] },
      'Adobe': { category: 'design', keywords: ['adobe', 'creative cloud'] },
      'Shopify': { category: 'ecommerce', keywords: ['shopify'] },
      'Midjourney': { category: 'ai', keywords: ['midjourney'] },
      'Anthropic': { category: 'ai', keywords: ['anthropic', 'claude'] },
      'OpenAI': { category: 'ai', keywords: ['openai', 'chatgpt'] },
      'Apple': { category: 'services', keywords: ['apple', 'apple services'] },
      'Google': { category: 'services', keywords: ['google', 'google workspace'] },
      'FLIKI': { category: 'video', keywords: ['fliki'] },
      'FUNDINGTRADERS': { category: 'trading', keywords: ['fundingtraders'] },
      'Printify': { category: 'print', keywords: ['printify'] },
      'SIGNALXPERT': { category: 'trading', keywords: ['signalxpert'] },
      'NUMERO': { category: 'telecom', keywords: ['numero'] }
    };
    
    this.ensureStorageDir();
    this.loadInvoices();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  loadInvoices() {
    try {
      const filePath = path.join(this.storagePath, 'invoices.json');
      if (fs.existsSync(filePath)) {
        const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        this.invoices = data.invoices || [];
        this.detectedContracts = new Map(data.contracts || []);
      }
    } catch (err) {
      this.logger.error?.('invoice-hunter.load_failed', { error: err.message });
    }
  }

  saveInvoices() {
    try {
      fs.writeFileSync(
        path.join(this.storagePath, 'invoices.json'),
        JSON.stringify({
          updatedAt: new Date().toISOString(),
          invoices: this.invoices,
          contracts: Array.from(this.detectedContracts.entries())
        }, null, 2)
      );
    } catch (err) {
      this.logger.error?.('invoice-hunter.save_failed', { error: err.message });
    }
  }

  /**
   * Parse invoice from text content (email body, PDF text, etc.)
   */
  parseInvoice(text, source = 'unknown') {
    const invoice = {
      id: `inv_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
      source,
      detectedAt: new Date().toISOString(),
      raw: text.substring(0, 500),
      extracted: {}
    };

    // Extract amount
    const amountMatch = text.match(this.patterns.amount);
    if (amountMatch) {
      invoice.extracted.amount = this.parseAmount(amountMatch[1]);
      invoice.extracted.currency = amountMatch[2] || 'EUR';
    }

    // Extract invoice number
    const invoiceMatch = text.match(this.patterns.invoiceNumber);
    if (invoiceMatch) {
      invoice.extracted.invoiceNumber = invoiceMatch[1];
    }

    // Extract dates
    const dateMatch = text.match(this.patterns.date);
    if (dateMatch) {
      invoice.extracted.date = this.parseDate(dateMatch[1]);
    }

    const dueMatch = text.match(this.patterns.dueDate);
    if (dueMatch) {
      invoice.extracted.dueDate = this.parseDate(dueMatch[1]);
    }

    // Extract vendor
    let vendorName = 'Unknown';
    const vendorMatch = text.match(this.patterns.vendor);
    if (vendorMatch) {
      vendorName = vendorMatch[1].trim();
    } else {
      // Try to detect vendor from text content
      vendorName = this.detectVendor(text);
    }
    invoice.extracted.vendor = vendorName;

    // Detect category
    invoice.extracted.category = this.detectCategory(vendorName, text);

    // Extract contract ID
    const contractMatch = text.match(this.patterns.contractId);
    if (contractMatch) {
      invoice.extracted.contractId = contractMatch[1];
    }

    // Extract cancellation period
    const cancelMatch = text.match(this.patterns.cancellationPeriod);
    if (cancelMatch) {
      invoice.extracted.cancellationPeriod = cancelMatch[1].trim();
    }

    // Detect if recurring
    invoice.extracted.isRecurring = this.patterns.recurring.test(text);

    // Extract IBAN
    const ibanMatch = text.match(this.patterns.iban);
    if (ibanMatch) {
      invoice.extracted.iban = ibanMatch[1].replace(/\s/g, '');
    }

    // Check if this is a subscription/contract invoice
    if (invoice.extracted.isRecurring || invoice.extracted.cancellationPeriod) {
      this.updateContract(invoice);
    }

    this.invoices.push(invoice);
    this.saveInvoices();

    return invoice;
  }

  /**
   * Detect vendor from text using known patterns
   */
  detectVendor(text) {
    const lowerText = text.toLowerCase();
    
    for (const [vendorName, config] of Object.entries(this.vendorPatterns)) {
      for (const keyword of config.keywords) {
        if (lowerText.includes(keyword.toLowerCase())) {
          return vendorName;
        }
      }
    }
    
    // Fallback: Try to find company name after common prefixes
    const companyMatches = text.match(/(?:von|from|by)\s+([A-Z][A-Za-z\s]{2,30})/i);
    if (companyMatches) {
      return companyMatches[1].trim();
    }
    
    return 'Unknown';
  }

  /**
   * Detect category from vendor name
   */
  detectCategory(vendorName, text) {
    const lowerVendor = vendorName.toLowerCase();
    const lowerText = text.toLowerCase();
    
    for (const [vendorNamePattern, config] of Object.entries(this.vendorPatterns)) {
      if (lowerVendor.includes(vendorNamePattern.toLowerCase())) {
        return config.category;
      }
      for (const keyword of config.keywords) {
        if (lowerText.includes(keyword.toLowerCase())) {
          return config.category;
        }
      }
    }
    
    return 'other';
  }

  /**
   * Update contract tracking from invoice
   */
  updateContract(invoice) {
    const vendor = invoice.extracted.vendor;
    const existing = this.detectedContracts.get(vendor);
    
    const contractData = {
      vendor,
      category: invoice.extracted.category,
      lastInvoiceAmount: invoice.extracted.amount,
      lastInvoiceDate: invoice.extracted.date,
      dueDate: invoice.extracted.dueDate,
      contractId: invoice.extracted.contractId,
      cancellationPeriod: invoice.extracted.cancellationPeriod,
      isRecurring: invoice.extracted.isRecurring,
      invoiceCount: 1,
      firstDetected: invoice.detectedAt,
      lastDetected: invoice.detectedAt
    };

    if (existing) {
      contractData.invoiceCount = existing.invoiceCount + 1;
      contractData.firstDetected = existing.firstDetected;
      // Keep earliest known cancellation period
      if (!contractData.cancellationPeriod && existing.cancellationPeriod) {
        contractData.cancellationPeriod = existing.cancellationPeriod;
      }
    }

    this.detectedContracts.set(vendor, contractData);
  }

  /**
   * Parse amount string
   */
  parseAmount(amountStr) {
    if (!amountStr) return 0;
    const clean = amountStr
      .replace(/\./g, '')  // Remove thousand separators
      .replace(',', '.')   // German comma to decimal
      .replace(/[^\d.-]/g, '');
    const num = parseFloat(clean);
    return isNaN(num) ? 0 : num;
  }

  /**
   * Parse date string (handles multiple formats)
   */
  parseDate(dateStr) {
    if (!dateStr) return '';
    
    // German format: 03.06.2026
    const germanMatch = dateStr.match(/(\d{1,2})\.(\d{1,2})\.(\d{2,4})/);
    if (germanMatch) {
      const year = germanMatch[3].length === 2 ? '20' + germanMatch[3] : germanMatch[3];
      return `${year}-${germanMatch[2].padStart(2, '0')}-${germanMatch[1].padStart(2, '0')}`;
    }
    
    // US format: 06/03/2026
    const usMatch = dateStr.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
    if (usMatch) {
      const year = usMatch[3].length === 2 ? '20' + usMatch[3] : usMatch[3];
      return `${year}-${usMatch[1].padStart(2, '0')}-${usMatch[2].padStart(2, '0')}`;
    }
    
    return dateStr;
  }

  /**
   * Get all detected contracts
   */
  getContracts() {
    return Array.from(this.detectedContracts.values())
      .sort((a, b) => (b.lastInvoiceAmount || 0) - (a.lastInvoiceAmount || 0));
  }

  /**
   * Get contracts with upcoming cancellations
   */
  getContractsWithCancellationDeadline() {
    const contracts = this.getContracts();
    const withDeadline = [];
    
    for (const contract of contracts) {
      if (contract.cancellationPeriod) {
        const deadline = this.calculateCancellationDeadline(contract);
        if (deadline) {
          withDeadline.push({
            ...contract,
            cancellationDeadline: deadline,
            daysUntilDeadline: this.daysUntil(deadline)
          });
        }
      }
    }
    
    return withDeadline.sort((a, b) => a.daysUntilDeadline - b.daysUntilDeadline);
  }

  /**
   * Calculate cancellation deadline from contract data
   */
  calculateCancellationDeadline(contract) {
    if (!contract.cancellationPeriod) return null;
    
    const periodText = contract.cancellationPeriod.toLowerCase();
    const lastInvoice = contract.lastInvoiceDate ? new Date(contract.lastInvoiceDate) : new Date();
    
    let days = 30; // Default
    
    if (periodText.includes('1 monat') || periodText.includes('30 tag')) {
      days = 30;
    } else if (periodText.includes('3 monat') || periodText.includes('quartal')) {
      days = 90;
    } else if (periodText.includes('6 monat')) {
      days = 180;
    } else if (periodText.includes('1 jahr') || periodText.includes('12 monat')) {
      days = 365;
    } else if (periodText.includes('2 woche') || periodText.includes('14 tag')) {
      days = 14;
    }
    
    // For monthly contracts, deadline is typically end of current period minus notice period
    const deadline = new Date(lastInvoice);
    deadline.setDate(deadline.getDate() + days);
    
    return deadline.toISOString().split('T')[0];
  }

  /**
   * Get invoices summary
   */
  getSummary() {
    const totalAmount = this.invoices.reduce((sum, inv) => sum + (inv.extracted.amount || 0), 0);
    const recurringCount = this.invoices.filter(inv => inv.extracted.isRecurring).length;
    
    return {
      totalInvoices: this.invoices.length,
      totalAmount,
      recurringInvoices: recurringCount,
      detectedContracts: this.detectedContracts.size,
      vendors: [...new Set(this.invoices.map(inv => inv.extracted.vendor))],
      categories: [...new Set(this.invoices.map(inv => inv.extracted.category))],
      contractsWithDeadlines: this.getContractsWithCancellationDeadline().length
    };
  }

  /**
   * Import invoices from file (PDF text, email export, etc.)
   */
  async importFromFile(filePath, source = 'file') {
    try {
      const content = fs.readFileSync(filePath, 'utf8');
      const invoices = [];
      
      // Split by common invoice separators
      const sections = content.split(/(?:Rechnung|Invoice)\s*(?:Nr|#)?/i);
      
      for (const section of sections) {
        if (section.trim().length > 50) {
          const invoice = this.parseInvoice(section, source);
          invoices.push(invoice);
        }
      }
      
      return {
        imported: invoices.length,
        invoices
      };
    } catch (err) {
      this.logger.error?.('invoice-hunter.import_failed', { error: err.message, file: filePath });
      throw err;
    }
  }

  daysUntil(dateString) {
    if (!dateString) return 999;
    const date = new Date(dateString);
    const now = new Date();
    return Math.floor((date - now) / (1000 * 60 * 60 * 24));
  }
}

module.exports = { InvoiceHunter };
