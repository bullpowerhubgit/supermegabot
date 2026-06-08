/**
 * Demo Output — Entscheidungen und Zusammenfassungen visualisieren
 * 
 * Funktionen:
 * - KI-Entscheidungen formatiert ausgeben
 * - Zusammenfassungen generieren
 * - Action-Items erstellen
 * - Progress-Tracking
 * - Export-Funktionen
 */

class DemoOutput {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.decisions = [];
    this.summaries = [];
    this.actionItems = [];
    this.metrics = {
      totalDecisions: 0,
      totalSavings: 0,
      cancelledSubscriptions: 0,
      protectedSubscriptions: 0
    };
  }

  /**
   * KI-Entscheidung formatieren
   */
  formatDecision(subscription, decision, context = {}) {
    const decisionOutput = {
      timestamp: new Date().toISOString(),
      subscription: {
        name: subscription.name,
        cost: subscription.cost || subscription.monthlyCost,
        category: subscription.category,
        vendor: subscription.vendor
      },
      decision: {
        action: decision.action,
        reason: decision.reason,
        confidence: decision.confidence || 0.8,
        priority: decision.priority,
        requiresApproval: decision.requiresApproval || false
      },
      context: {
        usageScore: subscription.usageScore,
        daysSinceLastUse: subscription.daysSinceLastUse || 0,
        paymentCount: subscription.paymentCount || 0,
        isProtected: subscription.protected || false
      },
      recommendation: this.generateRecommendation(decision, subscription),
      nextSteps: this.generateNextSteps(decision, subscription),
      riskAssessment: this.assessRisk(decision, subscription)
    };

    this.decisions.push(decisionOutput);
    this.updateMetrics(decision);

    return decisionOutput;
  }

  /**
   * Empfehlung generieren
   */
  generateRecommendation(decision, subscription) {
    const recommendations = {
      'cancel_immediately': {
        title: 'SOFORT KÜNDIGEN',
        urgency: 'HIGH',
        description: `Dieses Abo wird seit ${subscription.daysSinceLastUse || 30}+ Tagen nicht genutzt und kostet €${(subscription.cost || subscription.monthlyCost).toFixed(2)}/Monat.`,
        savings: `Ersparnis: €${(subscription.cost || subscription.monthlyCost * 12).toFixed(2)}/Jahr`,
        action: 'Kündigung sofort einleiten'
      },
      'downgrade': {
        title: 'DOWNGRADE PRÜFEN',
        urgency: 'MEDIUM',
        description: `Nutzung ist gering (${subscription.usageScore || 50}%). Prüfe kleineren Plan oder Alternative.`,
        savings: `Potenzielle Ersparnis: €${((subscription.cost || subscription.monthlyCost) * 0.3 * 12).toFixed(2)}/Jahr`,
        action: 'Kleineren Plan recherchieren'
      },
      'review': {
        title: 'MANUELLE PRÜFUNG',
        urgency: 'MEDIUM',
        description: `Abo benötigt manuelle Überprüfung. Nutzung: ${subscription.usageScore || 50}%, Kosten: €${(subscription.cost || subscription.monthlyCost).toFixed(2)}/Monat.`,
        savings: `Mögliche Ersparnis: €${((subscription.cost || subscription.monthlyCost) * 0.5 * 12).toFixed(2)}/Jahr`,
        action: 'Nutzung analysieren und entscheiden'
      },
      'protected': {
        title: 'GESCHÜTZT - KEINE AKTION',
        urgency: 'NONE',
        description: `Dieses Abo ist geschützt: ${subscription.protectedReason || 'Kritische Infrastruktur'}.`,
        savings: 'Keine Ersparnis - geschützt',
        action: 'Status beibehalten'
      },
      'keep': {
        title: 'BEHALTEN',
        urgency: 'NONE',
        description: `Abo wird aktiv genutzt (Score: ${subscription.usageScore || 80}%). Behalten für Produktivität.`,
        savings: 'Keine Ersparnis - notwendig',
        action: 'Weiter nutzen'
      }
    };

    return recommendations[decision.action] || recommendations['keep'];
  }

  /**
   * Nächste Schritte generieren
   */
  generateNextSteps(decision, subscription) {
    const steps = [];

    switch (decision.action) {
      case 'cancel_immediately':
        steps.push({
          step: 1,
          action: 'Kündigung vorbereiten',
          description: 'Browser Cancel Agent starten',
          timeframe: 'Sofort',
          automated: true
        });
        steps.push({
          step: 2,
          action: 'Kündigungsbestätigung einholen',
          description: 'Screenshot der Kündigung speichern',
          timeframe: '1 Stunde',
          automated: false
        });
        break;

      case 'downgrade':
        steps.push({
          step: 1,
          action: 'Alternative recherchieren',
          description: 'Kleinere Pläne oder günstigere Alternativen finden',
          timeframe: '2 Tage',
          automated: true
        });
        steps.push({
          step: 2,
          action: 'Vergleich durchführen',
          description: 'Funktionen vs. Kosten abwägen',
          timeframe: '1 Tag',
          automated: false
        });
        break;

      case 'review':
        steps.push({
          step: 1,
          action: 'Nutzungsanalyse durchführen',
          description: 'Letzte 30 Tage Aktivität prüfen',
          timeframe: '1 Stunde',
          automated: true
        });
        steps.push({
          step: 2,
          action: 'Entscheidung treffen',
          description: 'Basierend auf Analyse entscheiden',
          timeframe: '1 Tag',
          automated: false
        });
        break;
    }

    return steps;
  }

  /**
   * Risiko-Bewertung
   */
  assessRisk(decision, subscription) {
    const risks = [];

    // Financial risk
    if (decision.action === 'cancel_immediately' && (subscription.cost || subscription.monthlyCost) > 100) {
      risks.push({
        type: 'financial',
        level: 'HIGH',
        description: `Hohe monatliche Kosten (€${(subscription.cost || subscription.monthlyCost).toFixed(2)}) - sorgfältige Prüfung erforderlich`
      });
    }

    // Business impact risk
    if (subscription.category === 'essential' || subscription.category === 'development') {
      risks.push({
        type: 'business_impact',
        level: 'MEDIUM',
        description: 'Könnte Business-Operationen beeinträchtigen'
      });
    }

    // Data loss risk
    if (subscription.category === 'storage' || subscription.tags?.includes('data')) {
      risks.push({
        type: 'data_loss',
        level: 'MEDIUM',
        description: 'Daten-Export vor Kündigung erforderlich'
      });
    }

    return risks;
  }

  /**
   * Zusammenfassung generieren
   */
  generateSummary(decisions, timeframe = 'current') {
    const summary = {
      generatedAt: new Date().toISOString(),
      timeframe,
      overview: {
        totalSubscriptions: decisions.length,
        totalMonthlyCost: decisions.reduce((sum, d) => sum + (d.subscription.cost || 0), 0),
        totalYearlyCost: decisions.reduce((sum, d) => sum + (d.subscription.cost || 0) * 12, 0)
      },
      actions: {
        cancelImmediately: decisions.filter(d => d.decision.action === 'cancel_immediately').length,
        downgrade: decisions.filter(d => d.decision.action === 'downgrade').length,
        review: decisions.filter(d => d.decision.action === 'review').length,
        keep: decisions.filter(d => d.decision.action === 'keep').length,
        protected: decisions.filter(d => d.decision.action === 'protected').length
      },
      savings: {
        immediate: this.calculateSavings(decisions, 'cancel_immediately'),
        downgrade: this.calculateSavings(decisions, 'downgrade'),
        review: this.calculateSavings(decisions, 'review'),
        total: this.calculateTotalSavings(decisions)
      },
      priorities: {
        high: decisions.filter(d => d.decision.priority === 'high').length,
        medium: decisions.filter(d => d.decision.priority === 'medium').length,
        low: decisions.filter(d => d.decision.priority === 'low').length
      },
      recommendations: this.generateTopRecommendations(decisions)
    };

    this.summaries.push(summary);
    return summary;
  }

  /**
   * Ersparnisse berechnen
   */
  calculateSavings(decisions, action) {
    const relevantDecisions = decisions.filter(d => d.decision.action === action);
    
    return relevantDecisions.reduce((sum, decision) => {
      const monthlyCost = decision.subscription.cost || 0;
      let savings = 0;
      
      switch (action) {
        case 'cancel_immediately':
          savings = monthlyCost * 12;
          break;
        case 'downgrade':
          savings = monthlyCost * 0.3 * 12; // 30% savings estimate
          break;
        case 'review':
          savings = monthlyCost * 0.5 * 12; // 50% savings estimate
          break;
      }
      
      return sum + savings;
    }, 0);
  }

  /**
   * Gesamtersparnisse
   */
  calculateTotalSavings(decisions) {
    return this.calculateSavings(decisions, 'cancel_immediately') +
           this.calculateSavings(decisions, 'downgrade') +
           this.calculateSavings(decisions, 'review');
  }

  /**
   * Top-Empfehlungen
   */
  generateTopRecommendations(decisions) {
    return decisions
      .filter(d => d.decision.action !== 'keep' && d.decision.action !== 'protected')
      .sort((a, b) => {
        const aSavings = (a.subscription.cost || 0) * 12;
        const bSavings = (b.subscription.cost || 0) * 12;
        return bSavings - aSavings;
      })
      .slice(0, 5)
      .map(d => ({
        subscription: d.subscription.name,
        action: d.decision.action,
        savings: (d.subscription.cost || 0) * 12,
        reason: d.decision.reason,
        priority: d.decision.priority
      }));
  }

  /**
   * Action-Items erstellen
   */
  createActionItems(decisions) {
    const actionItems = [];

    for (const decision of decisions) {
      if (decision.decision.action === 'cancel_immediately') {
        actionItems.push({
          id: `action_cancel_${decision.subscription.name.replace(/\s+/g, '_')}`,
          type: 'cancellation',
          priority: 'HIGH',
          subscription: decision.subscription.name,
          description: `Kündigung für ${decision.subscription.name} einleiten`,
          estimatedTime: '30 Minuten',
          automated: true,
          deadline: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), // 24 hours
          status: 'pending'
        });
      } else if (decision.decision.action === 'downgrade') {
        actionItems.push({
          id: `action_downgrade_${decision.subscription.name.replace(/\s+/g, '_')}`,
          type: 'research',
          priority: 'MEDIUM',
          subscription: decision.subscription.name,
          description: `Alternative für ${decision.subscription.name} recherchieren`,
          estimatedTime: '2 Stunden',
          automated: true,
          deadline: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(), // 3 days
          status: 'pending'
        });
      } else if (decision.decision.action === 'review') {
        actionItems.push({
          id: `action_review_${decision.subscription.name.replace(/\s+/g, '_')}`,
          type: 'analysis',
          priority: 'MEDIUM',
          subscription: decision.subscription.name,
          description: `Nutzungsanalyse für ${decision.subscription.name} durchführen`,
          estimatedTime: '1 Stunde',
          automated: true,
          deadline: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString(), // 2 days
          status: 'pending'
        });
      }
    }

    this.actionItems = actionItems;
    return actionItems;
  }

  /**
   * Progress-Tracking
   */
  getProgressReport() {
    const completed = this.actionItems.filter(item => item.status === 'completed').length;
    const pending = this.actionItems.filter(item => item.status === 'pending').length;
    const overdue = this.actionItems.filter(item => 
      item.status === 'pending' && new Date(item.deadline) < new Date()
    ).length;

    return {
      total: this.actionItems.length,
      completed,
      pending,
      overdue,
      completionRate: this.actionItems.length > 0 ? (completed / this.actionItems.length * 100).toFixed(1) : 0,
      estimatedTimeRemaining: this.actionItems
        .filter(item => item.status === 'pending')
        .reduce((sum, item) => sum + parseInt(item.estimatedTime), 0)
    };
  }

  /**
   * Konsolen-Ausgabe formatieren
   */
  printDecision(decision) {
    console.log('\n' + '='.repeat(60));
    console.log(`🤖 KI-ENTSCHEIDUNG: ${decision.recommendation.title}`);
    console.log('='.repeat(60));
    console.log(`📋 Abo: ${decision.subscription.name}`);
    console.log(`💰 Kosten: €${decision.subscription.cost.toFixed(2)}/Monat`);
    console.log(`📂 Kategorie: ${decision.subscription.category}`);
    console.log(`⚡ Dringlichkeit: ${decision.recommendation.urgency}`);
    console.log(`\n📝 Begründung:`);
    console.log(`   ${decision.recommendation.description}`);
    console.log(`\n💡 Ersparnis:`);
    console.log(`   ${decision.recommendation.savings}`);
    console.log(`\n🎯 Empfohlene Aktion:`);
    console.log(`   ${decision.recommendation.action}`);
    
    if (decision.nextSteps && decision.nextSteps.length > 0) {
      console.log(`\n📋 Nächste Schritte:`);
      decision.nextSteps.forEach(step => {
        const icon = step.automated ? '🤖' : '👤';
        console.log(`   ${icon} ${step.action} (${step.timeframe})`);
      });
    }

    if (decision.riskAssessment && decision.riskAssessment.length > 0) {
      console.log(`\n⚠️  Risiken:`);
      decision.riskAssessment.forEach(risk => {
        console.log(`   [${risk.level}] ${risk.description}`);
      });
    }

    console.log('='.repeat(60));
  }

  /**
   * Zusammenfassung ausgeben
   */
  printSummary(summary) {
    console.log('\n' + '='.repeat(60));
    console.log('📊 ZUSAMMENFASSUNG DER KI-ENTSCHEIDUNGEN');
    console.log('='.repeat(60));
    
    console.log(`\n📈 Übersicht:`);
    console.log(`   Abos insgesamt: ${summary.overview.totalSubscriptions}`);
    console.log(`   Monatliche Kosten: €${summary.overview.totalMonthlyCost.toFixed(2)}`);
    console.log(`   Jährliche Kosten: €${summary.overview.totalYearlyCost.toFixed(2)}`);
    
    console.log(`\n🎯 Aktionen:`);
    console.log(`   🔴 Sofort kündigen: ${summary.actions.cancelImmediately}`);
    console.log(`   🟡 Downgrade prüfen: ${summary.actions.downgrade}`);
    console.log(`   🟠 Manuell prüfen: ${summary.actions.review}`);
    console.log(`   🟢 Behalten: ${summary.actions.keep}`);
    console.log(`   🔒 Geschützt: ${summary.actions.protected}`);
    
    console.log(`\n💰 Ersparnis-Potenzial:`);
    console.log(`   Sofort kündigen: €${summary.savings.immediate.toFixed(2)}/Jahr`);
    console.log(`   Downgrade: €${summary.savings.downgrade.toFixed(2)}/Jahr`);
    console.log(`   Review: €${summary.savings.review.toFixed(2)}/Jahr`);
    console.log(`   📈 GESAMT: €${summary.savings.total.toFixed(2)}/Jahr`);
    
    if (summary.recommendations.length > 0) {
      console.log(`\n🏆 Top 5 Empfehlungen:`);
      summary.recommendations.forEach((rec, index) => {
        const icon = rec.priority === 'high' ? '🔴' : rec.priority === 'medium' ? '🟡' : '🟢';
        console.log(`   ${index + 1}. ${icon} ${rec.subscription} — €${rec.savings.toFixed(2)}/Jahr`);
      });
    }

    console.log('='.repeat(60));
  }

  /**
   * Action-Items ausgeben
   */
  printActionItems() {
    console.log('\n' + '='.repeat(60));
    console.log('✅ ACTION-ITEMS');
    console.log('='.repeat(60));
    
    const highPriority = this.actionItems.filter(item => item.priority === 'HIGH');
    const mediumPriority = this.actionItems.filter(item => item.priority === 'MEDIUM');
    const lowPriority = this.actionItems.filter(item => item.priority === 'LOW');

    if (highPriority.length > 0) {
      console.log(`\n🔴 HOHE PRIORITÄT:`);
      highPriority.forEach(item => {
        const icon = item.automated ? '🤖' : '👤';
        console.log(`   ${icon} ${item.description} (${item.estimatedTime})`);
      });
    }

    if (mediumPriority.length > 0) {
      console.log(`\n🟡 MITTEL PRIORITÄT:`);
      mediumPriority.forEach(item => {
        const icon = item.automated ? '🤖' : '👤';
        console.log(`   ${icon} ${item.description} (${item.estimatedTime})`);
      });
    }

    if (lowPriority.length > 0) {
      console.log(`\n🟢 NIEDRIGE PRIORITÄT:`);
      lowPriority.forEach(item => {
        const icon = item.automated ? '🤖' : '👤';
        console.log(`   ${icon} ${item.description} (${item.estimatedTime})`);
      });
    }

    const progress = this.getProgressReport();
    console.log(`\n📊 FORTSCHRITT: ${progress.completed}/${progress.total} (${progress.completionRate}%)`);
    console.log(`⏰ Geschätzte Restzeit: ${progress.estimatedTimeRemaining} Minuten`);
    
    console.log('='.repeat(60));
  }

  /**
   * Metriken aktualisieren
   */
  updateMetrics(decision) {
    this.metrics.totalDecisions++;
    
    if (decision.action === 'cancel_immediately') {
      this.metrics.cancelledSubscriptions++;
      this.metrics.totalSavings += (decision.cost || 0) * 12;
    } else if (decision.action === 'protected') {
      this.metrics.protectedSubscriptions++;
    }
  }

  /**
   * Export-Funktionen
   */
  exportToJson() {
    return {
      generatedAt: new Date().toISOString(),
      metrics: this.metrics,
      decisions: this.decisions,
      summaries: this.summaries,
      actionItems: this.actionItems
    };
  }

  exportToMarkdown() {
    let markdown = '# Abo-Optimizer Report\n\n';
    markdown += `Generiert am: ${new Date().toLocaleString('de-DE')}\n\n`;
    
    markdown += '## 📊 Metriken\n';
    markdown += `- Gesamt-Entscheidungen: ${this.metrics.totalDecisions}\n`;
    markdown += `- Gekündigte Abos: ${this.metrics.cancelledSubscriptions}\n`;
    markdown += `- Geschützte Abos: ${this.metrics.protectedSubscriptions}\n`;
    markdown += `- Ersparnis: €${this.metrics.totalSavings.toFixed(2)}/Jahr\n\n`;
    
    if (this.decisions.length > 0) {
      markdown += '## 🤖 KI-Entscheidungen\n\n';
      this.decisions.forEach(decision => {
        markdown += `### ${decision.subscription.name}\n`;
        markdown += `- **Aktion:** ${decision.decision.action}\n`;
        markdown += `- **Grund:** ${decision.decision.reason}\n`;
        markdown += `- **Kosten:** €${decision.subscription.cost.toFixed(2)}/Monat\n`;
        markdown += `- **Priorität:** ${decision.decision.priority}\n\n`;
      });
    }
    
    return markdown;
  }
}

module.exports = { DemoOutput };
