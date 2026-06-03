const express = require('express');
const router = express.Router();

/**
 * Dashboard Routes — Alle Endpunkte für das Optimizer Dashboard
 * 
 * Bereiche:
 * - Übersicht / KPIs
 * - Abo-Verwaltung
 * - Kündigungen
 * - Importe (PayPal, Bank)
 * - Analyse & Reports
 * - Einstellungen
 */

function createDashboardRoutes(services) {
  const {
    subscriptionOptimizer,
    subscriptionClassifier,
    costMonitorService,
    assistantService,
    paypalImporter,
    bankImporter,
    browserCancelAgent,
    invoiceHunter,
    reminderService,
    protectionList,
    caseManager,
    elsterAssistant,
    expenseRadar,
    demoOutput
  } = services;

  // ── ÜBERSICHT / KPIs ──────────────────────────────────────────────

  router.get('/overview', async (req, res) => {
    try {
      const optimizer = subscriptionOptimizer?.getReport?.() || {};
      const costs = costMonitorService?.getDashboardData?.() || {};
      
      res.json({
        ok: true,
        overview: {
          totalMonthlyCost: optimizer.summary?.totalMonthlyCost || 0,
          totalSubscriptions: optimizer.summary?.totalSubscriptions || 0,
          potentialSavings: optimizer.summary?.savingsPotential || 0,
          activeCancellations: browserCancelAgent?.getLog?.().summary?.pending || 0,
          revenueToday: costs.revenue?.today || 0,
          profitMargin: costs.health?.metrics?.profitMargin || 0,
          healthScore: costs.health?.score || 0
        }
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/kpis', async (req, res) => {
    try {
      const costs = costMonitorService?.getDashboardData?.() || {};
      const health = costs.health || {};
      
      res.json({
        ok: true,
        kpis: {
          revenue: {
            today: costs.revenue?.today || 0,
            weekly: costs.revenue?.last7Days?.total || 0,
            monthly: costs.revenue?.last30Days?.total || 0,
            growth: costs.revenue?.last7Days?.growth || 0
          },
          costs: {
            monthly: costs.costs?.grandTotal || 0,
            breakdown: costs.costs?.breakdown || [],
            alerts: costs.costs?.alerts?.length || 0
          },
          health: {
            score: health.score || 0,
            status: health.status || 'unknown',
            profitMargin: health.metrics?.profitMargin || 0,
            monthlyProfit: health.metrics?.monthlyProfit || 0
          }
        }
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── ABO-VERWALTUNG ────────────────────────────────────────────────

  router.get('/subscriptions', async (req, res) => {
    try {
      const subs = subscriptionOptimizer?.subscriptions || new Map();
      const classified = subscriptionClassifier?.subscriptions || new Map();
      
      const merged = [];
      for (const [id, sub] of subs) {
        const cls = classified.get(id);
        merged.push({
          ...sub,
          classification: cls?.classification || null
        });
      }

      res.json({
        ok: true,
        subscriptions: merged,
        totalMonthly: merged.reduce((sum, s) => sum + (s.cost || 0), 0)
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/subscriptions/classified', async (req, res) => {
    try {
      const report = subscriptionClassifier?.getReport?.() || {};
      
      res.json({
        ok: true,
        summary: report.summary || {},
        byAction: report.byAction || {},
        byCategory: report.byCategory || {}
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/subscriptions/add', async (req, res) => {
    try {
      const { name, cost, category, billingCycle, url, platform } = req.body || {};
      
      if (!name || !cost) {
        return res.status(400).json({ ok: false, error: 'name_and_cost_required' });
      }

      const sub = subscriptionOptimizer?.addSubscription?.({
        name,
        cost: parseFloat(cost),
        category: category || 'other',
        billingCycle: billingCycle || 'monthly',
        url,
        platform: platform || 'manual',
        addedAt: new Date().toISOString()
      });

      res.json({
        ok: true,
        subscription: sub,
        message: 'Abo hinzugefügt'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.delete('/subscriptions/:id', async (req, res) => {
    try {
      const { id } = req.params;
      subscriptionOptimizer?.markCancelled?.(id, { reason: 'Manuell gelöscht' });
      
      res.json({
        ok: true,
        message: `Abo ${id} als gekündigt markiert`
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── KÜNDIGUNGEN ─────────────────────────────────────────────────

  router.get('/cancellations', async (req, res) => {
    try {
      const log = browserCancelAgent?.getLog?.() || { jobs: [], summary: {} };
      
      res.json({
        ok: true,
        jobs: log.jobs,
        summary: log.summary
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/cancellations/prepare', async (req, res) => {
    try {
      const { subscriptionId } = req.body || {};
      
      if (!subscriptionId) {
        return res.status(400).json({ ok: false, error: 'subscription_id_required' });
      }

      const sub = subscriptionOptimizer?.subscriptions?.get?.(subscriptionId);
      if (!sub) {
        return res.status(404).json({ ok: false, error: 'subscription_not_found' });
      }

      const job = await browserCancelAgent?.prepareCancellation?.(sub);
      
      res.json({
        ok: true,
        job,
        message: job.requiresApproval 
          ? 'Kündigung vorbereitet. Approval erforderlich.' 
          : 'Kündigung vorbereitet. Sofort ausführbar.'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/cancellations/:jobId/approve', async (req, res) => {
    try {
      const { jobId } = req.params;
      const result = browserCancelAgent?.approveCancellation?.(jobId);
      
      res.json({
        ok: true,
        result,
        message: 'Kündigung genehmigt'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/cancellations/:jobId/execute', async (req, res) => {
    try {
      const { jobId } = req.params;
      const credentials = req.body?.credentials || {};
      
      const result = await browserCancelAgent?.executeCancellation?.(jobId, credentials);
      
      res.json({
        ok: true,
        result,
        message: result.success 
          ? 'Kündigung erfolgreich' 
          : 'Kündigung erfordert manuelle Aktion'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── IMPORTE ──────────────────────────────────────────────────────

  router.post('/import/paypal', async (req, res) => {
    try {
      const { filePath } = req.body || {};
      
      if (!filePath) {
        return res.status(400).json({ ok: false, error: 'file_path_required' });
      }

      const result = await paypalImporter?.importCSV?.(filePath);
      
      // Merge into classifier
      if (subscriptionClassifier && result?.subscriptions) {
        subscriptionClassifier.mergeFromSources([{ subscriptions: result.subscriptions }]);
      }
      
      res.json({
        ok: true,
        imported: result.imported,
        detectedSubscriptions: result.subscriptions?.length || 0,
        summary: paypalImporter?.getSummary?.()
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/import/bank', async (req, res) => {
    try {
      const { filePath, format } = req.body || {};
      
      if (!filePath) {
        return res.status(400).json({ ok: false, error: 'file_path_required' });
      }

      const result = await bankImporter?.importCSV?.(filePath, format || 'auto');
      
      // Merge into classifier
      if (subscriptionClassifier && result?.subscriptions) {
        subscriptionClassifier.mergeFromSources([{ subscriptions: result.subscriptions }]);
      }
      
      res.json({
        ok: true,
        imported: result.imported,
        format: result.format,
        detectedSubscriptions: result.subscriptions?.length || 0,
        summary: bankImporter?.getSubscriptionSummary?.()
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── ANALYSE & REPORTS ───────────────────────────────────────────

  router.get('/analysis', async (req, res) => {
    try {
      const optimizerReport = subscriptionOptimizer?.getReport?.() || {};
      const classifierReport = subscriptionClassifier?.getReport?.() || {};
      const costData = costMonitorService?.getDashboardData?.() || {};
      
      res.json({
        ok: true,
        analysis: {
          optimizer: optimizerReport,
          classifier: classifierReport,
          costs: costData.costs,
          health: costData.health
        }
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/reports/savings', async (req, res) => {
    try {
      const classified = subscriptionClassifier?.getByAction?.() || {};
      const immediate = classified.cancelImmediately || [];
      const review = classified.review || [];
      
      const immediateSavings = immediate.reduce((sum, s) => sum + (s.classification?.monthlyCost || 0), 0);
      const reviewSavings = review.reduce((sum, s) => sum + (s.classification?.monthlyCost || 0) * 0.5, 0);
      
      res.json({
        ok: true,
        savings: {
          immediate: {
            count: immediate.length,
            monthly: immediateSavings,
            yearly: immediateSavings * 12,
            subscriptions: immediate.map(s => ({
              name: s.name,
              cost: s.classification?.monthlyCost || s.cost,
              reason: s.classification?.actionReason
            }))
          },
          review: {
            count: review.length,
            monthly: reviewSavings,
            yearly: reviewSavings * 12,
            subscriptions: review.map(s => ({
              name: s.name,
              cost: s.classification?.monthlyCost || s.cost,
              reason: s.classification?.actionReason
            }))
          },
          totalPotential: {
            monthly: immediateSavings + reviewSavings,
            yearly: (immediateSavings + reviewSavings) * 12
          }
        }
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── ASSISTANT ────────────────────────────────────────────────────

  router.post('/assistant/optimize-costs', async (req, res) => {
    try {
      const analysis = subscriptionOptimizer?.analyze?.() || {};
      const suggestions = assistantService?.getSuggestions?.({
        current_page: 'optimizer',
        data: { costs: { unusual: analysis.potentialSavings > 100 } }
      }) || {};
      
      res.json({
        ok: true,
        recommendations: {
          immediate: analysis.immediateCancel || [],
          consider: analysis.considerCancel || [],
          optimize: analysis.optimizePlan || [],
          potentialSavings: analysis.potentialSavings || 0
        },
        assistantSuggestions: suggestions
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── INVOICE HUNTER ─────────────────────────────────────────────

  router.get('/invoices', async (req, res) => {
    try {
      const summary = invoiceHunter?.getSummary?.() || {};
      const contracts = invoiceHunter?.getContracts?.() || [];
      
      res.json({
        ok: true,
        summary,
        contracts
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/invoices/deadlines', async (req, res) => {
    try {
      const deadlines = invoiceHunter?.getContractsWithCancellationDeadline?.() || [];
      
      res.json({
        ok: true,
        deadlines
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/invoices/parse', async (req, res) => {
    try {
      const { text, source } = req.body || {};
      
      if (!text) {
        return res.status(400).json({ ok: false, error: 'text_required' });
      }

      const invoice = invoiceHunter?.parseInvoice?.(text, source || 'api');
      
      res.json({
        ok: true,
        invoice
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── REMINDERS ───────────────────────────────────────────────────

  router.get('/reminders', async (req, res) => {
    try {
      const active = reminderService?.getActiveReminders?.() || [];
      const upcoming = reminderService?.getUpcomingDeadlines?.(30) || [];
      const summary = reminderService?.getSummary?.() || {};
      
      res.json({
        ok: true,
        active,
        upcoming,
        summary
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/reminders/add', async (req, res) => {
    try {
      const { type, title, deadline, details } = req.body || {};
      
      if (!type || !title || !deadline) {
        return res.status(400).json({ ok: false, error: 'type_title_deadline_required' });
      }

      const reminder = reminderService?.addCustomReminder?.(type, title, deadline, details || {});
      
      res.json({
        ok: true,
        reminder,
        message: 'Erinnerung erstellt'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/reminders/:id/complete', async (req, res) => {
    try {
      const { id } = req.params;
      const success = reminderService?.completeReminder?.(id);
      
      res.json({
        ok: success,
        message: success ? 'Erinnerung abgeschlossen' : 'Nicht gefunden'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/reminders/ics', async (req, res) => {
    try {
      const filePath = reminderService?.generateICS?.();
      
      if (filePath && fs.existsSync(filePath)) {
        res.setHeader('Content-Type', 'text/calendar');
        res.setHeader('Content-Disposition', 'attachment; filename=reminders.ics');
        res.sendFile(filePath);
      } else {
        res.status(404).json({ ok: false, error: 'ICS-Datei nicht gefunden' });
      }
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── EINSTELLUNGEN ────────────────────────────────────────────────

  router.get('/settings', async (req, res) => {
    try {
      res.json({
        ok: true,
        settings: {
          autoCancelThreshold: 20,  // € - unterhalb direkt, drüber Approval
          approvalThreshold: 50,     // € - drüber hart blockiert
          reminderDays: 7,            // Tage vor Kündigungsfrist
          scanInterval: 'daily',      // Häufigkeit der Analyse
          notifyChannels: ['telegram', 'dashboard']
        }
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/settings', async (req, res) => {
    try {
      const settings = req.body || {};
      // In production: save to config file
      
      res.json({
        ok: true,
        settings,
        message: 'Einstellungen aktualisiert'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── PROTECTION LIST ────────────────────────────────────────────────

  router.get('/protection/overview', async (req, res) => {
    try {
      const subscriptions = subscriptionClassifier?.getSubscriptions?.() || [];
      const report = protectionList?.getProtectionReport?.(subscriptions) || {};
      
      res.json({
        ok: true,
        protection: {
          categories: protectionList?.getCategories?.() || {},
          report,
          manualProtections: protectionList?.getManualProtections?.() || []
        }
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/protection/add', async (req, res) => {
    try {
      const protection = req.body || {};
      const result = protectionList?.addManualProtection?.(protection);
      
      res.json({
        ok: true,
        protection: result,
        message: 'Schutz hinzugefügt'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.delete('/protection/:id', async (req, res) => {
    try {
      const { id } = req.params;
      const removed = protectionList?.removeManualProtection?.(id);
      
      res.json({
        ok: true,
        removed,
        message: removed ? 'Schutz entfernt' : 'Schutz nicht gefunden'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── CASE MANAGER ───────────────────────────────────────────────────

  router.get('/cases', async (req, res) => {
    try {
      const filter = req.query || {};
      const cases = caseManager?.getCases?.(filter) || [];
      const statistics = caseManager?.getStatistics?.() || {};
      
      res.json({
        ok: true,
        cases,
        statistics,
        types: caseManager?.getCaseTypes?.() || {}
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/cases', async (req, res) => {
    try {
      const caseData = req.body || {};
      const newCase = caseManager?.createCase?.(caseData);
      
      res.json({
        ok: true,
        case: newCase,
        message: 'Fall erstellt'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/cases/:id/documents', async (req, res) => {
    try {
      const { id } = req.params;
      const document = req.body || {};
      const result = caseManager?.addDocument?.(id, document);
      
      res.json({
        ok: true,
        document: result,
        message: 'Dokument hinzugefügt'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/cases/overdue', async (req, res) => {
    try {
      const overdue = caseManager?.getOverdueCases?.() || [];
      
      res.json({
        ok: true,
        overdue: overdue.length,
        cases: overdue
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── ELSTER ASSISTANT ─────────────────────────────────────────────────

  router.get('/elster/overview', async (req, res) => {
    try {
      const summary = elsterAssistant?.getSummary?.() || {};
      const taxYears = elsterAssistant?.getTaxYears?.() || [];
      
      res.json({
        ok: true,
        elster: {
          summary,
          taxYears,
          documentTypes: elsterAssistant?.documentTypes || {}
        }
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/elster/tax-years/:year', async (req, res) => {
    try {
      const { year } = req.params;
      const options = req.body || {};
      const taxYear = elsterAssistant?.initializeTaxYear?.(parseInt(year), options);
      
      res.json({
        ok: true,
        taxYear,
        message: 'Steuerjahr initialisiert'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/elster/tax-years/:year/checklist', async (req, res) => {
    try {
      const { year } = req.params;
      const checklist = elsterAssistant?.generateChecklist?.(parseInt(year));
      
      res.json({
        ok: true,
        checklist
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/elster/tax-years/:year/missing', async (req, res) => {
    try {
      const { year } = req.params;
      const missing = elsterAssistant?.getMissingDocuments?.(parseInt(year));
      
      res.json({
        ok: true,
        missing
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── EXPENSE RADAR ───────────────────────────────────────────────────

  router.get('/expenses/overview', async (req, res) => {
    try {
      const overview = expenseRadar?.getRadarOverview?.() || {};
      
      res.json({
        ok: true,
        expenses: overview
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/expenses', async (req, res) => {
    try {
      const expense = req.body || {};
      const result = expenseRadar?.addExpense?.(expense);
      
      res.json({
        ok: true,
        expense: result,
        message: 'Ausgabe hinzugefügt'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/expenses/trends', async (req, res) => {
    try {
      const months = parseInt(req.query.months) || 6;
      const trend = expenseRadar?.getTrendAnalysis?.(months);
      const history = expenseRadar?.getMonthlyHistory?.(months);
      
      res.json({
        ok: true,
        trend,
        history
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/expenses/anomalies', async (req, res) => {
    try {
      const anomalies = expenseRadar?.detectAnomalies?.() || [];
      
      res.json({
        ok: true,
        anomalies
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/expenses/savings', async (req, res) => {
    try {
      const opportunities = expenseRadar?.identifySavingsOpportunities?.() || [];
      
      res.json({
        ok: true,
        opportunities
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/expenses/budgets', async (req, res) => {
    try {
      const { category, amount, period } = req.body || {};
      const budget = expenseRadar?.setBudget?.(category, amount, period);
      
      res.json({
        ok: true,
        budget,
        message: 'Budget gesetzt'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── DEMO OUTPUT ─────────────────────────────────────────────────────

  router.get('/demo/decisions', async (req, res) => {
    try {
      const decisions = demoOutput?.decisions || [];
      
      res.json({
        ok: true,
        decisions
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/demo/decisions', async (req, res) => {
    try {
      const { subscription, decision, context } = req.body || {};
      const formattedDecision = demoOutput?.formatDecision?.(subscription, decision, context);
      
      res.json({
        ok: true,
        decision: formattedDecision,
        message: 'Entscheidung formatiert'
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/demo/summary', async (req, res) => {
    try {
      const timeframe = req.query.timeframe || 'current';
      const decisions = demoOutput?.decisions || [];
      const summary = demoOutput?.generateSummary?.(decisions, timeframe);
      
      res.json({
        ok: true,
        summary
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/demo/actions', async (req, res) => {
    try {
      const decisions = demoOutput?.decisions || [];
      const actionItems = demoOutput?.createActionItems?.(decisions);
      const progress = demoOutput?.getProgressReport?.();
      
      res.json({
        ok: true,
        actionItems,
        progress
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/demo/export/json', async (req, res) => {
    try {
      const exportData = demoOutput?.exportToJson?.() || {};
      
      res.json({
        ok: true,
        export: exportData
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/demo/export/markdown', async (req, res) => {
    try {
      const markdown = demoOutput?.exportToMarkdown?.() || '';
      
      res.setHeader('Content-Type', 'text/markdown');
      res.setHeader('Content-Disposition', 'attachment; filename=abo-optimizer-report.md');
      res.send(markdown);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  return router;
}

module.exports = { createDashboardRoutes };
