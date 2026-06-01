/**
 * Analytics Controller
 * SEO und Verkaufsanalysen mit GA4 Integration
 */

import { AnalyticsService } from '../../../services/analytics-service-fixed.js';

class AnalyticsController {
  constructor() {
    this.analyticsService = new AnalyticsService();
  }

  async dashboard(req, res) {
    try {
      const heute = new Date();
      const daten = {
        umsatz: {
          heute: 245.50,
          gestern: 189.99,
          dieseWoche: 1450.00,
          letzteWoche: 1200.00
        },
        besucher: {
          heute: 342,
          gestern: 289,
          unique: 156
        },
        konversion: {
          rate: '3.2%',
          durchschnittlicherWarenkorb: 48.50
        },
        seo: {
          keywordsTop10: 12,
          keywordsTop50: 45,
          organischerTraffic: 89,
          backlinksNeu: 5
        },
        topProdukte: [
          { name: 'Premium T-Shirt', verkauft: 45, umsatz: 1349.55 },
          { name: 'Designer Hoodie', verkauft: 22, umsatz: 1319.78 },
          { name: 'Sport Cap', verkauft: 38, umsatz: 759.62 }
        ],
        trafficQuellen: [
          { quelle: 'Organisch', anteil: 35 },
          { quelle: 'Social Media', anteil: 28 },
          { quelle: 'Bezahlte Werbung', anteil: 22 },
          { quelle: 'Direkt', anteil: 15 }
        ]
      };

      // Track dashboard view event
      await this.analyticsService.trackEvent('dashboard_view', {
        user_id: req.user?.id || 'anonymous',
        timestamp: new Date().toISOString()
      });

      res.json({ erfolg: true, dashboard: daten });
    } catch (error) {
      console.error('Dashboard analytics error:', error);
      res.status(500).json({ 
        erfolg: false, 
        fehler: 'Analytics-Daten konnten nicht geladen werden' 
      });
    }
  }

  async seoUebersicht(req, res) {
    try {
      // Track SEO overview access
      await this.analyticsService.trackEvent('seo_overview_access', {
        user_id: req.user?.id || 'anonymous',
        timestamp: new Date().toISOString()
      });

      res.json({
        erfolg: true,
        seo: {
          rankingKeywords: [
            { keyword: 'premium tshirt', position: 3, volumen: 1200 },
            { keyword: 'designer hoodie', position: 8, volumen: 800 },
            { keyword: 'streetwear shop', position: 12, volumen: 2500 }
          ],
          technischeSEO: {
            ladezeit: '1.2s',
            mobileScore: 95,
            coreWebVitals: 'gut'
          }
        }
      });
    } catch (error) {
      console.error('SEO overview analytics error:', error);
      res.status(500).json({ 
        erfolg: false, 
        fehler: 'SEO-Daten konnten nicht geladen werden' 
      });
    }
  }

  async umsatzTrend(req, res) {
    try {
      const { zeitraum = '7d' } = req.query;
      
      // Track revenue trend access
      await this.analyticsService.trackEvent('revenue_trend_access', {
        user_id: req.user?.id || 'anonymous',
        zeitraum,
        timestamp: new Date().toISOString()
      });

      res.json({
        erfolg: true,
        zeitraum,
        trend: [
          { datum: '2026-05-24', umsatz: 189.99 },
          { datum: '2026-05-25', umsatz: 210.50 },
          { datum: '2026-05-26', umsatz: 175.00 },
          { datum: '2026-05-27', umsatz: 245.00 },
          { datum: '2026-05-28', umsatz: 198.50 },
          { datum: '2026-05-29', umsatz: 267.00 },
          { datum: '2026-05-30', umsatz: 245.50 }
        ]
      });
    } catch (error) {
      console.error('Revenue trend analytics error:', error);
      res.status(500).json({ 
        erfolg: false, 
        fehler: 'Umsatz-Trend konnte nicht geladen werden' 
      });
    }
  }

  async trackPurchase(req, res) {
    try {
      const purchaseData = req.body;
      
      // Track purchase event with proper queue handling
      const result = await this.analyticsService.trackPurchase(purchaseData);
      
      if (result.queued) {
        res.json({
          erfolg: true,
          status: 'queued',
          eventId: result.eventId,
          nachricht: 'Bestellung wurde zur Verarbeitung in die Warteschlange gestellt'
        });
      } else if (result.success) {
        res.json({
          erfolg: true,
          status: 'tracked',
          eventId: result.eventId,
          nachricht: 'Bestellung wurde erfolgreich erfasst'
        });
      } else {
        res.status(500).json({
          erfolg: false,
          fehler: result.error || 'Bestellung konnte nicht erfasst werden'
        });
      }
    } catch (error) {
      console.error('Purchase tracking error:', error);
      res.status(500).json({ 
        erfolg: false, 
        fehler: 'Bestellung konnte nicht verarbeitet werden' 
      });
    }
  }

  async trackEvent(req, res) {
    try {
      const { eventName, params } = req.body;
      
      // Track custom event with proper queue handling
      const result = await this.analyticsService.trackEvent(eventName, params);
      
      if (result.queued) {
        res.json({
          erfolg: true,
          status: 'queued',
          eventId: result.eventId,
          nachricht: 'Ereignis wurde zur Verarbeitung in die Warteschlange gestellt'
        });
      } else if (result.success) {
        res.json({
          erfolg: true,
          status: 'tracked',
          eventId: result.eventId,
          nachricht: 'Ereignis wurde erfolgreich erfasst'
        });
      } else {
        res.status(500).json({
          erfolg: false,
          fehler: result.error || 'Ereignis konnte nicht erfasst werden'
        });
      }
    } catch (error) {
      console.error('Event tracking error:', error);
      res.status(500).json({ 
        erfolg: false, 
        fehler: 'Ereignis konnte nicht verarbeitet werden' 
      });
    }
  }

  async getQueueStatus(req, res) {
    try {
      const queueStatus = this.analyticsService.getQueueStatus();
      
      res.json({
        erfolg: true,
        queue: queueStatus
      });
    } catch (error) {
      console.error('Queue status error:', error);
      res.status(500).json({ 
        erfolg: false, 
        fehler: 'Warteschlangen-Status konnte nicht abgerufen werden' 
      });
    }
  }
}

export default new AnalyticsController();
