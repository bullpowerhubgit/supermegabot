/**
 * Bestellung Controller
 * Verwaltet Bestellungen aus dem E-Commerce System
 */

class BestellungController {
  constructor() {
    this.bestellungen = [];
    this.ladeDummyDaten();
  }

  ladeDummyDaten() {
    this.bestellungen = [
      {
        id: 'b1001',
        kunde: 'Max Mustermann',
        email: 'max@example.com',
        produkte: [
          { produktId: 'p1', name: 'Premium T-Shirt', menge: 2, preis: 29.99 }
        ],
        gesamtbetrag: 59.98,
        status: 'versendet',
        erstelltAm: '2026-05-28T10:00:00Z'
      },
      {
        id: 'b1002',
        kunde: 'Anna Schmidt',
        email: 'anna@example.com',
        produkte: [
          { produktId: 'p2', name: 'Designer Hoodie', menge: 1, preis: 59.99 }
        ],
        gesamtbetrag: 59.99,
        status: 'bearbeitung',
        erstelltAm: '2026-05-29T14:30:00Z'
      },
      {
        id: 'b1003',
        kunde: 'Lisa Mueller',
        email: 'lisa@example.com',
        produkte: [
          { produktId: 'p1', name: 'Premium T-Shirt', menge: 1, preis: 29.99 },
          { produktId: 'p3', name: 'Sport Cap', menge: 2, preis: 19.99 }
        ],
        gesamtbetrag: 69.97,
        status: 'bezahlt',
        erstelltAm: '2026-05-30T08:15:00Z'
      }
    ];
  }

  async alleBestellungen(req, res) {
    const { status, von, bis } = req.query;
    let ergebnis = [...this.bestellungen];

    if (status) {
      ergebnis = ergebnis.filter(b => b.status === status);
    }
    if (von) {
      ergebnis = ergebnis.filter(b => new Date(b.erstelltAm) >= new Date(von));
    }
    if (bis) {
      ergebnis = ergebnis.filter(b => new Date(b.erstelltAm) <= new Date(bis));
    }

    ergebnis.sort((a, b) => new Date(b.erstelltAm) - new Date(a.erstelltAm));

    res.json({
      erfolg: true,
      anzahl: ergebnis.length,
      gesamtUmsatz: ergebnis.reduce((sum, b) => sum + b.gesamtbetrag, 0),
      bestellungen: ergebnis
    });
  }

  async bestellungDetails(req, res) {
    const { id } = req.params;
    const bestellung = this.bestellungen.find(b => b.id === id);
    if (!bestellung) {
      return res.status(404).json({ erfolg: false, fehler: 'Bestellung nicht gefunden' });
    }
    res.json({ erfolg: true, bestellung });
  }

  async bestellungErstellen(req, res) {
    const { kunde, email, produkte } = req.body;
    const gesamtbetrag = produkte.reduce((sum, p) => sum + (p.preis * p.menge), 0);

    const neueBestellung = {
      id: `b${Date.now()}`,
      kunde,
      email,
      produkte,
      gesamtbetrag,
      status: 'bezahlt',
      erstelltAm: new Date().toISOString()
    };

    this.bestellungen.push(neueBestellung);
    res.status(201).json({ erfolg: true, bestellung: neueBestellung });
  }

  async statusAendern(req, res) {
    const { id } = req.params;
    const { status } = req.body;
    const index = this.bestellungen.findIndex(b => b.id === id);

    if (index === -1) {
      return res.status(404).json({ erfolg: false, fehler: 'Bestellung nicht gefunden' });
    }

    this.bestellungen[index].status = status;
    res.json({ erfolg: true, bestellung: this.bestellungen[index] });
  }

  async statistiken(req, res) {
    const heute = new Date().toISOString().split('T')[0];
    const heuteBestellungen = this.bestellungen.filter(b => b.erstelltAm.startsWith(heute));

    const stats = {
      gesamtBestellungen: this.bestellungen.length,
      heuteBestellungen: heuteBestellungen.length,
      gesamtUmsatz: this.bestellungen.reduce((s, b) => s + b.gesamtbetrag, 0),
      heuteUmsatz: heuteBestellungen.reduce((s, b) => s + b.gesamtbetrag, 0),
      statusVerteilung: {
        bezahlt: this.bestellungen.filter(b => b.status === 'bezahlt').length,
        bearbeitung: this.bestellungen.filter(b => b.status === 'bearbeitung').length,
        versendet: this.bestellungen.filter(b => b.status === 'versendet').length
      }
    };

    res.json({ erfolg: true, statistiken: stats });
  }
}

export default new BestellungController();
