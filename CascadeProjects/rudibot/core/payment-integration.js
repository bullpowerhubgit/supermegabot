/**
 * RUDIBOT Stripe Payment Integration
 * Subscription management with tiers: Starter, Pro, Agency
 */

class PaymentIntegration {
  constructor() {
    this.logger = console;
    this.stripe = null;
    
    // Initialize Stripe if key available
    if (process.env.STRIPE_SECRET_KEY) {
      try {
        const Stripe = require('stripe');
        this.stripe = Stripe(process.env.STRIPE_SECRET_KEY);
      } catch (e) {
        this.logger.warn('Stripe not installed, payment processing disabled');
      }
    }
    
    // Pricing tiers
    this.plans = {
      starter: {
        id: 'starter',
        name: 'Starter',
        price: 2900, // €29.00 in cents
        interval: 'month',
        features: [
          '1 Shopify Store',
          'Basic Automation',
          'Email Support',
          '500 Orders/Month'
        ],
        limits: {
          stores: 1,
          ordersPerMonth: 500,
          agents: 3,
          workflows: 5
        }
      },
      pro: {
        id: 'pro',
        name: 'Pro',
        price: 7900, // €79.00 in cents
        interval: 'month',
        features: [
          '3 Shopify Stores',
          'Advanced Automation',
          'Priority Support',
          'Multi-Agent System',
          '2500 Orders/Month'
        ],
        limits: {
          stores: 3,
          ordersPerMonth: 2500,
          agents: 6,
          workflows: 15
        }
      },
      agency: {
        id: 'agency',
        name: 'Agency',
        price: 19900, // €199.00 in cents
        interval: 'month',
        features: [
          'Unlimited Stores',
          'Full Automation Suite',
          'Dedicated Support',
          'All Agents + Custom',
          'Unlimited Orders',
          'White Label Option'
        ],
        limits: {
          stores: Infinity,
          ordersPerMonth: Infinity,
          agents: Infinity,
          workflows: Infinity
        }
      }
    };
    
    // In-memory subscription store (replace with DB in production)
    this.subscriptions = new Map();
  }

  // Get available plans
  getPlans() {
    return Object.values(this.plans).map(plan => ({
      id: plan.id,
      name: plan.name,
      price: plan.price / 100,
      interval: plan.interval,
      features: plan.features,
      limits: plan.limits
    }));
  }

  // Create checkout session
  async createCheckoutSession(planId, customerEmail, successUrl, cancelUrl) {
    if (!this.stripe) {
      return { success: false, error: 'Stripe not configured' };
    }

    const plan = this.plans[planId];
    if (!plan) {
      return { success: false, error: 'Invalid plan' };
    }

    try {
      const session = await this.stripe.checkout.sessions.create({
        customer_email: customerEmail,
        payment_method_types: ['card', 'sepa_debit'],
        line_items: [{
          price_data: {
            currency: 'eur',
            product_data: {
              name: `RudiBot ${plan.name} Plan`,
              description: plan.features.join(', ')
            },
            unit_amount: plan.price,
            recurring: { interval: plan.interval }
          },
          quantity: 1
        }],
        mode: 'subscription',
        success_url: successUrl || `${process.env.DOMAIN}/dashboard?success=true&session_id={CHECKOUT_SESSION_ID}`,
        cancel_url: cancelUrl || `${process.env.DOMAIN}/pricing?canceled=true`,
        subscription_data: {
          trial_period_days: 14 // 14-day free trial
        }
      });

      return {
        success: true,
        sessionId: session.id,
        url: session.url
      };
    } catch (error) {
      this.logger.error('Stripe checkout error:', error);
      return { success: false, error: error.message };
    }
  }

  // Verify subscription status
  async getSubscriptionStatus(userId) {
    const sub = this.subscriptions.get(userId);
    
    if (!sub) {
      return { status: 'inactive', plan: null };
    }

    // Check if trial expired
    if (sub.status === 'trialing' && new Date() > new Date(sub.trialEnd)) {
      sub.status = 'past_due';
    }

    return {
      status: sub.status,
      plan: sub.planId,
      currentPeriodEnd: sub.currentPeriodEnd,
      trialEnd: sub.trialEnd,
      cancelAtPeriodEnd: sub.cancelAtPeriodEnd
    };
  }

  // Handle webhook
  async handleWebhook(payload, signature) {
    if (!this.stripe) {
      return { success: false, error: 'Stripe not configured' };
    }

    const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
    if (!webhookSecret) {
      return { success: false, error: 'Webhook secret not configured' };
    }

    try {
      const event = this.stripe.webhooks.constructEvent(payload, signature, webhookSecret);
      
      switch (event.type) {
        case 'checkout.session.completed':
          await this.handleCheckoutComplete(event.data.object);
          break;
        
        case 'invoice.payment_succeeded':
          await this.handlePaymentSuccess(event.data.object);
          break;
        
        case 'invoice.payment_failed':
          await this.handlePaymentFailure(event.data.object);
          break;
        
        case 'customer.subscription.deleted':
          await this.handleSubscriptionDeleted(event.data.object);
          break;
        
        case 'customer.subscription.updated':
          await this.handleSubscriptionUpdated(event.data.object);
          break;
      }

      return { success: true, event: event.type };
    } catch (error) {
      this.logger.error('Webhook error:', error);
      return { success: false, error: error.message };
    }
  }

  async handleCheckoutComplete(session) {
    const userId = session.client_reference_id;
    const subscription = await this.stripe.subscriptions.retrieve(session.subscription);
    
    this.subscriptions.set(userId, {
      userId,
      stripeCustomerId: session.customer,
      stripeSubscriptionId: session.subscription,
      planId: this.getPlanFromPrice(subscription.items.data[0].price.id),
      status: subscription.status,
      currentPeriodStart: new Date(subscription.current_period_start * 1000),
      currentPeriodEnd: new Date(subscription.current_period_end * 1000),
      trialEnd: subscription.trial_end ? new Date(subscription.trial_end * 1000) : null,
      cancelAtPeriodEnd: subscription.cancel_at_period_end,
      createdAt: new Date()
    });

    this.logger.info(`✅ Subscription created for user ${userId}`);
  }

  async handlePaymentSuccess(invoice) {
    this.logger.info(`💰 Payment successful: ${invoice.id}`);
  }

  async handlePaymentFailure(invoice) {
    this.logger.warn(`❌ Payment failed: ${invoice.id}`);
    // Send notification to user
  }

  async handleSubscriptionDeleted(subscription) {
    const userSub = Array.from(this.subscriptions.values())
      .find(s => s.stripeSubscriptionId === subscription.id);
    
    if (userSub) {
      userSub.status = 'canceled';
      this.logger.info(`🚫 Subscription canceled for user ${userSub.userId}`);
    }
  }

  async handleSubscriptionUpdated(subscription) {
    const userSub = Array.from(this.subscriptions.values())
      .find(s => s.stripeSubscriptionId === subscription.id);
    
    if (userSub) {
      userSub.status = subscription.status;
      userSub.planId = this.getPlanFromPrice(subscription.items.data[0].price.id);
      userSub.cancelAtPeriodEnd = subscription.cancel_at_period_end;
      this.logger.info(`📝 Subscription updated for user ${userSub.userId}`);
    }
  }

  getPlanFromPrice(priceId) {
    // Map Stripe price IDs to plan IDs
    const priceMap = {
      [process.env.STRIPE_STARTER_PRICE_ID]: 'starter',
      [process.env.STRIPE_PRO_PRICE_ID]: 'pro',
      [process.env.STRIPE_AGENCY_PRICE_ID]: 'agency'
    };
    return priceMap[priceId] || 'starter';
  }

  // Express Router
  getRouter() {
    const express = require('express');
    const router = express.Router();

    // Get pricing plans
    router.get('/plans', (req, res) => {
      res.json({
        success: true,
        plans: this.getPlans()
      });
    });

    // Create checkout session
    router.post('/checkout', async (req, res) => {
      const { planId, email, successUrl, cancelUrl } = req.body;
      
      const result = await this.createCheckoutSession(planId, email, successUrl, cancelUrl);
      res.json(result);
    });

    // Get subscription status
    router.get('/status/:userId', async (req, res) => {
      const status = await this.getSubscriptionStatus(req.params.userId);
      res.json({
        success: true,
        ...status
      });
    });

    // Stripe webhook
    router.post('/webhook', express.raw({ type: 'application/json' }), async (req, res) => {
      const signature = req.headers['stripe-signature'];
      const result = await this.handleWebhook(req.body, signature);
      
      if (result.success) {
        res.json({ received: true });
      } else {
        res.status(400).json(result);
      }
    });

    return router;
  }
}

module.exports = { PaymentIntegration };
