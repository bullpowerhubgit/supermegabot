# RudiBot Secure API Configuration

Diese Konfiguration speichert die aktivierten GCP APIs für zukünftige Tools.

## Projektinformationen

- **Projekt-ID:** `gen-lang-client-0895465231`
- **Projektnummer:** `1023902745882`
- **Projektname:** Shopy
- **Billing-Konto:** 0119F3-58784D-13BCB6 (Mein Rechnungskonto)

## Aktivierte APIs (19)

### Core APIs
- `iam.googleapis.com` - Identity and Access Management
- `logging.googleapis.com` - Cloud Logging
- `cloudtrace.googleapis.com` - Cloud Trace

### AI & ML
- `aiplatform.googleapis.com` - Vertex AI
- `agentregistry.googleapis.com` - Agent Registry
- `modelarmor.googleapis.com` - Model Armor

### Compute & Infrastructure
- `compute.googleapis.com` - Compute Engine
- `networksecurity.googleapis.com` - Network Security
- `networkservices.googleapis.com` - Network Services
- `storage-component.googleapis.com` - Cloud Storage

### Application Services
- `apphub.googleapis.com` - App Hub
- `apptopology.googleapis.com` - App Topology
- `cloudapiregistry.googleapis.com` - Cloud API Registry
- `iap.googleapis.com` - Identity-Aware Proxy
- `notebooks.googleapis.com` - Notebooks

### Observability
- `observability.googleapis.com` - Observability
- `telemetry.googleapis.com` - Telemetry

### Other
- `dataform.googleapis.com` - Dataform
- `iamconnectors.googleapis.com` - IAM Connectors
- `texttospeech.googleapis.com` - Text-to-Speech

## Verwendung in Tools

### Python Beispiel
```python
import json

with open('RudiBot-Secure-API/gcp-config.json') as f:
    config = json.load(f)

project_id = config['project']['id']
apis = [api['name'] for api in config['apis']['enabled']]
```

### Node.js Beispiel
```javascript
const config = require('./RudiBot-Secure-API/gcp-config.json');

const projectId = config.project.id;
const apis = config.apis.enabled.map(api => api.name);
```

### Shell Beispiel
```bash
PROJECT_ID=$(jq -r '.project.id' RudiBot-Secure-API/gcp-config.json)
APIS=$(jq -r '.apis.enabled[].name' RudiBot-Secure-API/gcp-config.json)
```

## Authentifizierung

Die Konfiguration ist für Cloud Shell vorgesehen. Authentifizierung erfolgt über:
- gcloud CLI (in Cloud Shell automatisch)
- Service Account Keys (für lokale Entwicklung)

## Billing-Abhängigkeiten

Folgende APIs benötigen aktiviertes Billing:
- `compute.googleapis.com`
- `networksecurity.googleapis.com`
- `texttospeech.googleapis.com`

## Sicherheit

- Diese Datei enthält keine geheimen Schlüssel
- API-Schlüssel sollten separat in Umgebungsvariablen oder Secret Manager gespeichert werden
- Für Produktion: IAM-Rollen statt Service Account Keys verwenden
