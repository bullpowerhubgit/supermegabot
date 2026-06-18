#!/usr/bin/env bash
# EmailBrain — Railway Env-Var Setup für alle 7 Email-Konten
# Ausführen: bash scripts/setup_email_railway.sh
# App-Passwörter erstellen: myaccount.google.com → Sicherheit → 2FA → App-Passwörter
# Hinweis: Passwörter HIER eintragen, dann Datei sofort löschen (niemals committen!)

set -e

SERVICE="supermegabot"

echo "Setze EmailBrain Env-Vars für Railway Service: $SERVICE"
echo "Bitte erst App-Passwörter in diesem Script eintragen!"

# ── Konto 1: dragonadnp@gmail.com ─────────────────────────────────────────────
railway variables set \
  GMAIL_USER_1="dragonadnp@gmail.com" \
  GMAIL_APP_PASSWORD_1="HIER_APP_PASSWORT_EINTRAGEN" \
  --service "$SERVICE"

# ── Konto 2: nikolestimi@gmail.com ───────────────────────────────────────────
railway variables set \
  GMAIL_USER_2="nikolestimi@gmail.com" \
  GMAIL_APP_PASSWORD_2="HIER_APP_PASSWORT_EINTRAGEN" \
  --service "$SERVICE"

# ── Konto 3: bullpowersrtkennels@gmail.com ────────────────────────────────────
railway variables set \
  GMAIL_USER_3="bullpowersrtkennels@gmail.com" \
  GMAIL_APP_PASSWORD_3="HIER_APP_PASSWORT_EINTRAGEN" \
  --service "$SERVICE"

# ── Konto 4: looopwave@gmail.com ─────────────────────────────────────────────
railway variables set \
  GMAIL_USER_4="looopwave@gmail.com" \
  GMAIL_APP_PASSWORD_4="HIER_APP_PASSWORT_EINTRAGEN" \
  --service "$SERVICE"

# ── Konto 5: aiitecbuuss@gmail.com ───────────────────────────────────────────
railway variables set \
  GMAIL_USER_5="aiitecbuuss@gmail.com" \
  GMAIL_APP_PASSWORD_5="HIER_APP_PASSWORT_EINTRAGEN" \
  --service "$SERVICE"

# ── Konto 6: rudolf.sarkany@aitec.de (Custom Domain) ─────────────────────────
# IMAP-Host anpassen falls nicht Strato: imap.ionos.de / imap.gmail.com / mail.your-server.de
railway variables set \
  GMAIL_USER_6="rudolf.sarkany@aitec.de" \
  GMAIL_APP_PASSWORD_6="HIER_APP_PASSWORT_EINTRAGEN" \
  IMAP_HOST_6="imap.strato.de" \
  SMTP_HOST_6="smtp.strato.de" \
  --service "$SERVICE"

# ── Konto 7: rudolf.sarkany.aiitec@gmail.com ─────────────────────────────────
railway variables set \
  GMAIL_USER_7="rudolf.sarkany.aiitec@gmail.com" \
  GMAIL_APP_PASSWORD_7="HIER_APP_PASSWORT_EINTRAGEN" \
  --service "$SERVICE"

echo ""
echo "Fertig! Railway deployt neu."
echo "Test: curl https://dudirudibot-mega-production.up.railway.app/api/email/brain/setup"
echo ""
echo "WICHTIG: App-Passwörter aus diesem Script entfernen und nicht committen!"
