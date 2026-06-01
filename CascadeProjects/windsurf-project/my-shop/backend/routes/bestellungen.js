import { Router } from 'express';
import bestellungController from '../controllers/bestellungen.js';

const router = Router();

router.get('/', (req, res) => bestellungController.alleBestellungen(req, res));
router.get('/statistiken', (req, res) => bestellungController.statistiken(req, res));
router.get('/:id', (req, res) => bestellungController.bestellungDetails(req, res));
router.post('/', (req, res) => bestellungController.bestellungErstellen(req, res));
router.patch('/:id/status', (req, res) => bestellungController.statusAendern(req, res));

export default router;
