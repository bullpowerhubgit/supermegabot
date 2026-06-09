const fs = require('fs');
const path = require('path');

/**
 * Case Manager — Steuer-, Streit- und Problemfälle verwalten
 * 
 * Funktionen:
 * - Fall-Tracking (Steuer, rechtlich, technisch)
 * - Dokumenten-Management
 * - Fristen-Verfolgung
 * - Status-Updates
 * - Lösungsvorschläge
 */

class CaseManager {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../state/cases');
    this.cases = new Map();
    this.caseTypes = {
      'tax': {
        name: 'Steuerfall',
        priority: 1,
        color: '#DC2626',
        description: 'Steuererklärungen, Bescheide, Nachweise',
        defaultActions: ['document_request', 'filing_deadline', 'payment_required'],
        requiredDocuments: ['steuerbescheid', 'einnahmenübersicht', 'ausgabenbelege']
      },
      'legal': {
        name: 'Rechtsfall',
        priority: 1,
        color: '#DC2626',
        description: 'Vertragsstreitigkeiten, Abmahnungen, Gerichtsverfahren',
        defaultActions: ['legal_review', 'response_deadline', 'evidence_collection'],
        requiredDocuments: ['vertrag', 'korrespondenz', 'nachweise']
      },
      'technical': {
        name: 'Technischer Fall',
        priority: 2,
        color: '#F59E0B',
        description: 'System-Ausfälle, Integrationen, Daten-Probleme',
        defaultActions: ['troubleshooting', 'vendor_contact', 'backup_recovery'],
        requiredDocuments: ['error_logs', 'system_config', 'screenshots']
      },
      'financial': {
        name: 'Finanzfall',
        priority: 2,
        color: '#3B82F6',
        description: 'Zahlungsprobleme, Rechnungsdispute, Buchungsfehler',
        defaultActions: ['payment_verification', 'dispute_filing', 'account_reconciliation'],
        requiredDocuments: ['rechnung', 'zahlungsnachweis', 'kontoauszug']
      },
      'compliance': {
        name: 'Compliance-Fall',
        priority: 1,
        color: '#DC2626',
        description: 'DSGVO, Impressum, AGB, Lizenzen',
        defaultActions: ['compliance_check', 'document_update', 'deadline_reminder'],
        requiredDocuments: ['nachweis', 'zertifizierung', 'dokumentation']
      },
      'general': {
        name: 'Allgemeiner Fall',
        priority: 3,
        color: '#6B7280',
        description: 'Sonstige Anliegen und Probleme',
        defaultActions: ['investigation', 'research', 'solution_proposal'],
        requiredDocuments: []
      }
    };
    
    this.ensureStorageDir();
    this.loadCases();
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

  loadCases() {
    try {
      const filePath = path.join(this.storagePath, 'cases.json');
      if (fs.existsSync(filePath)) {
        const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        this.cases = new Map(data.cases || []);
      }
    } catch (err) {
      this.logger.error?.('case.load_failed', { error: err.message });
    }
  }

  saveCases() {
    try {
      fs.writeFileSync(
        path.join(this.storagePath, 'cases.json'),
        JSON.stringify({
          updatedAt: new Date().toISOString(),
          cases: Array.from(this.cases.entries())
        }, null, 2)
      );
    } catch (err) {
      this.logger.error?.('case.save_failed', { error: err.message });
    }
  }

  /**
   * Neuen Fall erstellen
   */
  createCase(caseData) {
    const id = `case_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
    const caseType = this.caseTypes[caseData.type] || this.caseTypes['general'];
    
    const newCase = {
      id,
      type: caseData.type,
      title: caseData.title,
      description: caseData.description || '',
      priority: caseData.priority || caseType.priority,
      status: 'open',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      deadline: caseData.deadline || null,
      assignedTo: caseData.assignedTo || null,
      tags: caseData.tags || [],
      documents: [],
      actions: this.generateDefaultActions(caseType),
      timeline: [{
        timestamp: new Date().toISOString(),
        action: 'created',
        description: 'Fall erstellt',
        user: 'system'
      }],
      metadata: {
        estimatedResolution: this.estimateResolutionTime(caseType),
        complexity: caseData.complexity || 'medium',
        impact: caseData.impact || 'medium'
      }
    };
    
    this.cases.set(id, newCase);
    this.saveCases();
    
    this.logger.info?.('case.created', { id, type: caseData.type, title: caseData.title });
    return newCase;
  }

  /**
   * Standard-Aktionen für Fall-Typ generieren
   */
  generateDefaultActions(caseType) {
    return caseType.defaultActions.map((action, index) => ({
      id: `action_${index}`,
      type: action,
      status: 'pending',
      assignedTo: null,
      dueDate: this.calculateActionDueDate(action),
      notes: '',
      completedAt: null
    }));
  }

  /**
   * Fälligkeitsdatum für Aktion berechnen
   */
  calculateActionDueDate(actionType) {
    const now = new Date();
    let days = 7; // Default
    
    switch (actionType) {
      case 'document_request': days = 3; break;
      case 'filing_deadline': days = 14; break;
      case 'payment_required': days = 5; break;
      case 'legal_review': days = 7; break;
      case 'response_deadline': days = 10; break;
      case 'troubleshooting': days = 2; break;
      case 'compliance_check': days = 14; break;
      case 'investigation': days = 5; break;
    }
    
    now.setDate(now.getDate() + days);
    return now.toISOString().split('T')[0];
  }

  /**
   * Geschätzte Lösungszeit
   */
  estimateResolutionTime(caseType) {
    switch (caseType.priority) {
      case 1: return '2-4 Wochen';
      case 2: return '1-2 Wochen';
      case 3: return '3-7 Tage';
      default: return '1 Woche';
    }
  }

  /**
   * Dokument zum Fall hinzufügen
   */
  addDocument(caseId, document) {
    const caseItem = this.cases.get(caseId);
    if (!caseItem) {
      throw new Error(`Case ${caseId} not found`);
    }
    
    const docId = `doc_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
    const newDocument = {
      id: docId,
      name: document.name,
      type: document.type || 'unknown',
      path: document.path || null,
      uploadedAt: new Date().toISOString(),
      size: document.size || 0,
      required: document.required || false,
      verified: document.verified || false,
      notes: document.notes || ''
    };
    
    caseItem.documents.push(newDocument);
    caseItem.timeline.push({
      timestamp: new Date().toISOString(),
      action: 'document_added',
      description: `Dokument hinzugefügt: ${document.name}`,
      user: 'system'
    });
    
    caseItem.updatedAt = new Date().toISOString();
    this.cases.set(caseId, caseItem);
    this.saveCases();
    
    this.logger.info?.('case.document_added', { caseId, document: document.name });
    return newDocument;
  }

  /**
   * Aktion aktualisieren
   */
  updateAction(caseId, actionId, updates) {
    const caseItem = this.cases.get(caseId);
    if (!caseItem) {
      throw new Error(`Case ${caseId} not found`);
    }
    
    const action = caseItem.actions.find(a => a.id === actionId);
    if (!action) {
      throw new Error(`Action ${actionId} not found`);
    }
    
    Object.assign(action, updates);
    
    if (updates.status === 'completed' && !action.completedAt) {
      action.completedAt = new Date().toISOString();
      caseItem.timeline.push({
        timestamp: new Date().toISOString(),
        action: 'action_completed',
        description: `Aktion abgeschlossen: ${action.type}`,
        user: 'system'
      });
    }
    
    caseItem.updatedAt = new Date().toISOString();
    this.cases.set(caseId, caseItem);
    this.saveCases();
    
    return action;
  }

  /**
   * Fall-Status aktualisieren
   */
  updateCaseStatus(caseId, status, notes = '') {
    const caseItem = this.cases.get(caseId);
    if (!caseItem) {
      throw new Error(`Case ${caseId} not found`);
    }
    
    const oldStatus = caseItem.status;
    caseItem.status = status;
    caseItem.updatedAt = new Date().toISOString();
    
    caseItem.timeline.push({
      timestamp: new Date().toISOString(),
      action: 'status_changed',
      description: `Status geändert: ${oldStatus} → ${status}${notes ? ` (${notes})` : ''}`,
      user: 'system'
    });
    
    this.cases.set(caseId, caseItem);
    this.saveCases();
    
    this.logger.info?.('case.status_updated', { caseId, oldStatus, newStatus: status });
    return caseItem;
  }

  /**
   * Fälle nach Typ und Status filtern
   */
  getCases(filter = {}) {
    let cases = Array.from(this.cases.values());
    
    if (filter.type) {
      cases = cases.filter(c => c.type === filter.type);
    }
    
    if (filter.status) {
      cases = cases.filter(c => c.status === filter.status);
    }
    
    if (filter.priority) {
      cases = cases.filter(c => c.priority === filter.priority);
    }
    
    if (filter.assignedTo) {
      cases = cases.filter(c => c.assignedTo === filter.assignedTo);
    }
    
    if (filter.hasDeadline) {
      const today = new Date().toISOString().split('T')[0];
      cases = cases.filter(c => c.deadline && c.deadline >= today);
    }
    
    // Sort by priority and creation date
    return cases.sort((a, b) => {
      if (a.priority !== b.priority) {
        return a.priority - b.priority;
      }
      return new Date(b.createdAt) - new Date(a.createdAt);
    });
  }

  /**
   * Überfällige Fälle
   */
  getOverdueCases() {
    const today = new Date().toISOString().split('T')[0];
    return this.getCases().filter(c => {
      if (c.deadline && c.deadline < today && c.status !== 'closed') {
        return true;
      }
      
      // Check overdue actions
      return c.actions.some(action => 
        action.dueDate < today && action.status !== 'completed'
      );
    });
  }

  /**
   * Fall-Statistik
   */
  getStatistics() {
    const cases = Array.from(this.cases.values());
    const byType = {};
    const byStatus = {};
    const byPriority = {};
    
    for (const caseItem of cases) {
      // By type
      byType[caseItem.type] = (byType[caseItem.type] || 0) + 1;
      
      // By status
      byStatus[caseItem.status] = (byStatus[caseItem.status] || 0) + 1;
      
      // By priority
      byPriority[caseItem.priority] = (byPriority[caseItem.priority] || 0) + 1;
    }
    
    const overdue = this.getOverdueCases();
    const avgResolutionTime = this.calculateAverageResolutionTime();
    
    return {
      total: cases.length,
      byType,
      byStatus,
      byPriority,
      overdue: overdue.length,
      averageResolutionTime: avgResolutionTime,
      openCases: cases.filter(c => c.status === 'open').length,
      closedCases: cases.filter(c => c.status === 'closed').length
    };
  }

  /**
   * Durchschnittliche Lösungszeit berechnen
   */
  calculateAverageResolutionTime() {
    const closedCases = Array.from(this.cases.values())
      .filter(c => c.status === 'closed' && c.timeline.length > 1);
    
    if (closedCases.length === 0) return 'N/A';
    
    const totalDays = closedCases.reduce((sum, caseItem) => {
      const created = new Date(caseItem.createdAt);
      const lastUpdate = new Date(caseItem.timeline[caseItem.timeline.length - 1].timestamp);
      return sum + Math.floor((lastUpdate - created) / (1000 * 60 * 60 * 24));
    }, 0);
    
    return `${Math.round(totalDays / closedCases.length)} Tage`;
  }

  /**
   * Lösungs-Vorschlag generieren
   */
  generateSolutionProposal(caseId) {
    const caseItem = this.cases.get(caseId);
    if (!caseItem) {
      throw new Error(`Case ${caseId} not found`);
    }
    
    const caseType = this.caseTypes[caseItem.type];
    const missingDocuments = caseType.requiredDocuments.filter(
      req => !caseItem.documents.some(doc => doc.type === req)
    );
    
    const pendingActions = caseItem.actions.filter(a => a.status === 'pending');
    const overdueActions = pendingActions.filter(a => 
      a.dueDate < new Date().toISOString().split('T')[0]
    );
    
    const proposal = {
      caseId,
      caseType: caseType.name,
      priority: caseItem.priority,
      currentStatus: caseItem.status,
      nextSteps: [],
      risks: [],
      estimatedResolution: caseItem.metadata.estimatedResolution,
      documents: {
        required: caseType.requiredDocuments,
        missing: missingDocuments,
        uploaded: caseItem.documents.length
      },
      actions: {
        total: caseItem.actions.length,
        pending: pendingActions.length,
        overdue: overdueActions.length,
        completed: caseItem.actions.filter(a => a.status === 'completed').length
      }
    };
    
    // Next steps based on case type
    if (missingDocuments.length > 0) {
      proposal.nextSteps.push({
        action: 'documents_required',
        priority: 'high',
        description: `Fehlende Dokumente hochladen: ${missingDocuments.join(', ')}`,
        deadline: this.calculateActionDueDate('document_request')
      });
    }
    
    if (overdueActions.length > 0) {
      proposal.nextSteps.push({
        action: 'overdue_actions',
        priority: 'critical',
        description: `${overdueActions.length} überfällige Aktionen bearbeiten`,
        deadline: 'sofort'
      });
    }
    
    // Risks based on case type and overdue items
    if (caseItem.type === 'tax' && overdueActions.length > 0) {
      proposal.risks.push({
        type: 'financial_penalty',
        description: 'Mögliche Strafzahlung bei Fristüberschreitung',
        severity: 'high'
      });
    }
    
    if (caseItem.type === 'legal' && missingDocuments.length > 0) {
      proposal.risks.push({
        type: 'legal_disadvantage',
        description: 'Rechtlicher Nachteil durch fehlende Dokumente',
        severity: 'high'
      });
    }
    
    return proposal;
  }

  /**
   * Get case types
   */
  getCaseTypes() {
    return this.caseTypes;
  }
}

module.exports = { CaseManager };
