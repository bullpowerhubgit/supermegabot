import crypto from 'crypto';
export function verifyShopifyWebhook(body: string, hmac: string, secret: string): boolean {
  const digest = crypto.createHmac('sha256', secret).update(body, 'utf8').digest('base64');
  try {
    return crypto.timingSafeEqual(Buffer.from(digest), Buffer.from(hmac));
  } catch {
    return false;
  }
}
export function verifyShopifyOAuth(query: Record<string, string>, secret: string): boolean {
  const { hmac, ...params } = query;
  const message = Object.keys(params).sort().map(k => `${k}=${params[k]}`).join('&');
  const digest = crypto.createHmac('sha256', secret).update(message).digest('hex');
  try {
    return crypto.timingSafeEqual(Buffer.from(digest), Buffer.from(hmac));
  } catch {
    return false;
  }
}
