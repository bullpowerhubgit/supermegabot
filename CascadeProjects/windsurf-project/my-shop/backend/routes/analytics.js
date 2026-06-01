import { Router } from 'express';
import analyticsController from '../controllers/analytics.js';

const router = Router();

// GET routes
router.get('/dashboard', (req, res) => analyticsController.dashboard(req, res));
router.get('/seo', (req, res) => analyticsController.seoUebersicht(req, res));
router.get('/umsatz', (req, res) => analyticsController.umsatzTrend(req, res));
router.get('/queue/status', (req, res) => analyticsController.getQueueStatus(req, res));

// POST routes for tracking
router.post('/track/purchase', (req, res) => analyticsController.trackPurchase(req, res));
router.post('/track/event', (req, res) => analyticsController.trackEvent(req, res));

export default router;
