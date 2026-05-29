# @DudiRudibot Setup-Anleitung

## Was ist @DudiRudibot?

@DudiRudibot ist dein **Public Bot** fuer User. Er bietet:

- WebApp-Zugriff (Mini-App in Telegram)
- Start-Menue mit Inline-Buttons
- User-Registrierung in Supabase
- Event-Weiterleitung an den Control Bot

## Schritt 1: Bot bei BotFather erstellen

1. Oeffne [@BotFather](https://t.me/botfather) in Telegram
2. Sende `/newbot`
3. Name: `DudiRudibot` (oder wie du willst)
4. Username: `DudiRudibot` (muss auf `bot` enden)
5. Speichere den Token (sieht aus wie: `123456:ABC-DEF...`)

## Schritt 2: WebApp bei BotFather aktivieren

1. Sende `/mybots` an BotFather
2. Waehle `@DudiRudibot`
3. Gehe zu **Bot Settings** > **Menu Button** > **Configure menu button**
4. Setze die WebApp URL (z.B. deine Deploy-URL + `/bots/webapp/index.html`)

Alternative: Nutze Inline-Button in `/start` (bereits im Code implementiert)

## Schritt 3: .env konfigurieren

Erstelle im Projekt-Root eine `.env` Datei:

```env
# @DudiRudibot Token (von BotFather)
PUBLIC_BOT_TOKEN=123456:DEIN-TOKEN-HIER

# Control Bot Token (zweiter Bot fuer Admin)
CONTROL_BOT_TOKEN=123456:ZWEITER-TOKEN-HIER

# Deine Telegram User ID (von @userinfobot)
ADMIN_TELEGRAM_ID=123456789

# WebApp URL (nach Deployment)
WEBAPP_URL=https://deine-domain.com/bots/webapp/index.html

# Supabase (falls noch nicht vorhanden)
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
```

## Schritt 4: Bot starten

```bash
# Nur @DudiRudibot (Public Bot)
npm run bot:public

# Oder beide Bots gleichzeitig
npm run bot:both
```

## Befehle die @DudiRudibot versteht

| Befehl | Funktion |
| ------ | -------- |
| `/start` | Startet Bot, zeigt WebApp-Button |
| `/help` | Zeigt Hilfe |
| `/status` | Zeigt Account-Status |

## Was passiert im Hintergrund?

1. User sendet `/start` → Bot speichert User in Supabase
2. Bot sendet Event an Control Bot → Admin bekommt Benachrichtigung
3. User klickt WebApp-Button → Mini-App oeffnet sich
4. User sendet Daten aus WebApp → Bot empfaengt und leitet an Admin weiter

## Control Bot Befehle (nur Admin)

Der Control Bot ist dein Admin-Panel. Siehe `control-bot.js` fuer alle Befehle.

## Troubleshooting

### Bot antwortet nicht?

- Pruefe ob Token korrekt in `.env`
- Stelle sicher dass nur eine Instanz laeuft (keine doppelten Polling-Prozesse)
- Loesche Webhook falls vorhanden: `curl https://api.telegram.org/bot<TOKEN>/deleteWebhook`

### WebApp oeffnet nicht?

- Pruefe `WEBAPP_URL` in `.env`
- URL muss HTTPS sein
- Domain muss bei BotFather erlaubt sein

## Naechste Schritte

- [ ] Deployment auf Railway/Render/VPS
- [ ] Supabase Tables erstellen (`telegram_users`, `bot_events`)
- [ ] WebApp anpassen (Design, Features)
- [ ] MTProto Client aktivieren (erweiterte Automation)
