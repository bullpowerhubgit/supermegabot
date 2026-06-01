/**
 * Produkt Controller
 * Verwaltet Produktdaten aus dem E-Commerce System
 */

class ProduktController {
  constructor() {
    this.produkte = [];
    this.ladeDummyDaten();
  }

  ladeDummyDaten() {
    this.produkte = [
      { id: 'p1', name: 'Premium T-Shirt', preis: 29.99, lager: 150, kategorie: 'Fashion', status: 'aktiv' },
      { id: 'p2', name: 'Designer Hoodie', preis: 59.99, lager: 80, kategorie: 'Fashion', status: 'aktiv' },
      { id: 'p3', name: 'Sport Cap', preis: 19.99, lager: 200, kategorie: 'Accessoires', status: 'aktiv' },
      { id: 'p4', name: 'Laptop Sticker Set', preis: 9.99, lager: 500, kategorie: 'Accessoires', status: 'aktiv' },
      { id: 'p5', name: 'Phone Case Pro', preis: 24.99, lager: 0, kategorie: 'Tech', status: 'ausverkauft' }
    ];
  }

  async alleProdukte(req, res) {
    const { kategorie, status, suche } = req.query;
    let ergebnis = [...this.produkte];

    if (kategorie) {
      ergebnis = ergebnis.filter(p => p.kategorie.toLowerCase() === kategorie.toLowerCase());
    }
    if (status) {
      ergebnis = ergebnis.filter(p => p.status === status);
    }
    if (suche) {
      const q = suche.toLowerCase();
      ergebnis = ergebnis.filter(p => p.name.toLowerCase().includes(q));
    }

    res.json({
      erfolg: true,
      anzahl: ergebnis.length,
      produkte: ergebnis
    });
  }

  async produktDetails(req, res) {
    const { id } = req.params;
    const produkt = this.produkte.find(p => p.id === id);
    if (!produkt) {
      return res.status(404).json({ erfolg: false, fehler: 'Produkt nicht gefunden' });
    }
    res.json({ erfolg: true, produkt });
  }

  async produktErstellen(req, res) {
    const { name, preis, lager, kategorie } = req.body;
    const neuesProdukt = {
      id: `p${Date.now()}`,
      name,
      preis: parseFloat(preis),
      lager: parseInt(lager),
      kategorie: kategorie || 'Sonstiges',
      status: 'aktiv',
      erstelltAm: new Date().toISOString()
    };
    this.produkte.push(neuesProdukt);
    res.status(201).json({ erfolg: true, produkt: neuesProdukt });
  }

  async produktAktualisieren(req, res) {
    const { id } = req.params;
    const index = this.produkte.findIndex(p => p.id === id);
    if (index === -1) {
      return res.status(404).json({ erfolg: false, fehler: 'Produkt nicht gefunden' });
    }
    this.produkte[index] = { ...this.produkte[index], ...req.body };
    res.json({ erfolg: true, produkt: this.produkte[index] });
  }

  async produktLoeschen(req, res) {
    const { id } = req.params;
    const index = this.produkte.findIndex(p => p.id === id);
    if (index === -1) {
      return res.status(404).json({ erfolg: false, fehler: 'Produkt nicht gefunden' });
    }
    this.produkte.splice(index, 1);
    res.json({ erfolg: true, nachricht: 'Produkt geloescht' });
  }

  async kategorien(req, res) {
    const kategorien = [...new Set(this.produkte.map(p => p.kategorie))];
    res.json({ erfolg: true, kategorien });
  }
}

export default new ProduktController();
