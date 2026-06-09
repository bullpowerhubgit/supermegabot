#!/usr/bin/env node

// 💰 VOLLAUTOMATISCHE MONETARISIERUNG
// Rudolf Sarkany · Autonomous Revenue System
// ============================================================

const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
const jwt = require('jsonwebtoken');

// 🎯 Preis-Modelle (automatisch konfiguriert)
const PRICING_TIERS = {
    starter: {
        name: 'Starter',
        price: 29, // EUR
        interval: 'month',
        features: [
            '1 Shopify Store',
            'Basis Automation',
            'Telegram Alerts',
            'Email Support'
        ],
        limits: {
            stores: 1,
            products: 100,
            automations: 5,
            apiCalls: 1000
        }
    },
    pro: {
        name: 'Pro',
        price: 79, // EUR
        interval: 'month',
        features: [
            '5 Shopify Stores',
            'Erweiterte Automation',
            'KI-Produktfinder',
            'Prioritäts-Support',
            'Analytics Dashboard'
        ],
        limits: {
            stores: 5,
            products: 1000,
            automations: 25,
            apiCalls: 10000
        }
    },
    agency: {
        name: 'Agency',
        price: 199, // EUR
        interval: 'month',
        features: [
            'Unbegrenzte Stores',
            'Vollautomation',
            'White-Label Option',
            'Team Management',
            'API-Zugriff',
            '24/7 Premium Support'
        ],
        limits: {
            stores: -1, // unlimited
            products: -1,
            automations: -1,
            apiCalls: 100000
        }
    }
};

// 🤖 Autonome Abonnement-Verwaltung
class AutonomousMonetization {
    constructor() {
        this.subscriptions = new Map();
        this.revenue = 0;
        this.initialize();
    }

    async initialize() {
        console.log('💰 AUTONOMOUS MONETIZATION SYSTEM INITIALIZED');
        console.log('='.repeat(60));
        
        Object.entries(PRICING_TIERS).forEach(([key, tier]) => {
            console.log(`📦 ${tier.name}: ${tier.price}€/${tier.interval}`);
        });
        
        // Starte autonome Revenue-Überwachung
        this.startRevenueMonitoring();
    }

    // 🔄 Autonome Stripe-Integration
    async createCheckoutSession(tier, customerEmail) {
        const tierConfig = PRICING_TIERS[tier];
        if (!tierConfig) throw new Error('Invalid tier');

        try {
            const session = await stripe.checkout.sessions.create({
                payment_method_types: ['card'],
                line_items: [{
                    price_data: {
                        currency: 'eur',
                        product_data: {
                            name: `AutoPilot ${tierConfig.name}`,
                            description: tierConfig.features.join(', ')
                        },
                        unit_amount: tierConfig.price * 100, // Cent
                        recurring: {
                            interval: tierConfig.interval
                        }
                    },
                    quantity: 1
                }],
                mode: 'subscription',
                success_url: `${process.env.FRONTEND_URL}/success?session_id={CHECKOUT_SESSION_ID}`,
                cancel_url: `${process.env.FRONTEND_URL}/cancel`,
                customer_email: customerEmail,
                metadata: {
                    tier: tier,
                    plan: tierConfig.name
                }
            });

            console.log(`✅ Checkout session created for ${tierConfig.name}`);
            return session;
        } catch (error) {
            console.error('❌ Stripe error:', error.message);
            throw error;
        }
    }

    // 🎯 Autonome Usage-Tracking
    trackUsage(userId, action) {
        if (!this.subscriptions.has(userId)) {
            this.subscriptions.set(userId, {
                usage: {},
                lastReset: new Date()
            });
        }

        const userData = this.subscriptions.get(userId);
        userData.usage[action] = (userData.usage[action] || 0) + 1;
        
        console.log(`📊 Usage tracked: ${userId} - ${action}: ${userData.usage[action]}`);
    }

    // 📈 Autonome Revenue-Überwachung
    startRevenueMonitoring() {
        setInterval(() => {
            this.calculateRevenue();
        }, 60000); // Jede Minute

        console.log('📈 Revenue monitoring: ACTIVE');
    }

    async calculateRevenue() {
        try {
            // Hole Stripe-Daten
            const subscriptions = await stripe.subscriptions.list({
                status: 'active',
                limit: 100
            });

            let monthlyRevenue = 0;
            subscriptions.data.forEach(sub => {
                monthlyRevenue += sub.items.data[0].plan.amount / 100;
            });

            this.revenue = monthlyRevenue;
            
            if (monthlyRevenue > 0) {
                console.log(`💰 Monthly Revenue: ${monthlyRevenue.toFixed(2)} EUR`);
            }

            return monthlyRevenue;
        } catch (error) {
            console.error('❌ Revenue calculation error:', error.message);
            return 0;
        }
    }

    // 🎁 Autonomes Trial-System
    async createTrial(userId, tier = 'starter') {
        const trialEnd = new Date();
        trialEnd.setDate(trialEnd.getDate() + 14); // 14 Tage Trial

        const trialData = {
            userId,
            tier,
            startDate: new Date(),
            endDate: trialEnd,
            status: 'active',
            features: PRICING_TIERS[tier].features
        };

        console.log(`🎁 Trial created for ${userId}: ${tier} until ${trialEnd.toISOString()}`);
        return trialData;
    }

    // 🚨 Autonome Limits-Überprüfung
    checkLimits(userId, tier) {
        const tierConfig = PRICING_TIERS[tier];
        const userData = this.subscriptions.get(userId);
        
        if (!userData) return { allowed: false, reason: 'No subscription' };

        const currentUsage = userData.usage;
        const limits = tierConfig.limits;

        // Prüfe ob Limits überschritten
        for (const [resource, limit] of Object.entries(limits)) {
            if (limit === -1) continue; // Unlimited
            
            const usage = currentUsage[resource] || 0;
            if (usage >= limit) {
                return {
                    allowed: false,
                    reason: `${resource} limit exceeded: ${usage}/${limit}`,
                    resource,
                    limit,
                    usage
                };
            }
        }

        return { allowed: true };
    }
}

// 🚀 Singleton Export
const monetization = new AutonomousMonetization();
module.exports = monetization;
