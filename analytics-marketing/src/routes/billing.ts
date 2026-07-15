import Stripe from 'stripe'
import { Router, Request, Response } from 'express'

const router = Router()

const PLANS = {
  starter: { price: process.env.AMS_PRICE_STARTER || 'price_1TjdqvRJECiV6vSmwaIdnSgW', name: 'Analytics Starter', amount: 49 },
  pro: { price: process.env.AMS_PRICE_PRO || 'price_1TjdqvRJECiV6vSmVopeUjYM', name: 'Analytics Pro', amount: 99 },
}

router.post('/billing/checkout', async (req: Request, res: Response) => {
  try {
    const { plan, email } = req.body as { plan: string; email: string }
    const sk = process.env.STRIPE_SECRET_KEY || ''
    if (!sk) return res.status(500).json({ error: 'Stripe not configured' })
    const planData = PLANS[plan as keyof typeof PLANS]
    if (!planData) return res.status(400).json({ error: 'Invalid plan. Choose: starter, pro' })
    if (!planData.price) return res.status(500).json({ error: `Price ID for ${plan} not set` })

    const stripe = new Stripe(sk)
    const appUrl = process.env.APP_URL || `https://${req.headers.host}`
    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      customer_email: email || undefined,
      line_items: [{ price: planData.price, quantity: 1 }],
      success_url: `${appUrl}/?success=true`,
      cancel_url: `${appUrl}/`,
      allow_promotion_codes: true,
      subscription_data: { trial_period_days: 14 },
    })
    res.json({ url: session.url })
  } catch (err) {
    res.status(500).json({ error: (err as Error).message })
  }
})

router.get('/billing/plans', (_req: Request, res: Response) => {
  res.json({
    plans: [
      { id: 'starter', name: 'Analytics Starter', price: 49, currency: 'EUR', trial_days: 14, features: ['Klaviyo Integration', 'Mailchimp Sync', '10k Events/mo', 'Facebook Pixel', 'Email Support'] },
      { id: 'pro', name: 'Analytics Pro', price: 99, currency: 'EUR', trial_days: 14, features: ['Alles aus Starter', 'Custom Events', '100k Events/mo', 'Google Analytics 4', 'Priority Support', 'Webhook Forwarding'] },
    ],
  })
})

export default router
