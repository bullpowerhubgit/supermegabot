import express, { Request, Response } from 'express';
import Stripe from 'stripe';

// Stripe Configuration
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', {
    apiVersion: '2024-06-20',
});

const router = express.Router();

interface CheckoutRequest {
    priceId: string;
    package: 'audit' | 'fix' | 'care';
    mode?: 'payment' | 'subscription';
    ui_mode?: 'hosted' | 'embedded';
    customerEmail?: string;
}

// Create Checkout Session
router.post('/create-checkout-session', async (req: Request, res: Response) => {
    try {
        const { priceId, package: pkg, mode = 'payment', customerEmail } = req.body as CheckoutRequest;

        // Validate price ID
        if (!priceId || priceId.startsWith('price_')) {
            // Use test price IDs if not configured
            const testPrices = {
                audit: 'price_1TEST_audit_light_299',
                fix: 'price_1TEST_fix_sprint_990',
                care: 'price_1TEST_care_monthly_199'
            };
        }

        const sessionConfig: Stripe.Checkout.SessionCreateParams = {
            payment_method_types: ['card', 'sepa_debit'],
            line_items: [
                {
                    price: priceId,
                    quantity: 1,
                }
            ],
            mode: mode as Stripe.Checkout.SessionCreateParams.Mode,
            success_url: `${process.env.FRONTEND_URL || 'http://localhost:3000'}/success?session_id={CHECKOUT_SESSION_ID}&package=${pkg}`,
            cancel_url: `${process.env.FRONTEND_URL || 'http://localhost:3000'}/cancel?package=${pkg}`,
            metadata: {
                package: pkg,
                source: 'rudibot_landing'
            }
        };

        // Add customer email if provided
        if (customerEmail) {
            sessionConfig.customer_email = customerEmail;
        }

        // For subscriptions, add trial if desired
        if (mode === 'subscription') {
            sessionConfig.subscription_data = {
                trial_period_days: 7, // 7-day trial for Care package
                metadata: {
                    package: pkg
                }
            };
        }

        const session = await stripe.checkout.sessions.create(sessionConfig);

        res.json({ id: session.id, url: session.url });
    } catch (error: any) {
        console.error('Stripe Checkout Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Verify Checkout Session
router.get('/session/:sessionId', async (req: Request, res: Response) => {
    try {
        const session = await stripe.checkout.sessions.retrieve(req.params.sessionId);
        res.json({
            status: session.status,
            payment_status: session.payment_status,
            customer_email: session.customer_email,
            metadata: session.metadata
        });
    } catch (error: any) {
        res.status(500).json({ error: error.message });
    }
});

// Webhook handler for Stripe events
router.post('/webhook', express.raw({ type: 'application/json' }), async (req: Request, res: Response) => {
    const sig = req.headers['stripe-signature'];
    const endpointSecret = process.env.STRIPE_WEBHOOK_SECRET;

    let event: Stripe.Event;

    try {
        event = stripe.webhooks.constructEvent(req.body, sig as string, endpointSecret!);
    } catch (err: any) {
        console.error('Webhook Error:', err.message);
        return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    // Handle events
    switch (event.type) {
        case 'checkout.session.completed':
            const session = event.data.object as Stripe.Checkout.Session;
            console.log('✅ Payment successful:', session.id);
            // TODO: Send confirmation email, activate service, notify via Telegram
            break;

        case 'invoice.payment_succeeded':
            const invoice = event.data.object as Stripe.Invoice;
            console.log('✅ Subscription payment:', invoice.id);
            break;

        case 'invoice.payment_failed':
            const failedInvoice = event.data.object as Stripe.Invoice;
            console.log('❌ Payment failed:', failedInvoice.id);
            // TODO: Notify customer, retry logic
            break;

        case 'customer.subscription.deleted':
            const subscription = event.data.object as Stripe.Subscription;
            console.log('❌ Subscription cancelled:', subscription.id);
            break;

        default:
            console.log(`Unhandled event type: ${event.type}`);
    }

    res.json({ received: true });
});

// Create customer portal session
router.post('/customer-portal', async (req: Request, res: Response) => {
    try {
        const { customerId } = req.body;
        
        const session = await stripe.billingPortal.sessions.create({
            customer: customerId,
            return_url: `${process.env.FRONTEND_URL || 'http://localhost:3000'}/account`
        });

        res.json({ url: session.url });
    } catch (error: any) {
        res.status(500).json({ error: error.message });
    }
});

export default router;
