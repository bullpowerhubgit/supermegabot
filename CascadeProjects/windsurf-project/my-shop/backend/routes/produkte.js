import { Router } from 'express';
import produktController from '../controllers/produkte.js';

const router = Router();

router.get('/', (req, res) => produktController.alleProdukte(req, res));
router.get('/kategorien', (req, res) => produktController.kategorien(req, res));
router.get('/:id', (req, res) => produktController.produktDetails(req, res));
router.post('/', (req, res) => produktController.produktErstellen(req, res));
router.put('/:id', (req, res) => produktController.produktAktualisieren(req, res));
router.delete('/:id', (req, res) => produktController.produktLoeschen(req, res));

export default router;
