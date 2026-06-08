const fs = require('fs');
const path = require('path');

/**
 * ELSTER Document Assistant — Fehlende Unterlagen für Steuerfälle
 * 
 * Funktionen:
 * - ELSTER-Dokumente erkennen und kategorisieren
 * - Fehlende Unterlagen identifizieren
 * - Dokumenten-Anforderungen generieren
 * - Fristen-Tracking für Steuererklärungen
 * - Automatische Checklisten erstellen
 */

class ElsterAssistant {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../state/elster');
    
    this.documentTypes = {
      'steuerbescheid': {
        name: 'Steuerbescheid',
        category: 'official',
        required: true,
        description: 'Offizieller Steuerbescheid vom Finanzamt',
        filePatterns: ['*steuerbescheid*', '*bescheid*', '*finanzamt*'],
        contentKeywords: ['steuerbescheid', 'bescheid', 'finanzamt', 'einkommensteuer'],
        deadlineType: 'filing_deadline'
      },
      'einnahmenuebersicht': {
        name: 'Einnahmenübersicht',
        category: 'financial',
        required: true,
        description: 'Übersicht aller Einnahmen im Steuerjahr',
        filePatterns: ['*einnahmen*', '*umsatz*', '*revenue*'],
        contentKeywords: ['einnahmen', 'umsatz', 'revenue', 'erträge'],
        deadlineType: 'none'
      },
      'ausgabenbelege': {
        name: 'Ausgabenbelege',
        category: 'financial',
        required: true,
        description: 'Alle betrieblichen Ausgaben mit Belegen',
        filePatterns: ['*ausgaben*', '*belege*', '*receipts*', '*expenses*'],
        contentKeywords: ['ausgaben', 'belege', 'receipts', 'expenses', 'kosten'],
        deadlineType: 'none'
      },
      'anlagenaufstellungen': {
        name: 'Anlagenaufstellungen',
        category: 'asset',
        required: false,
        description: 'Verzeichnis der abnutzbaren Wirtschaftsgüter',
        filePatterns: ['*anlagen*', '*afast*', '*depreciation*'],
        contentKeywords: ['anlagen', 'afast', 'abschreibung', 'depreciation'],
        deadlineType: 'none'
      },
      'vorauszahlungsbescheid': {
        name: 'Vorauszahlungsbescheid',
        category: 'official',
        required: false,
        description: 'Bescheid über Steuervorauszahlungen',
        filePatterns: ['*vorauszahlung*', '*vorab*'],
        contentKeywords: ['vorauszahlung', 'steuervorauszahlung', 'vorabzahlung'],
        deadlineType: 'payment_deadline'
      },
      'elster_zertifikat': {
        name: 'ELSTER-Zertifikat',
        category: 'technical',
        required: true,
        description: 'Aktuelles ELSTER-Benutzerzertifikat',
        filePatterns: ['*elster*', '*zertifikat*', '*.pfx', '*.p12'],
        contentKeywords: ['elster', 'zertifikat', 'benutzerzertifikat'],
        deadlineType: 'certificate_expiry'
      },
      'kontoauszuege': {
        name: 'Kontoauszüge',
        category: 'financial',
        required: false,
        description: 'Bankkontoauszüge für Nachweisprüfung',
        filePatterns: ['*kontoauszug*', '*bank*', '*statement*'],
        contentKeywords: ['kontoauszug', 'bank', 'statement', 'kontostand'],
        deadlineType: 'none'
      },
      'mietvertrag': {
        name: 'Mietvertrag',
        category: 'contract',
        required: false,
        description: 'Mietvertrag für Homeoffice-Pauschale',
        filePatterns: ['*mietvertrag*', '*miete*'],
        contentKeywords: ['mietvertrag', 'miete', 'wohnung'],
        deadlineType: 'none'
      },
      'versicherungsbeitraege': {
        name: 'Versicherungsbeiträge',
        category: 'financial',
        required: false,
        description: 'Nachweise über Versicherungsbeiträge',
        filePatterns: ['*versicherung*', '*versicherungsnachweis*'],
        contentKeywords: ['versicherung', 'beitrag', 'police'],
        deadlineType: 'none'
      }
    };
    
    this.taxYears = new Map();
    this.documents = new Map();
    this.requirements = new Map();
    
    this.ensureStorageDir();
    this.loadElsterData();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
    // Documents subdirectory
    if (!fs.existsSync(path.join(this.storagePath, 'documents'))) {
      fs.mkdirSync(path.join(this.storagePath, 'documents'), { recursive: true });
    }
  }

  loadElsterData() {
    try {
      const filePath = path.join(this.storagePath, 'elster-data.json');
      if (fs.existsSync(filePath)) {
        const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        this.taxYears = new Map(data.taxYears || []);
        this.documents = new Map(data.documents || []);
        this.requirements = new Map(data.requirements || []);
      }
    } catch (err) {
      this.logger.error?.('elster.load_failed', { error: err.message });
    }
  }

  saveElsterData() {
    try {
      fs.writeFileSync(
        path.join(this.storagePath, 'elster-data.json'),
        JSON.stringify({
          updatedAt: new Date().toISOString(),
          taxYears: Array.from(this.taxYears.entries()),
          documents: Array.from(this.documents.entries()),
          requirements: Array.from(this.requirements.entries())
        }, null, 2)
      );
    } catch (err) {
      this.logger.error?.('elster.save_failed', { error: err.message });
    }
  }

  /**
   * Neues Steuerjahr initialisieren
   */
  initializeTaxYear(year, options = {}) {
    if (this.taxYears.has(year.toString())) {
      throw new Error(`Tax year ${year} already exists`);
    }
    
    const taxYear = {
      year: year.toString(),
      status: 'preparation',
      filingDeadline: options.filingDeadline || this.calculateFilingDeadline(year),
      paymentDeadlines: options.paymentDeadlines || [],
      documents: [],
      requirements: this.generateDefaultRequirements(year),
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      notes: options.notes || '',
      assignedTo: options.assignedTo || null
    };
    
    this.taxYears.set(year.toString(), taxYear);
    this.saveElsterData();
    
    this.logger.info?.('elster.year_initialized', { year, deadline: taxYear.filingDeadline });
    return taxYear;
  }

  /**
   * Frist für Steuererklärung berechnen
   */
  calculateFilingDeadline(year) {
    const currentYear = new Date().getFullYear();
    const targetYear = parseInt(year);
    
    if (targetYear === currentYear - 1) {
      // Last year - deadline is May 31 of current year
      return `${currentYear}-05-31`;
    } else if (targetYear === currentYear) {
      // Current year - deadline is May 31 of next year
      return `${currentYear + 1}-05-31`;
    } else {
      // Other years - default May 31
      return `${targetYear + 1}-05-31`;
    }
  }

  /**
   * Standard-Anforderungen für Steuerjahr generieren
   */
  generateDefaultRequirements(year) {
    const requirements = [];
    
    for (const [docType, config] of Object.entries(this.documentTypes)) {
      if (config.required) {
        requirements.push({
          id: `req_${docType}_${year}`,
          type: docType,
          year: year.toString(),
          status: 'pending',
          priority: config.category === 'official' ? 'high' : 'medium',
          deadline: this.calculateRequirementDeadline(docType, year),
          description: config.description,
          category: config.category,
          uploaded: false,
          verified: false,
          notes: ''
        });
      }
    }
    
    return requirements;
  }

  /**
   * Frist für Anforderung berechnen
   */
  calculateRequirementDeadline(docType, year) {
    const filingDeadline = this.calculateFilingDeadline(year);
    const deadline = new Date(filingDeadline);
    
    // Different deadlines based on document type
    switch (docType) {
      case 'steuerbescheid':
        deadline.setDate(deadline.getDate() - 30);
        break;
      case 'elster_zertifikat':
        deadline.setDate(deadline.getDate() - 7);
        break;
      case 'einnahmenuebersicht':
      case 'ausgabenbelege':
        deadline.setDate(deadline.getDate() - 14);
        break;
      default:
        deadline.setDate(deadline.getDate() - 21);
    }
    
    return deadline.toISOString().split('T')[0];
  }

  /**
   * Dokument analysieren und kategorisieren
   */
  analyzeDocument(filePath, content = '') {
    const fileName = path.basename(filePath).toLowerCase();
    let matchedType = null;
    let confidence = 0;
    
    // File pattern matching
    for (const [docType, config] of Object.entries(this.documentTypes)) {
      let patternScore = 0;
      
      for (const pattern of config.filePatterns) {
        if (fileName.includes(pattern.replace(/\*/g, ''))) {
          patternScore += 0.5;
        }
      }
      
      // Content keyword matching
      if (content) {
        const lowerContent = content.toLowerCase();
        for (const keyword of config.contentKeywords) {
          if (lowerContent.includes(keyword.toLowerCase())) {
            patternScore += 0.3;
          }
        }
      }
      
      if (patternScore > confidence) {
        confidence = patternScore;
        matchedType = docType;
      }
    }
    
    if (matchedType && confidence > 0.3) {
      return {
        type: matchedType,
        confidence,
        config: this.documentTypes[matchedType]
      };
    }
    
    return {
      type: 'unknown',
      confidence: 0,
      config: null
    };
  }

  /**
   * Dokument hochladen und zuordnen
   */
  uploadDocument(year, filePath, options = {}) {
    const taxYear = this.taxYears.get(year.toString());
    if (!taxYear) {
      throw new Error(`Tax year ${year} not found`);
    }
    
    // Analyze document
    let content = '';
    try {
      content = fs.readFileSync(filePath, 'utf8');
    } catch (err) {
      // Binary file - skip content analysis
    }
    
    const analysis = this.analyzeDocument(filePath, content);
    
    const docId = `doc_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
    const document = {
      id: docId,
      year: year.toString(),
      type: analysis.type,
      originalName: path.basename(filePath),
      filePath: filePath,
      fileSize: options.fileSize || 0,
      uploadedAt: new Date().toISOString(),
      confidence: analysis.confidence,
      verified: false,
      notes: options.notes || '',
      metadata: {
        analyzed: true,
        category: analysis.config?.category || 'unknown',
        required: analysis.config?.required || false
      }
    };
    
    this.documents.set(docId, document);
    
    // Update tax year
    taxYear.documents.push(docId);
    taxYear.updatedAt = new Date().toISOString();
    this.taxYears.set(year.toString(), taxYear);
    
    // Update requirements
    this.updateRequirementStatus(year, analysis.type, 'uploaded');
    
    this.saveElsterData();
    
    this.logger.info?.('elster.document_uploaded', { 
      year, 
      type: analysis.type, 
      confidence: analysis.confidence 
    });
    
    return document;
  }

  /**
   * Anforderungs-Status aktualisieren
   */
  updateRequirementStatus(year, docType, status) {
    const taxYear = this.taxYears.get(year.toString());
    if (!taxYear) return;
    
    const requirement = taxYear.requirements.find(req => req.type === docType);
    if (requirement) {
      requirement.status = status;
      requirement.updatedAt = new Date().toISOString();
      
      if (status === 'uploaded') {
        requirement.uploaded = true;
        requirement.uploadedAt = new Date().toISOString();
      }
    }
  }

  /**
   * Fehlende Dokumente für Steuerjahr
   */
  getMissingDocuments(year) {
    const taxYear = this.taxYears.get(year.toString());
    if (!taxYear) {
      throw new Error(`Tax year ${year} not found`);
    }
    
    const missing = taxYear.requirements.filter(req => 
      req.status === 'pending' && req.uploaded === false
    );
    
    const overdue = missing.filter(req => 
      req.deadline < new Date().toISOString().split('T')[0]
    );
    
    const urgent = missing.filter(req => {
      const daysUntil = this.daysUntil(req.deadline);
      return daysUntil <= 7 && daysUntil > 0;
    });
    
    return {
      total: missing.length,
      overdue: overdue.length,
      urgent: urgent.length,
      missing,
      overdue: overdue.map(req => ({
        ...req,
        daysOverdue: -this.daysUntil(req.deadline)
      })),
      urgent: urgent.map(req => ({
        ...req,
        daysUntil: this.daysUntil(req.deadline)
      }))
    };
  }

  /**
   * Checkliste für Steuerjahr erstellen
   */
  generateChecklist(year) {
    const taxYear = this.taxYears.get(year.toString());
    if (!taxYear) {
      throw new Error(`Tax year ${year} not found`);
    }
    
    const missing = this.getMissingDocuments(year);
    const uploaded = taxYear.requirements.filter(req => req.uploaded === true);
    
    const checklist = {
      year: year.toString(),
      status: this.calculateYearStatus(missing.total),
      filingDeadline: taxYear.filingDeadline,
      daysUntilFiling: this.daysUntil(taxYear.filingDeadline),
      progress: {
        total: taxYear.requirements.length,
        uploaded: uploaded.length,
        missing: missing.total,
        percentage: Math.round((uploaded.length / taxYear.requirements.length) * 100)
      },
      sections: {
        'official_documents': this.getChecklistSection(taxYear, 'official'),
        'financial_documents': this.getChecklistSection(taxYear, 'financial'),
        'asset_documents': this.getChecklistSection(taxYear, 'asset'),
        'contract_documents': this.getChecklistSection(taxYear, 'contract'),
        'technical_documents': this.getChecklistSection(taxYear, 'technical')
      },
      urgentActions: this.getUrgentActions(taxYear, missing),
      nextSteps: this.getNextSteps(taxYear, missing)
    };
    
    return checklist;
  }

  /**
   * Status für Steuerjahr berechnen
   */
  calculateYearStatus(missingCount) {
    if (missingCount === 0) return 'complete';
    if (missingCount <= 2) return 'almost_complete';
    if (missingCount <= 5) return 'in_progress';
    return 'preparation';
  }

  /**
   * Checkliste-Sektion
   */
  getChecklistSection(taxYear, category) {
    return taxYear.requirements
      .filter(req => {
        const docConfig = this.documentTypes[req.type];
        return docConfig && docConfig.category === category;
      })
      .map(req => ({
        ...req,
        daysUntil: this.daysUntil(req.deadline),
        isOverdue: req.deadline < new Date().toISOString().split('T')[0]
      }));
  }

  /**
   * Dringende Aktionen
   */
  getUrgentActions(taxYear, missing) {
    const actions = [];
    
    // Overdue documents
    if (missing.overdue.length > 0) {
      actions.push({
        type: 'overdue_documents',
        priority: 'critical',
        description: `${missing.overdue.length} überfällige Dokumente sofort hochladen`,
        deadline: 'sofort',
        items: missing.overdue.map(req => req.type)
      });
    }
    
    // Urgent documents
    if (missing.urgent.length > 0) {
      actions.push({
        type: 'urgent_documents',
        priority: 'high',
        description: `${missing.urgent.length} Dokumente in den nächsten 7 Tagen hochladen`,
        deadline: '7 Tage',
        items: missing.urgent.map(req => req.type)
      });
    }
    
    // Filing deadline approaching
    const daysUntilFiling = this.daysUntil(taxYear.filingDeadline);
    if (daysUntilFiling <= 30 && daysUntilFiling > 0) {
      actions.push({
        type: 'filing_deadline',
        priority: 'high',
        description: `Steuererklärungsfrist am ${taxYear.filingDeadline}`,
        deadline: taxYear.filingDeadline,
        daysUntil: daysUntilFiling
      });
    }
    
    return actions;
  }

  /**
   * Nächste Schritte
   */
  getNextSteps(taxYear, missing) {
    const steps = [];
    
    if (missing.total > 0) {
      // Most critical missing document
      const criticalMissing = missing.missing
        .filter(req => req.priority === 'high')
        .sort((a, b) => new Date(a.deadline) - new Date(b.deadline))[0];
      
      if (criticalMissing) {
        steps.push({
          action: 'upload_critical_document',
          description: `Kritisches Dokument hochladen: ${this.documentTypes[criticalMissing.type]?.name}`,
          documentType: criticalMissing.type,
          deadline: criticalMissing.deadline,
          priority: 'high'
        });
      }
    } else {
      steps.push({
        action: 'review_documents',
        description: 'Alle Dokumente überprüfen und ELSTER-Einreichung vorbereiten',
        priority: 'medium'
      });
    }
    
    // Check ELSTER certificate
    const certReq = taxYear.requirements.find(req => req.type === 'elster_zertifikat');
    if (certReq && certReq.status !== 'verified') {
      steps.push({
        action: 'verify_elster_certificate',
        description: 'ELSTER-Zertifikat überprüfen und ggf. erneuern',
        priority: 'high'
      });
    }
    
    return steps;
  }

  /**
   * Alle Steuerjahren
   */
  getTaxYears() {
    return Array.from(this.taxYears.values()).sort((a, b) => b.year - a.year);
  }

  /**
   * ELSTER-Zusammenfassung
   */
  getSummary() {
    const years = this.getTaxYears();
    const totalDocuments = this.documents.size;
    const totalRequirements = Array.from(this.taxYears.values())
      .reduce((sum, year) => sum + year.requirements.length, 0);
    
    const activeYears = years.filter(y => y.status !== 'complete');
    const overdueYears = activeYears.filter(y => 
      new Date(y.filingDeadline) < new Date()
    );
    
    return {
      totalTaxYears: years.length,
      activeYears: activeYears.length,
      overdueYears: overdueYears.length,
      totalDocuments,
      totalRequirements,
      completionRate: totalRequirements > 0 ? 
        Math.round((totalDocuments / totalRequirements) * 100) : 0,
      nextDeadline: this.getNextFilingDeadline()
    };
  }

  /**
   * Nächste Frist
   */
  getNextFilingDeadline() {
    const years = this.getTaxYears();
    const upcoming = years
      .filter(y => new Date(y.filingDeadline) > new Date())
      .sort((a, b) => new Date(a.filingDeadline) - new Date(b.filingDeadline));
    
    return upcoming.length > 0 ? upcoming[0].filingDeadline : null;
  }

  daysUntil(dateString) {
    if (!dateString) return 999;
    const date = new Date(dateString);
    const now = new Date();
    return Math.floor((date - now) / (1000 * 60 * 60 * 24));
  }
}

module.exports = { ElsterAssistant };
