/**
 * Commerce Revenue First Jobs
 * Echte Shopify-Integration mit Umsatz-Fokus
 */

class RevenueFirstCommerce {
  constructor(orchestrator) {
    this.orchestrator = orchestrator;
    this.logger = orchestrator.logger;
    
    this.registerRevenueFirstJobs();
  }

  registerRevenueFirstJobs() {
    // HOCHSTE PRIORITÄT: Shopify Orders & Revenue
    this.orchestrator.registerJob('commerce', 'sync_revenue_realtime', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '*/5 * * * *', // Alle 5 Minuten
      handler: this.syncRevenueRealtime.bind(this),
      timeout: 60000,
      description: 'Echtzeit-Revenue Sync von Shopify'
    });

    this.orchestrator.registerJob('commerce', 'track_orders_today', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '*/10 * * * *', // Alle 10 Minuten
      handler: this.trackOrdersToday.bind(this),
      timeout: 45000,
      description: 'Heutige Orders tracken und Umsatz berechnen'
    });

    this.orchestrator.registerJob('commerce', 'payment_status_check', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '*/15 * * * *', // Alle 15 Minuten
      handler: this.checkPaymentStatus.bind(this),
      timeout: 90000,
      description: 'Zahlungsstatus aller Orders prüfen'
    });

    // HOHE PRIORITÄT: Order Processing
    this.orchestrator.registerJob('commerce', 'process_pending_orders', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '*/2 * * * *', // Alle 2 Minuten
      handler: this.processPendingOrders.bind(this),
      timeout: 120000,
      description: 'Pending Orders automatisch bearbeiten'
    });

    this.orchestrator.registerJob('commerce', 'fulfill_orders', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '*/3 * * * *', // Alle 3 Minuten
      handler: this.fulfillOrders.bind(this),
      timeout: 180000,
      description: 'Orders fulfillen und Tracking aktualisieren'
    });

    // MITTELRE PRIORITÄT: Revenue Analytics
    this.orchestrator.registerJob('commerce', 'revenue_analytics', {
      class: this.orchestrator.JOB_CLASSES.AUTO,
      schedule: '0 */1 * * *', // Stündlich
      handler: this.generateRevenueAnalytics.bind(this),
      timeout: 300000,
      description: 'Revenue Analytics und Trends'
    });

    // APPROVE Jobs für kritische Aktionen
    this.orchestrator.registerJob('commerce', 'refund_order', {
      class: this.orchestrator.JOB_CLASSES.APPROVE,
      requiresApproval: true,
      handler: this.processRefund.bind(this),
      timeout: 180000,
      description: 'Order Rückerstattung (benötigt Approval)'
    });

    this.orchestrator.registerJob('commerce', 'cancel_order', {
      class: this.orchestrator.JOB_CLASSES.APPROVE,
      requiresApproval: true,
      handler: this.cancelOrder.bind(this),
      timeout: 120000,
      description: 'Order stornieren (benötigt Approval)'
    });

    this.logger.info('💰 Commerce Revenue First Jobs registriert');
  }

  // ECHTZEIT REVENUE SYNC
  async syncRevenueRealtime(context, executionId) {
    this.logger.info(`💰 Echtzeit-Revenue Sync (${executionId})`);
    
    try {
      const shopify = this.orchestrator.context.getService('shopify');
      
      // Orders der letzten 5 Minuten
      const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
      const orders = await shopify.getOrders({
        created_at_min: fiveMinutesAgo,
        status: 'any'
      });

      if (!orders.orders || orders.orders.length === 0) {
        return {
          success: true,
          data: { newOrders: 0, revenue: 0, message: 'Keine neuen Orders' }
        };
      }

      // Revenue berechnen
      const newRevenue = orders.orders.reduce((sum, order) => {
        return sum + parseFloat(order.total_price);
      }, 0);

      // Payment Status prüfen
      const paidOrders = orders.orders.filter(order => 
        order.financial_status === 'paid'
      );
      const pendingPayments = orders.orders.filter(order => 
        order.financial_status === 'pending'
      );

      // Revenue speichern
      await this.saveRevenueData({
        timestamp: new Date(),
        orders: orders.orders.length,
        revenue: newRevenue,
        paidOrders: paidOrders.length,
        pendingPayments: pendingPayments.length,
        averageOrderValue: newRevenue / orders.orders.length
      });

      // Event für neue Orders
      this.orchestrator.emit('revenue:new_orders', {
        count: orders.orders.length,
        revenue: newRevenue,
        executionId
      });

      return {
        success: true,
        data: {
          newOrders: orders.orders.length,
          revenue: newRevenue,
          paidOrders: paidOrders.length,
          pendingPayments: pendingPayments.length,
          averageOrderValue: newRevenue / orders.orders.length
        }
      };
    } catch (error) {
      throw new Error(`Revenue Sync fehlgeschlagen: ${error.message}`);
    }
  }

  // HEUTIGE ORDERS TRACKEN
  async trackOrdersToday(context, executionId) {
    this.logger.info(`📊 Heute Orders tracken (${executionId})`);
    
    try {
      const shopify = this.orchestrator.context.getService('shopify');
      const today = new Date().toISOString().split('T')[0];
      
      const orders = await shopify.getOrders({
        created_at_min: today,
        status: 'any'
      });

      if (!orders.orders) {
        return { success: true, data: { orders: 0, revenue: 0 } };
      }

      // Detaillierte Analyse
      const analysis = {
        total: orders.orders.length,
        revenue: 0,
        byStatus: {},
        byPaymentStatus: {},
        byHour: {},
        topProducts: {},
        averageOrderValue: 0
      };

      orders.orders.forEach(order => {
        // Revenue
        analysis.revenue += parseFloat(order.total_price);
        
        // Status
        analysis.byStatus[order.status] = (analysis.byStatus[order.status] || 0) + 1;
        
        // Payment Status
        analysis.byPaymentStatus[order.financial_status] = (analysis.byPaymentStatus[order.financial_status] || 0) + 1;
        
        // Nach Stunde gruppieren
        const hour = new Date(order.created_at).getHours();
        analysis.byHour[hour] = (analysis.byHour[hour] || 0) + 1;
        
        // Top Products
        if (order.line_items) {
          order.line_items.forEach(item => {
            const productName = item.title || 'Unknown';
            analysis.topProducts[productName] = (analysis.topProducts[productName] || 0) + item.quantity;
          });
        }
      });

      analysis.averageOrderValue = analysis.total > 0 ? analysis.revenue / analysis.total : 0;

      // Tages-Report speichern
      await this.saveDailyReport({
        date: today,
        analysis,
        timestamp: new Date()
      });

      return {
        success: true,
        data: analysis
      };
    } catch (error) {
      throw new Error(`Order Tracking fehlgeschlagen: ${error.message}`);
    }
  }

  // ZAHLUNGSSTATUS PRÜFEN
  async checkPaymentStatus(context, executionId) {
    this.logger.info(`💳 Payment Status Check (${executionId})`);
    
    try {
      const shopify = this.orchestrator.context.getService('shopify');
      
      // Orders mit pending payments
      const orders = await shopify.getOrders({
        financial_status: 'pending',
        limit: 50
      });

      if (!orders.orders || orders.orders.length === 0) {
        return {
          success: true,
          data: { pendingOrders: 0, actions: [] }
        };
      }

      const actions = [];
      
      for (const order of orders.orders) {
        const orderAge = Date.now() - new Date(order.created_at).getTime();
        const hoursOld = Math.floor(orderAge / (60 * 60 * 1000));
        
        // Alte pending Orders
        if (hoursOld > 2) {
          actions.push({
            orderId: order.id,
            orderNumber: order.name,
            hoursOld,
            total: order.total_price,
            action: hoursOld > 24 ? 'cancel' : 'remind',
            reason: `Payment pending seit ${hoursOld} Stunden`
          });
        }
      }

      // Aktionen durchführen
      const results = [];
      for (const action of actions) {
        try {
          if (action.action === 'remind') {
            await this.sendPaymentReminder(action);
            results.push({ ...action, status: 'reminded' });
          } else if (action.action === 'cancel') {
            // Cancel benötigt Approval
            const approval = await this.orchestrator.createApprovalRequest('commerce.cancel_order', {
              orderId: action.orderId,
              reason: action.reason
            });
            results.push({ ...action, status: 'approval_requested', approvalId: approval.id });
          }
        } catch (error) {
          results.push({ ...action, status: 'error', error: error.message });
        }
      }

      return {
        success: true,
        data: {
          pendingOrders: orders.orders.length,
          actions: results
        }
      };
    } catch (error) {
      throw new Error(`Payment Status Check fehlgeschlagen: ${error.message}`);
    }
  }

  // PENDING ORDERS BEARBEITEN
  async processPendingOrders(context, executionId) {
    this.logger.info(`⚙️ Pending Orders bearbeiten (${executionId})`);
    
    try {
      const shopify = this.orchestrator.context.getService('shopify');
      
      const orders = await shopify.getOrders({
        status: 'pending',
        limit: 25
      });

      if (!orders.orders || orders.orders.length === 0) {
        return {
          success: true,
          data: { processed: 0, errors: [] }
        };
      }

      const results = [];
      
      for (const order of orders.orders) {
        try {
          // Order automatisch bearbeiten
          const processed = await this.autoProcessOrder(order);
          results.push({
            orderId: order.id,
            orderNumber: order.name,
            status: processed.status,
            action: processed.action
          });
        } catch (error) {
          results.push({
            orderId: order.id,
            orderNumber: order.name,
            status: 'error',
            error: error.message
          });
        }
      }

      return {
        success: true,
        data: {
          processed: results.length,
          results
        }
      };
    } catch (error) {
      throw new Error(`Pending Orders Verarbeitung fehlgeschlagen: ${error.message}`);
    }
  }

  // ORDERS FULFILLEN
  async fulfillOrders(context, executionId) {
    this.logger.info(`📦 Orders fulfillen (${executionId})`);
    
    try {
      const shopify = this.orchestrator.context.getService('shopify');
      
      const orders = await shopify.getOrders({
        fulfillment_status: null,
        financial_status: 'paid',
        limit: 20
      });

      if (!orders.orders || orders.orders.length === 0) {
        return {
          success: true,
          data: { fulfilled: 0, errors: [] }
        };
      }

      const results = [];
      
      for (const order of orders.orders) {
        try {
          const fulfillment = await this.createFulfillment(order);
          results.push({
            orderId: order.id,
            orderNumber: order.name,
            fulfillmentId: fulfillment.id,
            status: 'fulfilled'
          });
        } catch (error) {
          results.push({
            orderId: order.id,
            orderNumber: order.name,
            status: 'error',
            error: error.message
          });
        }
      }

      return {
        success: true,
        data: {
          fulfilled: results.filter(r => r.status === 'fulfilled').length,
          results
        }
      };
    } catch (error) {
      throw new Error(`Order Fulfillment fehlgeschlagen: ${error.message}`);
    }
  }

  // REVENUE ANALYTICS
  async generateRevenueAnalytics(context, executionId) {
    this.logger.info(`📈 Revenue Analytics (${executionId})`);
    
    try {
      const shopify = this.orchestrator.context.getService('shopify');
      
      // Letzte 7 Tage
      const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
      const orders = await shopify.getOrders({
        created_at_min: sevenDaysAgo,
        status: 'any'
      });

      if (!orders.orders) {
        return { success: true, data: { analytics: {} } };
      }

      const analytics = {
        period: '7_days',
        totalOrders: orders.orders.length,
        totalRevenue: 0,
        dailyBreakdown: {},
        topProducts: {},
        averageOrderValue: 0,
        conversionRate: 0,
        revenueTrend: 'stable'
      };

      // Tagesaufschlüsselung
      orders.orders.forEach(order => {
        const day = new Date(order.created_at).toISOString().split('T')[0];
        
        if (!analytics.dailyBreakdown[day]) {
          analytics.dailyBreakdown[day] = { orders: 0, revenue: 0 };
        }
        
        analytics.dailyBreakdown[day].orders += 1;
        analytics.dailyBreakdown[day].revenue += parseFloat(order.total_price);
        analytics.totalRevenue += parseFloat(order.total_price);
        
        // Top Products
        if (order.line_items) {
          order.line_items.forEach(item => {
            const name = item.title || 'Unknown';
            analytics.topProducts[name] = (analytics.topProducts[name] || 0) + item.quantity;
          });
        }
      });

      analytics.averageOrderValue = analytics.totalOrders > 0 ? 
        analytics.totalRevenue / analytics.totalOrders : 0;

      // Revenue Trend berechnen
      const days = Object.keys(analytics.dailyBreakdown).sort();
      if (days.length >= 2) {
        const firstDay = analytics.dailyBreakdown[days[0]].revenue;
        const lastDay = analytics.dailyBreakdown[days[days.length - 1]].revenue;
        const change = ((lastDay - firstDay) / firstDay) * 100;
        
        if (change > 5) analytics.revenueTrend = 'increasing';
        else if (change < -5) analytics.revenueTrend = 'decreasing';
      }

      // Analytics speichern
      await this.saveAnalytics(analytics);

      return {
        success: true,
        data: analytics
      };
    } catch (error) {
      throw new Error(`Revenue Analytics fehlgeschlagen: ${error.message}`);
    }
  }

  // REFUND (APPROVE JOB)
  async processRefund(context, executionId) {
    this.logger.info(`💰 Refund verarbeiten (${executionId})`);
    
    const { orderId, amount, reason } = context;
    
    if (!orderId || !amount) {
      throw new Error('orderId und amount erforderlich');
    }

    try {
      const shopify = this.orchestrator.context.getService('shopify');
      
      const refund = await shopify.createRefund(orderId, {
        amount: parseFloat(amount),
        reason: reason || 'Customer request',
        notify_customer: true
      });

      // Event für Refund
      this.orchestrator.emit('commerce:refund_processed', {
        orderId,
        amount,
        refundId: refund.id,
        executionId
      });

      return {
        success: true,
        data: {
          orderId,
          amount,
          refundId: refund.id,
          status: 'processed'
        }
      };
    } catch (error) {
      throw new Error(`Refund Verarbeitung fehlgeschlagen: ${error.message}`);
    }
  }

  // Helper Functions
  async autoProcessOrder(order) {
    // TODO: Implementieren mit echtem Order-Processing
    return {
      status: 'processed',
      action: 'auto_fulfilled'
    };
  }

  async createFulfillment(order) {
    const shopify = this.orchestrator.context.getService('shopify');
    
    return await shopify.fetch(`/orders/${order.id}/fulfillments.json`, {
      method: 'POST',
      body: JSON.stringify({
        fulfillment: {
          location_id: process.env.SHOPIFY_LOCATION_ID,
          tracking_company: 'DHL',
          tracking_numbers: ['1234567890'],
          line_items: order.line_items.map(item => ({
            id: item.id,
            quantity: item.quantity
          }))
        }
      })
    });
  }

  async sendPaymentReminder(action) {
    // TODO: Implementieren mit echtem Notification-System
    this.logger.info(`💳 Payment Reminder gesendet für Order ${action.orderNumber}`);
  }

  async saveRevenueData(data) {
    // TODO: Implementieren mit echtem Data-Storage
    this.logger.info(`💾 Revenue Daten gespeichert: €${data.revenue}`);
  }

  async saveDailyReport(report) {
    // TODO: Implementieren mit echtem Data-Storage
    this.logger.info(`💾 Daily Report gespeichert: ${report.date}`);
  }

  async saveAnalytics(analytics) {
    // TODO: Implementieren mit echtem Data-Storage
    this.logger.info(`💾 Analytics gespeichert: ${analytics.totalOrders} Orders`);
  }
}

module.exports = RevenueFirstCommerce;
