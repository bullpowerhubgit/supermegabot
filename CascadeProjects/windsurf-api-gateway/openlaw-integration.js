#!/usr/bin/env node

// ⚖️ OPENLAW INTEGRATION - Vollautonom
// Rechtliche Dokumente, Verträge, Compliance
// ============================================================

const axios = require('axios');

// ⚖️ OpenLaw Konfiguration
const OPENLAW_CONFIG = {
    apiUrl: process.env.OPENLAW_API_URL || 'https://app.openlaw.io',
    apiKey: process.env.OPENLAW_API_KEY || '',
    templateLibrary: 'default',
    timeout: 30000
};

// 📋 Rechtliche Dokument-Templates
const LEGAL_TEMPLATES = {
    'privacy-policy': {
        name: 'Datenschutzerklärung (DSGVO)',
        description: 'DSGVO-konforme Datenschutzerklärung',
        category: 'privacy',
        requiredVars: ['companyName', 'website', 'email', 'address'],
        jurisdictions: ['EU', 'DE', 'AT', 'CH']
    },
    'terms-of-service': {
        name: 'Nutzungsbedingungen',
        description: 'Allgemeine Geschäftsbedingungen für SaaS',
        category: 'terms',
        requiredVars: ['companyName', 'website', 'serviceName', 'jurisdiction'],
        jurisdictions: ['EU', 'DE', 'US']
    },
    'imprint': {
        name: 'Impressum',
        description: 'Deutsches Impressum (TMG)',
        category: 'compliance',
        requiredVars: ['companyName', 'address', 'email', 'phone', 'vatId', 'ceo'],
        jurisdictions: ['DE', 'AT']
    },
    'cookie-policy': {
        name: 'Cookie-Richtlinie',
        description: 'Cookie-Hinweis und Opt-Out',
        category: 'privacy',
        requiredVars: ['companyName', 'website', 'contactEmail'],
        jurisdictions: ['EU']
    },
    'data-processing-agreement': {
        name: 'Auftragsverarbeitungsvertrag (AVV)',
        description: 'DPA für DSGVO-konforme Datenverarbeitung',
        category: 'privacy',
        requiredVars: ['processorName', 'controllerName', 'serviceDescription', 'duration'],
        jurisdictions: ['EU', 'DE']
    },
    'software-license': {
        name: 'Software-Lizenzvertrag',
        description: 'EULA für Software-Produkte',
        category: 'license',
        requiredVars: ['companyName', 'productName', 'licenseType', 'jurisdiction'],
        jurisdictions: ['EU', 'DE', 'US']
    },
    'consulting-agreement': {
        name: 'Beratungsvertrag',
        description: 'Dienstleistungsvertrag für Consulting',
        category: 'business',
        requiredVars: ['consultantName', 'clientName', 'serviceScope', 'fee', 'duration'],
        jurisdictions: ['EU', 'DE']
    },
    'nda': {
        name: 'Geheimhaltungsvereinbarung (NDA)',
        description: 'Vertraulichkeitsvereinbarung',
        category: 'business',
        requiredVars: ['partyA', 'partyB', 'purpose', 'duration'],
        jurisdictions: ['EU', 'DE', 'US', 'CH']
    },
    'employment-contract': {
        name: 'Arbeitsvertrag',
        description: 'Standard Arbeitsvertrag',
        category: 'employment',
        requiredVars: ['employer', 'employee', 'position', 'salary', 'startDate'],
        jurisdictions: ['DE', 'AT', 'CH']
    },
    'freelance-contract': {
        name: 'Freelancer-Vertrag',
        description: 'Vertrag für Freelancer und Selbstständige',
        category: 'employment',
        requiredVars: ['client', 'freelancer', 'projectScope', 'payment', 'deadline'],
        jurisdictions: ['DE', 'AT', 'CH', 'EU']
    }
};

// ⚖️ Compliance-Checker
const COMPLIANCE_RULES = {
    'GDPR': {
        name: 'DSGVO (GDPR)',
        requirements: [
            'Rechtsgrundlage für Datenverarbeitung',
            'Datenschutzerklärung vorhanden',
            'Cookie-Hinweis implementiert',
            'Löschfunktion vorhanden',
            'Datenportabilität möglich',
            'DSB registriert (wenn >9 Mitarbeiter)'
        ],
        fines: 'Bis zu 20 Mio. EUR oder 4% des weltweiten Jahresumsatzes'
    },
    'Imprint': {
        name: 'Impressumspflicht (TMG)',
        requirements: [
            'Firmenname/Name',
            'Anschrift',
            'Kontaktdaten (Email, Telefon)',
            'USt-IdNr. (falls vorhanden)',
            'Geschäftsführer',
            'Handelsregister (falls vorhanden)'
        ],
        fines: 'Abmahnungen ab 500-1.500 EUR'
    },
    'eCommerce': {
        name: 'E-Commerce Recht',
        requirements: [
            'Widerrufsbelehrung',
            'AGB',
            'Preisangaben (Endpreis)',
            'Versandkosten',
            'Zahlungsarten',
            'Lieferzeiten'
        ],
        fines: 'Ordnungsgeld bis 50.000 EUR'
    },
    'Cookie': {
        name: 'Cookie-Richtlinie (ePrivacy)',
        requirements: [
            'Cookie-Banner vorhanden',
            'Opt-In für nicht-essentielle Cookies',
            'Kategorisierung der Cookies',
            'Widerrufsmöglichkeit',
            'Cookie-Richtlinie verlinkt'
        ],
        fines: 'Bis zu 300.000 EUR'
    }
};

// ⚖️ Autonome OpenLaw Klasse
class AutonomousOpenLaw {
    constructor() {
        this.config = OPENLAW_CONFIG;
        this.templates = LEGAL_TEMPLATES;
        this.compliance = COMPLIANCE_RULES;
        this.generatedDocuments = [];
        this.initialize();
    }

    initialize() {
        console.log('⚖️ AUTONOMOUS OPENLAW SYSTEM INITIALIZED');
        console.log('='.repeat(60));
        console.log(`📋 Templates: ${Object.keys(this.templates).length}`);
        console.log(`🔍 Compliance Rules: ${Object.keys(this.compliance).length}`);
        console.log('');
    }

    // 📋 Dokument generieren
    async generateDocument(templateKey, variables = {}) {
        const template = this.templates[templateKey];
        if (!template) {
            throw new Error(`Template '${templateKey}' not found`);
        }

        console.log(`📄 Generating: ${template.name}`);

        // Prüfe erforderliche Variablen
        const missingVars = template.requiredVars.filter(v => !variables[v]);
        if (missingVars.length > 0) {
            throw new Error(`Missing variables: ${missingVars.join(', ')}`);
        }

        // Generiere Dokument (lokal, ohne API)
        const document = this.fillTemplate(template, variables);
        
        // Speichere in History
        this.generatedDocuments.push({
            template: templateKey,
            name: template.name,
            generated: new Date().toISOString(),
            variables: Object.keys(variables)
        });

        console.log(`✅ Document generated: ${template.name}`);
        
        return {
            title: template.name,
            content: document,
            template: templateKey,
            category: template.category,
            jurisdiction: template.jurisdictions,
            variables: variables,
            generated: new Date().toISOString()
        };
    }

    // 📝 Template ausfüllen
    fillTemplate(template, vars) {
        const templates = {
            'privacy-policy': this.generatePrivacyPolicy(vars),
            'terms-of-service': this.generateTermsOfService(vars),
            'imprint': this.generateImprint(vars),
            'cookie-policy': this.generateCookiePolicy(vars),
            'nda': this.generateNDA(vars)
        };

        return templates[Object.keys(this.templates).find(k => this.templates[k] === template)] || 
               this.generateGenericDocument(template, vars);
    }

    // 🔒 Datenschutzerklärung
    generatePrivacyPolicy(vars) {
        return `# Datenschutzerklärung

**Firma:** ${vars.companyName}  
**Website:** ${vars.website}  
**Stand:** ${new Date().toLocaleDateString('de-DE')}

## 1. Verantwortlicher

${vars.companyName}  
${vars.address || 'Adresse gemäß Impressum'}

E-Mail: ${vars.email}

## 2. Erhebung und Verarbeitung personenbezogener Daten

Wir erheben und verarbeiten personenbezogene Daten nur, wenn dies:
- Für die Bereitstellung unserer Dienste erforderlich ist
- Aufgrund Ihrer Einwilligung erfolgt
- Aufgrund gesetzlicher Vorschriften erfolgt

## 3. Ihre Rechte

Sie haben das Recht auf:
- Auskunft über Ihre Daten
- Berichtigung falscher Daten
- Löschung Ihrer Daten
- Einschränkung der Verarbeitung
- Datenübertragbarkeit
- Widerspruch gegen die Verarbeitung

## 4. Kontakt Datenschutzbeauftragter

${vars.dpoEmail || vars.email}

## 5. Beschwerderecht

Sie haben das Recht, sich bei einer Aufsichtsbehörde zu beschweren.

---
*Diese Datenschutzerklärung wurde automatisch generiert und sollte von einem Rechtsanwalt überprüft werden.*`;
    }

    // 📜 Nutzungsbedingungen
    generateTermsOfService(vars) {
        return `# Nutzungsbedingungen

**Dienst:** ${vars.serviceName}  
**Anbieter:** ${vars.companyName}  
**Stand:** ${new Date().toLocaleDateString('de-DE')}

## 1. Geltungsbereich

Diese Nutzungsbedingungen gelten für die Nutzung von ${vars.serviceName}.

## 2. Vertragsgegenstand

${vars.companyName} stellt ${vars.serviceName} als Software-as-a-Service (SaaS) zur Verfügung.

## 3. Registrierung und Konto

- Account-Erstellung erforderlich
- Wahrheitsgemäße Angaben
- Geheimhaltung der Zugangsdaten

## 4. Preise und Zahlung

- Preise gemäß aktueller Preisliste
- Zahlung im Voraus
- 14-tägige Widerrufsfrist

## 5. Haftung

Haftungsausschluss für indirekte Schäden, außer bei Vorsatz oder grober Fahrlässigkeit.

## 6. Kündigung

- Monatliche Kündigungsfrist
- sofortige Kündigung bei Verstoß

## 7. Anwendbares Recht

Dieser Vertrag unterliegt dem Recht der ${vars.jurisdiction || 'Bundesrepublik Deutschland'}.

---
*Diese Nutzungsbedingungen wurden automatisch generiert und sollten von einem Rechtsanwalt überprüft werden.*`;
    }

    // 🏢 Impressum
    generateImprint(vars) {
        return `# Impressum

**Angaben gemäß § 5 TMG:**

${vars.companyName}  
${vars.address}

**Vertreten durch:**  
${vars.ceo}

**Kontakt:**  
Telefon: ${vars.phone}  
E-Mail: ${vars.email}

${vars.vatId ? `**USt-IdNr.:** ${vars.vatId}` : ''}
${vars.register ? `**Handelsregister:** ${vars.register}` : ''}

## Verantwortlich für den Inhalt nach § 55 Abs. 2 RStV:

${vars.ceo}

## Haftung für Inhalte

Als Diensteanbieter sind wir gemäß § 7 Abs.1 TMG für eigene Inhalte auf diesen Seiten verantwortlich.

## Streitschlichtung

Die Europäische Kommission stellt eine Plattform zur Online-Streitbeilegung (OS) bereit: https://ec.europa.eu/consumers/odr/`;
    }

    // 🍪 Cookie-Richtlinie
    generateCookiePolicy(vars) {
        return `# Cookie-Richtlinie

**Website:** ${vars.website}  
**Stand:** ${new Date().toLocaleDateString('de-DE')}

## 1. Was sind Cookies?

Cookies sind kleine Textdateien, die auf Ihrem Gerät gespeichert werden.

## 2. Welche Cookies verwenden wir?

- **Essenzielle Cookies**: Erforderlich für den Betrieb
- **Funktionale Cookies**: Verbessern die Funktionalität
- **Analyse-Cookies**: Statistische Zwecke
- **Marketing-Cookies**: Personalisierte Werbung

## 3. Cookie-Verwaltung

Sie können Cookies in Ihren Browsereinstellungen verwalten.

## 4. Kontakt

Bei Fragen: ${vars.contactEmail}

## 5. Änderungen

Wir behalten uns vor, diese Cookie-Richtlinie zu ändern.`;
    }

    // 🔒 Geheimhaltungsvereinbarung
    generateNDA(vars) {
        return `# Geheimhaltungsvereinbarung (NDA)

**Zwischen:**
${vars.partyA}

**und:**
${vars.partyB}

**Stand:** ${new Date().toLocaleDateString('de-DE')}

## 1. Zweck

Diese Vereinbarung dient dem Schutz vertraulicher Informationen im Rahmen von: ${vars.purpose}

## 2. Vertrauliche Informationen

Vertrauliche Informationen umfassen:
- Geschäftsgeheimnisse
- Technische Daten
- Finanzinformationen
- Kundendaten
- Marketingpläne

## 3. Verpflichtungen

Beide Parteien verpflichten sich:
- Vertrauliche Informationen geheim zu halten
- Informationen nur für den vereinbarten Zweck zu nutzen
- Informationen nicht an Dritte weiterzugeben

## 4. Laufzeit

Diese Vereinbarung gilt für ${vars.duration || '3 Jahre'} ab Unterzeichnung.

## 5. Sanktionen

Bei Verstoß gegen diese Vereinbarung können Schadensersatzansprüche geltend gemacht werden.

---
*Diese Geheimhaltungsvereinbarung wurde automatisch generiert und sollte von einem Rechtsanwalt überprüft werden.*`;
    }

    // 📄 Generisches Dokument
    generateGenericDocument(template, vars) {
        return `# ${template.name}

**Generiert am:** ${new Date().toLocaleDateString('de-DE')}

## Dokument-Details

- **Kategorie:** ${template.category}
- **Geltungsbereich:** ${template.jurisdictions.join(', ')}

## Variablen

${Object.entries(vars).map(([key, value]) => `- **${key}:** ${value}`).join('\n')}

---
*Dieses Dokument wurde automatisch generiert und sollte von einem Rechtsanwalt überprüft werden.*`;
    }

    // 🔍 Compliance-Check
    async checkCompliance(type, data = {}) {
        const rule = this.compliance[type];
        if (!rule) {
            throw new Error(`Compliance type '${type}' not found`);
        }

        console.log(`🔍 Checking: ${rule.name}`);

        const checks = rule.requirements.map(req => ({
            requirement: req,
            status: data[req] || false,
            message: data[req] ? '✅ Erfüllt' : '❌ Fehlt'
        }));

        const passed = checks.filter(c => c.status).length;
        const total = checks.length;
        const percentage = Math.round((passed / total) * 100);

        return {
            type: type,
            name: rule.name,
            score: percentage,
            passed: passed,
            total: total,
            checks: checks,
            risk: percentage < 50 ? 'high' : percentage < 80 ? 'medium' : 'low',
            potentialFines: rule.fines,
            recommendations: checks
                .filter(c => !c.status)
                .map(c => `Fügen Sie hinzu: ${c.requirement}`)
        };
    }

    // 🎯 Vollständiger Website-Check
    async fullWebsiteCheck(websiteData) {
        console.log('🌐 Starting full website compliance check...');

        const results = {};
        for (const type of Object.keys(this.compliance)) {
            try {
                results[type] = await this.checkCompliance(type, websiteData);
            } catch (error) {
                results[type] = { error: error.message };
            }
        }

        const overallScore = Object.values(results)
            .filter(r => r.score)
            .reduce((sum, r) => sum + r.score, 0) / Object.keys(results).length;

        return {
            overallScore: Math.round(overallScore),
            results: results,
            timestamp: new Date().toISOString(),
            criticalIssues: Object.values(results)
                .filter(r => r.risk === 'high')
                .length
        };
    }

    // 📊 Dokument-History
    getDocumentHistory() {
        return this.generatedDocuments;
    }

    // 📋 Verfügbare Templates
    getAvailableTemplates() {
        return Object.entries(this.templates).map(([key, template]) => ({
            key,
            name: template.name,
            description: template.description,
            category: template.category,
            jurisdictions: template.jurisdictions,
            requiredVars: template.requiredVars
        }));
    }
}

// 🚀 Singleton Export
const openlaw = new AutonomousOpenLaw();
module.exports = openlaw;
