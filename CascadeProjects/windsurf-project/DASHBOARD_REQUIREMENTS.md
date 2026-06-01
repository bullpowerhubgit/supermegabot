# Mega-Dashboard Requirements
## Ein zentrales Command Center statt 1.000 Mini-Dashboards

**Zielgruppe:** Management & Entwickler  
**Status:** Draft v1.0  
**Autor:** Code-CLI / SuperMegaBot Team  

---

## 1. Executive Summary (für Management)

Aktuell betreiben wir eine fragmentierte Landschaft aus Dutzenden einzelnen Teil-Dashboards, Skripten und Monitoring-Tools. Jede Komponente erfordert eigenes Setup, eigenen Wartungsaufwand und eigene Schulung. Das Ergebnis: Hohe Komplexität, schlechte Übersicht, versteckte Ausfälle.

**Dieses Dokument belegt:** Ein einziges, professionelles Mega-Dashboard mit klarer Struktur und starker Automatisierung ist deutlich wirkungsvoller als 1.000 verstreute Einzelansichten.

| Kennzahl | Aktueller Zustand | Zielzustand (Mega-Dashboard) |
|----------|-------------------|------------------------------|
| Dashboards im Einsatz | 15+ separate Tools | **1 zentrales Command Center** |
| Wartungsaufwand pro Woche | ~4-6h | **< 30 Minuten** |
| Time-to-Insight | Minuten bis Stunden | **< 5 Sekunden** |
| Automatisierungsgrad | Gering (manuelle Checks) | **Hoch (Self-Healing, Alerts)** |
| Onboarding neuer Teammitglieder | Tage | **Minuten** |

**Business Case:** Reduzierung der operativen Komplexitat, schnellere Fehlererkennung, niedrigere Betriebskosten, bessere Skalierbarkeit.

---

## 2. Problemstellung: Warum die aktuelle Fragmentierung scheitert

### 2.1 Die Fragmentierungsfalle

Unsere aktuelle Infrastruktur verteilt sich uber mehrere Dateien und Prozesse:

- `watchdog.js` – Memory-Monitoring
- `watchdog-monitor-server.js` – Watchdog-Status-Anzeige
- `mega-dashboard.js` – Teil-Dashboard A
- `shopify-dashboard.html` – Teil-Dashboard B
- `ultimate-ecommerce-dashboard.html` – Teil-Dashboard C
- `orchestrator-dashboard.js` – Teil-Dashboard D
- `bot-clones/security-bot.js` – Bot-Monitoring
- `bot-clones/performance-bot.js` – Performance-Monitoring
- ...und weitere Einzeldateien

**Konsequenzen:**
- **Kein Single Source of Truth:** Jeder Check liefert andere Werte
- **Multiplizierter Wartungsaufwand:** Bugfixes mussen an 10+ Stellen eingespielt werden
- **Ressourcenfressend:** Jeder Prozess belegt RAM und CPU
- **Keine zentrale Alerting-Logik:** Warnungen gehen verloren oder uberlappen sich
- **Schlechte Fehlerkorrelation:** Zusammenhange zwischen System-Load und Bot-Ausfallen sind nicht sichtbar

### 2.2 Die Kosten der Komplexitat

| Kostenfaktor | Schatzung |
|--------------|-----------|
| Zeit fur Kontextwechsel zwischen Tools | ~30 min/Tag pro Entwickler |
| Doppelte Implementierungen (Monitoring-Logik) | ~40% des Codes sind Redundanzen |
| Vergessene Checks bei neuen Features | RegelmaBig – fuhrt zu unentdeckten Ausfallen |
| Dokumentationsaufwand pro Tool | Exponentiell mit Anzahl der Tools |

---

## 3. Losung: Das Mega-Dashboard Konzept

### 3.1 Vision

**Ein zentrales Command Center** – professionell, klar strukturiert, automatisiert – das alle kritischen Systeme, Bots, Services und Kennzahlen in Echtzeit bündelt.

**Kernprinzipien:**
1. **One Source of Truth** – Alle Daten kommen aus einer verifizierten Quelle
2. **Self-Healing by Default** – Erkannte Probleme werden automatisch behoben
3. **Actions > Data** – Nicht nur anzeigen, sondern direkt handeln konnen
4. **Zero-Config Onboarding** – Nach Deployment sofort funktionsfahig
5. **Progressive Disclosure** – Management sieht KPIs, Devs sehen Details

### 3.2 Architektur-Prinzip

```
┌─────────────────────────────────────────┐
│         Mega Dashboard Server         │
│              (Port 3200)                │
├─────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌─────────┐│
│  │ System   │ │ Bot      │ │ Service ││
│  │ Monitor  │ │ Monitor  │ │ Monitor ││
│  │ (CPU/RAM)│ │ (Status) │ │ (launchd)│
│  └────┬─────┘ └────┬─────┘ └────┬────┘│
│       └─────────────┴────────────┘      │
│                Data Collection          │
├─────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌─────────┐│
│  │ Alert    │ │ Auto-    │ │ Action  ││
│  │ Engine   │ │ Repair   │ │ API     ││
│  │ (Rules)  │ │ (Scripts)│ │ (Start/ ││
│  │          │ │          │ │  Stop)  ││
│  └──────────┘ └──────────┘ └─────────┘│
├─────────────────────────────────────────┤
│         Professional Web UI           │
│  • Real-time Stats  • Action Buttons   │
│  • Tabbed Views     • Mobile Ready    │
│  • Dark Theme       • No CDN Deps     │
└─────────────────────────────────────────┘
```

---

## 4. Konkrete Anforderungen

### 4.1 Dashboard-Bereiche (Tabs)

| Tab | Zielgruppe | Inhalt | Auto-Refresh |
|-----|-----------|--------|-------------|
| **Overview** | Management | Health Score, KPI-Karten, Alerts | 5s |
| **System** | Devs/Ops | CPU, RAM, Disk, Prozesse, Uptime | 5s |
| **Services** | Devs/Ops | launchd Services, Status, Start/Stop | 5s |
| **Bots** | Devs | Bot-Status, Orchestrator, Logs | 5s |
| **Processes** | Devs | Top-Prozesse, Kill-Actions | 5s |

### 4.2 Kennzahlen-Karten (Overview-Tab)

**Vier Hauptkarten – immer sichtbar:**

1. **RAM Usage**
   - Wert: Prozent + absolut (z.B. "87% – 41.8 / 48 GB")
   - Farbcodierung: Grun (<75%), Gelb (75-90%), Rot (>90%)
   - Mini-Sparkline (letzte 60 Werte)
   - Freier Speicher als Subtext

2. **CPU Usage**
   - Wert: Prozent + Core-Anzahl
   - Farbcodierung: gleiche Logik
   - Mini-Sparkline
   - Load Average als Subtext

3. **Disk Usage**
   - Wert: Prozent
   - Farbcodierung: Grun (<70%), Gelb (70-85%), Rot (>85%)
   - Freier Platz als Subtext

4. **System Health Score**
   - Wert: 0-100 (berechnet aus allen Metriken)
   - Ring-Chart Visualisierung
   - Farbe: Grun (>80), Gelb (50-80), Rot (<50)
   - Uptime + aktive Services als Subtext

### 4.3 Alerting-System

**Automatische Erkennung:**
- RAM > 90% → Critical Alert + Auto-Cleanup
- CPU > 90% → Critical Alert
- Disk > 85% → Warning Alert
- Service gestoppt → Warning Alert + Auto-Restart
- Bot offline → Warning Alert

**Darstellung:**
- Rot bei Critical, Orange bei Warning
- Kompakte Liste ohne Klick-Wahnsinn
- "System OK"-Status wenn alles grun

### 4.4 Aktionen (Actions)

**Jeder Tab enthalt direkt ausfuhrbare Aktionen:**

| Aktion | Tab | Effekt |
|--------|-----|--------|
| Restart All Services | System | Alle launchd Services neu starten |
| Stop Service | Services | Einzelnen Service stoppen |
| Start Service | Services | Einzelnen Service starten |
| Restart Bots | Bots | Bot-Orchestrator neu starten |
| Run Cleanup | Sidebar | Speicher-Cleanup triggern |
| Kill Process | Processes | Prozess terminieren |
| Refresh Now | Uberall | Sofortiges Daten-Update |

**Regel:** Keine Aktion darf mehr als 1 Klick vom Dashboard entfernt sein.

### 4.5 Design-Vorgaben

**Professionelles Dark Theme:**
- Hintergrund: `#060b14` (tiefes Blau-Schwarz)
- Karten: `#0f172a` mit subtilem Border
- Akzent: Blau-Violett-Gradient (`#3b82f6` → `#8b5cf6`)
- Erfolg: `#10b981`, Warnung: `#f59e0b`, Fehler: `#ef4444`
- Font: System-Font-Stack (kein externes CDN)

**Layout:**
- Sticky Header mit Brand + Health Score + Live-Indikator
- Fixed Sidebar mit Navigation
- Tab-System statt endlosen Scroll-Seiten
- Responsive: 4-Spalten-Grid (Desktop), 2-Spalten (Tablet), 1-Spalte (Mobile)

**Keine externen Abhangigkeiten:**
- Kein FontAwesome CDN → Inline SVG Icons
- Kein Chart.js CDN → CSS/SVG Sparklines
- Kein Bootstrap CDN → Eigenes CSS
- Alles in einer Datei, keine 404-Risiken

---

## 5. Technische Architektur (für Entwickler)

### 5.1 Stack

| Komponente | Technologie | Begrundung |
|------------|-------------|------------|
| Backend | Node.js `http` Modul | Keine Dependencies, stabil |
| Datenquellen | `os`, `child_process` | Native, keine Latenz |
| UI | Inline HTML + CSS | Kein Build-Step, kein CDN-Risiko |
| Icons | Inline SVG | Skalierbar, kein Netzwerk-Request |
| Charts | SVG Sparklines | Leichtgewichtig, kein JS-Framework |
| Auto-Refresh | `meta refresh` + JS | Fallback fur alle Browser |

### 5.2 Datenfluss

```
Request ──→ Server ──┬─→ System Stats (os module, vm_stat)
                     ├─→ Bot Status (pgrep, launchctl)
                     ├─→ Service Status (launchctl list)
                     ├─→ Process List (ps)
                     └─→ Alerts (Rule Engine)
                              │
                              ▼
                        HTML Template (Inline)
                              │
                              ▼
                        Response (5s Cache)
```

**Performance-Ziele:**
- Page Load: < 200ms
- API Response: < 100ms
- Memory Footprint Server: < 50 MB
- Keine Datenbank notig

### 5.3 Deployment

**Als launchd Service:**
- Label: `com.supermegabot.mega-dashboard`
- Port: 3200
- KeepAlive: Bei Crash automatischer Neustart
- RunAtLoad: Startet mit dem System
- Log: `/tmp/mega-dashboard.log`

**Dateien:**
- `mega-dashboard-server.js` – Einzeldatei-Server
- `com.supermegabot.mega-dashboard.plist` – launchd Config

---

## 6. Akzeptanzkriterien

### 6.1 Funktional

- [ ] Dashboard erreichbar auf `http://localhost:3200`
- [ ] Auto-Refresh alle 5 Sekunden
- [ ] RAM, CPU, Disk in Echtzeit sichtbar
- [ ] Alle launchd Services mit Status
- [ ] Alle Bots mit Status
- [ ] Alerts bei kritischen Zustanden
- [ ] Health Score berechnet und angezeigt
- [ ] Aktionen direkt aus dem Dashboard ausfuhrbar

### 6.2 Design

- [ ] Dark Theme, professionell
- [ ] Keine externen CDN-Abhangigkeiten
- [ ] Responsive Layout
- [ ] Tab-Navigation statt Scroll-Monster
- [ ] Farbcodierte Status (Grun/Gelb/Rot)
- [ ] Inline SVG Icons

### 6.3 Automatisierung

- [ ] Self-Healing: Services starten automatisch neu
- [ ] Auto-Cleanup bei RAM > 90%
- [ ] Alert-Erkennung ohne manuelle Checks
- [ ] launchd KeepAlive fur permanenter Betrieb

---

## 7. Abgrenzung: Was das Dashboard NICHT macht

**Out of Scope (bewusst weggelassen):**
- Historische Daten (nur Echtzeit, kein Langzeit-Archiv)
- User-Authentifizierung (lokaler Zugriff)
- Multi-System-Monitoring (nur lokaler Mac)
- Business-Intelligence (keine Umsatz-KPIs)
- Mobile App (nur responsive Web)

**Grund:** Fokus auf technische System-Uberwachung und Betrieb. Wenn BI oder Auth gebraucht wird, separater Service.

---

## 8. Vergleich: Vorher vs. Nachher

### Vorher (Fragmentiert)
```
watchdog.js                 – Memory Check
watchdog-monitor.html       – Watchdog UI (Port 3456)
mega-dashboard.js           – Teil-Dashboard
shopify-dashboard.html      – Shopify-Only
ultimate-ecommerce-...      – Ecommerce-Only
orchestrator-dashboard.js   – Orchestrator-Only
monitor-bot.js              – Bot-Monitoring
security-bot.js             – Security-Checks
performance-bot.js          – Performance-Checks
... 15+ Dateien
```

### Nachher (Zentral)
```
mega-dashboard-server.js    – Ein Server, alles drin
watchdog.js                 – Watchdog bleibt (Hintergrund)
```

**Reduktion:** 15+ Dateien → 2 Dateien.  
**Wartung:** ~80% weniger Code-Pfade.

---

## 9. Zusammenfassung

**Die These:** Ein professionelles, zentralisiertes Dashboard mit Echtzeit-Monitoring, automatischer Fehlerbehebung und direkten Aktionen ist deutlich effektiver als eine zersplitterte Sammlung von Mini-Tools.

**Das Ergebnis:**
- Management sieht sofort den System-Health-Score
- Entwickler sehen Details und konnen direkt handeln
- Kein Kontextwechsel zwischen Tools
- Keine verlorenen Checks oder Warnungen
- Nachhaltig wartbar und skalierbar

**Next Steps:**
1. Implementierung des Mega-Dashboards (eine Datei, ein Port)
2. Migration der launchd Services auf das neue Dashboard
3. Deaktivierung der alten Teil-Dashboards
4. Dokumentation im Team verteilen

---

*Dieses Dokument wurde mit dem Code-CLI erstellt. Die Architektur ist bewusst simpel gehalten – keine uberflussigen Abhangigkeiten, keine verteilten Microservices, sondern ein robustes Monolith, das seinen Job erledigt.*
