# KIVO — Kognitive Voice Operator

**Local-first voice agent for the Rudibot ecosystem.**

KIVO ist ein lokaler Sprachassistent, der dein Zuhause steuert, deine Projekte versteht, mit Rudibot kommuniziert und komplexe Aufgaben als Agent durchführt — alles ohne Cloud-Abhängigkeit.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  KIVO CORE                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ kivo-voice   │  │ kivo-memory  │  │ kivo-home    │    │
│  │ Wake, STT    │  │ Context,     │  │ Home         │    │
│  │ TTS, Intent  │  │ Projects,    │  │ Assistant    │    │
│  │              │  │ Preferences  │  │ Bridge       │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ kivo-agents  │  │ kivo-rudibot │  │ kivo-guard   │    │
│  │ Workflows,   │  │ Bridge to    │  │ Roles,       │    │
│  │ Tools        │  │ Rudibot      │  │ Approvals    │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│  ┌──────────────┐                                        │
│  │ kivo-llm     │  OpenAI-compatible LLM provider        │
│  │ Chat, Intent │  (optional)                             │
│  └──────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Modules

### kivo-voice-core
Wake word detection, STT, TTS, session handling, intent classification.

**Intent Types:**
- `home` — Fast path for lights, climate, timers, garage
- `agent` — Complex tasks: subscriptions, taxes, scans, reports
- `rudibot` — Direct Rudibot commands
- `memory` — Store and retrieve context

### kivo-memory
Persistent memory for user profiles, projects, routines, device knowledge, conversation history.

### kivo-home
Home Assistant bridge for smart home control.

**Fast Path Commands:**
- `turnOn/Off(entity)` — Lights, switches
- `setBrightness(entity, level)` — Dimmers
- `setTemperature(entity, temp)` — Climate
- `setTimer(minutes)` — Timers
- `openGarage/closeGarage(entity)` — Access control
- `activateScene(sceneId)` — Scene management

### kivo-agents
Complex multi-step workflows with tool calls.

**Built-in Workflows:**
- `saas_cost_analysis` — Find and rank killable subscriptions
- `morning_briefing` — System status + subscriptions
- `tax_preparation` — Generate report, validate, ELSTER export
- `security_audit` — Run deep scan, report results

### kivo-rudibot-bridge
Translates KIVO intents into Rudibot Telegram commands.

**Mapped Commands:**
- `/fin-grid`, `/subs`, `/sub-kill`, `/tax`, `/spend`, `/elster`
- `/validate`, `/deepscan`, `/audit`, `/security`
- `/status`, `/health`, `/restart`, `/deploy`

### kivo-llm (optional)
OpenAI-compatible LLM provider for enhanced intent classification and chat completions.

**Features:**
- `chat(messages)` — Generic chat completion
- `classifyIntent(text)` — LLM-based intent classification fallback

**Usage:**
```javascript
const kivo = new KivoCore({
  llm: {
    provider: 'openai',
    apiKey: 'DEIN_KEY',
    baseURL: 'https://dein-server.tld/v1',
    model: 'kivo-coder',
  }
});
```

### kivo-guard
Role-based access control and approval workflows.

**Roles:** `guest`, `user`, `admin`

**Sensitive Actions (require approval):**
- Subscription cancellation (level 2)
- ELSTER export (level 2)
- System restart (level 2)
- System deploy (level 3)
- Deep scan (level 1 — notification only)

---

## Fast Path vs Agent Path

| Fast Path | Agent Path |
|-----------|------------|
| "Hey Kivo, Licht an" | "Hey Kivo, prüf meine Abos" |
| "Hey Kivo, Timer 10 Minuten" | "Hey Kivo, starte Deepscan" |
| "Hey Kivo, Tor öffnen" | "Hey Kivo, bereite Steuerdaten vor" |
| "Hey Kivo, Heizung auf 21 Grad" | "Hey Kivo, was kostet mich gerade unnötig Geld?" |

Fast path = Home Assistant, direkt, sub-100ms.
Agent path = Workflow, mehrstufig, Tool-Aufrufe, ggf. Freigabe.

---

## Usage

```javascript
const { KivoCore } = require('./kivo-core');

const kivo = new KivoCore();

// Process voice/text command
const result = await kivo.processText('Hey Kivo, prüf meine Abos');

// Approve sensitive action
await kivo.approve('finance.kill_subscription');

// Get status
console.log(kivo.getStatus());
```

---

## Demo

```bash
cd /Users/rudolfsarkany/CascadeProjects/50-kivo
node kivo-core.js
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KIVO_STT_PROVIDER` | `whisper-local` | Speech-to-text engine |
| `KIVO_TTS_PROVIDER` | `piper` | Text-to-speech engine |
| `KIVO_LANGUAGE` | `de-DE` | Primary language |
| `KIVO_ROLE` | `user` | Default user role |
| `HOME_ASSISTANT_URL` | — | Home Assistant instance |
| `HOME_ASSISTANT_TOKEN` | — | HA long-lived token |
| `RUDIBOT_API_URL` | `http://localhost:3201` | Rudibot health endpoint |
| `KIVO_LLM_PROVIDER` | `openai` | LLM provider name |
| `KIVO_LLM_API_KEY` | — | API key for LLM endpoint |
| `KIVO_LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `KIVO_LLM_MODEL` | `gpt-4o-mini` | Model identifier |

---

## Integration with Rudibot

KIVO extends Rudibot with voice control:
- Fast home commands execute directly via Home Assistant
- Complex queries route through Rudibot bridge to Finance Grid
- Approval-required actions pause for confirmation
- All actions are audited in `logs/kivo-guard-audit.log`

---

## Future Hardware

- **Raspberry Pi 5** + ReSpeaker HAT for local wake word + audio
- **Whisper.cpp** or **faster-whisper** for local STT
- **Piper** for local TTS
- **Home Assistant** on same network for sub-50ms response times

---

**KIVO — Dein lokaler Agent. Schnell. Privat. Intelligent.**
