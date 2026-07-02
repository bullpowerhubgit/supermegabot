import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const SHOPIFY_DOMAIN = Deno.env.get("SHOPIFY_SHOP_DOMAIN") ?? "autopilot-store-suite-fmbka.myshopify.com";
const FB_PAGE_ID     = Deno.env.get("FACEBOOK_PAGE_ID") ?? "1016738738178786";
const FB_TOKEN       = Deno.env.get("FACEBOOK_PAGE_TOKEN") ?? "";
const TG_TOKEN       = Deno.env.get("TELEGRAM_BOT_TOKEN") ?? "";
const TG_CHAT_ID     = Deno.env.get("TELEGRAM_CHAT_ID") ?? "";
const SHOP_URL       = "https://ineedit.com.co";

const CAPTIONS = [
  "🔥 Trending jetzt: {title}\n💶 Nur €{price}\n👉 {link}\n\n#fashion #style #gadgets #deals",
  "✨ Neu im Shop: {title}\n💰 €{price} — Limitiert!\n🛒 {link}\n\n#onlineshopping #gadgets #smarthome",
  "🛍️ {title}\n💶 Jetzt für €{price}\n👆 Link im Profil oder: {link}\n\n#shopping #deals #techgadgets",
  "💥 Deal des Tages: {title}\n💵 €{price}\n🔗 {link}\n\n#sale #deals #gadgets #smarthome",
  "🎯 {title}\n⚡ Nur €{price} | Schnell zugreifen!\n{link}\n\n#deals #gadgets #techdeals",
];

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

  const p = products[Math.floor(Math.random() * products.length)];
  return {
    title: p.title ?? "Top Produkt",
    price: p.variants?.[0]?.price ?? "29.99",
    img:   p.images?.[0]?.src ?? "",
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

serve(async (_req) => {
  try {
    const prod = await getRandomProduct();
    console.log(`Produkt: ${prod.title} | €${prod.price}`);

    const [fbOk, tgOk] = await Promise.all([postFacebook(prod), postTelegram(prod)]);

    const status = { product: prod.title, price: prod.price, facebook: fbOk, telegram: tgOk };
    return new Response(JSON.stringify(status), {
      headers: { "Content-Type": "application/json" },
      status: fbOk || tgOk ? 200 : 500,
    });
  } catch (err) {
    console.error(err);
    return new Response(JSON.stringify({ error: String(err) }), { status: 500 });
  }
});
