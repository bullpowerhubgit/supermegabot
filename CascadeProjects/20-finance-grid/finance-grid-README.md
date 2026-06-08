# 💰 RUDIBOT FINANCE GRID

**Autonomous Finance & Administration Operating System**

Ein autonomes Verwaltungs- und Finanzbetriebssystem, das samtliche Kontozugange, E-Mail-Postfacher, Abos, Vertrage, Einnahmen, Ausgaben und Steuerdaten in einer zentralen Kommandoschicht zusammenfuhrt.

---

## System Overview

Rudibot Finance Grid ist ein orbitales Kontrollsystem, das alle deine Konten, E-Mails, Abos, Vertrage, Einnahmen, Ausgaben und Steuerthemen unter eine einzige Kommandoschicht zwingt – mit Rudibot als Operator.

---

## Modules

### 🔐 identity-vault
Sicherer Speicher fur ELSTER-Zertifikate, Portal-Logins, API-Keys und Bank-Zugange. Zugriff nur uber Rudibot-Commands mit starker Authentifizierung.

**Features:**
- AES-256-GCM Verschlusselung
- Portal Access Management
- Bank Access Storage
- API Key Vault
- ELSTER Access Storage

### 📧 mail-command
Listener & Parser fur E-Mail-Konten, inkl. Filterregeln fur Rechnungen, Transaktionen, Abo-Updates und Vertragsmails.

### 🎯 subscription-hunter
Engine, die automatisch Abos findet, Preise trackt, Renewal-Daten speichert und Kundigungen vorbereitet oder semi-automatisch auslost.

**Features:**
- Email-based Detection
- Transaction-based Detection
- Provider Registry (8 default providers)
- Renewal Tracking
- Kill Preparation
- Monthly Cost Calculation

### 💰 expense-radar
Zentrales Register fur alle Einnahmen und Ausgaben, konsolidiert aus Mails, CSV-Exports oder APIs, inkl. intelligenter Analyse.

**Features:**
- Auto-Categorization (17 categories)
- German Tax Categories (EStG/UStG)
- Monthly Summaries
- Tax Relevant Expense Tracking
- Anomaly Detection
- CSV Export

### 📋 tax-core
Mapping deiner Kategorien auf deutsche Steuerlogik, Organisation von Belegen und Berechnungen fur USt, ESt, ggf. Gewerbe – mit Export-Schnittstellen in ELSTER-kompatible Formate.

**Features:**
- Income Tax Calculation (German EStG)
- VAT Calculation (UStG)
- ELSTER JSON Export
- CSV Tax Export
- Document Management
- Year Summary

### ⚖️ compliance-engine
Fristenuberwachung: Steuertermine, Zahlungstermine, Vertragsende, Verlangerungen, Mahnrisiken. Warnings, wenn Daten fehlen.

**Features:**
- Tax Deadline Tracking
- Compliance Rules Engine
- Overdue Detection
- Priority Calculation
- Status Monitoring

### 🗡️ cancellation-engine
Regelgesteuertes Kundigungssystem, das Vertrage erkennt, Fristen berechnet, den optimalen Kundigungskanal auswahlt und Kundigungen mit Nachweis, Audit-Log und Bestatigungspfad ausfuhrt.

**Features:**
- Provider Registry
- Eligibility Engine
- Execution Engine (Web, Email, API, Manual Letter)
- Audit Logging
- Status Machine

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/fin-grid` | Finance Grid Overview |
| `/subs` | Subscriptions & Contracts |
| `/sub-kill` | Cancel Subscription |
| `/tax` | Tax Status |
| `/spend` | Expense Radar |
| `/elster` | ELSTER Export |

---

## Architecture

```bash
20-finance-grid/
├── identity-vault/
│   └── index.js              # Secure credential storage
├── mail-command/
│   └── (planned)             # Email parsing & routing
├── subscription-hunter/
│   └── index.js              # Subscription detection & mgmt
├── expense-radar/
│   └── index.js              # Income & expense tracking
├── tax-core/
│   └── index.js              # Tax calculation & export
├── compliance-engine/
│   └── index.js              # Deadline & compliance monitoring
├── cancellation-engine/
│   ├── src/
│   │   ├── config/
│   │   │   └── providers.js  # Provider definitions
│   │   ├── core/
│   │   │   ├── eligibility-engine.js
│   │   │   ├── execution-engine.js
│   │   │   ├── audit-log.js
│   │   │   └── status-machine.js
│   │   ├── channels/
│   │   │   ├── cancel-by-email.js
│   │   │   ├── cancel-by-api.js
│   │   │   ├── cancel-by-web.js
│   │   │   └── create-manual-letter.js
│   │   ├── templates/
│   │   │   └── cancellation-email-template.js
│   │   ├── utils/
│   │   │   ├── date-utils.js
│   │   │   └── validation-utils.js
│   │   └── index.js
│   └── package.json
└── finance-grid-README.md
```

---

## Integration

Finance Grid ist in Rudibot integriert:

```javascript
// bot.js imports
const { SubscriptionHunter } = require('../20-finance-grid/subscription-hunter');
const { ExpenseRadar } = require('../20-finance-grid/expense-radar');
const { TaxCore } = require('../20-finance-grid/tax-core');
const { ComplianceEngine } = require('../20-finance-grid/compliance-engine');
```

---

## Data Storage

All modules use JSON file storage by default:
- `subscriptions.json` — Subscription data
- `transactions.json` — Expense & income data
- `tax-data.json` — Tax documents & calculations
- `compliance-data.json` — Deadlines & compliance checks
- `logs/cancellation-audit.log` — Cancellation audit trail

---

## Startup

```bash
# Initialize all modules
cd /Users/rudolfsarkany/CascadeProjects/20-finance-grid

# Start Rudibot (includes Finance Grid)
cd /Users/rudolfsarkany/CascadeProjects/rudibot
node bot.js

# Use Telegram commands:
# /fin-grid — Overview
# /subs — Subscriptions
# /sub-kill — Cancel
# /tax — Tax status
# /spend — Expenses
# /elster — Export
```

---

**💰 RUDIBOT FINANCE GRID — Your Personal Finance & Administration OS**
