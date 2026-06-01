import { Router } from 'express';
import systemController from '../controllers/system.js';

const router = Router();

router.get('/status', (req, res) => systemController.status(req, res));
router.get('/einstellungen', (req, res) => systemController.einstellungen(req, res));
router.get('/logs', (req, res) => systemController.logs(req, res));

export default router;
