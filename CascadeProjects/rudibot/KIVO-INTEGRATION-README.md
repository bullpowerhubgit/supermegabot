# KIVO Integration — Rudibot + Voice Assistant

**Complete integration of KIVO voice assistant into Rudibot with modular architecture.**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Rudibot + KIVO Main Entry                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ src/bot/     │  │ src/kivo/    │  │ src/actions/ │    │
│  │ router,      │  │ core,        │  │ deepscan,    │    │
│  │ handlers,    │  │ intents,     │  │ cancel, home, │    │
│  │ callbacks    │  │ voice, guard │  │ dashboard     │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ src/integrations/ │           │              │    │
│  │ telegram,    │  │ whisper,     │  │ tts,         │    │
│  │ homeassistant│  │ voice        │  │ audio        │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Structure

### src/bot/
- **telegram-router.js** — Routes messages to handlers, distinguishes commands vs KIVO requests
- **command-handler.js** — Traditional `/command` processing, maintains existing Rudibot commands
- **callback-handler.js** — Inline keyboard callbacks, approval workflows

### src/kivo/
- **kivo-core.js** — Embedded KIVO thinking, memory, intent detection
- **kivo-intents.js** — Centralized intent definitions and entity extraction
- **kivo-voice.js** — Voice message processing, transcription, TTS
- **kivo-guard.js** — Pairing, approval, roles, secure release
- **kivo-reply.js** — Response formatting, keyboards, markdown

### src/actions/
- **deepscan-action.js** — Security deep scan execution
- **cancel-subscription-action.js** — Subscription cancellation workflow
- **homeassistant-action.js** — Smart home device control
- **dashboard-action.js** — Status reports and metrics

### src/integrations/
- **telegram.js** — Core Telegram bot functionality
- **whisper/** — Speech-to-text pipeline (modular)
  - **download-telegram-voice.js** — Download voice messages from Telegram
  - **convert-audio.js** — FFmpeg audio normalization (OGG → WAV)
  - **transcribe-openai.js** — OpenAI Whisper API transcription
  - **transcribe-local.js** — Local faster-whisper server transcription
  - **whisper-service.js** — Central orchestrator (download → convert → transcribe → cleanup)
- **tts.js** — Text-to-speech with Piper
- **homeassistant.js** — Home Assistant platform integration

---

## Usage

### Basic Setup
```javascript
const { RudibotKivo } = require('./src/index');

const bot = new RudibotKivo(token, {
  allowedUserIds: ['123456789'],
  kivoRole: 'user',
  homeAssistant: {
    baseUrl: 'http://homeassistant.local:8123',
    token: 'ha_long_lived_token'
  }
});

bot.start();
```

### Environment Variables
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
ALLOWED_USER_IDS=123456789,987654321
KIVO_ROLE=user
WHISPER_PATH=/path/to/whisper
PIPER_PATH=/path/to/piper
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=ha_long_lived_token
```

---

## Features

### 🎙️ Voice Commands
- "Hey KIVO, Licht an" → Toggle lights
- "KIVO, Timer 10 Minuten" → Set timer
- "Hey KIVO, prüf meine Abos" → Show subscriptions
- "KIVO, starte Deepscan" → Security scan
- "Hey KIVO, was ist der Status" → System overview

### 🤖 Conversational Operations
- Multi-step workflows with approval
- Context-aware responses
- Entity extraction (devices, times, providers)
- Intent classification with confidence scoring

### 🔐 Security & Approval
- Role-based access control (guest, user, admin)
- Sensitive actions require approval
- Audit logging for all operations
- User authorization by Telegram ID

### 🏠 Smart Home Integration
- Direct Home Assistant API integration
- Device discovery and control
- Scene activation
- Climate control and timers

### 💰 Finance Grid Integration
- Subscription management
- Cancellation workflows
- Tax preparation
- ELSTER export with approval

---

## Message Flow

```
User sends message/voice
        ↓
Telegram Router
        ↓
┌─────────────────┐
│ Command?        │ → Command Handler → Direct response
│ KIVO Request?  │ → KIVO Core → Intent → Action → Response
│ Voice?          │ → Whisper → Text → KIVO Core → TTS → Audio
└─────────────────┘
        ↓
Response Formatting
        ↓
Telegram Reply (with keyboards if needed)
```

---

## Approval Workflow

1. **Sensitive Action Detected** → Guard blocks
2. **Approval Request Sent** → Inline keyboard (Approve/Cancel)
3. **User Approves** → Execute action
4. **Result Delivered** → Success/failure message
5. **Audit Log Updated** → Complete trail

---

## Integration Points

### With Existing Rudibot
- All existing `/commands` preserved
- Finance Grid commands available
- Security commands functional
- Backward compatibility maintained

### With Home Assistant
- Real-time device control
- State monitoring
- Automation triggers
- Scene management

### With Voice Stack
- Whisper for STT (local or cloud)
- Piper for TTS (local synthesis)
- Audio file management
- Fallback to text commands

---

## Development

### Adding New Intents
```javascript
// In src/kivo/kivo-intents.js
this.intents.set('my.intent', {
  patterns: ['trigger phrase', 'alternative'],
  entities: ['device', 'action'],
  handler: this.handleMyIntent.bind(this)
});
```

### Adding New Actions
```javascript
// In src/actions/my-action.js
class MyAction {
  async execute(options) {
    // Implementation
    return { success: true, message: 'Action completed' };
  }
}
```

### Adding New Integrations
```javascript
// In src/integrations/my-service.js
class MyServiceIntegration {
  constructor(config) {
    this.config = config;
  }
  
  async callAPI(endpoint, data) {
    // Implementation
  }
}
```

---

## Security Considerations

1. **User Authorization** — Only allowed Telegram IDs
2. **Role-Based Access** — Different permissions per role
3. **Approval Required** — Sensitive actions need confirmation
4. **Audit Logging** — All actions logged with timestamps
5. **Input Validation** — All user inputs validated
6. **Rate Limiting** — Prevent abuse and spam

---

## Monitoring & Debugging

### Status Endpoint
```javascript
const status = await bot.getStatus();
console.log('Bot Status:', status);
```

### Health Checks
- Rudibot health endpoint
- Home Assistant connectivity
- Voice service availability
- Memory usage monitoring

### Logs
- KIVO guard audit logs: `logs/kivo-guard-audit.log`
- Bot operation logs
- Error tracking and reporting

---

## Performance

### Optimizations
- Lazy loading of integrations
- Audio file cleanup (hourly)
- Response caching for common queries
- Async processing for long-running actions

### Resource Usage
- Memory: ~50MB base + voice processing
- CPU: Minimal for text, moderate for voice
- Storage: Temp files for audio (auto-cleanup)
- Network: Home Assistant + optional cloud services

---

## Future Enhancements

1. **Advanced Workflows** — Multi-step automation chains
2. **Natural Language Understanding** — Better intent recognition
3. **Voice Biometrics** — User identification by voice
4. **Multi-Language Support** — International voice commands
5. **Dashboard Integration** — Real-time status visualization
6. **Mobile App** — Native KIVO interface

---

**KIVO Integration — Your voice-controlled autonomous assistant.**
