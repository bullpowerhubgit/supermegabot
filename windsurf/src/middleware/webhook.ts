import { Request, Response, NextFunction } from 'express';
import crypto from 'crypto';

export function verifyHmacWebhook(req: Request, res: Response, next: NextFunction) {
  try {
    const signature = req.headers['x-webhook-signature'] as string;
    const timestamp = req.headers['x-webhook-timestamp'] as string;

    if (!signature || !timestamp) {
      return res.status(401).json({ error: 'Missing webhook signature headers' });
    }

    // Check timestamp (prevent replay attacks - 5 min window)
    const now = Math.floor(Date.now() / 1000);
    const webhookTime = parseInt(timestamp, 10);
    if (Math.abs(now - webhookTime) > 300) {
      return res.status(401).json({ error: 'Webhook timestamp too old' });
    }

    // Verify HMAC signature
    const secret = process.env.WEBHOOK_SECRET || '';
    const payload = JSON.stringify(req.body);
    const expectedSig = crypto
      .createHmac('sha256', secret)
      .update(`${timestamp}.${payload}`)
      .digest('hex');

    // Use timing-safe comparison
    const sigBuffer = Buffer.from(signature, 'hex');
    const expectedBuffer = Buffer.from(expectedSig, 'hex');

    if (sigBuffer.length !== expectedBuffer.length || !crypto.timingSafeEqual(sigBuffer, expectedBuffer)) {
      return res.status(401).json({ error: 'Invalid webhook signature' });
    }

    next();
  } catch (err) {
    return res.status(500).json({ error: 'Webhook verification failed', message: (err as Error).message });
  }
}

export function verifyStripeWebhook(req: Request, res: Response, next: NextFunction) {
  try {
    const sig = req.headers['stripe-signature'] as string;
    if (!sig) {
      return res.status(401).json({ error: 'Missing Stripe signature' });
    }

    const secret = process.env.STRIPE_WEBHOOK_SECRET || '';

    // Stripe webhook verification would use stripe library in production
    // For now, we'll do a basic check - in production use stripe.webhooks.constructEvent
    if (!secret) {
      console.warn('STRIPE_WEBHOOK_SECRET not set, skipping verification');
      return next();
    }

    // TODO: Implement proper Stripe webhook verification
    // const event = stripe.webhooks.constructEvent(req.body, sig, secret);
    // req.stripeEvent = event;

    next();
  } catch (err) {
    return res.status(400).json({ error: 'Invalid Stripe webhook', message: (err as Error).message });
  }
}

export function verifyShopifyWebhook(req: Request, res: Response, next: NextFunction) {
  try {
    const hmac = req.headers['x-shopify-hmac-sha256'] as string;
    if (!hmac) {
      return res.status(401).json({ error: 'Missing Shopify HMAC' });
    }

    const secret = process.env.SHOPIFY_API_SECRET || '';
    if (!secret) {
      console.warn('SHOPIFY_API_SECRET not set');
      return res.status(500).json({ error: 'Shopify secret not configured' });
    }

    const rawBody = (req as any).rawBody || JSON.stringify(req.body);
    const hash = crypto.createHmac('sha256', secret).update(rawBody).digest('base64');

    if (hash !== hmac) {
      return res.status(401).json({ error: 'Invalid Shopify webhook signature' });
    }

    next();
  } catch (err) {
    return res.status(500).json({ error: 'Shopify verification failed', message: (err as Error).message });
  }
}
