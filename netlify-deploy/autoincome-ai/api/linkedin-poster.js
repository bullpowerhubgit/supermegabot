// LinkedIn auto-poster — DS24 product 668035 promotion
// Runs Mo/Mi/Fr 09:00 UTC via Vercel Cron

const PERSON_URN = process.env.LINKEDIN_PERSON_URN || 'urn:li:person:YcxbqVN0ZR';
const PRODUCT_URL = 'https://www.checkout-ds24.com/product/668035';
const TELEGRAM_BOT = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT = process.env.TELEGRAM_CHAT_ID;

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

Provision: 40% = €14,80 pro Verkauf
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
    mediaDesc: '40% Provision — werde Affiliate für meinen KI-Blueprint',
  },
];

async function sendTelegram(msg) {
  if (!TELEGRAM_BOT || !TELEGRAM_CHAT) return;
  await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: msg, parse_mode: 'HTML' }),
  });
}

export default async function handler(req, res) {
  const secret = req.headers['x-cron-secret'] || req.query?.secret;
  if (secret !== process.env.CRON_SECRET) {
    return res.status(401).json({ error: 'unauthorized' });
  }

  const accessToken = process.env.LINKEDIN_ACCESS_TOKEN;
  if (!accessToken) {
    return res.status(500).json({ error: 'LINKEDIN_ACCESS_TOKEN missing' });
  }

  // Rotate posts by week number
  const weekNum = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  const post = POSTS[weekNum % POSTS.length];

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
            originalUrl: PRODUCT_URL,
            title: { text: post.mediaTitle },
          },
        ],
      },
    },
    visibility: {
      'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC',
    },
  };

  const response = await fetch('https://api.linkedin.com/v2/ugcPosts', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      'X-Restli-Protocol-Version': '2.0.0',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const err = await response.text();
    await sendTelegram(`❌ LinkedIn-Post fehlgeschlagen: ${err.substring(0, 200)}`);
    return res.status(500).json({ ok: false, error: err });
  }

  const data = await response.json();
  const postId = data.id || '';

  await sendTelegram(
    `✅ LinkedIn-Post live!\n<b>Post #${(weekNum % POSTS.length) + 1}/${POSTS.length}</b>\nID: <code>${postId}</code>`
  );

  return res.status(200).json({
    ok: true,
    postId,
    postIndex: weekNum % POSTS.length,
    url: `https://www.linkedin.com/feed/update/${postId}/`,
  });
}
