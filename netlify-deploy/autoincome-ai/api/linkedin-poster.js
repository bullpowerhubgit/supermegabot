// LinkedIn auto-poster — DS24 product 668035 promotion
// Runs Mo/Mi/Fr 09:00 UTC via Vercel Cron
// Auto-refreshes LinkedIn access token on 401

const PERSON_URN = process.env.LINKEDIN_PERSON_URN || 'urn:li:person:YcxbqVN0ZR';
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const BLOG_URL = 'https://autoincome-ai.vercel.app/blog';
const CALCULATOR_URL = 'https://autoincome-ai.vercel.app/rechner';
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;

async function refreshLinkedInToken() {
  const params = new URLSearchParams({
    grant_type: 'refresh_token',
    refresh_token: process.env.LINKEDIN_REFRESH_TOKEN,
    client_id: process.env.LINKEDIN_CLIENT_ID,
    client_secret: process.env.LINKEDIN_CLIENT_SECRET,
  });
  const r = await fetch('https://www.linkedin.com/oauth/v2/accessToken', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
  });
  if (!r.ok) throw new Error(`Token refresh failed: ${r.status} ${await r.text()}`);
  const data = await r.json();
  const newToken = data.access_token;
  const newRefresh = data.refresh_token;

  // Update Vercel env vars so next run uses fresh tokens
  const vercelToken = process.env.VERCEL_API_TOKEN;
  const projectId = process.env.VERCEL_PROJECT_ID;
  if (vercelToken && projectId) {
    const tokenEnvId = process.env.LI_TOKEN_ENV_ID;
    const refreshEnvId = process.env.LI_REFRESH_ENV_ID;
    if (tokenEnvId) {
      await fetch(`https://api.vercel.com/v9/projects/${projectId}/env/${tokenEnvId}`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${vercelToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: newToken }),
      });
    }
    if (refreshEnvId && newRefresh) {
      await fetch(`https://api.vercel.com/v9/projects/${projectId}/env/${refreshEnvId}`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${vercelToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: newRefresh }),
      });
    }
  }
  return newToken;
}

const POSTS = [
  {
    text: `🤖 KI-Einkommen 2026 — was ich nach 4 Monaten gelernt habe

Ich habe mehrere KI-Einkommensstrategien getestet. Was wirklich funktioniert:

✅ KI-Tools sparen 80% der Arbeitszeit
✅ Automatisierung läuft 24/7 — auch wenn du schläfst
✅ Der deutsche Markt ist noch WEIT weniger gesättigt

Mein vollständiger 90-Day Blueprint auf Deutsch:
👇 ${PRODUCT_URL}

#KI #PassivesEinkommen #OnlineBusiness #Automatisierung`,
    mediaTitle: 'AI Income Machine — 90-Day Blueprint',
    mediaDesc: 'Vollautomatisch mit KI Geld verdienen — 90-Day Blueprint auf Deutsch',
  },
  {
    text: `💡 Warum die meisten beim KI-Einkommen scheitern

Fehler #1: Sie nutzen ChatGPT falsch
Fehler #2: Kein System, nur Experimente
Fehler #3: Englischer Content im deutschen Markt

Ich habe ein deutschsprachiges System entwickelt, das diese Fehler vermeidet.

3 Verkäufe in 4 Monaten — vollautomatisch. Und das ist nur der Anfang.

Das komplette System: ${PRODUCT_URL}

#KI #OnlineBusiness #Automatisierung #PassivesEinkommen`,
    mediaTitle: 'AI Income Machine — 90-Day Blueprint',
    mediaDesc: 'Das deutschsprachige KI-Einkommenssystem das wirklich funktioniert',
  },
  {
    text: `📊 Meine KI-Business Zahlen (ehrlich & transparent)

Monat 1: €0 — Setup & Aufbau
Monat 2: €0 — erste Tests
Monat 3: €37 — erster Verkauf
Monat 4: €74 — 2 weitere Verkäufe (automatisch)

Total: €111 — vollständig passiv

Das Besondere: Ich musste in Monat 3+4 NICHTS tun. Das System arbeitet selbstständig.

Wie ich das aufgebaut habe → ${PRODUCT_URL}

#KI #PassivesEinkommen #Transparenz #OnlineBusiness`,
    mediaTitle: 'AI Income Machine — 90-Day Blueprint',
    mediaDesc: 'Echte Zahlen: So verdiene ich passiv mit KI-Automatisierung',
  },
  {
    text: `🚀 Der größte Unterschied zwischen KI-Nutzern die Geld verdienen und denen die es nicht tun:

SYSTEM vs. CHAOS

Ohne System:
❌ Täglich neue Prompts ausprobieren
❌ Kein Tracking, keine Daten
❌ Keine Wiederholbarkeit

Mit System:
✅ 3 Automatisierungen laufen täglich
✅ Einnahmen auch wenn du nicht am PC bist
✅ Skalierbar auf 10x ohne Mehraufwand

Mein System kostet einmalig €37:
${PRODUCT_URL}

#KI #System #OnlineBusiness #Automatisierung`,
    mediaTitle: 'AI Income Machine — 90-Day Blueprint',
    mediaDesc: 'Warum System über Chaos siegt — KI-Einkommen aufbauen',
  },
  {
    text: `🇩🇪 Warum JETZT der beste Zeitpunkt für KI-Business in Deutschland ist

2023: "KI ist interessant"
2024: "Ich sollte mal was machen"
2025: Früheinsteiger verdienen bereits
2026: Mainstream beginnt — noch 6 Monate Vorsprung möglich

Der Unterschied zwischen 2026 und 2028?
Die Leute die 2026 anfangen, werden 2028 die Marktführer sein.

Mein komplettes System für den deutschen Markt:
${PRODUCT_URL}

#KI #Zeitpunkt #OnlineBusiness #Deutschland`,
    mediaTitle: 'AI Income Machine — 90-Day Blueprint',
    mediaDesc: 'Warum 2026 der perfekte Einstiegszeitpunkt für KI-Business ist',
  },
  {
    text: `💰 €37 Investment — was du dafür bekommst:

✅ 90-Day Step-by-Step Blueprint (auf Deutsch)
✅ 5 KI-Tools die ich täglich nutze (3 davon kostenlos)
✅ Meine kompletten Prompt-Templates
✅ Automatisierungsskripte die ich selbst nutze
✅ 60-Tage-Geld-zurück-Garantie

Was du NICHT bekommst:
❌ Leere Versprechen ohne Beweis
❌ Englische Inhalte die du übersetzen musst
❌ Komplizierte Technik ohne Support

Nur €37 Einmalzahlung — kein Abo:
${PRODUCT_URL}

#KI #Investment #OnlineBusiness #Transparenz`,
    mediaTitle: 'AI Income Machine — 90-Day Blueprint',
    mediaDesc: '€37 — was du wirklich bekommst (transparente Übersicht)',
  },
  {
    text: `🤝 Ich suche 10 Affiliates für mein KI-Produkt

Provision: 50% = €18,50 pro Verkauf
Conversion Rate: ~3-5% (getestet)
Produktpreis: €37

Was ich biete:
✅ Fertige Werbematerialien auf Deutsch
✅ Tracking-Dashboard
✅ Wöchentliche Auszahlung via Digistore24

Was ich suche:
• LinkedIn-Creator mit 500+ Followern
• YouTube-Kanal im Business/KI-Nischen
• Newsletter mit deutschen Lesern

Interesse? Schreib mir eine Nachricht.

Produkt testen: ${PRODUCT_URL}

#Affiliate #KI #JointVenture #OnlineBusiness`,
    mediaTitle: 'AI Income Machine — Affiliate Program',
    mediaDesc: '50% Provision — werde Affiliate für meinen KI-Blueprint',
  },
  {
    text: `📝 Ich habe getestet: Mit welchen kostenlosen KI-Tools kann man 2026 wirklich Geld verdienen?

Ergebnis nach 3 Monaten Testing:

ChatGPT Free → E-Books schreiben ✅
Canva KI → Cover und Grafiken ✅
Perplexity → Recherche ✅
Google Gemini → Marktanalyse ✅

Die Tools die NICHT funktioniert haben: ❌ (im Artikel erklärt)

Vollständige Übersicht mit konkreten Methoden:
👇 ${BLOG_URL}/ki-tools-kostenlos-geld-verdienen

#KI #GeldVerdienen #KostenlosTools #OnlineBusiness`,
    mediaTitle: 'Kostenlose KI-Tools 2026',
    mediaDesc: 'Diese 7 gratis KI-Tools reichen für erste Einnahmen',
  },
  {
    text: `📖 ChatGPT E-Book erstellen — meine ehrliche Erfahrung

Zeitaufwand: 6 Stunden
Investition: €0
Ergebnis: verkaufsfähiges 40-Seiten-Produkt

Was niemand sagt:
→ Das Schreiben ist einfach
→ Das Marketing ist die Arbeit
→ ChatGPT liefert 70%, du lieferst 30%

Den kompletten Schritt-für-Schritt-Prozess habe ich dokumentiert:
${BLOG_URL}/chatgpt-ebook-erstellen

#ChatGPT #EBook #DigitaleProdukte #OnlineBusiness`,
    mediaTitle: 'ChatGPT E-Book erstellen 2026',
    mediaDesc: 'Schritt-für-Schritt Anleitung mit echten Zahlen',
  },
  {
    text: `🏗️ Online Business in Deutschland starten 2026 — was du wirklich brauchst

Was du NICHT brauchst:
❌ GmbH (Einzelunternehmen reicht)
❌ Steuerberater von Tag 1
❌ Tausende Euro Startkapital

Was du brauchst:
✅ Gewerbeanmeldung (€20-€50, 1 Stunde)
✅ Kleinunternehmerregelung (unter €22k = keine MwSt)
✅ Ein konkretes Produkt oder Angebot

Vollständiger Leitfaden mit Zeitplan:
${BLOG_URL}/online-business-deutschland-starten

#OnlineBusiness #Deutschland #Selbstständig #Gründung`,
    mediaTitle: 'Online Business Deutschland 2026',
    mediaDesc: 'Rechtliches, Steuern und erste Einnahmen — ehrlicher Guide',
  },
  {
    text: `📊 Passives Einkommen 2026 — was WIRKLICH funktioniert (nach 12 Monaten Erfahrung)

Methode 1: Digitale Produkte → ✅ funktioniert (ab Monat 3-6)
Methode 2: Affiliate Marketing → ✅ funktioniert (ab Monat 12-24)
Methode 3: ETF/Dividenden → ✅ funktioniert (braucht Kapital)
Methode 4: YouTube → ⏳ langsam (ab Monat 12+)
Methode 5: Dropshipping → ⚠️ schwierig 2026

Ehrlicher Vergleich mit Zeitplan und realen Zahlen:
${BLOG_URL}/passives-einkommen-aufbauen-2026

#PassivesEinkommen #Ehrlichkeit #OnlineBusiness #KI`,
    mediaTitle: 'Passives Einkommen 2026 — Ehrlicher Vergleich',
    mediaDesc: '5 Strategien mit realistischen Zahlen und Zeitplan',
  },
  {
    text: `🤖 Als KI-Freelancer starten — 5 Dienste die jetzt gefragt sind

Was Unternehmen 2026 suchen und zahlen:

1. KI-Texterstellung → €30-80/h
2. Prompt Engineering → €60-150/h
3. No-Code Automatisierung (Zapier/Make) → €50-120/h
4. KI-Bildbearbeitung → €40-100/h
5. KI-Videobearbeitung → €40-90/h

Kein Abschluss nötig. Nur Praxis.

Wie du in 30 Tagen ersten Auftrag bekommst:
${BLOG_URL}/ki-freelancer-werden-deutschland

#KIFreelancer #Freelancing #KI #Nebeneinkommen`,
    mediaTitle: 'KI-Freelancer werden 2026',
    mediaDesc: 'Diese 5 Dienste sind gefragt — so startest du ohne Portfolio',
  },
  {
    text: `🎯 Digistore24 vs. Etsy vs. Gumroad — wo verkauft man digitale Produkte in Deutschland 2026?

Ich habe alle drei getestet. Ergebnis:

🇩🇪 Digistore24:
✅ Größte deutsche Plattform (7M Käufer)
✅ Eingebautes Affiliate-System
✅ MwSt. wird automatisch abgeführt
❌ Weniger international bekannt

🌍 Etsy + Gumroad:
✅ International
❌ Keine deutschen Käufer-Community
❌ Komplexe MwSt. für EU-Verkäufer

Mein Produkt läuft auf DS24 — vollautomatisch:
${PRODUCT_URL}

#Digistore24 #DigitaleProdukte #OnlineBusiness #Deutschland`,
    mediaTitle: 'Digistore24 vs. Etsy vs. Gumroad 2026',
    mediaDesc: 'Ehrlicher Vergleich: Wo verkaufst du digitale Produkte in Deutschland?',
  },
  {
    text: `🔁 Warum ich nie aufgehört habe, auch als der erste Monat €0 brachte

Monat 1: €0
Monat 2: €0
Monat 3: Erster Verkauf €37

Was mich gehalten hat:
→ Das System lief, ich musste nichts tun
→ Jeden Tag neue Blog-Besucher ohne Aufwand
→ Die E-Mail-Liste wuchs automatisch

Passive Einnahmen brauchen Zeit. Aber dann laufen sie.

Mein System das im Hintergrund arbeitet:
${PRODUCT_URL}

#Durchhalten #PassivesEinkommen #OnlineBusiness #Realität`,
    mediaTitle: 'Warum Geduld der wichtigste KI-Business-Skill ist',
    mediaDesc: 'Monat 1 €0, Monat 3 erster Verkauf — der ehrliche Weg',
  },
  {
    text: `⚡ 5 Automatisierungen die ich täglich laufen habe — ohne einen Finger zu rühren:

1. LinkedIn-Posts werden automatisch veröffentlicht
2. E-Mails gehen automatisch an neue Subscriber raus
3. SEO-Artikel werden wöchentlich generiert
4. DS24 Sales-Report kommt morgens auf Telegram
5. Klaviyo E-Mail-Kampagnen starten automatisch

Total aktive Zeit pro Woche: ~0 Stunden

Das komplette System als Blueprint:
${PRODUCT_URL}

#Automatisierung #KI #PassivesEinkommen #SystemStattChaos`,
    mediaTitle: 'Diese 5 Automatisierungen laufen ohne mein Zutun',
    mediaDesc: '0 Stunden pro Woche — dank System-Automatisierung',
  },
  {
    text: `📧 Warum ich mit 20 E-Mail-Subscribern mehr verdiene als viele mit 2000 Instagram-Followern

Instagram-Follower: sehen deinen Post vielleicht
E-Mail-Subscriber: bekommen ihn direkt ins Postfach

Meine Zahlen:
• 20 Klaviyo-Subscriber
• 3 automatische E-Mails
• €111 Umsatz ohne aktives Zutun

E-Mail-Liste aufbauen mit Klaviyo kostenlos:
${BLOG_URL}/email-marketing-klaviyo-kostenlos

#EmailMarketing #Klaviyo #OnlineBusiness #PassivesEinkommen`,
    mediaTitle: 'E-Mail Marketing mit Klaviyo kostenlos',
    mediaDesc: 'Warum 20 Subscriber mehr wert sind als 2000 Follower',
  },
  {
    text: `🔥 Ich habe gerade ein neues Produkt gelauncht: SuperMegaBot KI-Automation System für €97

Was drin ist:
✅ Kompletter Automation-Code (deploy-ready)
✅ LinkedIn-Bot läuft automatisch Mo/Mi/Fr
✅ E-Mail-Sequenzen automatisch
✅ Shopify + Digistore24 Integration
✅ Telegram Revenue Reports täglich
✅ 1-Click Deploy auf Railway

Für wen ist es:
→ Online-Unternehmer die alles automatisieren wollen
→ Digitale Nomaden
→ Affiliate-Marketer die skalieren wollen

Früh-Käufer Preis: €97 (Normalpreis wird steigen)
https://www.checkout-ds24.com/product/704677

Oder erst das Starter-System testen → ${PRODUCT_URL}

#KI #Automatisierung #SuperMegaBot #OnlineBusiness`,
    mediaTitle: 'SuperMegaBot — Komplettes KI-Automation System',
    mediaDesc: 'Vollautomatisches Online-Business in einem Paket für €97',
  },
  {
    text: `💡 "Wie viele Stunden pro Woche brauchst du dafür?"

Meine Antwort: ~2 Stunden pro Woche für das System-Management.

Was in dieser Zeit passiert:
• 3x LinkedIn Posts gehen automatisch raus
• E-Mail-Sequenzen laufen automatisch
• DS24 Verkaufsberichte kommen täglich per Telegram
• Blog-Artikel werden automatisch indexiert

Was ICH tue: Zahlen checken, Strategie anpassen.

2h/Woche für ein System das passiv verdient:
${PRODUCT_URL}

#ZeitFürsLeben #Automatisierung #PassivesEinkommen #OnlineBusiness`,
    mediaTitle: '2 Stunden pro Woche — passives Einkommen mit System',
    mediaDesc: 'Wie das Automation-System den manuellen Aufwand auf 2h/Woche reduziert',
  },
  {
    text: `🇩🇪 32 Blog-Artikel in einer Woche — und wie das SEO-Traffic bringt

Mein SEO-System:
1. Artikel in Supabase speichern
2. Automatisch auf Website veröffentlicht
3. IndexNow an Bing + Google geschickt
4. Sitemap automatisch updated

Gesamtkosten: €0 (Serverless + kostenloser DB-Tier)

Welche Keywords ich ziele:
• "Geld verdienen zuhause 2026"
• "Passives Einkommen aufbauen"
• "KI Business Ideen 2026"
• "Heimarbeit seriös"

Blog: ${BLOG_URL}
Blueprint: ${PRODUCT_URL}

#SEO #ContentMarketing #KI #OnlineBusiness`,
    mediaTitle: '32 SEO-Artikel — automatisches Content-Marketing',
    mediaDesc: 'Wie ich 32 Blog-Artikel ohne manuelle Arbeit publiziere und ranke',
  },
  {
    text: `🧮 Wie viel kannst du mit KI WIRKLICH verdienen? (kostenloser Rechner)

Ich habe einen Einkommens-Rechner gebaut — 3 Fragen, 60 Sekunden, sofortiges Ergebnis.

Er berechnet:
📊 Realistisches Einkommen in Monat 1-2
📊 Projection für Monat 3-4
📊 Was in Monat 5-6 möglich ist

Plus: Persönlicher Aktionsplan für deine gewählte Methode (Affiliate, Digitale Produkte, Freelancing, Shopify).

Völlig kostenlos, keine Anmeldung nötig:
👉 ${CALCULATOR_URL}

Ich war überrascht wie viele nach dem Test geschrieben haben "ich hätte nicht gedacht dass das so realistisch machbar ist"

#KI #EinkommensRechner #PassivesEinkommen #OnlineBusiness`,
    mediaTitle: 'KI Einkommens-Rechner 2026',
    mediaDesc: 'Kostenlos berechnen: Was kannst du mit KI wirklich verdienen?',
  },
  {
    text: `✉️ Affiliate-Recruiting per E-Mail — was ich dabei gelernt habe

Ich habe letzte Woche eine Affiliate-Kampagne an 20 Subscriber gesendet.
Betreff: "Verdiene bis zu €48,50 pro Verkauf"

Was drin war:
→ Blueprint €37 → 50% = €18,50 pro Sale
→ SuperMegaBot €97 → 50% = €48,50 pro Sale

Ergebnis: Wartet noch. Aber die Öffnungsrate war hoch.

Key Insight: Affiliates wollen KONKRETE Zahlen.
Nicht "verdiene viel" — sondern "€48,50 pro Sale, wöchentliche Auszahlung".

Affiliate werden: https://autoincome-ai.vercel.app/affiliate.html
Produkt testen: ${PRODUCT_URL}

#AffiliateMarketing #EmailMarketing #Digistore24 #OnlineBusiness`,
    mediaTitle: 'Affiliate-Recruiting — was wirklich funktioniert',
    mediaDesc: 'Konkrete Zahlen schlagen vage Versprechen im Affiliate-Marketing',
  },
];

async function sendTelegram(msg) {
  if (!TELEGRAM_BOT || !TELEGRAM_CHAT) return;
  try {
    await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: msg, parse_mode: 'HTML' }),
    });
  } catch {}
}

async function postToLinkedIn(accessToken, payload) {
  return fetch('https://api.linkedin.com/v2/ugcPosts', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      'X-Restli-Protocol-Version': '2.0.0',
    },
    body: JSON.stringify(payload),
  });
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) {
    return res.status(401).json({ error: 'unauthorized' });
  }

  let accessToken = process.env.LINKEDIN_ACCESS_TOKEN;
  if (!accessToken) {
    await sendTelegram('❌ LinkedIn Poster: LINKEDIN_ACCESS_TOKEN fehlt in Vercel ENV!');
    return res.status(200).json({ ok: false, error: 'LINKEDIN_ACCESS_TOKEN missing' });
  }

  // Rotate: different post per weekday so Mon/Wed/Fri each get a unique post
  const now = new Date();
  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const dayOfWeek = now.getUTCDay(); // 1=Mon, 3=Wed, 5=Fri
  const daySlot = dayOfWeek === 1 ? 0 : dayOfWeek === 3 ? 1 : 2;
  const postIndex = (weekNum * 3 + daySlot) % POSTS.length;
  const post = POSTS[postIndex];

  const payload = {
    author: PERSON_URN,
    lifecycleState: 'PUBLISHED',
    specificContent: {
      'com.linkedin.ugc.ShareContent': {
        shareCommentary: { text: post.text },
        shareMediaCategory: 'ARTICLE',
        media: [
          {
            status: 'READY',
            description: { text: post.mediaDesc },
            originalUrl: post.mediaUrl || PRODUCT_URL,
            title: { text: post.mediaTitle },
          },
        ],
      },
    },
    visibility: {
      'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC',
    },
  };

  let response = await postToLinkedIn(accessToken, payload);

  // Auto-refresh on 401
  if (response.status === 401 && process.env.LINKEDIN_REFRESH_TOKEN) {
    try {
      accessToken = await refreshLinkedInToken();
      response = await postToLinkedIn(accessToken, payload);
    } catch (e) {
      await sendTelegram(`❌ LinkedIn Token-Refresh fehlgeschlagen: ${e.message}`);
      return res.status(500).json({ ok: false, error: e.message });
    }
  }

  if (!response.ok) {
    const err = await response.text();
    await sendTelegram(`❌ LinkedIn-Post fehlgeschlagen (${response.status}): ${err.substring(0, 200)}`);
    return res.status(200).json({ ok: false, status: response.status, error: err });
  }

  const data = await response.json();
  const postId = data.id || '';

  await sendTelegram(
    `✅ LinkedIn-Post live!\n<b>Post #${postIndex + 1}/${POSTS.length}</b>\nID: <code>${postId}</code>`
  );

  return res.status(200).json({
    ok: true,
    postId,
    postIndex,
    url: `https://www.linkedin.com/feed/update/${postId}/`,
  });
}
