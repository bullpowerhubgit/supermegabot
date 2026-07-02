import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const SHOPIFY_DOMAIN = Deno.env.get("SHOPIFY_SHOP_DOMAIN") ?? "autopilot-store-suite-fmbka.myshopify.com";
const FB_PAGE_ID     = Deno.env.get("FACEBOOK_PAGE_ID") ?? "1016738738178786";
const FB_TOKEN       = Deno.env.get("FACEBOOK_PAGE_TOKEN") ?? "";
const TG_TOKEN       = Deno.env.get("TELEGRAM_BOT_TOKEN") ?? "";
const TG_CHAT_ID     = Deno.env.get("TELEGRAM_CHAT_ID") ?? "";
const SHOP_URL       = "https://ineedit.com.co";
const BOT_URL        = Deno.env.get("BOT_LANDING_URL") ?? "https://dudirudibot-mega-production.up.railway.app/telegram";
const SHARE_BOT_DAILY = Deno.env.get("SHARE_BOT_DAILY") ?? "true";

const CAPTIONS = [
  "🔥 Trending jetzt: {title}\n💶 Nur €{price}\n👉 {link}\n\n#fashion #style #gadgets #deals",
  "✨ Neu im Shop: {title}\n💰 €{price} — Limitiert!\n🛒 {link}\n\n#onlineshopping #gadgets #smarthome",
  "🛍️ {title}\n💶 Jetzt für €{price}\n👆 Link im Profil oder: {link}\n\n#shopping #deals #techgadgets",
  "💥 Deal des Tages: {title}\n💵 €{price}\n🔗 {link}\n\n#sale #deals #gadgets #smarthome",
  "🎯 {title}\n⚡ Nur €{price} | Schnell zugreifen!\n{link}\n\n#deals #gadgets #techdeals",
];

// Bild-URLs die NICHT gepostet werden dürfen (Amazon-Branding, Logos, Platzhalter)
const BAD_IMG_PATTERNS = [
  "media-amazon.com",
  "ssl-images-amazon.com",
  "images-amazon.com",
  "amazon.com/images",
  "/amazon-",
  "smile",
  "prime",
  "fresh",
  "logo",
  "brand",
  "icon",
  "placeholder",
  "no-image",
  "noimage",
  "default-image",
];

function isValidProductImg(url: string): boolean {
  if (!url) return false;
  const lower = url.toLowerCase();
  // Ablehnen wenn URL Amazon-Branding oder bekannte Platzhalter enthält
  if (BAD_IMG_PATTERNS.some(p => lower.includes(p))) return false;
  // Nur HTTPS-Bilder mit Bild-Endung akzeptieren
  return /\.(jpg|jpeg|png|webp)(\?|$)/i.test(lower);
}

function getValidImg(images: any[]): string {
  if (!images?.length) return "";
  // Alle Bilder durchsuchen, erstes valides nehmen
  for (const img of images) {
    const src = img?.src ?? "";
    if (isValidProductImg(src)) return src;
  }
  return ""; // Kein valides Bild → Text-only Post
}

async function getRandomProduct() {
  const page = Math.floor(Math.random() * 5) + 1;
  const url = `https://${SHOPIFY_DOMAIN}/products.json?limit=50&page=${page}`;
  const res = await fetch(url);
  const data = await res.json();
  let products: any[] = data.products ?? [];

  if (!products.length) {
    const fallback = await fetch(`https://${SHOPIFY_DOMAIN}/products.json?limit=50`);
    const fb = await fallback.json();
    products = fb.products ?? [];
  }

  if (!products.length) throw new Error("Keine Produkte gefunden");

  // Produkte mit validen Bildern bevorzugen
  const withImg = products.filter(p => getValidImg(p.images ?? []) !== "");
  const pool    = withImg.length > 0 ? withImg : products;
  const p       = pool[Math.floor(Math.random() * pool.length)];
  const img     = getValidImg(p.images ?? []);

  console.log(`Bild: ${img ? "OK" : "FEHLT/UNGÜLTIG — Text-only"} | ${img.slice(0,60)}`);

  return {
    title: p.title ?? "Top Produkt",
    price: p.variants?.[0]?.price ?? "29.99",
    img,
    link:  `${SHOP_URL}/products/${p.handle ?? ""}`,
  };
}

function fillCaption(prod: { title: string; price: string; link: string }) {
  const tpl = CAPTIONS[Math.floor(Math.random() * CAPTIONS.length)];
  return tpl.replace("{title}", prod.title).replace("{price}", prod.price).replace("{link}", prod.link);
}

async function postFacebook(prod: any): Promise<boolean> {
  if (!FB_TOKEN) return false;
  const caption = fillCaption(prod);
  const endpoint = prod.img
    ? `https://graph.facebook.com/v21.0/${FB_PAGE_ID}/photos`
    : `https://graph.facebook.com/v21.0/${FB_PAGE_ID}/feed`;
  const body = prod.img
    ? { url: prod.img, caption, access_token: FB_TOKEN }
    : { message: caption, link: prod.link, access_token: FB_TOKEN };

  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await res.json();
  if (result.error) {
    console.error("FB error:", result.error.message);
    return false;
  }
  console.log("FB ok:", result.id ?? result.post_id);
  return true;
}

async function postTelegram(prod: any): Promise<boolean> {
  if (!TG_TOKEN || !TG_CHAT_ID) return false;
  const text = `🛍 *${prod.title}*\n💶 €${prod.price}\n[➡️ Jetzt kaufen](${prod.link})`;

  const endpoint = prod.img
    ? `https://api.telegram.org/bot${TG_TOKEN}/sendPhoto`
    : `https://api.telegram.org/bot${TG_TOKEN}/sendMessage`;
  const body = prod.img
    ? { chat_id: TG_CHAT_ID, photo: prod.img, caption: text, parse_mode: "Markdown" }
    : { chat_id: TG_CHAT_ID, text, parse_mode: "Markdown" };

  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await res.json();
  console.log("TG:", result.ok ? "ok" : result.description);
  return result.ok;
}

async function postBotPromo(): Promise<boolean> {
  if (SHARE_BOT_DAILY !== "true") return false;
  const hour = new Date().getUTCHours();
  // Nur einmal täglich um 18:00 UTC (20:00 CEST)
  if (hour !== 18) return false;

  const promoTexts = [
    `🤖 Dein Shop auf Autopilot — @DudiRudibot automatisiert Shopify, Social-Posts & Umsatz-Tracking.\n👉 ${BOT_URL}\n\n#automation #shopify #ecommerce #telegram`,
    `💡 110+ Befehle für deinen Online-Shop — direkt in Telegram.\n🛒 Shopify Sync · 📊 Revenue · 🔥 AI Trends\n👉 ${BOT_URL}\n\n#smarthome #gadgets #onlineshop`,
    `⚡ Weniger Zeit im Dashboard, mehr Umsatz.\n@DudiRudibot macht die Arbeit — du gibst die Richtung vor.\n🔗 ${BOT_URL}\n\n#aitools #shopautomation #telegram`,
  ];
  const text = promoTexts[Math.floor(Math.random() * promoTexts.length)];

  const tgRes = await fetch(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: TG_CHAT_ID, text, parse_mode: "Markdown", disable_web_page_preview: false }),
  });
  const tgData = await tgRes.json();

  const fbRes = await fetch(`https://graph.facebook.com/v21.0/${FB_PAGE_ID}/feed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text, link: BOT_URL, access_token: FB_TOKEN }),
  });
  const fbData = await fbRes.json();

  console.log("Bot promo TG:", tgData.ok, "FB:", !fbData.error);
  return tgData.ok || !fbData.error;
}

serve(async (_req) => {
  try {
    const prod = await getRandomProduct();
    console.log(`Produkt: ${prod.title} | €${prod.price}`);

    const [fbOk, tgOk, promoOk] = await Promise.all([
      postFacebook(prod),
      postTelegram(prod),
      postBotPromo(),
    ]);

    const status = { product: prod.title, price: prod.price, facebook: fbOk, telegram: tgOk, bot_promo: promoOk };
    return new Response(JSON.stringify(status), {
      headers: { "Content-Type": "application/json" },
      status: fbOk || tgOk ? 200 : 500,
    });
  } catch (err) {
    console.error(err);
    return new Response(JSON.stringify({ error: String(err) }), { status: 500 });
  }
});
