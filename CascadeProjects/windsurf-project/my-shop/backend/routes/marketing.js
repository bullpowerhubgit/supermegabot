import { Router } from 'express';
import marketingController from '../controllers/marketing.js';

const router = Router();

router.get('/', (req, res) => marketingController.alleKampagnen(req, res));
router.get('/performance', (req, res) => marketingController.performance(req, res));
router.post('/', (req, res) => marketingController.kampagneErstellen(req, res));
router.put('/:id', (req, res) => marketingController.kampagneAktualisieren(req, res));

export default router;
