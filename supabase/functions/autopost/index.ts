import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const SHOPIFY_DOMAIN  = Deno.env.get("SHOPIFY_SHOP_DOMAIN") ?? "autopilot-store-suite-fmbka.myshopify.com";
const FB_PAGE_ID      = Deno.env.get("FACEBOOK_PAGE_ID") ?? "1016738738178786";
const FB_TOKEN        = Deno.env.get("FACEBOOK_PAGE_TOKEN") ?? "";
const FB_TOKEN_INEEDIT = Deno.env.get("FACEBOOK_PAGE_TOKEN_I_NEED_IT") ?? "";
const FB_PAGE_INEEDIT = "1058648427339278";
const IG_BUSINESS_ID  = Deno.env.get("INSTAGRAM_BUSINESS_ACCOUNT_ID") ?? "17841478315197796";
const TG_TOKEN        = Deno.env.get("TELEGRAM_BOT_TOKEN") ?? "";
const TG_CHAT_ID      = Deno.env.get("TELEGRAM_CHAT_ID") ?? "";
const LI_TOKEN        = Deno.env.get("LINKEDIN_ACCESS_TOKEN") ?? "";
const LI_PERSON_URN   = Deno.env.get("LINKEDIN_PERSON_URN") ?? "urn:li:person:YcxbqVN0ZR";
const DISCORD_TOKEN   = Deno.env.get("DISCORD_BOT_TOKEN") ?? "";
const DISCORD_CHAN    = Deno.env.get("DISCORD_CHANNEL_ID") ?? "";
const PINTEREST_TOKEN = Deno.env.get("PINTEREST_ACCESS_TOKEN") ?? "";
const PINTEREST_BOARD = Deno.env.get("PINTEREST_BOARD_ID") ?? "";
const SHOP_URL        = "https://ineedit.com.co";
const BOT_URL         = Deno.env.get("BOT_LANDING_URL") ?? "https://dudirudibot-mega-production.up.railway.app/telegram";

const CAPTIONS = [
  "🔥 Trending: {title}\n💶 Nur €{price}\n👉 {link}\n\n#smarthome #gadgets #techdeals #deals #ineedit",
  "✨ Neu im Shop: {title}\n💰 €{price} — jetzt zugreifen!\n🛒 {link}\n\n#onlineshopping #gadgets #deals",
  "🛍️ {title}\n💶 Jetzt für €{price}\n👆 {link}\n\n#shopping #techgadgets #smarthome #sale",
  "💥 Deal: {title}\n💵 €{price}\n🔗 {link}\n\n#deals #gadgets #smarthome #lifestyle",
  "🎯 {title}\n⚡ Nur €{price} | Schnell!\n{link}\n\n#techdeals #gadgets #smarthome",
  "🌟 {title} — Top Qualität!\n💶 €{price} | 🚚 Schnelle Lieferung\n{link}\n\n#shopping #deals",
];

const BAD_IMG_PATTERNS = [
  "media-amazon.com", "ssl-images-amazon.com", "images-amazon.com",
  "amazon.com/images", "logo", "brand", "icon", "placeholder",
  "no-image", "noimage", "default-image", "images.unsplash.com",
  "picsum.photos", "loremflickr", "pexels",
];

function isValidProductImg(url: string): boolean {
  if (!url) return false;
  const lower = url.toLowerCase();
  if (BAD_IMG_PATTERNS.some(p => lower.includes(p))) return false;
  return /\.(jpg|jpeg|png|webp)(\?|$)/i.test(lower);
}

function getValidImg(images: any[]): string {
  for (const img of (images ?? [])) {
    const src = img?.src ?? "";
    if (isValidProductImg(src)) return src;
  }
  return "";
}

function fillCaption(title: string, price: string, link: string) {
  const tpl = CAPTIONS[Math.floor(Math.random() * CAPTIONS.length)];
  return tpl.replace("{title}", title).replace("{price}", price).replace("{link}", link);
}

async function getRandomProduct() {
  const page = Math.floor(Math.random() * 8) + 1;
  const url  = `https://${SHOPIFY_DOMAIN}/products.json`;
  let products: any[] = [];
  for (const pg of [page, 1, 2]) {
    const res = await fetch(`${url}?limit=50&page=${pg}`);
    const data = await res.json();
    products = data.products ?? [];
    if (products.length) break;
  }
  if (!products.length) throw new Error("Keine Produkte");
  // Filter fake products (€29.99 placeholder)
  const real = products.filter(p => p.variants?.[0]?.price !== "29.99");
  const pool = real.length > 0 ? real : products;
  const withImg = pool.filter(p => getValidImg(p.images ?? []) !== "");
  const src  = withImg.length > 0 ? withImg : pool;
  const p    = src[Math.floor(Math.random() * src.length)];
  const img  = getValidImg(p.images ?? []);
  return {
    title: p.title ?? "Top Produkt",
    price: p.variants?.[0]?.price ?? "0",
    img,
    link:  `${SHOP_URL}/products/${p.handle ?? ""}`,
  };
}

async function postFacebook(prod: any, pageId = FB_PAGE_ID, token = FB_TOKEN): Promise<boolean> {
  if (!token) return false;
  const caption = fillCaption(prod.title, prod.price, prod.link);
  const endpoint = prod.img
    ? `https://graph.facebook.com/v21.0/${pageId}/photos`
    : `https://graph.facebook.com/v21.0/${pageId}/feed`;
  const body = prod.img
    ? { url: prod.img, caption, access_token: token }
    : { message: caption, link: prod.link, access_token: token };
  const res    = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const result = await res.json();
  if (result.error) { console.error("FB error:", result.error.message); return false; }
  console.log("FB ok:", result.id ?? result.post_id);
  return true;
}

async function postInstagram(prod: any): Promise<boolean> {
  if (!FB_TOKEN || !IG_BUSINESS_ID || !prod.img) return false;
  const caption = fillCaption(prod.title, prod.price, prod.link) + "\n\n#aaiitecc #ineedit";
  // Step 1: Create media container
  const r1 = await fetch(`https://graph.facebook.com/v21.0/${IG_BUSINESS_ID}/media`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_url: prod.img, caption, access_token: FB_TOKEN }),
  });
  const d1 = await r1.json();
  if (d1.error) { console.error("IG create error:", d1.error.message); return false; }
  const creationId = d1.id;
  if (!creationId) return false;
  // Step 2: Publish
  await new Promise(r => setTimeout(r, 3000));
  const r2 = await fetch(`https://graph.facebook.com/v21.0/${IG_BUSINESS_ID}/media_publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ creation_id: creationId, access_token: FB_TOKEN }),
  });
  const d2 = await r2.json();
  if (d2.error) { console.error("IG publish error:", d2.error.message); return false; }
  console.log("Instagram ok:", d2.id);
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
  const res    = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const result = await res.json();
  console.log("TG:", result.ok ? "ok" : result.description);
  return result.ok;
}

async function postLinkedIn(prod: any): Promise<boolean> {
  if (!LI_TOKEN || !LI_PERSON_URN) return false;
  const text = `🔥 ${prod.title}\n\n💶 Nur €${prod.price} — jetzt im Shop!\n👉 ${prod.link}\n\n#SmartHome #Gadgets #Deals #Ecommerce #OnlineShopping`;
  const body = {
    author: LI_PERSON_URN,
    lifecycleState: "PUBLISHED",
    specificContent: {
      "com.linkedin.ugc.ShareContent": {
        shareCommentary: { text },
        shareMediaCategory: "ARTICLE",
        media: [{ status: "READY", originalUrl: prod.link }],
      },
    },
    visibility: { "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC" },
  };
  const res = await fetch("https://api.linkedin.com/v2/ugcPosts", {
    method: "POST",
    headers: { "Authorization": `Bearer ${LI_TOKEN}`, "Content-Type": "application/json", "X-Restli-Protocol-Version": "2.0.0" },
    body: JSON.stringify(body),
  });
  if (res.status === 200 || res.status === 201) { console.log("LinkedIn ok:", (await res.json()).id); return true; }
  console.error("LinkedIn error:", res.status, await res.text());
  return false;
}

async function postDiscord(prod: any): Promise<boolean> {
  if (!DISCORD_TOKEN || !DISCORD_CHAN) return false;
  const content = `🛍️ **${prod.title}**\n💶 **€${prod.price}**\n🔗 ${prod.link}\n\n#deals #gadgets #smarthome`;
  const body: any = { content };
  if (prod.img) body.embeds = [{ image: { url: prod.img }, color: 0xC9A84C }];
  const res = await fetch(`https://discord.com/api/v10/channels/${DISCORD_CHAN}/messages`, {
    method: "POST",
    headers: { "Authorization": `Bot ${DISCORD_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 200) { console.log("Discord ok:", (await res.json()).id); return true; }
  console.error("Discord error:", res.status);
  return false;
}

async function postPinterest(prod: any): Promise<boolean> {
  if (!PINTEREST_TOKEN || !PINTEREST_BOARD || !prod.img) return false;
  const body = {
    board_id: PINTEREST_BOARD,
    title: prod.title,
    description: `💶 €${prod.price} | ${prod.link}`,
    link: prod.link,
    media_source: { source_type: "image_url", url: prod.img },
  };
  const res = await fetch("https://api.pinterest.com/v5/pins", {
    method: "POST",
    headers: { "Authorization": `Bearer ${PINTEREST_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 200 || res.status === 201) { console.log("Pinterest ok:", (await res.json()).id); return true; }
  console.error("Pinterest error:", res.status);
  return false;
}

serve(async (_req) => {
  try {
    const prod = await getRandomProduct();
    console.log(`Produkt: ${prod.title} | €${prod.price} | img=${prod.img ? "OK" : "FEHLT"}`);

    const [fbAiitec, fbIneedit, ig, tg, li, discord, pinterest] = await Promise.all([
      postFacebook(prod, FB_PAGE_ID, FB_TOKEN),
      postFacebook(prod, FB_PAGE_INEEDIT, FB_TOKEN_INEEDIT),
      postInstagram(prod),
      postTelegram(prod),
      postLinkedIn(prod),
      postDiscord(prod),
      postPinterest(prod),
    ]);

    const status = {
      product: prod.title,
      price: prod.price,
      facebook_aiitec: fbAiitec,
      facebook_ineedit: fbIneedit,
      instagram: ig,
      telegram: tg,
      linkedin: li,
      discord,
      pinterest,
      timestamp: new Date().toISOString(),
    };

    console.log("RESULT:", JSON.stringify(status));
    return new Response(JSON.stringify(status), {
      headers: { "Content-Type": "application/json" },
      status: fbAiitec || tg ? 200 : 500,
    });
  } catch (err) {
    console.error(err);
    return new Response(JSON.stringify({ error: String(err) }), { status: 500 });
  }
});
