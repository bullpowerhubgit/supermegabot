import { Router, raw } from 'express';
import Stripe from 'stripe';

const router = Router();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', { apiVersion: '2024-06-20' as any });

const PRICE_IDS = {
  starter: process.env.STRIPE_STARTER_PRICE_ID || '',
  pro: process.env.STRIPE_PRO_PRICE_ID || '',
  enterprise: process.env.STRIPE_ENTERPRISE_PRICE_ID || '',
};

// Create Checkout Session
router.post('/create-checkout-session', async (req, res) => {
  try {
    const { priceKey, customerEmail, successUrl, cancelUrl } = req.body;
    const priceId = PRICE_IDS[priceKey as keyof typeof PRICE_IDS];
    
    if (!priceId) {
      return res.status(400).json({ error: 'Invalid price plan' });
    }

    const session = await stripe.checkout.sessions.create({
      payment_method_types: ['card'],
      line_items: [{ price: priceId, quantity: 1 }],
      mode: 'subscription',
      customer_email: customerEmail,
      success_url: successUrl || `${req.headers.origin}/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: cancelUrl || `${req.headers.origin}/cancel`,
      metadata: { plan: priceKey },
    });

    res.json({ sessionId: session.id, url: session.url });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

// Customer Portal
router.post('/create-portal-session', async (req, res) => {
  try {
    const { customerId } = req.body;
    const session = await stripe.billingPortal.sessions.create({
      customer: customerId,
      return_url: `${req.headers.origin}/dashboard`,
    });
    res.json({ url: session.url });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

// Webhook (raw body needed)
router.post('/webhook', raw({ type: 'application/json' }), async (req, res) => {
  const sig = req.headers['stripe-signature'] as string;
  const endpointSecret = process.env.STRIPE_WEBHOOK_SECRET || '';

  try {
    const event = stripe.webhooks.constructEvent(req.body, sig, endpointSecret);

    switch (event.type) {
      case 'checkout.session.completed':
        const session = event.data.object as Stripe.Checkout.Session;
        console.log(`Payment successful for ${session.customer_email}`);
        break;
      case 'invoice.payment_succeeded':
        console.log('Subscription payment succeeded');
        break;
      case 'customer.subscription.deleted':
        console.log('Subscription cancelled');
        break;
    }

    res.json({ received: true });
  } catch (error: any) {
    res.status(400).send(`Webhook Error: ${error.message}`);
  }
});

// Get subscription status
router.get('/subscription/:customerId', async (req, res) => {
  try {
    const subscriptions = await stripe.subscriptions.list({
      customer: req.params.customerId,
      status: 'all',
    });
    res.json({ subscriptions: subscriptions.data });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

export default router;
