#!/usr/bin/env node
import crypto from "node:crypto";
import fsSync from "node:fs";
import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { MultiAccountSync } from "./multi_account_sync.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const appRoot = path.resolve(__dirname, "..");
const publicDir = path.join(appRoot, "www");
const statePath = path.join(__dirname, "sync_state.json");
const envLocalPath = path.join(appRoot, ".env.local");

function loadEnvFile(filePath) {
  if (!fsSync.existsSync(filePath)) {
    return;
  }

  const raw = fsSync.readFileSync(filePath, "utf8");
  for (const line of raw.split(/\r?\n/u)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const splitIndex = trimmed.indexOf("=");
    if (splitIndex <= 0) {
      continue;
    }

    const key = trimmed.slice(0, splitIndex).trim();
    let value = trimmed.slice(splitIndex + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }

    if (!Object.prototype.hasOwnProperty.call(process.env, key)) {
      process.env[key] = value;
    }
  }
}

loadEnvFile(path.join(appRoot, ".env.local"));
loadEnvFile(path.join(appRoot, ".env"));
// Also load supermegabot .env for broader API key coverage
loadEnvFile(path.join(process.env.HOME || appRoot, "supermegabot", ".env"));

function loadGoogleClientFile() {
  const explicitPath = (process.env.GOOGLE_OAUTH_CLIENT_FILE || "").trim();
  const downloadsDir = path.join(process.env.HOME || appRoot, "Downloads");
  const implicitCandidates = fsSync.existsSync(downloadsDir)
    ? fsSync
        .readdirSync(downloadsDir)
        .filter((name) => /^client_secret_.*\.apps\.googleusercontent\.com\.json$/u.test(name))
        .map((name) => path.join(downloadsDir, name))
    : [];

  const candidatePath = explicitPath || (implicitCandidates.length === 1 ? implicitCandidates[0] : "");
  if (!candidatePath || !fsSync.existsSync(candidatePath)) {
    return;
  }

  const raw = fsSync.readFileSync(candidatePath, "utf8");
  const payload = JSON.parse(raw);
  const oauthConfig = payload.web || payload.installed;
  if (!oauthConfig) {
    return;
  }

  if (!process.env.GOOGLE_CLIENT_ID && oauthConfig.client_id) {
    process.env.GOOGLE_CLIENT_ID = oauthConfig.client_id;
  }
  if (!process.env.GOOGLE_CLIENT_SECRET && oauthConfig.client_secret) {
    process.env.GOOGLE_CLIENT_SECRET = oauthConfig.client_secret;
  }
  if (!process.env.GOOGLE_REDIRECT_URI) {
    const localhostRedirect = (oauthConfig.redirect_uris || []).find((uri) =>
      uri.startsWith("http://localhost:")
    );
    if (localhostRedirect) {
      process.env.GOOGLE_REDIRECT_URI = localhostRedirect;
    }
  }
}

loadGoogleClientFile();

const port = Number.parseInt(process.env.SYNC_PORT || "3041", 10);

const googleClientId = (process.env.GOOGLE_CLIENT_ID || "").trim();
const googleClientSecret = (process.env.GOOGLE_CLIENT_SECRET || "").trim();
const googleRedirectUri = (
  process.env.GOOGLE_REDIRECT_URI || `http://localhost:${port}/oauth/google/callback`
).trim();
let stripeSecretKey = (process.env.STRIPE_SECRET_KEY || "").trim();
let stripePublishableKey = (process.env.STRIPE_PUBLISHABLE_KEY || "").trim();
const stripeWebhookSecret = (process.env.STRIPE_WEBHOOK_SECRET || "").trim();
const stripePriceStarter = (process.env.STRIPE_PRICE_STARTER || "").trim();
const stripePricePro = (process.env.STRIPE_PRICE_PRO || "").trim();
const stripePriceEnterprise = (process.env.STRIPE_PRICE_ENTERPRISE || "").trim();
const stripeLinkStarter = (process.env.STRIPE_LINK_STARTER || "https://buy.stripe.com/live_REPLACE_STARTER").trim();
const stripeLinkPro = (process.env.STRIPE_LINK_PRO || "https://buy.stripe.com/live_REPLACE_PRO").trim();
const stripeLinkEnterprise = (
  process.env.STRIPE_LINK_ENTERPRISE || "https://buy.stripe.com/live_REPLACE_ENTERPRISE"
).trim();

// === MULTI-ACCOUNT EMAIL SYNC WITH AES ===
const email1 = (process.env.EMAIL_ACCOUNT_1 || "bullpowersrtkennel@gmail.com").trim();
const email2 = (process.env.EMAIL_ACCOUNT_2 || "aiitecbuuss@gmail.com").trim();
const aesEncryptionKey = (process.env.AES_ENCRYPTION_KEY || "").trim();

let multiAccountSync = null;
if (aesEncryptionKey && aesEncryptionKey.length === 64) {
  try {
    multiAccountSync = new MultiAccountSync(aesEncryptionKey);
    console.log(`✓ Multi-Account Sync initialized for: ${email1} + ${email2}`);
  } catch (e) {
    console.warn(`⚠ Multi-Account Sync init failed: ${e.message}`);
  }
} else if (aesEncryptionKey) {
  console.warn("⚠ AES_ENCRYPTION_KEY ungültig (muss 64 hex Zeichen sein)");
}

// ─── Stripe API Helper ───────────────────────────────────────────────────────

async function stripeRequest(method, path, body = null) {
  if (!stripeSecretKey) {
    throw new Error("STRIPE_SECRET_KEY not configured");
  }

  const opts = {
    method,
    headers: {
      Authorization: `Bearer ${stripeSecretKey}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
  };

  if (body) {
    opts.body = new URLSearchParams(body).toString();
  }

  const response = await fetch(`https://api.stripe.com/v1${path}`, opts);
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.error?.message || `Stripe API error ${response.status}`);
  }

  return payload;
}

async function stripeVerifyWebhook(rawBody, signature) {
  if (!stripeWebhookSecret) {
    return null;
  }

  const parts = String(signature || "").split(",");
  const tPart = parts.find((p) => p.startsWith("t="));
  const v1Part = parts.find((p) => p.startsWith("v1="));
  if (!tPart || !v1Part) {
    return null;
  }

  const timestamp = tPart.slice(2);
  const expectedSig = v1Part.slice(3);
  const signedPayload = `${timestamp}.${rawBody}`;

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(stripeWebhookSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const computed = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(signedPayload));
  const computedHex = Array.from(new Uint8Array(computed))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return computedHex === expectedSig ? JSON.parse(rawBody) : null;
}

function planFromStripePrice(priceId) {
  if (!priceId) {
    return null;
  }
  if (priceId === stripePricePro || priceId.includes("pro")) {
    return "pro";
  }
  if (priceId === stripePriceEnterprise || priceId.includes("enterprise")) {
    return "enterprise";
  }
  if (priceId === stripePriceStarter || priceId.includes("starter")) {
    return "starter";
  }
  return "starter";
}
const googleScopes = [
  "openid",
  "email",
  "profile",
];

const cryptoPlatformMatchers = [
  { id: "binance", name: "Binance", terms: ["binance"] },
  { id: "kraken", name: "Kraken", terms: ["kraken"] },
  { id: "coinbase", name: "Coinbase", terms: ["coinbase"] },
  { id: "bitpanda", name: "Bitpanda", terms: ["bitpanda"] },
  { id: "bybit", name: "Bybit", terms: ["bybit"] },
  { id: "kucoin", name: "KuCoin", terms: ["kucoin"] },
  { id: "okx", name: "OKX", terms: ["okx"] },
  { id: "bitget", name: "Bitget", terms: ["bitget"] },
  { id: "gateio", name: "Gate.io", terms: ["gate.io", "gateio"] },
  { id: "mexc", name: "MEXC", terms: ["mexc"] },
  { id: "cryptocom", name: "Crypto.com", terms: ["crypto.com", "crypto com"] },
  { id: "blockchain", name: "Blockchain.com", terms: ["blockchain.com", "blockchain"] },
  { id: "moonpay", name: "MoonPay", terms: ["moonpay"] },
  { id: "ramp", name: "Ramp", terms: ["ramp.network", "ramp network"] },
  { id: "banxa", name: "Banxa", terms: ["banxa"] },
  { id: "transak", name: "Transak", terms: ["transak"] },
];

const cancellationTargets = {
  netflix: {
    id: "netflix",
    name: "Netflix",
    cancelUrl: "https://www.netflix.com/CancelPlan",
    manageUrl: "https://www.netflix.com/YourAccount",
  },
  spotify: {
    id: "spotify",
    name: "Spotify",
    cancelUrl: "https://www.spotify.com/account/subscription/",
    manageUrl: "https://www.spotify.com/account/subscription/",
  },
  chatgpt: {
    id: "chatgpt",
    name: "ChatGPT",
    cancelUrl: "https://chatgpt.com/#settings/Billing",
    manageUrl: "https://chatgpt.com/#settings/Billing",
  },
  canva: {
    id: "canva",
    name: "Canva",
    cancelUrl: "https://www.canva.com/settings/billing-and-teams",
    manageUrl: "https://www.canva.com/settings/billing-and-teams",
  },
  notion: {
    id: "notion",
    name: "Notion",
    cancelUrl: "https://www.notion.so/my-account",
    manageUrl: "https://www.notion.so/my-account",
  },
  adobe: {
    id: "adobe",
    name: "Adobe",
    cancelUrl: "https://account.adobe.com/plans",
    manageUrl: "https://account.adobe.com/plans",
  },
  shopify: {
    id: "shopify",
    name: "Shopify",
    cancelUrl: "https://admin.shopify.com/store/*/settings/plan",
    manageUrl: "https://admin.shopify.com/store/*/settings/plan",
  },
  paypal: {
    id: "paypal",
    name: "PayPal",
    cancelUrl: "https://www.paypal.com/myaccount/autopay/",
    manageUrl: "https://www.paypal.com/myaccount/autopay/",
  },
};

const defaultState = {
  google: null,
  queue: [],
  reminders: [],
  oauthStates: {},
  kmuSuite: {
    trial: {
      startedAt: null,
      expiresAt: null,
      active: false,
    },
    offers: [],
    leads: [],
    callbacks: [],
    shifts: [],
  },
};

const platformTargets = [
  {
    id: "telegram-automation-bot",
    name: "Telegram Automation Bot",
    type: "automation",
    url: "http://localhost:3000/api/health",
    launchUrl: "http://localhost:3000",
  },
  {
    id: "creatorai-backend",
    name: "CreatorAI Ultra Backend",
    type: "api",
    url: "http://localhost:3001/health",
    launchUrl: "http://localhost:3001/health",
  },
  {
    id: "digistore24-automation",
    name: "Digistore24 Automation",
    type: "revenue",
    url: "http://localhost:3010/api/digistore/stats",
    launchUrl: "http://localhost:3010",
  },
  {
    id: "autoincome-ai",
    name: "AutoIncome AI",
    type: "billing",
    url: "http://localhost:3020",
    launchUrl: "http://localhost:3020",
  },
  {
    id: "monetization-hub",
    name: "Monetization Hub",
    type: "dashboard",
    url: "http://localhost:3030",
    launchUrl: "http://localhost:3030",
  },
  {
    id: "steuercockpit",
    name: "Steuercockpit",
    type: "dashboard",
    url: "http://localhost:3032",
    launchUrl: "http://localhost:3032",
  },
  {
    id: "subscription-assistant",
    name: "Subscription Assistant",
    type: "assistant",
    url: `http://localhost:${port}/health`,
    launchUrl: `http://localhost:${port}/assistant`,
  },
];

async function readState() {
  try {
    const raw = await fs.readFile(statePath, "utf8");
    return { ...defaultState, ...JSON.parse(raw) };
  } catch (error) {
    if (error.code === "ENOENT") {
      return structuredClone(defaultState);
    }
    throw error;
  }
}

async function writeState(nextState) {
  await fs.writeFile(statePath, `${JSON.stringify(nextState, null, 2)}\n`, "utf8");
}

function json(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(`${JSON.stringify(payload, null, 2)}\n`);
}

async function readJsonBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  return raw ? JSON.parse(raw) : {};
}

async function updateEnvLocal(updates) {
  let raw = "";
  try {
    raw = await fs.readFile(envLocalPath, "utf8");
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }

  let next = raw;
  for (const [key, value] of Object.entries(updates)) {
    const normalizedValue = String(value ?? "").replace(/\s+/g, "");
    const pattern = new RegExp(`^${key}=.*$`, "m");
    if (pattern.test(next)) {
      next = next.replace(pattern, `${key}=${normalizedValue}`);
    } else {
      if (next && !next.endsWith("\n")) {
        next += "\n";
      }
      next += `${key}=${normalizedValue}\n`;
    }
  }

  if (next && !next.endsWith("\n")) {
    next += "\n";
  }

  await fs.writeFile(envLocalPath, next, "utf8");
}

function sanitizeState(state) {
  const google = state.google
    ? {
        connected: true,
        email: state.google.email || null,
        scopes: state.google.scopes || [],
        connectedAt: state.google.connectedAt || null,
        expiresAt: state.google.expiresAt || null,
      }
    : {
        connected: false,
      };

  return {
    google,
    queue: state.queue || [],
    reminders: state.reminders || [],
  };
}

async function serveFile(res, filePath) {
  const ext = path.extname(filePath);
  const contentType =
    {
      ".html": "text/html; charset=utf-8",
      ".js": "text/javascript; charset=utf-8",
      ".json": "application/json; charset=utf-8",
      ".css": "text/css; charset=utf-8",
    }[ext] || "text/plain; charset=utf-8";

  const content = await fs.readFile(filePath);
  res.writeHead(200, { "Content-Type": contentType, "Cache-Control": "no-store" });
  res.end(content);
}

async function getGoogleTokensFromCode(code) {
  const body = new URLSearchParams({
    code,
    client_id: googleClientId,
    client_secret: googleClientSecret,
    redirect_uri: googleRedirectUri,
    grant_type: "authorization_code",
  });

  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error_description || payload.error || "Google token exchange failed");
  }

  return payload;
}

async function refreshGoogleAccessToken(refreshToken) {
  const body = new URLSearchParams({
    client_id: googleClientId,
    client_secret: googleClientSecret,
    refresh_token: refreshToken,
    grant_type: "refresh_token",
  });

  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error_description || payload.error || "Google token refresh failed");
  }

  return payload;
}

async function fetchGoogleProfile(accessToken) {
  const response = await fetch("https://www.googleapis.com/oauth2/v2/userinfo", {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error?.message || "Failed to fetch Google profile");
  }
  return payload;
}

async function ensureGoogleAccessToken(state) {
  if (!state.google?.refreshToken) {
    throw new Error("Google is not connected");
  }

  const currentExpiresAt = Date.parse(state.google.expiresAt || "");
  if (state.google.accessToken && Number.isFinite(currentExpiresAt) && currentExpiresAt > Date.now() + 60_000) {
    return { state, accessToken: state.google.accessToken };
  }

  const refreshed = await refreshGoogleAccessToken(state.google.refreshToken);
  const nextState = {
    ...state,
    google: {
      ...state.google,
      accessToken: refreshed.access_token,
      expiresAt: new Date(Date.now() + (refreshed.expires_in || 3600) * 1000).toISOString(),
    },
  };
  await writeState(nextState);
  return { state: nextState, accessToken: refreshed.access_token };
}

async function fetchPlatformStatus(target) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 3000);
  try {
    const response = await fetch(target.url, { signal: controller.signal });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : null;
    const summary =
      target.id === "digistore24-automation" && payload
        ? `Revenue ${payload.total?.revenue ?? 0} / Count ${payload.total?.count ?? 0}`
        : payload?.status || response.statusText;

    return {
      ...target,
      online: response.ok,
      statusCode: response.status,
      summary,
    };
  } catch (error) {
    return {
      ...target,
      online: false,
      statusCode: 0,
      summary: error.name === "AbortError" ? "timeout" : "offline",
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function listPlatformStatuses(state) {
  const statuses = await Promise.all(platformTargets.map((target) => fetchPlatformStatus(target)));
  statuses.unshift({
    id: "google-account",
    name: "Google Account",
    type: "identity",
    url: `http://localhost:${port}/api/oauth/google/start`,
    launchUrl: `http://localhost:${port}/assistant`,
    online: Boolean(state.google?.email),
    statusCode: state.google?.email ? 200 : 0,
    summary: state.google?.email || "not connected",
  });
  return statuses;
}

async function buildConnectAllStatus(state) {
  const platforms = await listPlatformStatuses(state);
  const onlineCount = platforms.filter((platform) => platform.online).length;
  const totalCount = platforms.length;
  const googleConfigured = Boolean(googleClientId && googleClientSecret);
  const googleConnected = Boolean(state.google?.email);

  const checklist = [
    {
      id: "bridge",
      title: "Local Sync Bridge",
      ready: true,
      detail: `http://localhost:${port}`,
    },
    {
      id: "google-config",
      title: "Google OAuth Konfiguration",
      ready: googleConfigured,
      detail: googleConfigured
        ? "GOOGLE_CLIENT_ID und GOOGLE_CLIENT_SECRET gesetzt"
        : "GOOGLE_CLIENT_ID und GOOGLE_CLIENT_SECRET fehlen",
    },
    {
      id: "google-connection",
      title: "Google Konto verbunden",
      ready: googleConnected,
      detail: googleConnected ? state.google.email : "Noch nicht verbunden",
    },
    {
      id: "platforms",
      title: "Lokale Plattformen erreichbar",
      ready: onlineCount > 1,
      detail: `${onlineCount}/${totalCount} online`,
    },
  ];

  return {
    ready: checklist.every((item) => item.ready),
    onlineCount,
    totalCount,
    checklist,
    connectGoogleUrl: "/api/oauth/google/start",
    assistantUrl: "/assistant",
    platforms,
  };
}

async function gmailSearch(accessToken, query, maxResults = 10) {
  const listResponse = await fetch(
    `https://gmail.googleapis.com/gmail/v1/users/me/messages?${new URLSearchParams({
      q: query,
      maxResults: String(Math.max(1, Math.min(Number(maxResults) || 10, 100))),
    })}`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    }
  );
  const listPayload = await listResponse.json();
  if (!listResponse.ok) {
    throw new Error(listPayload.error?.message || "Failed to search Gmail");
  }

  const messages = listPayload.messages || [];
  const detailedMessages = await Promise.all(
    messages.map(async ({ id, threadId }) => {
      const response = await fetch(
        `https://gmail.googleapis.com/gmail/v1/users/me/messages/${id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date`,
        {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        }
      );
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error?.message || `Failed to read Gmail message ${id}`);
      }

      const headers = Object.fromEntries((payload.payload?.headers || []).map((header) => [header.name, header.value]));
      return {
        id,
        threadId,
        from: headers.From || "",
        subject: headers.Subject || "",
        date: headers.Date || "",
        snippet: payload.snippet || "",
        link: `https://mail.google.com/mail/u/0/#inbox/${id}`,
      };
    })
  );

  return detailedMessages;
}

function buildDefaultCryptoQuery() {
  const tokens = cryptoPlatformMatchers
    .flatMap((platform) => platform.terms)
    .map((term) => `"${term}"`);
  return `(${tokens.join(" OR ")}) newer_than:1825d`;
}

function toNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizePlatformId(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/gu, "");
}

function classifySubscription(item) {
  const monthlyCost = Math.max(0, toNumber(item.monthlyCost));
  const usedDays30 = Math.max(0, Math.min(30, toNumber(item.usedDays30, 0)));
  const hasFreePlan = Boolean(item.hasFreePlan);
  const critical = Boolean(item.critical);
  const targetPlanPrice = Math.max(0, toNumber(item.targetPlanPrice, 0));

  if (critical) {
    return {
      action: "keep",
      reason: "Kritisch markiert",
      monthlySavings: 0,
      priority: "low",
    };
  }

  if (usedDays30 <= 1) {
    return {
      action: "cancel",
      reason: "Fast keine Nutzung in den letzten 30 Tagen",
      monthlySavings: monthlyCost,
      priority: monthlyCost >= 20 ? "high" : "medium",
    };
  }

  if (hasFreePlan && usedDays30 <= 6) {
    return {
      action: "downgrade",
      reason: "Niedrige Nutzung und Free-Plan verfuegbar",
      monthlySavings: Math.max(0, monthlyCost - targetPlanPrice),
      priority: monthlyCost >= 15 ? "high" : "medium",
    };
  }

  if (monthlyCost >= 40 && usedDays30 <= 10) {
    return {
      action: "downgrade",
      reason: "Hohe Kosten bei moderater Nutzung",
      monthlySavings: Math.max(0, monthlyCost - targetPlanPrice),
      priority: "high",
    };
  }

  return {
    action: "keep",
    reason: "Nutzung rechtfertigt aktuellen Tarif",
    monthlySavings: 0,
    priority: "low",
  };
}

function buildSubscriptionOptimization(subscriptions) {
  const normalized = subscriptions.map((entry, index) => {
    const monthlyCost = Math.max(0, toNumber(entry.monthlyCost));
    const suggestion = classifySubscription(entry);
    return {
      id: entry.id || crypto.randomUUID(),
      index,
      name: (entry.name || `Abo ${index + 1}`).trim(),
      platform: (entry.platform || "unknown").trim(),
      monthlyCost,
      usedDays30: Math.max(0, Math.min(30, toNumber(entry.usedDays30, 0))),
      hasFreePlan: Boolean(entry.hasFreePlan),
      currentPlan: (entry.currentPlan || "paid").trim(),
      targetPlan: (entry.targetPlan || (entry.hasFreePlan ? "free" : "basic")).trim(),
      targetPlanPrice: Math.max(0, toNumber(entry.targetPlanPrice, 0)),
      critical: Boolean(entry.critical),
      ...suggestion,
    };
  });

  const totalMonthly = normalized.reduce((sum, item) => sum + item.monthlyCost, 0);
  const potentialSavings = normalized.reduce((sum, item) => sum + item.monthlySavings, 0);
  const optimizedMonthly = Math.max(0, totalMonthly - potentialSavings);

  return {
    totalSubscriptions: normalized.length,
    totalMonthly,
    potentialSavings,
    optimizedMonthly,
    actions: {
      cancel: normalized.filter((item) => item.action === "cancel").length,
      downgrade: normalized.filter((item) => item.action === "downgrade").length,
      keep: normalized.filter((item) => item.action === "keep").length,
    },
    items: normalized.sort((a, b) => {
      if (b.monthlySavings !== a.monthlySavings) {
        return b.monthlySavings - a.monthlySavings;
      }
      return b.monthlyCost - a.monthlyCost;
    }),
  };
}

function buildCancellationPlan(item) {
  const platformId = normalizePlatformId(item.platform);
  const target = cancellationTargets[platformId] || null;
  const action = String(item.action || "cancel").toLowerCase() === "downgrade" ? "downgrade" : "cancel";
  const monthlyCost = Math.max(0, toNumber(item.monthlyCost));
  const targetPlanPrice = Math.max(0, toNumber(item.targetPlanPrice, 0));
  const monthlySavings = action === "cancel" ? monthlyCost : Math.max(0, monthlyCost - targetPlanPrice);

  const steps = [
    target
      ? `1. Oeffne ${target.manageUrl}`
      : "1. Oeffne die Konto- und Abo-Einstellungen der Plattform",
    action === "cancel"
      ? "2. Waehle Kuendigung des aktiven Tarifs"
      : `2. Wechsle auf Tarif ${item.targetPlan || "free"}`,
    "3. Speichere Zahlungsbeleg oder Screenshot",
    "4. Setze Reminder fuer das naechste Abrechnungsdatum",
  ];

  return {
    platform: item.platform || "unknown",
    platformId,
    action,
    supportedDirectLink: Boolean(target),
    cancelUrl: target?.cancelUrl || null,
    manageUrl: target?.manageUrl || null,
    monthlySavings,
    steps,
    note: target
      ? "Direktlink verfuegbar. Abschluss muss aus Sicherheitsgruenden vom Nutzer bestaetigt werden."
      : "Kein Direktlink hinterlegt. Bitte Plattform manuell aufrufen.",
  };
}

function discoverCryptoPlatformsFromMessages(messages) {
  const map = new Map();

  for (const platform of cryptoPlatformMatchers) {
    map.set(platform.id, {
      id: platform.id,
      name: platform.name,
      evidenceCount: 0,
      latestDate: null,
      sample: null,
    });
  }

  for (const message of messages) {
    const haystack = `${message.from} ${message.subject} ${message.snippet}`.toLowerCase();
    const messageDate = Date.parse(message.date || "");

    for (const platform of cryptoPlatformMatchers) {
      const hit = platform.terms.some((term) => haystack.includes(term.toLowerCase()));
      if (!hit) {
        continue;
      }

      const current = map.get(platform.id);
      current.evidenceCount += 1;
      if (!current.sample) {
        current.sample = {
          from: message.from,
          subject: message.subject,
          date: message.date,
          link: message.link,
        };
      }

      if (Number.isFinite(messageDate)) {
        const currentDate = Date.parse(current.latestDate || "");
        if (!Number.isFinite(currentDate) || messageDate > currentDate) {
          current.latestDate = new Date(messageDate).toISOString();
        }
      }
    }
  }

  return Array.from(map.values())
    .filter((item) => item.evidenceCount > 0)
    .sort((a, b) => {
      if (b.evidenceCount !== a.evidenceCount) {
        return b.evidenceCount - a.evidenceCount;
      }
      const ad = Date.parse(a.latestDate || "");
      const bd = Date.parse(b.latestDate || "");
      if (Number.isFinite(ad) && Number.isFinite(bd)) {
        return bd - ad;
      }
      return a.name.localeCompare(b.name, "de");
    });
}

async function createCalendarReminder(accessToken, summary, dateTime) {
  const start = new Date(dateTime);
  const end = new Date(start.getTime() + 30 * 60 * 1000);
  const response = await fetch("https://www.googleapis.com/calendar/v3/calendars/primary/events", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      summary,
      start: { dateTime: start.toISOString() },
      end: { dateTime: end.toISOString() },
    }),
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error?.message || "Failed to create Google Calendar event");
  }

  return payload;
}

function googleConfigSummary(state) {
  return {
    configured: Boolean(googleClientId && googleClientSecret),
    redirectUri: googleRedirectUri,
    scopes: googleScopes,
    google: sanitizeState(state).google,
  };
}

function sanitizeKmuSuite(state) {
  const suite = state.kmuSuite || {};
  const trial = suite.trial || {};
  const expiresAtMs = Date.parse(trial.expiresAt || "");
  const trialActive = Boolean(trial.active) && Number.isFinite(expiresAtMs) && expiresAtMs > Date.now();
  const daysLeft = trialActive ? Math.max(0, Math.ceil((expiresAtMs - Date.now()) / 86_400_000)) : 0;
  return {
    trial: {
      startedAt: trial.startedAt || null,
      expiresAt: trial.expiresAt || null,
      active: trialActive,
      daysLeft,
    },
    offers: suite.offers || [],
    leads: suite.leads || [],
    callbacks: suite.callbacks || [],
    shifts: suite.shifts || [],
  };
}

function buildKmuPlans() {
  return {
    currency: "EUR",
    plans: [
      {
        id: "starter",
        name: "Starter",
        pricePerMonth: 49,
        checkoutUrl: stripeLinkStarter,
        features: ["50 Leads / Monat", "Angebotsgenerator", "CSV Export"],
      },
      {
        id: "pro",
        name: "Pro",
        pricePerMonth: 149,
        checkoutUrl: stripeLinkPro,
        features: ["500 Leads / Monat", "Lead Scoring", "Rueckruf-Workflow"],
      },
      {
        id: "enterprise",
        name: "Enterprise",
        pricePerMonth: 499,
        checkoutUrl: stripeLinkEnterprise,
        features: ["Unbegrenzt", "Mehrere Teams", "Prioritaets-Support"],
      },
    ],
  };
}

function scoreLead(lead) {
  let score = 0;
  const budget = Number.parseFloat(String(lead.budget || "0"));
  if (Number.isFinite(budget)) {
    if (budget >= 2000) score += 45;
    else if (budget >= 1000) score += 30;
    else if (budget >= 500) score += 15;
  }

  const urgency = String(lead.urgency || "").toLowerCase();
  if (urgency === "sofort") score += 30;
  if (urgency === "diese_woche") score += 20;
  if (urgency === "dieser_monat") score += 10;

  const channel = String(lead.channel || "").toLowerCase();
  if (channel === "whatsapp") score += 15;
  if (channel === "telegram") score += 12;
  if (channel === "web") score += 8;

  const useCase = String(lead.useCase || "").trim();
  if (useCase.length > 24) score += 10;

  const normalized = Math.max(0, Math.min(100, score));
  const grade = normalized >= 70 ? "A" : normalized >= 50 ? "B" : normalized >= 30 ? "C" : "D";
  const nextAction =
    grade === "A"
      ? "Heute anrufen und Angebot senden"
      : grade === "B"
        ? "Innerhalb von 24h Rueckruf einplanen"
        : grade === "C"
          ? "Nurturing-Nachricht senden"
          : "In 7 Tagen Follow-up";

  return { score: normalized, grade, nextAction };
}

function buildOfferText(offer) {
  const price = Number.parseFloat(String(offer.price || "0"));
  const days = Number.parseInt(String(offer.deliveryDays || "7"), 10);
  return [
    `Angebot fuer ${offer.company}`,
    "",
    `Kontakt: ${offer.contact || "-"}`,
    `Leistung: ${offer.service}`,
    `Lieferzeit: ${Number.isFinite(days) ? days : 7} Tage`,
    `Preis: ${Number.isFinite(price) ? price.toFixed(2) : "0.00"} EUR zzgl. USt`,
    "",
    "Leistungsumfang:",
    "- Setup und Konfiguration",
    "- Schulung (30 Minuten)",
    "- 14 Tage Support nach Go-Live",
    "",
    `Notizen: ${offer.notes || "keine"}`,
    "",
    "Dieses Angebot ist 14 Tage gueltig.",
  ].join("\n");
}

function buildShiftSummary(shift) {
  const labels = {
    "1": "Fruehschicht",
    "2": "Spaetschicht",
    "3": "Nachtschicht",
  };
  const label = labels[String(shift.shiftType || "")] || "Schicht";
  const nurses = Number.parseInt(String(shift.requiredNurses || "0"), 10);
  return `${label} fuer ${shift.company}: ${Number.isFinite(nurses) ? nurses : 0} Pflegekraefte benoetigt.`;
}

function normalizeShiftType(value) {
  const normalized = String(value || "1").trim();
  return ["1", "2", "3"].includes(normalized) ? normalized : "1";
}

function generateShiftDistributions(requiredNurses) {
  const n = Number.parseInt(String(requiredNurses || "0"), 10) || 0;
  if (n <= 0) return [];

  const distributions = [];
  const teamSizes = [5, 4, 3, 2];

  for (const size of teamSizes) {
    const numTeams = Math.ceil(n / size);
    const lastTeamSize = n - (numTeams - 1) * size;
    const valid = lastTeamSize > 0;

    if (valid) {
      const teams = [];
      for (let i = 0; i < numTeams - 1; i += 1) {
        teams.push(size);
      }
      teams.push(lastTeamSize);

      distributions.push({
        teamSize: size,
        totalTeams: numTeams,
        breakdown: teams,
        efficiency: ((n / (numTeams * size)) * 100).toFixed(1),
        description: `${numTeams}x Team(s) mit je ${size} Personen (effiziente Verteilung: ${((n / (numTeams * size)) * 100).toFixed(1)}%)`,
      });
    }
  }

  return distributions.sort((a, b) => Number.parseFloat(b.efficiency) - Number.parseFloat(a.efficiency));
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", `http://${req.headers.host}`);
    const state = await readState();

    if (req.method === "GET" && url.pathname === "/health") {
      return json(res, 200, { status: "ok", port });
    }

    if (req.method === "GET" && url.pathname === "/") {
      return serveFile(res, path.join(publicDir, "index.html"));
    }

    if (req.method === "GET" && url.pathname === "/assistant") {
      return serveFile(res, path.join(publicDir, "subscription-assistant.html"));
    }

    if (req.method === "GET" && url.pathname === "/kmu-suite") {
      return serveFile(res, path.join(publicDir, "kmu-suite.html"));
    }

    if (req.method === "GET" && url.pathname === "/api/platforms/status") {
      return json(res, 200, { platforms: await listPlatformStatuses(state) });
    }

    if (req.method === "GET" && url.pathname === "/api/assistant/state") {
      return json(res, 200, {
        ...sanitizeState(state),
        platforms: await listPlatformStatuses(state),
      });
    }

    if (req.method === "GET" && url.pathname === "/api/setup/connect-all") {
      return json(res, 200, await buildConnectAllStatus(state));
    }

    if (req.method === "GET" && url.pathname === "/api/monitor/status") {
      const forceRefresh = url.searchParams.get("refresh") === "1";
      if (forceRefresh) {
        return json(res, 200, await runHealthCheck());
      }
      return json(res, 200, await getMonitorState());
    }

    // ─── Stripe Plugin ───────────────────────────────────────────────────────

    if (req.method === "POST" && url.pathname === "/api/stripe/config") {
      const body = await readJsonBody(req);
      const nextSecretKey = String(body.secretKey || "").replace(/\s+/g, "");
      const nextPublishableKey = String(body.publishableKey || "").replace(/\s+/g, "");

      if (!nextSecretKey && !nextPublishableKey) {
        return json(res, 400, {
          error: "missing_config",
          message: "Gib mindestens einen Stripe Key ein.",
        });
      }

      if (nextSecretKey && !/^(sk|rk)_(live|test)_/u.test(nextSecretKey)) {
        return json(res, 400, {
          error: "invalid_secret_key",
          message: "Secret Key muss mit sk_live_, sk_test_, rk_live_ oder rk_test_ beginnen.",
        });
      }

      if (nextPublishableKey && !/^pk_(live|test)_/u.test(nextPublishableKey)) {
        return json(res, 400, {
          error: "invalid_publishable_key",
          message: "Publishable Key muss mit pk_live_ oder pk_test_ beginnen.",
        });
      }

      const updates = {};
      if (nextSecretKey) {
        updates.STRIPE_SECRET_KEY = nextSecretKey;
      }
      if (nextPublishableKey) {
        updates.STRIPE_PUBLISHABLE_KEY = nextPublishableKey;
      }

      await updateEnvLocal(updates);

      if (nextSecretKey) {
        stripeSecretKey = nextSecretKey;
        process.env.STRIPE_SECRET_KEY = nextSecretKey;
      }
      if (nextPublishableKey) {
        stripePublishableKey = nextPublishableKey;
        process.env.STRIPE_PUBLISHABLE_KEY = nextPublishableKey;
      }

      return json(res, 200, {
        saved: true,
        configured: Boolean(stripeSecretKey),
        stripeSecretKeySet: Boolean(stripeSecretKey),
        stripePublishableKeySet: Boolean(stripePublishableKey),
        message: "Stripe Keys gespeichert und sofort aktiv.",
      });
    }

    if (req.method === "GET" && url.pathname === "/api/stripe/status") {
      const configured = Boolean(stripeSecretKey);
      const suite = state.kmuSuite || {};
      const sub = suite.stripeSubscription || null;
      return json(res, 200, {
        configured,
        stripeSecretKeySet: Boolean(stripeSecretKey),
        stripePublishableKeySet: Boolean(stripePublishableKey),
        webhookConfigured: Boolean(stripeWebhookSecret),
        pricesConfigured: Boolean(stripePriceStarter || stripePricePro || stripePriceEnterprise),
        paymentLinks: {
          starter: stripeLinkStarter,
          pro: stripeLinkPro,
          enterprise: stripeLinkEnterprise,
        },
        subscription: sub,
        plan: suite.plan || null,
        trial: suite.trial || null,
      });
    }

    if (req.method === "POST" && url.pathname === "/api/stripe/checkout/create") {
      if (!stripeSecretKey) {
        return json(res, 400, {
          error: "stripe_not_configured",
          message: "STRIPE_SECRET_KEY fehlt in .env.local",
          hint: "Trage deinen Stripe Secret Key ein und starte die Bridge neu.",
        });
      }

      const body = await readJsonBody(req);
      const priceId = (body.priceId || "").trim();
      const plan = (body.plan || "starter").trim();
      const email = (body.email || "").trim();
      const successUrl = (body.successUrl || `http://localhost:${port}/assistant?stripe=success`).trim();
      const cancelUrl = (body.cancelUrl || `http://localhost:${port}/assistant?stripe=cancel`).trim();

      const resolvedPrice =
        priceId ||
        (plan === "enterprise" ? stripePriceEnterprise : plan === "pro" ? stripePricePro : stripePriceStarter);

      if (!resolvedPrice) {
        return json(res, 400, {
          error: "no_price_id",
          message: "Kein Stripe Price ID konfiguriert. Trage STRIPE_PRICE_STARTER / STRIPE_PRICE_PRO / STRIPE_PRICE_ENTERPRISE ein.",
        });
      }

      const params = {
        mode: "subscription",
        "line_items[0][price]": resolvedPrice,
        "line_items[0][quantity]": "1",
        success_url: successUrl,
        cancel_url: cancelUrl,
      };

      if (email) {
        params.customer_email = email;
      }

      const session = await stripeRequest("POST", "/checkout/sessions", params);

      return json(res, 200, {
        sessionId: session.id,
        checkoutUrl: session.url,
        plan,
        priceId: resolvedPrice,
      });
    }

    if (req.method === "POST" && url.pathname === "/api/stripe/webhook") {
      const rawBodyChunks = [];
      for await (const chunk of req) {
        rawBodyChunks.push(chunk);
      }
      const rawBody = Buffer.concat(rawBodyChunks).toString("utf8");
      const signature = req.headers["stripe-signature"] || "";

      let event;
      if (stripeWebhookSecret) {
        event = await stripeVerifyWebhook(rawBody, signature);
        if (!event) {
          res.writeHead(400, { "Content-Type": "text/plain" });
          return res.end("Webhook signature verification failed");
        }
      } else {
        try {
          event = JSON.parse(rawBody);
        } catch {
          res.writeHead(400, { "Content-Type": "text/plain" });
          return res.end("Invalid JSON");
        }
      }

      const eventType = event.type || "";
      const eventObj = event.data?.object || {};
      let stateChanged = false;
      const currentState = await readState();
      let nextState = currentState;

      if (eventType === "checkout.session.completed" || eventType === "customer.subscription.created" || eventType === "customer.subscription.updated") {
        const priceId = eventObj.plan?.id || eventObj.items?.data?.[0]?.price?.id || "";
        const plan = planFromStripePrice(priceId);
        const customerId = eventObj.customer || eventObj.id || "";
        const subscriptionId = eventObj.subscription || eventObj.id || "";
        const status = eventObj.status || "active";
        const currentPeriodEnd = eventObj.current_period_end ? new Date(eventObj.current_period_end * 1000).toISOString() : null;

        nextState = {
          ...currentState,
          kmuSuite: {
            ...(currentState.kmuSuite || {}),
            plan: plan || (currentState.kmuSuite || {}).plan,
            stripeSubscription: {
              id: subscriptionId,
              customerId,
              priceId,
              status,
              plan: plan || "starter",
              activatedAt: new Date().toISOString(),
              currentPeriodEnd,
              event: eventType,
            },
          },
        };
        stateChanged = true;
        console.log(`[Stripe] Plan activated: ${plan} (${eventType})`);
      }

      if (eventType === "customer.subscription.deleted" || eventType === "invoice.payment_failed") {
        nextState = {
          ...currentState,
          kmuSuite: {
            ...(currentState.kmuSuite || {}),
            plan: null,
            stripeSubscription: {
              ...(currentState.kmuSuite?.stripeSubscription || {}),
              status: eventType === "customer.subscription.deleted" ? "canceled" : "payment_failed",
              canceledAt: new Date().toISOString(),
              event: eventType,
            },
          },
        };
        stateChanged = true;
        console.log(`[Stripe] Subscription event: ${eventType}`);
      }

      if (stateChanged) {
        await writeState(nextState);
      }

      return json(res, 200, { received: true, type: eventType });
    }

    if (req.method === "GET" && url.pathname === "/api/stripe/subscription") {
      const suite = state.kmuSuite || {};
      const sub = suite.stripeSubscription || null;

      if (!sub?.id || !stripeSecretKey) {
        return json(res, 200, {
          subscription: sub,
          live: false,
          message: sub ? "Lokale Daten (kein API-Key)" : "Kein aktives Abo",
        });
      }

      try {
        const liveSub = await stripeRequest("GET", `/subscriptions/${sub.id}`);
        return json(res, 200, {
          subscription: liveSub,
          live: true,
          localPlan: suite.plan,
        });
      } catch (err) {
        return json(res, 200, {
          subscription: sub,
          live: false,
          error: err.message,
        });
      }
    }

    if (req.method === "GET" && url.pathname === "/api/oauth/google/start") {
      if (!googleClientId || !googleClientSecret) {
        return json(res, 200, {
          ...googleConfigSummary(state),
          message: "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to enable full Gmail and Calendar sync.",
        });
      }

      const oauthState = crypto.randomBytes(16).toString("hex");
      const nextState = {
        ...state,
        oauthStates: {
          ...(state.oauthStates || {}),
          [oauthState]: { createdAt: new Date().toISOString() },
        },
      };
      await writeState(nextState);

      const authUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
      authUrl.search = new URLSearchParams({
        client_id: googleClientId,
        redirect_uri: googleRedirectUri,
        response_type: "code",
        access_type: "offline",
        prompt: "consent",
        scope: googleScopes.join(" "),
        state: oauthState,
      }).toString();

      return json(res, 200, {
        ...googleConfigSummary(state),
        url: authUrl.toString(),
      });
    }

    if (req.method === "GET" && url.pathname === "/oauth/google/callback") {
      const code = url.searchParams.get("code");
      const oauthState = url.searchParams.get("state");
      if (!code || !oauthState || !state.oauthStates?.[oauthState]) {
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        res.end(`<!doctype html>
<html lang="de">
<head><meta charset="utf-8"><title>Google OAuth</title></head>
<body style="font-family:Inter,Arial,sans-serif;background:#030712;color:#f9fafb;display:grid;place-items:center;min-height:100vh">
  <div style="max-width:520px;padding:24px;text-align:center">
    <h1 style="margin:0 0 12px">Google-Verbindung fehlgeschlagen</h1>
    <p style="margin:0 0 16px;color:#cbd5e1">State oder Code fehlt. Bitte den Login neu starten.</p>
    <script>
      if (window.opener) {
        window.opener.postMessage({ type: 'google-oauth', status: 'invalid' }, window.location.origin);
      }
      setTimeout(() => {
        if (window.opener) window.close();
        else window.location.replace('/assistant?google=invalid');
      }, 1200);
    </script>
  </div>
</body>
</html>`);
        return res.end();
      }

      const tokens = await getGoogleTokensFromCode(code);
      const profile = await fetchGoogleProfile(tokens.access_token);
      const nextState = {
        ...state,
        google: {
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token || state.google?.refreshToken || null,
          expiresAt: new Date(Date.now() + (tokens.expires_in || 3600) * 1000).toISOString(),
          scopes: googleScopes,
          email: profile.email || "",
          connectedAt: new Date().toISOString(),
        },
        oauthStates: Object.fromEntries(
          Object.entries(state.oauthStates || {}).filter(([key]) => key !== oauthState)
        ),
      };
      await writeState(nextState);
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(`<!doctype html>
<html lang="de">
<head><meta charset="utf-8"><title>Google OAuth</title></head>
<body style="font-family:Inter,Arial,sans-serif;background:#030712;color:#f9fafb;display:grid;place-items:center;min-height:100vh">
  <div style="max-width:520px;padding:24px;text-align:center">
    <h1 style="margin:0 0 12px">Google verbunden</h1>
    <p style="margin:0 0 16px;color:#cbd5e1">${profile.email || "Konto verbunden"}</p>
    <script>
      if (window.opener) {
        window.opener.postMessage(
          { type: 'google-oauth', status: 'connected', email: ${JSON.stringify(profile.email || "")} },
          window.location.origin
        );
      }
      setTimeout(() => {
        if (window.opener) window.close();
        else window.location.replace('/assistant?google=connected');
      }, 1200);
    </script>
  </div>
</body>
</html>`);
      return res.end();
    }

    if (req.method === "POST" && url.pathname === "/api/assistant/email/search") {
      const body = await readJsonBody(req);
      const query = (body.query || "").trim();
      if (!query) {
        return json(res, 400, { error: "missing_query" });
      }

      const { state: nextState, accessToken } = await ensureGoogleAccessToken(state);
      const messages = await gmailSearch(accessToken, query);
      return json(res, 200, {
        account: nextState.google?.email || null,
        query,
        count: messages.length,
        messages,
      });
    }

    if (req.method === "POST" && url.pathname === "/api/assistant/crypto/discover") {
      const body = await readJsonBody(req);
      const query = (body.query || "").trim() || buildDefaultCryptoQuery();
      const maxResults = Number.parseInt(body.maxResults || "40", 10);

      const { state: nextState, accessToken } = await ensureGoogleAccessToken(state);
      const messages = await gmailSearch(accessToken, query, maxResults);
      const platforms = discoverCryptoPlatformsFromMessages(messages);

      return json(res, 200, {
        account: nextState.google?.email || null,
        query,
        scannedMessages: messages.length,
        detectedPlatforms: platforms.length,
        platforms,
      });
    }

    if (req.method === "POST" && url.pathname === "/api/assistant/subscriptions/optimize") {
      const body = await readJsonBody(req);
      const subscriptions = Array.isArray(body.subscriptions) ? body.subscriptions : [];
      if (!subscriptions.length) {
        return json(res, 400, { error: "missing_subscriptions" });
      }

      return json(res, 200, buildSubscriptionOptimization(subscriptions));
    }

    if (req.method === "POST" && url.pathname === "/api/assistant/cancel/prepare") {
      const body = await readJsonBody(req);
      const subscription = body.subscription || {};
      if (!subscription.name && !subscription.platform) {
        return json(res, 400, { error: "missing_subscription_data" });
      }

      const plan = buildCancellationPlan(subscription);
      let queued = null;

      if (Boolean(body.enqueue)) {
        queued = {
          id: crypto.randomUUID(),
          action: plan.action,
          platform: subscription.platform || "unknown",
          name: subscription.name || "",
          subscriptionId: (subscription.subscriptionId || "").trim(),
          reason: (subscription.reason || "Kostenoptimierung").trim(),
          monthlyCost: Math.max(0, toNumber(subscription.monthlyCost, 0)),
          targetPlan: (subscription.targetPlan || "").trim(),
          currentPlan: (subscription.currentPlan || "").trim(),
          status: "planned",
          createdAt: new Date().toISOString(),
        };

        const nextState = {
          ...state,
          queue: [queued, ...(state.queue || [])].slice(0, 100),
        };
        await writeState(nextState);
      }

      return json(res, 200, {
        plan,
        queued,
      });
    }

    if (req.method === "POST" && url.pathname === "/api/assistant/reminders") {
      const body = await readJsonBody(req);
      const summary = (body.summary || "").trim();
      const dateTime = (body.dateTime || "").trim();
      if (!summary || !dateTime) {
        return json(res, 400, { error: "missing_fields" });
      }

      const { state: nextState, accessToken } = await ensureGoogleAccessToken(state);
      const event = await createCalendarReminder(accessToken, summary, dateTime);
      const reminder = {
        id: event.id,
        summary,
        dateTime,
        htmlLink: event.htmlLink || "",
        createdAt: new Date().toISOString(),
      };
      const persistedState = {
        ...nextState,
        reminders: [reminder, ...(nextState.reminders || [])].slice(0, 25),
      };
      await writeState(persistedState);

      return json(res, 200, reminder);
    }

    if (req.method === "POST" && url.pathname === "/api/assistant/queue") {
      const body = await readJsonBody(req);
      const entry = {
        id: crypto.randomUUID(),
        action: ["cancel", "suspend"].includes(body.action) ? body.action : "suspend",
        platform: (body.platform || "").trim(),
        name: (body.name || "").trim(),
        subscriptionId: (body.subscriptionId || "").trim(),
        reason: (body.reason || "").trim(),
        monthlyCost: Math.max(0, toNumber(body.monthlyCost, 0)),
        currentPlan: (body.currentPlan || "").trim(),
        targetPlan: (body.targetPlan || "").trim(),
        status: (body.status || "planned").trim(),
        createdAt: new Date().toISOString(),
      };
      const nextState = {
        ...state,
        queue: [entry, ...(state.queue || [])].slice(0, 50),
      };
      await writeState(nextState);
      return json(res, 200, entry);
    }

    if (req.method === "GET" && url.pathname === "/api/kmu/state") {
      return json(res, 200, {
        suite: sanitizeKmuSuite(state),
        monetization: buildKmuPlans(),
      });
    }

    if (req.method === "POST" && url.pathname === "/api/kmu/trial/start") {
      const suite = sanitizeKmuSuite(state);
      if (suite.trial.active) {
        return json(res, 200, { trial: suite.trial, message: "trial_already_active" });
      }

      const startedAt = new Date();
      const expiresAt = new Date(startedAt.getTime() + 14 * 86_400_000);
      const nextState = {
        ...state,
        kmuSuite: {
          ...(state.kmuSuite || {}),
          trial: {
            startedAt: startedAt.toISOString(),
            expiresAt: expiresAt.toISOString(),
            active: true,
          },
        },
      };
      await writeState(nextState);
      return json(res, 200, { trial: sanitizeKmuSuite(nextState).trial });
    }

    if (req.method === "POST" && url.pathname === "/api/kmu/offers/generate") {
      const body = await readJsonBody(req);
      const company = (body.company || "").trim();
      const service = (body.service || "").trim();
      if (!company || !service) {
        return json(res, 400, { error: "missing_fields", message: "company and service are required" });
      }

      const suite = state.kmuSuite || {};
      const trial = suite.trial || {};
      const offers = suite.offers || [];

      // === MONETARISIERUNG: Angebote limitieren ===
      const now = new Date();
      const trialExpired = trial.expiresAt && new Date(trial.expiresAt) < now;
      
      const offersThisMonth = offers.filter(o => {
        const d = new Date(o.createdAt);
        return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
      }).length;

      if (trialExpired && offersThisMonth >= 1) {
        return json(res, 402, {
          error: "upgrade_required",
          message: "Angebotslimit überschritten. Upgraden Sie für unbegrenzte Angebote.",
          currentOffers: offersThisMonth,
          upgradeLink: stripeLinkPro,
        });
      }

      if (trial.active && offersThisMonth >= 3) {
        return json(res, 402, {
          error: "trial_offer_limit_reached",
          message: `Trial-Limit: ${offersThisMonth}/3 Angebote. Premium jetzt starten!`,
          upgradeLink: stripeLinkStarter,
        });
      }

      const offer = {
        id: crypto.randomUUID(),
        company,
        contact: (body.contact || "").trim(),
        service,
        price: Number.parseFloat(String(body.price || "0")) || 0,
        deliveryDays: Number.parseInt(String(body.deliveryDays || "7"), 10) || 7,
        notes: (body.notes || "").trim(),
        offerText: "",
        createdAt: new Date().toISOString(),
      };
      offer.offerText = buildOfferText(offer);

      const nextState = {
        ...state,
        kmuSuite: {
          ...(state.kmuSuite || {}),
          offers: [offer, ...((state.kmuSuite || {}).offers || [])].slice(0, 100),
        },
      };
      await writeState(nextState);
      return json(res, 200, offer);
    }

    if (req.method === "POST" && url.pathname === "/api/kmu/leads/qualify") {
      const body = await readJsonBody(req);
      const suite = state.kmuSuite || {};
      const trial = suite.trial || {};
      const leads = suite.leads || [];

      // === MONETARISIERUNG: Trial- und Freemium-Limits ===
      const now = new Date();
      const trialExpired = trial.expiresAt && new Date(trial.expiresAt) < now;
      
      // Kostenlos: max 3 Leads in Trial oder ohne Plan
      const leadsThisMonth = leads.filter(l => {
        const d = new Date(l.createdAt);
        return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
      }).length;

      // Wenn Trial vorbei → Upgrade erforderlich
      if (trialExpired && leadsThisMonth >= 1) {
        return json(res, 402, {
          error: "upgrade_required",
          message: "Trial abgelaufen. Bitte auf einen Plan upgraden.",
          currentLeads: leadsThisMonth,
          upgradeLinks: {
            starter: stripeLinkStarter,
            pro: stripeLinkPro,
            enterprise: stripeLinkEnterprise,
          },
        });
      }

      // In Trial: max 3 Leads kostenlos
      if (trial.active && leadsThisMonth >= 3) {
        const expiresAtMs = Date.parse(trial.expiresAt || "");
        const daysLeftInTrial = Number.isFinite(expiresAtMs)
          ? Math.max(0, Math.ceil((expiresAtMs - Date.now()) / 86_400_000))
          : 0;

        return json(res, 402, {
          error: "trial_lead_limit_reached",
          message: `Trial-Limit: ${leadsThisMonth}/3 Leads. Upgraden für unbegrenzte Leads.`,
          daysLeftInTrial,
          upgradeLinks: {
            starter: stripeLinkStarter,
            pro: stripeLinkPro,
          },
        });
      }

      const lead = {
        id: crypto.randomUUID(),
        name: (body.name || "").trim(),
        company: (body.company || "").trim(),
        contact: (body.contact || "").trim(),
        channel: (body.channel || "web").trim(),
        budget: Number.parseFloat(String(body.budget || "0")) || 0,
        urgency: (body.urgency || "dieser_monat").trim(),
        useCase: (body.useCase || "").trim(),
        createdAt: new Date().toISOString(),
      };

      const rating = scoreLead(lead);
      const qualifiedLead = { ...lead, ...rating };
      const nextState = {
        ...state,
        kmuSuite: {
          ...(state.kmuSuite || {}),
          leads: [qualifiedLead, ...((state.kmuSuite || {}).leads || [])].slice(0, 250),
        },
      };
      await writeState(nextState);
      return json(res, 200, qualifiedLead);
    }

    if (req.method === "POST" && url.pathname === "/api/kmu/callbacks/book") {
      const body = await readJsonBody(req);
      const person = (body.person || "").trim();
      const dateTime = (body.dateTime || "").trim();
      if (!person || !dateTime) {
        return json(res, 400, { error: "missing_fields", message: "person and dateTime are required" });
      }

      const callback = {
        id: crypto.randomUUID(),
        person,
        organization: (body.organization || "").trim(),
        phone: (body.phone || "").trim(),
        dateTime,
        topic: (body.topic || "Rückruf").trim(),
        priority: ["hoch", "mittel", "niedrig"].includes(body.priority) ? body.priority : "mittel",
        createdAt: new Date().toISOString(),
      };

      const nextState = {
        ...state,
        kmuSuite: {
          ...(state.kmuSuite || {}),
          callbacks: [callback, ...((state.kmuSuite || {}).callbacks || [])].slice(0, 250),
        },
      };
      await writeState(nextState);
      return json(res, 200, callback);
    }

    if (req.method === "POST" && url.pathname === "/api/kmu/shifts/plan") {
      const body = await readJsonBody(req);
      const company = (body.company || "").trim();
      const shiftDate = (body.shiftDate || "").trim();
      if (!company || !shiftDate) {
        return json(res, 400, { error: "missing_fields", message: "company and shiftDate are required" });
      }

      const shift = {
        id: crypto.randomUUID(),
        company,
        teamLead: (body.teamLead || "").trim(),
        shiftDate,
        shiftType: normalizeShiftType(body.shiftType),
        requiredNurses: Number.parseInt(String(body.requiredNurses || "0"), 10) || 0,
        assignedNurses: Number.parseInt(String(body.assignedNurses || "0"), 10) || 0,
        selectedDistribution: body.selectedDistribution || null,
        note: (body.note || "").trim(),
        createdAt: new Date().toISOString(),
      };

      shift.summary = buildShiftSummary(shift);
      shift.coverage = Math.max(
        0,
        Math.min(100, shift.requiredNurses > 0 ? Math.round((shift.assignedNurses / shift.requiredNurses) * 100) : 0)
      );
      shift.distributionOptions = generateShiftDistributions(shift.requiredNurses);

      const nextState = {
        ...state,
        kmuSuite: {
          ...(state.kmuSuite || {}),
          shifts: [shift, ...((state.kmuSuite || {}).shifts || [])].slice(0, 250),
        },
      };
      await writeState(nextState);
      return json(res, 200, shift);
    }

    if (req.method === "GET" && url.pathname.startsWith("/api/kmu/shifts/distributions")) {
      const searchParams = url.searchParams;
      const requiredNurses = Number.parseInt(searchParams.get("nurses") || "0", 10) || 0;
      const distributions = generateShiftDistributions(requiredNurses);
      return json(res, 200, { requiredNurses, distributions });
    }

    // === KPI TRACKING ENDPOINTS ===
    if (req.method === "GET" && url.pathname === "/api/kmu/kpis/weekly") {
      const suite = state.kmuSuite || {};
      const weekAgo = new Date(Date.now() - 7 * 86_400_000);

      const kpis = {
        trialStartsThisWeek: (suite.eventLog || []).filter(
          (e) => e.type === "trial_started" && new Date(e.timestamp) > weekAgo
        ).length,
        leadsQualifiedThisWeek: (suite.eventLog || []).filter(
          (e) => e.type === "lead_qualified" && new Date(e.timestamp) > weekAgo
        ).length,
        callbacksBookedThisWeek: (suite.callbacks || []).filter(
          (c) => new Date(c.createdAt) > weekAgo
        ).length,
        shiftsPlannedThisWeek: (suite.shifts || []).filter(
          (s) => new Date(s.createdAt) > weekAgo
        ).length,
        totalLeads: suite.leads?.length || 0,
        totalOffers: suite.offers?.length || 0,
        trialActive: suite.trial?.active || false,
        daysLeftInTrial: suite.trial?.active
          ? Math.ceil((new Date(suite.trial.expiresAt) - Date.now()) / 86_400_000)
          : 0,
        averageLeadScore:
          suite.leads?.length > 0
            ? Math.round(suite.leads.reduce((sum, l) => sum + (l.score || 0), 0) / suite.leads.length)
            : 0,
        gradeDistribution: {
          A: (suite.leads || []).filter((l) => l.grade === "A").length,
          B: (suite.leads || []).filter((l) => l.grade === "B").length,
          C: (suite.leads || []).filter((l) => l.grade === "C").length,
          D: (suite.leads || []).filter((l) => l.grade === "D").length,
        },
        averageShiftCoverage:
          suite.shifts?.length > 0
            ? Math.round(suite.shifts.reduce((sum, s) => sum + (s.coverage || 0), 0) / suite.shifts.length)
            : 0,
      };

      return json(res, 200, kpis);
    }

    if (req.method === "POST" && url.pathname === "/api/kmu/kpis/track-event") {
      const body = await readJsonBody(req);
      const event = {
        type: (body.type || "").trim(),
        data: body.data || {},
        timestamp: new Date().toISOString(),
      };

      if (!event.type) {
        return json(res, 400, { error: "missing_event_type" });
      }

      const nextState = {
        ...state,
        kmuSuite: {
          ...(state.kmuSuite || {}),
          eventLog: [event, ...((state.kmuSuite || {}).eventLog || [])].slice(0, 1000),
        },
      };
      await writeState(nextState);

      return json(res, 200, { success: true, eventId: event.timestamp });
    }

    // === END KPI TRACKING ===

    // === MULTI-ACCOUNT SYNC ENDPOINTS ===
    if (req.method === "GET" && url.pathname === "/api/accounts/config") {
      return json(res, 200, {
        status: multiAccountSync ? "ready" : "not_configured",
        email1,
        email2,
        encryptionEnabled: Boolean(multiAccountSync),
        stripeConfigured: Boolean(stripeSecretKey),
      });
    }

    if (req.method === "POST" && url.pathname === "/api/accounts/sync") {
      if (!multiAccountSync) {
        return json(res, 400, { error: "encryption_not_configured" });
      }

      try {
        const body = await readJsonBody(req);
        const { account1Data, account2Data } = body;

        if (!account1Data || !account2Data) {
          return json(res, 400, { error: "missing_account_data" });
        }

        const syncedState = multiAccountSync.syncAccounts(account1Data, account2Data);
        const nextState = {
          ...state,
          multiAccountSync: syncedState,
        };
        await writeState(nextState);

        return json(res, 200, {
          success: true,
          syncedAt: syncedState.syncedAt,
          account1Email: email1,
          account2Email: email2,
          syncStatus: "encrypted_persisted",
        });
      } catch (e) {
        return json(res, 400, { error: e.message });
      }
    }

    if (req.method === "GET" && url.pathname === "/api/accounts/state") {
      if (!multiAccountSync || !state.multiAccountSync) {
        return json(res, 404, { error: "no_synced_state" });
      }

      try {
        const decodedAccounts = multiAccountSync.decodeSyncedAccounts(state.multiAccountSync);
        return json(res, 200, {
          account1: {
            email: email1,
            data: decodedAccounts.account1,
          },
          account2: {
            email: email2,
            data: decodedAccounts.account2,
          },
          lastSync: state.multiAccountSync.syncedAt,
        });
      } catch (e) {
        return json(res, 400, { error: e.message });
      }
    }

    // === STRIPE INTEGRATION STATUS ===
    if (req.method === "GET" && url.pathname === "/api/stripe/status") {
      return json(res, 200, {
        configured: Boolean(stripeSecretKey && stripePublishableKey),
        stripeSecretKeySet: Boolean(stripeSecretKey),
        stripePublishableKeySet: Boolean(stripePublishableKey),
        links: {
          starter: stripeLinkStarter,
          pro: stripeLinkPro,
          enterprise: stripeLinkEnterprise,
        },
        note: stripeSecretKey ? "✓ Stripe MCP bereit" : "⚠ Stripe Secret Key erforderlich",
      });
    }

    if (req.method === "GET" && url.pathname === "/platform-hub") {
      return serveFile(res, path.join(publicDir, "platform-hub.html"));
    }

    // ─── Platform API Key Management ────────────────────────────────────────
    const PLATFORM_DEFS = [
      // E-Commerce
      { id:"shopify",     name:"🛒 Shopify",         cat:"E-Commerce",    envKey:"SHOPIFY_ACCESS_TOKEN",      alt:["SHOPIFY_SHOP_DOMAIN"],            signup:"https://shopify.dev/docs/api/admin-rest" },
      { id:"etsy",        name:"🏪 Etsy",             cat:"E-Commerce",    envKey:"ETSY_API_KEY",              signup:"https://www.etsy.com/developers/documentation" },
      { id:"printify",    name:"🖨️ Printify",         cat:"E-Commerce",    envKey:"PRINTIFY_API_KEY",          signup:"https://developers.printify.com/" },
      { id:"printful",    name:"👕 Printful",         cat:"E-Commerce",    envKey:"PRINTFUL_API_KEY",          signup:"https://developers.printful.com/" },
      { id:"aliexpress",  name:"🛍️ AliExpress",       cat:"E-Commerce",    envKey:"ALIEXPRESS_API_KEY",        signup:"https://open.aliexpress.com/doc/doc.htm?spm=a2g0o.home.0.0" },
      { id:"fiverr",      name:"💼 Fiverr",           cat:"E-Commerce",    envKey:"FIVERR_CLIENT_ID",          signup:"https://developers.fiverr.com/" },
      { id:"upwork",      name:"🧑‍💻 Upwork",          cat:"E-Commerce",    envKey:"UPWORK_CLIENT_ID",          signup:"https://developers.upwork.com/" },
      { id:"gumroad",     name:"🎁 Gumroad",          cat:"E-Commerce",    envKey:"GUMROAD_ACCESS_TOKEN",      signup:"https://gumroad.com/api" },
      { id:"digistore24", name:"💰 Digistore24",      cat:"E-Commerce",    envKey:"DIGISTORE24_API_KEY",       signup:"https://www.digistore24.com/page/api" },
      // Payments
      { id:"stripe",      name:"💳 Stripe",           cat:"Payments",      envKey:"STRIPE_SECRET_KEY",         signup:"https://dashboard.stripe.com/register" },
      { id:"paypal",      name:"💳 PayPal",           cat:"Payments",      envKey:"PAYPAL_CLIENT_ID",          alt:["PAYPAL_SECRET"],                  signup:"https://developer.paypal.com/" },
      // AI & ML
      { id:"openai",      name:"🤖 OpenAI",           cat:"AI & ML",       envKey:"OPENAI_API_KEY",            signup:"https://platform.openai.com/api-keys" },
      { id:"anthropic",   name:"🤖 Anthropic",        cat:"AI & ML",       envKey:"ANTHROPIC_API_KEY",         signup:"https://console.anthropic.com/settings/keys" },
      { id:"perplexity",  name:"🔍 Perplexity",       cat:"AI & ML",       envKey:"PERPLEXITY_API_KEY",        signup:"https://www.perplexity.ai/settings/api" },
      { id:"llamaapi",    name:"🦙 Llama API",        cat:"AI & ML",       envKey:"LLAMA_API_KEY",             signup:"https://www.llama-api.com/" },
      { id:"firecrawl",   name:"🔥 Firecrawl",        cat:"AI & ML",       envKey:"FIRECRAWL_API_KEY",         signup:"https://www.firecrawl.dev/app/api-keys" },
      // Communication
      { id:"telegram",    name:"💬 Telegram",         cat:"Kommunikation", envKey:"TELEGRAM_BOT_TOKEN",        signup:"https://t.me/BotFather" },
      { id:"slack",       name:"💬 Slack",            cat:"Kommunikation", envKey:"SLACK_BOT_TOKEN",           alt:["SLACK_WEBHOOK_URL"],              signup:"https://api.slack.com/apps" },
      { id:"discord",     name:"🎮 Discord",          cat:"Kommunikation", envKey:"DISCORD_BOT_TOKEN",         alt:["DISCORD_WEBHOOK_URL"],            signup:"https://discord.com/developers/applications" },
      { id:"twilio",      name:"📞 Twilio",           cat:"Kommunikation", envKey:"TWILIO_ACCOUNT_SID",        alt:["TWILIO_AUTH_TOKEN"],              signup:"https://console.twilio.com/" },
      { id:"whatsapp",    name:"📱 WhatsApp",         cat:"Kommunikation", envKey:"WHATSAPP_TOKEN",            signup:"https://developers.facebook.com/docs/whatsapp/cloud-api" },
      // Email
      { id:"mailchimp",   name:"📧 Mailchimp",        cat:"Email",         envKey:"MAILCHIMP_API_KEY",         signup:"https://mailchimp.com/developer/" },
      { id:"klaviyo",     name:"📧 Klaviyo",          cat:"Email",         envKey:"KLAVIYO_API_KEY",           signup:"https://www.klaviyo.com/account#api-keys-tab" },
      { id:"sendgrid",    name:"📧 SendGrid",         cat:"Email",         envKey:"SENDGRID_API_KEY",          signup:"https://app.sendgrid.com/settings/api_keys" },
      { id:"resend",      name:"📧 Resend",           cat:"Email",         envKey:"RESEND_API_KEY",            signup:"https://resend.com/api-keys" },
      { id:"mailgun",     name:"📨 Mailgun",          cat:"Email",         envKey:"MAILGUN_API_KEY",           signup:"https://app.mailgun.com/settings/api_security" },
      { id:"brevo",       name:"📧 Brevo",            cat:"Email",         envKey:"BREVO_API_KEY",             signup:"https://app.brevo.com/settings/keys/api" },
      { id:"activecampaign",name:"⚡ ActiveCampaign", cat:"Email",         envKey:"ACTIVECAMPAIGN_API_KEY",    signup:"https://help.activecampaign.com/hc/en-us/articles/207317590" },
      { id:"convertkit",  name:"📧 Kit/ConvertKit",   cat:"Email",         envKey:"CONVERTKIT_API_KEY",        signup:"https://app.convertkit.com/account_settings/advanced_settings" },
      // Social Media
      { id:"twitter",     name:"🐦 Twitter/X",        cat:"Social Media",  envKey:"TWITTER_API_KEY",           alt:["TWITTER_API_SECRET"],             signup:"https://developer.twitter.com/en/portal/dashboard" },
      { id:"facebook",    name:"📘 Facebook",         cat:"Social Media",  envKey:"FACEBOOK_PAGE_ACCESS_TOKEN",alt:["META_PAGE_ID"],                   signup:"https://developers.facebook.com/" },
      { id:"instagram",   name:"📸 Instagram",        cat:"Social Media",  envKey:"INSTAGRAM_ACCESS_TOKEN",    signup:"https://developers.facebook.com/docs/instagram-api" },
      { id:"linkedin",    name:"💼 LinkedIn",         cat:"Social Media",  envKey:"LINKEDIN_CLIENT_ID",        alt:["LINKEDIN_CLIENT_SECRET"],         signup:"https://www.linkedin.com/developers/apps/new" },
      { id:"youtube",     name:"▶️ YouTube",          cat:"Social Media",  envKey:"YOUTUBE_API_KEY",           signup:"https://console.cloud.google.com/apis/credentials" },
      { id:"pinterest",   name:"📌 Pinterest",        cat:"Social Media",  envKey:"PINTEREST_ACCESS_TOKEN",    signup:"https://developers.pinterest.com/" },
      { id:"tiktok",      name:"🎵 TikTok",           cat:"Social Media",  envKey:"TIKTOK_ACCESS_TOKEN",       alt:["TIKTOK_APP_KEY"],                 signup:"https://developers.tiktok.com/" },
      // CRM
      { id:"hubspot",     name:"👥 HubSpot",          cat:"CRM",           envKey:"HUBSPOT_API_KEY",           signup:"https://app.hubspot.com/l/api-key" },
      { id:"salesforce",  name:"🏢 Salesforce",       cat:"CRM",           envKey:"SALESFORCE_CLIENT_ID",      signup:"https://developer.salesforce.com/" },
      { id:"pipedrive",   name:"🎯 Pipedrive",        cat:"CRM",           envKey:"PIPEDRIVE_API_KEY",         signup:"https://app.pipedrive.com/settings/api" },
      { id:"zoho",        name:"🌐 Zoho CRM",         cat:"CRM",           envKey:"ZOHO_CLIENT_ID",            signup:"https://api-console.zoho.com/" },
      // Support
      { id:"zendesk",     name:"🎫 Zendesk",          cat:"Support",       envKey:"ZENDESK_API_TOKEN",         alt:["ZENDESK_SUBDOMAIN"],              signup:"https://developer.zendesk.com/api-reference" },
      { id:"intercom",    name:"💬 Intercom",         cat:"Support",       envKey:"INTERCOM_TOKEN",            signup:"https://app.intercom.com/a/apps/_/developer-hub" },
      { id:"freshdesk",   name:"🎧 Freshdesk",        cat:"Support",       envKey:"FRESHDESK_API_KEY",         signup:"https://support.freshdesk.com/support/solutions/articles/215517-how-to-find-your-api-key" },
      // Project Mgmt
      { id:"jira",        name:"📋 Jira",             cat:"Projektmanagement", envKey:"JIRA_API_TOKEN",        alt:["JIRA_EMAIL","JIRA_DOMAIN"],       signup:"https://id.atlassian.com/manage-profile/security/api-tokens" },
      { id:"trello",      name:"📝 Trello",           cat:"Projektmanagement", envKey:"TRELLO_API_KEY",        alt:["TRELLO_TOKEN"],                   signup:"https://trello.com/power-ups/admin" },
      { id:"asana",       name:"✅ Asana",            cat:"Projektmanagement", envKey:"ASANA_TOKEN",           signup:"https://app.asana.com/0/developer-console" },
      { id:"linear",      name:"📐 Linear",           cat:"Projektmanagement", envKey:"LINEAR_API_KEY",        signup:"https://linear.app/settings/api" },
      { id:"monday",      name:"📅 Monday.com",       cat:"Projektmanagement", envKey:"MONDAY_API_KEY",        signup:"https://monday.com/developers/v2" },
      { id:"notion",      name:"📓 Notion",           cat:"Projektmanagement", envKey:"NOTION_TOKEN",          signup:"https://www.notion.so/my-integrations" },
      // Cloud
      { id:"aws",         name:"☁️ AWS",              cat:"Cloud",         envKey:"AWS_ACCESS_KEY_ID",         alt:["AWS_SECRET_ACCESS_KEY"],          signup:"https://console.aws.amazon.com/iam/home#/security_credentials" },
      { id:"gcp",         name:"🌐 Google Cloud",     cat:"Cloud",         envKey:"GCP_PROJECT_ID",            alt:["GOOGLE_APPLICATION_CREDENTIALS"], signup:"https://console.cloud.google.com/apis/credentials" },
      { id:"azure",       name:"🔷 Azure",            cat:"Cloud",         envKey:"AZURE_CLIENT_ID",           signup:"https://portal.azure.com/" },
      { id:"supabase",    name:"⚡ Supabase",         cat:"Cloud",         envKey:"SUPABASE_URL",              alt:["SUPABASE_SERVICE_KEY"],           signup:"https://supabase.com/dashboard/project/_/settings/api" },
      { id:"vercel",      name:"▲ Vercel",            cat:"Cloud",         envKey:"VERCEL_TEAM_ID",            signup:"https://vercel.com/account/tokens" },
      { id:"railway",     name:"🚂 Railway",          cat:"Cloud",         envKey:"RAILWAY_TOKEN",             signup:"https://railway.app/account/tokens" },
      { id:"cloudflare",  name:"🛡️ Cloudflare",       cat:"Cloud",         envKey:"CLOUDFLARE_API_TOKEN",      signup:"https://dash.cloudflare.com/profile/api-tokens" },
      { id:"heroku",      name:"🚀 Heroku",           cat:"Cloud",         envKey:"HEROKU_API_KEY",            signup:"https://dashboard.heroku.com/account" },
      // Dev
      { id:"github",      name:"🐙 GitHub",           cat:"Dev",           envKey:"GITHUB_TOKEN",              signup:"https://github.com/settings/tokens" },
      { id:"airtable",    name:"📊 Airtable",         cat:"Dev",           envKey:"AIRTABLE_API_KEY",          signup:"https://airtable.com/create/apikey" },
      { id:"microsoft365",name:"🏢 Microsoft 365",    cat:"Dev",           envKey:"MICROSOFT_CLIENT_ID",       signup:"https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps" },
      // E-Signature
      { id:"docusign",    name:"✍️ DocuSign",          cat:"E-Signature",   envKey:"DOCUSIGN_CLIENT_ID",        signup:"https://developers.docusign.com/" },
      { id:"pandadoc",    name:"📄 PandaDoc",          cat:"E-Signature",   envKey:"PANDADOC_API_KEY",          signup:"https://app.pandadoc.com/settings/api-settings/" },
      // SEO & Analytics
      { id:"semrush",     name:"📈 SEMrush",           cat:"SEO & Analytics", envKey:"SEMRUSH_API_KEY",          signup:"https://www.semrush.com/api-analytics/" },
      { id:"googleads",   name:"📢 Google Ads",        cat:"SEO & Analytics", envKey:"GOOGLE_ADS_DEVELOPER_TOKEN", alt:["GOOGLE_ADS_CUSTOMER_ID"], signup:"https://ads.google.com/aw/apicenter" },
    ];

    if (req.method === "GET" && url.pathname === "/api/platforms/all-status") {
      const result = PLATFORM_DEFS.map(p => {
        const keys = [p.envKey, ...(p.alt || [])];
        const configured = keys.some(k => Boolean((process.env[k] || "").trim()));
        return { ...p, configured, status: configured ? "connected" : "pending" };
      });
      const connected = result.filter(r => r.configured).length;
      return json(res, 200, { platforms: result, total: result.length, connected, pending: result.length - connected });
    }

    if (req.method === "POST" && url.pathname === "/api/platforms/validate") {
      const body = await readJsonBody(req);
      const { platformId, envKey, value } = body;
      if (!value) return json(res, 400, { valid: false, message: "Kein Key angegeben" });
      const key = String(value).trim().replace(/\s+/g, "");
      let result = { valid: false, message: "Unbekannte Plattform" };
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 8000);
        const fetchOpts = { signal: ctrl.signal };
        if (platformId === "shopify") {
          const domain = (process.env.SHOPIFY_SHOP_DOMAIN || "").replace("https://","");
          if (!domain) return json(res, 200, { valid: false, message: "SHOPIFY_SHOP_DOMAIN nicht gesetzt" });
          const r = await fetch(`https://${domain}/admin/api/2024-10/shop.json`, { ...fetchOpts, headers: { "X-Shopify-Access-Token": key } });
          result = r.ok ? { valid: true, message: `Shopify Shop verbunden ✅` } : { valid: false, message: `HTTP ${r.status} — Key ungültig` };
        } else if (platformId === "stripe") {
          const r = await fetch("https://api.stripe.com/v1/account", { ...fetchOpts, headers: { Authorization: `Bearer ${key}` } });
          const d = await r.json();
          result = r.ok ? { valid: true, message: `Stripe: ${d.email || d.id} ✅` } : { valid: false, message: d.error?.message || `HTTP ${r.status}` };
        } else if (platformId === "openai") {
          const r = await fetch("https://api.openai.com/v1/models", { ...fetchOpts, headers: { Authorization: `Bearer ${key}` } });
          result = r.ok ? { valid: true, message: "OpenAI API Key gültig ✅" } : { valid: false, message: `HTTP ${r.status} — Key ungültig` };
        } else if (platformId === "anthropic") {
          result = key.startsWith("sk-ant-") ? { valid: true, message: "Anthropic Key Format OK ✅" } : { valid: false, message: "Key muss mit sk-ant- beginnen" };
        } else if (platformId === "github") {
          const r = await fetch("https://api.github.com/user", { ...fetchOpts, headers: { Authorization: `token ${key}`, "User-Agent": "SuperMegaBot", Accept: "application/vnd.github+json" } });
          const d = await r.json();
          result = r.ok ? { valid: true, message: `GitHub: @${d.login} ✅` } : { valid: false, message: d.message || `HTTP ${r.status}` };
        } else if (platformId === "telegram") {
          const r = await fetch(`https://api.telegram.org/bot${key}/getMe`, fetchOpts);
          const d = await r.json();
          result = d.ok ? { valid: true, message: `Telegram Bot: @${d.result.username} ✅` } : { valid: false, message: d.description || "Ungültiger Token" };
        } else if (platformId === "mailchimp") {
          const server = (process.env.MAILCHIMP_SERVER_PREFIX || key.split("-").pop() || "us1");
          const r = await fetch(`https://${server}.api.mailchimp.com/3.0/ping`, { ...fetchOpts, headers: { Authorization: `Bearer ${key}` } });
          const d = await r.json();
          result = r.ok ? { valid: true, message: `Mailchimp: ${d.health_status || "OK"} ✅` } : { valid: false, message: `HTTP ${r.status}` };
        } else if (platformId === "klaviyo") {
          const r = await fetch("https://a.klaviyo.com/api/profiles/?page[size]=1", { ...fetchOpts, headers: { Authorization: `Klaviyo-API-Key ${key}`, revision: "2024-10-15" } });
          result = r.ok ? { valid: true, message: "Klaviyo API Key gültig ✅" } : { valid: false, message: `HTTP ${r.status}` };
        } else if (platformId === "sendgrid") {
          const r = await fetch("https://api.sendgrid.com/v3/user/profile", { ...fetchOpts, headers: { Authorization: `Bearer ${key}` } });
          const d = await r.json();
          result = r.ok ? { valid: true, message: `SendGrid: ${d.email || "OK"} ✅` } : { valid: false, message: d.errors?.[0]?.message || `HTTP ${r.status}` };
        } else if (platformId === "notion") {
          const r = await fetch("https://api.notion.com/v1/users/me", { ...fetchOpts, headers: { Authorization: `Bearer ${key}`, "Notion-Version": "2022-06-28" } });
          const d = await r.json();
          result = r.ok ? { valid: true, message: `Notion: ${d.name || d.type || "OK"} ✅` } : { valid: false, message: d.message || `HTTP ${r.status}` };
        } else if (platformId === "airtable") {
          const r = await fetch("https://api.airtable.com/v0/meta/whoami", { ...fetchOpts, headers: { Authorization: `Bearer ${key}` } });
          const d = await r.json();
          result = r.ok ? { valid: true, message: `Airtable: ${d.id || "OK"} ✅` } : { valid: false, message: d.error?.message || `HTTP ${r.status}` };
        } else if (platformId === "slack") {
          const r = await fetch("https://slack.com/api/auth.test", { method: "POST", ...fetchOpts, headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" } });
          const d = await r.json();
          result = d.ok ? { valid: true, message: `Slack: ${d.user || d.team || "OK"} ✅` } : { valid: false, message: d.error || "Auth fehlgeschlagen" };
        } else if (platformId === "hubspot") {
          const r = await fetch("https://api.hubapi.com/crm/v3/objects/contacts?limit=1", { ...fetchOpts, headers: { Authorization: `Bearer ${key}` } });
          result = r.ok ? { valid: true, message: "HubSpot API Key gültig ✅" } : { valid: false, message: `HTTP ${r.status}` };
        } else if (platformId === "pipedrive") {
          const r = await fetch(`https://api.pipedrive.com/v1/users/me?api_token=${key}`, fetchOpts);
          const d = await r.json();
          result = d.success ? { valid: true, message: `Pipedrive: ${d.data?.name || "OK"} ✅` } : { valid: false, message: d.error || "Ungültiger Key" };
        } else if (platformId === "resend") {
          const r = await fetch("https://api.resend.com/domains", { ...fetchOpts, headers: { Authorization: `Bearer ${key}` } });
          result = r.ok ? { valid: true, message: "Resend API Key gültig ✅" } : { valid: false, message: `HTTP ${r.status}` };
        } else if (platformId === "cloudflare") {
          const r = await fetch("https://api.cloudflare.com/client/v4/user/tokens/verify", { ...fetchOpts, headers: { Authorization: `Bearer ${key}` } });
          const d = await r.json();
          result = d.success ? { valid: true, message: "Cloudflare Token gültig ✅" } : { valid: false, message: d.errors?.[0]?.message || "Ungültig" };
        } else if (platformId === "zendesk") {
          const subdomain = (body.additionalKeys?.ZENDESK_SUBDOMAIN || "").replace("https://","").replace(".zendesk.com","");
          if (!subdomain) return json(res, 200, { valid: false, message: "Bitte ZENDESK_SUBDOMAIN eintragen" });
          const email = body.additionalKeys?.ZENDESK_EMAIL || "";
          const auth = Buffer.from(`${email}/token:${key}`).toString("base64");
          const r = await fetch(`https://${subdomain}.zendesk.com/api/v2/users/me.json`, { ...fetchOpts, headers: { Authorization: `Basic ${auth}` } });
          result = r.ok ? { valid: true, message: "Zendesk verbunden ✅" } : { valid: false, message: `HTTP ${r.status}` };
        } else {
          result = key.length > 5 ? { valid: true, message: "Key-Format OK ✅ (keine API-Verifikation für diese Plattform)" } : { valid: false, message: "Key zu kurz" };
        }
        clearTimeout(to);
      } catch (e) {
        result = { valid: false, message: e.name === "AbortError" ? "Timeout — API nicht erreichbar" : e.message };
      }
      return json(res, 200, result);
    }

    if (req.method === "POST" && url.pathname === "/api/platforms/save-key") {
      const body = await readJsonBody(req);
      const { envKey, value, additionalKeys } = body;
      if (!envKey || !value) return json(res, 400, { error: "envKey and value required" });
      const cleanVal = String(value).trim().replace(/\s+/g, "");
      let lines = `\n${envKey}=${cleanVal}`;
      if (additionalKeys) {
        for (const [k, v] of Object.entries(additionalKeys)) {
          if (v) lines += `\n${k}=${String(v).trim()}`;
        }
      }
      await fs.appendFile(envLocalPath, lines, "utf8");
      process.env[envKey] = cleanVal;
      if (additionalKeys) {
        for (const [k, v] of Object.entries(additionalKeys)) {
          if (v) process.env[k] = String(v).trim();
        }
      }
      return json(res, 200, { ok: true, envKey, saved: true });
    }

    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Not found");
  } catch (error) {
    json(res, 500, {
      error: "request_failed",
      message: error instanceof Error ? error.message : String(error),
    });
  }
});

server.on("error", (error) => {
  if (error && typeof error === "object" && error.code === "EADDRINUSE") {
    console.log(`Platform sync bridge already running on http://localhost:${port}`);
    process.exit(0);
  }

  throw error;
});

server.listen(port, () => {
  console.log(`Platform sync bridge listening on http://localhost:${port}`);
  startHealthMonitor();
});

// ─── Auto Health Monitor ────────────────────────────────────────────────────

const monitorLogPath = path.join(appRoot, ".runtime", "health-monitor.log");
const monitorStatePath = path.join(appRoot, ".runtime", "health-monitor-state.json");
const MONITOR_INTERVAL_MS = 60 * 60 * 1000; // 1 Stunde
const MONITOR_CHECK_TIMEOUT_MS = 4000;

const revenueTargets = [
  { id: "bridge",            name: "KMU Bridge",           url: `http://localhost:${port}/health`,           critical: true },
  { id: "digistore24",       name: "Digistore24 Automation",url: "http://localhost:3010/api/digistore/stats", critical: true },
  { id: "autoincome-ai",     name: "AutoIncome AI",         url: "http://localhost:3020/",                   critical: true },
  { id: "monetization-hub",  name: "Monetization Hub",      url: "http://localhost:3030/",                   critical: true },
  { id: "steuercockpit",     name: "Steuercockpit",         url: "http://localhost:3032/",                   critical: false },
  { id: "telegram-bot",      name: "Telegram Automation",   url: "http://localhost:3000/api/health",         critical: false },
  { id: "creatorai",         name: "CreatorAI Backend",     url: "http://localhost:3001/health",             critical: false },
];

async function checkTarget(target) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), MONITOR_CHECK_TIMEOUT_MS);
  const start = Date.now();
  try {
    const res = await fetch(target.url, { signal: controller.signal });
    return {
      id: target.id,
      name: target.name,
      critical: target.critical,
      online: res.ok,
      statusCode: res.status,
      latencyMs: Date.now() - start,
      checkedAt: new Date().toISOString(),
      error: null,
    };
  } catch (err) {
    return {
      id: target.id,
      name: target.name,
      critical: target.critical,
      online: false,
      statusCode: 0,
      latencyMs: Date.now() - start,
      checkedAt: new Date().toISOString(),
      error: err.name === "AbortError" ? "timeout" : "offline",
    };
  } finally {
    clearTimeout(timer);
  }
}

async function runHealthCheck() {
  const results = await Promise.all(revenueTargets.map(checkTarget));
  const onlineCount = results.filter((r) => r.online).length;
  const criticalOffline = results.filter((r) => !r.online && r.critical);
  const allOk = criticalOffline.length === 0;

  const snapshot = {
    checkedAt: new Date().toISOString(),
    allOk,
    onlineCount,
    totalCount: results.length,
    criticalOfflineCount: criticalOffline.length,
    results,
  };

  try {
    await fs.mkdir(path.dirname(monitorStatePath), { recursive: true });
    await fs.writeFile(monitorStatePath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
    const logLine = `[${snapshot.checkedAt}] ${allOk ? "OK" : "ALERT"} ${onlineCount}/${results.length} online${criticalOffline.length ? ` | CRITICAL offline: ${criticalOffline.map((r) => r.name).join(", ")}` : ""}\n`;
    await fs.appendFile(monitorLogPath, logLine, "utf8");
  } catch {
    // non-fatal
  }

  if (!allOk) {
    console.warn(`[HealthMonitor] ALERT: ${criticalOffline.map((r) => r.name).join(", ")} offline`);
  }

  return snapshot;
}

function startHealthMonitor() {
  runHealthCheck().catch(() => {});
  setInterval(() => runHealthCheck().catch(() => {}), MONITOR_INTERVAL_MS);
}

let latestMonitorSnapshot = null;

async function getMonitorState() {
  try {
    const raw = await fs.readFile(monitorStatePath, "utf8");
    latestMonitorSnapshot = JSON.parse(raw);
  } catch {
    // fall through to live check
  }

  if (!latestMonitorSnapshot) {
    latestMonitorSnapshot = await runHealthCheck();
  }

  return latestMonitorSnapshot;
}
