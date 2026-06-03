/**
 * Commerce Module
 * Shopify, Printify, Orders, Revenue
 */

const Orchestrator = require('../../core/orchestrator');

class CommerceModule {
  constructor(orchestrator) {
    this.orchestrator = orchestrator;
    this.logger = orchestrator.logger;
    this.name = 'commerce';
    
    this.registerJobs();
  }

  registerJobs() {
    // Shopify Jobs
    this.orchestrator.registerJob('commerce', 'sync_orders', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '*/5 * * * *', // Alle 5 Minuten
      handler: this.syncShopifyOrders.bind(this),
      timeout: 60000
    });

    this.orchestrator.registerJob('commerce', 'sync_products', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '0 */2 * * *', // Alle 2 Stunden
      handler: this.syncShopifyProducts.bind(this),
      timeout: 120000
    });

    this.orchestrator.registerJob('commerce', 'process_refunds', {
      class: Orchestrator.prototype.JOB_CLASSES.APPROVE,
      requiresApproval: true,
      handler: this.processRefunds.bind(this),
      timeout: 30000
    });

    // Printify Jobs
    this.orchestrator.registerJob('commerce', 'sync_printify_orders', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '*/10 * * * *', // Alle 10 Minuten
      handler: this.syncPrintifyOrders.bind(this),
      timeout: 60000
    });

    this.orchestrator.registerJob('commerce', 'create_printify_product', {
      class: Orchestrator.prototype.JOB_CLASSES.APPROVE,
      requiresApproval: true,
      handler: this.createPrintifyProduct.bind(this),
      timeout: 45000
    });

    // Revenue Jobs
    this.orchestrator.registerJob('commerce', 'calculate_revenue', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '0 0 * * *', // Täglich Mitternacht
      handler: this.calculateRevenue.bind(this),
      timeout: 300000
    });

    this.orchestrator.registerJob('commerce', 'revenue_report', {
      class: Orchestrator.prototype.JOB_CLASSES.AUTO,
      schedule: '0 8 * * 1', // Montags 8:00 Uhr
      handler: this.generateRevenueReport.bind(this),
      timeout: 60000
    });

    this.logger.info('📦 Commerce Module Jobs registriert');
  }

  // Shopify Orders Sync
  async syncShopifyOrders(context, executionId) {
    this.logger.info(`🔄 Shopify Orders Sync (${executionId})`);
    
    try {
      const shopify = require('../shopify/client');
      const orders = await shopify.getRecentOrders(50);
      
      let processed = 0;
      let errors = 0;

      for (const order of orders) {
        try {
          await this.processShopifyOrder(order);
          processed++;
        } catch (error) {
          this.logger.error(`Fehler bei Order ${order.id}:`, error.message);
          errors++;
        }
      }

      return {
        success: true,
        data: {
          total: orders.length,
          processed,
          errors,
          executionId
        }
      };
    } catch (error) {
      throw new Error(`Shopify Orders Sync fehlgeschlagen: ${error.message}`);
    }
  }

  // Shopify Products Sync
  async syncShopifyProducts(context, executionId) {
    this.logger.info(`🔄 Shopify Products Sync (${executionId})`);
    
    try {
      const shopify = require('../shopify/client');
      const products = await shopify.getAllProducts();
      
      let updated = 0;
      let created = 0;

      for (const product of products) {
        const existing = await this.findProductByShopifyId(product.id);
        
        if (existing) {
          await this.updateProduct(existing.id, product);
          updated++;
        } else {
          await this.createProduct(product);
          created++;
        }
      }

      return {
        success: true,
        data: {
          total: products.length,
          updated,
          created,
          executionId
        }
      };
    } catch (error) {
      throw new Error(`Shopify Products Sync fehlgeschlagen: ${error.message}`);
    }
  }

  // Refunds Processing (APPROVE Job)
  async processRefunds(context, executionId) {
    this.logger.info(`💰 Refunds Processing (${executionId})`);
    
    const { orderId, amount, reason } = context;
    
    if (!orderId || !amount) {
      throw new Error('orderId und amount erforderlich');
    }

    try {
      const shopify = require('../shopify/client');
      
      // Shopify Refund erstellen
      const refund = await shopify.createRefund(orderId, {
        amount: parseFloat(amount),
        reason: reason || 'Customer request'
      });

      // Lokale Daten aktualisieren
      await this.updateOrderRefundStatus(orderId, refund.id);

      // Event emittieren
      this.orchestrator.emit('refund:processed', {
        orderId,
        refundId: refund.id,
        amount,
        executionId
      });

      return {
        success: true,
        data: {
          refund,
          orderId,
          amount,
          executionId
        }
      };
    } catch (error) {
      throw new Error(`Refund Processing fehlgeschlagen: ${error.message}`);
    }
  }

  // Printify Orders Sync
  async syncPrintifyOrders(context, executionId) {
    this.logger.info(`🔄 Printify Orders Sync (${executionId})`);
    
    try {
      const printify = require('../printify/client');
      const orders = await printify.getRecentOrders();
      
      let processed = 0;

      for (const order of orders) {
        await this.processPrintifyOrder(order);
        processed++;
      }

      return {
        success: true,
        data: {
          total: orders.length,
          processed,
          executionId
        }
      };
    } catch (error) {
      throw new Error(`Printify Orders Sync fehlgeschlagen: ${error.message}`);
    }
  }

  // Printify Product Creation (APPROVE Job)
  async createPrintifyProduct(context, executionId) {
    this.logger.info(`🎨 Printify Product Creation (${executionId})`);
    
    const { shopifyProductId, printData } = context;
    
    if (!shopifyProductId || !printData) {
      throw new Error('shopifyProductId und printData erforderlich');
    }

    try {
      const shopify = require('../shopify/client');
      const printify = require('../printify/client');
      
      // Shopify Produkt holen
      const shopifyProduct = await shopify.getProduct(shopifyProductId);
      
      // Printify Produkt erstellen
      const printifyProduct = await printify.createProduct({
        title: shopifyProduct.title,
        description: shopifyProduct.description,
        print_data: printData
      });

      // Verknüpfung speichern
      await this.linkPrintifyProduct(shopifyProductId, printifyProduct.id);

      return {
        success: true,
        data: {
          shopifyProductId,
          printifyProductId: printifyProduct.id,
          executionId
        }
      };
    } catch (error) {
      throw new Error(`Printify Product Creation fehlgeschlagen: ${error.message}`);
    }
  }

  // Revenue Calculation
  async calculateRevenue(context, executionId) {
    this.logger.info(`💸 Revenue Calculation (${executionId})`);
    
    try {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const startDate = yesterday.toISOString().split('T')[0];
      const endDate = startDate;

      // Shopify Umsätze
      const shopifyRevenue = await this.calculateShopifyRevenue(startDate, endDate);
      
      // Printify Umsätze
      const printifyRevenue = await this.calculatePrintifyRevenue(startDate, endDate);
      
      // Gesamtumsatz
      const totalRevenue = shopifyRevenue + printifyRevenue;

      // In Datenbank speichern
      await this.saveRevenueData({
        date: startDate,
        shopify: shopifyRevenue,
        printify: printifyRevenue,
        total: totalRevenue,
        executionId
      });

      return {
        success: true,
        data: {
          date: startDate,
          shopify: shopifyRevenue,
          printify: printifyRevenue,
          total: totalRevenue,
          executionId
        }
      };
    } catch (error) {
      throw new Error(`Revenue Calculation fehlgeschlagen: ${error.message}`);
    }
  }

  // Revenue Report Generation
  async generateRevenueReport(context, executionId) {
    this.logger.info(`📊 Revenue Report Generation (${executionId})`);
    
    try {
      const lastWeek = new Date();
      lastWeek.setDate(lastWeek.getDate() - 7);
      
      const revenueData = await this.getRevenueData(lastWeek.toISOString().split('T')[0]);
      
      const report = {
        period: 'Letzte 7 Tage',
        totalRevenue: revenueData.reduce((sum, day) => sum + day.total, 0),
        shopifyRevenue: revenueData.reduce((sum, day) => sum + day.shopify, 0),
        printifyRevenue: revenueData.reduce((sum, day) => sum + day.printify, 0),
        dailyBreakdown: revenueData,
        generatedAt: new Date(),
        executionId
      };

      // Report speichern
      await this.saveRevenueReport(report);

      // Event emittieren
      this.orchestrator.emit('report:generated', {
        type: 'revenue',
        report,
        executionId
      });

      return {
        success: true,
        data: report
      };
    } catch (error) {
      throw new Error(`Revenue Report Generation fehlgeschlagen: ${error.message}`);
    }
  }

  // Helper Functions
  async processShopifyOrder(order) {
    // Order in lokale DB speichern/updaten
    await this.saveShopifyOrder(order);
    
    // Events auslösen
    if (order.financial_status === 'paid') {
      this.orchestrator.emit('order:paid', { order });
    }
    
    if (order.fulfillment_status === 'fulfilled') {
      this.orchestrator.emit('order:fulfilled', { order });
    }
  }

  async processPrintifyOrder(order) {
    // Printify Order in lokale DB speichern
    await this.savePrintifyOrder(order);
    
    // Shopify Order updaten falls vorhanden
    if (order.shopify_order_id) {
      await this.updateShopifyOrderFromPrintify(order);
    }
  }

  async calculateShopifyRevenue(startDate, endDate) {
    const shopify = require('../shopify/client');
    const orders = await shopify.getOrdersByDate(startDate, endDate);
    
    return orders
      .filter(order => order.financial_status === 'paid')
      .reduce((sum, order) => sum + parseFloat(order.total_price), 0);
  }

  async calculatePrintifyRevenue(startDate, endDate) {
    const printify = require('../printify/client');
    const orders = await printify.getOrdersByDate(startDate, endDate);
    
    return orders
      .filter(order => order.status === 'fulfilled')
      .reduce((sum, order) => sum + parseFloat(order.total_price), 0);
  }

  // Database Helper Functions (Platzhalter)
  async saveShopifyOrder(order) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`💾 Shopify Order gespeichert: ${order.id}`);
  }

  async savePrintifyOrder(order) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`💾 Printify Order gespeichert: ${order.id}`);
  }

  async findProductByShopifyId(shopifyId) {
    // TODO: Implementieren mit echter DB
    return null;
  }

  async createProduct(product) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`📦 Produkt erstellt: ${product.id}`);
  }

  async updateProduct(productId, product) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`📦 Produkt aktualisiert: ${productId}`);
  }

  async updateOrderRefundStatus(orderId, refundId) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`💰 Order Refund Status aktualisiert: ${orderId} -> ${refundId}`);
  }

  async linkPrintifyProduct(shopifyId, printifyId) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`🔗 Produkte verknüpft: Shopify ${shopifyId} -> Printify ${printifyId}`);
  }

  async saveRevenueData(data) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`💸 Revenue Daten gespeichert: ${data.date}`);
  }

  async getRevenueData(startDate) {
    // TODO: Implementieren mit echter DB
    return [];
  }

  async saveRevenueReport(report) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`📊 Revenue Report gespeichert`);
  }

  async updateShopifyOrderFromPrintify(printifyOrder) {
    // TODO: Implementieren mit echter DB
    this.logger.info(`🔄 Shopify Order von Printify aktualisiert: ${printifyOrder.shopify_order_id}`);
  }
}

module.exports = CommerceModule;
