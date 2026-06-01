/**
 * Marketing Controller
 * Kampagnen und Werbemassnahmen verwalten
 */

class MarketingController {
  constructor() {
    this.kampagnen = [];
    this.ladeDummyDaten();
  }

  ladeDummyDaten() {
    this.kampagnen = [
      {
        id: 'm1',
        name: 'Sommer Sale 2026',
        plattform: 'Meta Ads',
        budget: 500,
        ausgaben: 245.50,
        impressions: 15420,
        clicks: 312,
        konversionen: 18,
        status: 'aktiv',
        erstelltAm: '2026-05-15T00:00:00Z'
      },
      {
        id: 'm2',
        name: 'Influencer Kollaboration',
        plattform: 'Instagram',
        budget: 1000,
        ausgaben: 500,
        impressions: 45000,
        clicks: 890,
        konversionen: 42,
        status: 'aktiv',
        erstelltAm: '2026-05-20T00:00:00Z'
      },
      {
        id: 'm3',
        name: 'Google Shopping Kampagne',
        plattform: 'Google Ads',
        budget: 300,
        ausgaben: 300,
        impressions: 8200,
        clicks: 156,
        konversionen: 8,
        status: 'beendet',
        erstelltAm: '2026-04-01T00:00:00Z'
      }
    ];
  }

  async alleKampagnen(req, res) {
    const { status, plattform } = req.query;
    let ergebnis = [...this.kampagnen];

    if (status) ergebnis = ergebnis.filter(k => k.status === status);
    if (plattform) ergebnis = ergebnis.filter(k => k.plattform === plattform);

    res.json({ erfolg: true, anzahl: ergebnis.length, kampagnen: ergebnis });
  }

  async kampagneErstellen(req, res) {
    const { name, plattform, budget } = req.body;
    const neueKampagne = {
      id: `m${Date.now()}`,
      name,
      plattform,
      budget: parseFloat(budget),
      ausgaben: 0,
      impressions: 0,
      clicks: 0,
      konversionen: 0,
      status: 'aktiv',
      erstelltAm: new Date().toISOString()
    };
    this.kampagnen.push(neueKampagne);
    res.status(201).json({ erfolg: true, kampagne: neueKampagne });
  }

  async kampagneAktualisieren(req, res) {
    const { id } = req.params;
    const index = this.kampagnen.findIndex(k => k.id === id);
    if (index === -1) {
      return res.status(404).json({ erfolg: false, fehler: 'Kampagne nicht gefunden' });
    }
    this.kampagnen[index] = { ...this.kampagnen[index], ...req.body };
    res.json({ erfolg: true, kampagne: this.kampagnen[index] });
  }

  async performance(req, res) {
    const gesamt = {
      budget: this.kampagnen.reduce((s, k) => s + k.budget, 0),
      ausgaben: this.kampagnen.reduce((s, k) => s + k.ausgaben, 0),
      impressions: this.kampagnen.reduce((s, k) => s + k.impressions, 0),
      clicks: this.kampagnen.reduce((s, k) => s + k.clicks, 0),
      konversionen: this.kampagnen.reduce((s, k) => s + k.konversionen, 0)
    };

    const roas = gesamt.ausgaben > 0 ? (gesamt.konversionen * 50 / gesamt.ausgaben).toFixed(2) : 0;

    res.json({
      erfolg: true,
      performance: {
        ...gesamt,
        ctr: gesamt.impressions > 0 ? ((gesamt.clicks / gesamt.impressions) * 100).toFixed(2) : 0,
        cvr: gesamt.clicks > 0 ? ((gesamt.konversionen / gesamt.clicks) * 100).toFixed(2) : 0,
        roas
      }
    });
  }
}

export default new MarketingController();
