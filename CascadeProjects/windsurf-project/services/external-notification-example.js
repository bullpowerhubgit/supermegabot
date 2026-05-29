/**
 * Beispiel: Wie externe Services Notifications an den Telegram Bot senden
 * 
 * Dieses Beispiel zeigt, wie dein Shopify Service (oder jeder andere Service)
 * Notifications an den Standalone Telegram Bot senden kann.
 */

import NotificationClient from './telegram-notification-client.js';

// Beispiel für Shopify Service
class ShopifyNotificationService {
  constructor() {
    this.notifier = new NotificationClient({
      botUrl: process.env.TELEGRAM_BOT_URL || 'http://localhost:8000',
      serviceName: 'shopify'
    });
  }

  async handleNewOrder(order) {
    await this.notifier.info(
      `🛒 Neue Bestellung #${order.id}`,
      `Kunde: ${order.customer.firstName} ${order.customer.lastName}\n` +
      `Betrag: €${order.totalPrice}\n` +
      `Produkte: ${order.lineItems.length}x`,
      {
        order_id: order.id,
        customer_email: order.customer.email,
        total_price: order.totalPrice
      }
    );
  }

  async handleAbandonedCart(checkout) {
    await this.notifier.warning(
      `🛒 Warenkorb verlassen`,
      `Kunde hat Checkout bei €${checkout.totalPrice} verlassen\n` +
      `Verbleibende Zeit: 24h für Recovery`,
      {
        checkout_id: checkout.id,
        customer_email: checkout.customer.email,
        abandoned_value: checkout.totalPrice
      }
    );
  }

  async handleOrderFulfillment(order) {
    await this.notifier.success(
      `✅ Bestellung #${order.id} versendet`,
      `Tracking: ${order.trackingNumber}\n` +
      `Lieferung: ${order.shippingAddress.city}`,
      {
        order_id: order.id,
        tracking_number: order.trackingNumber,
        fulfillment_date: new Date().toISOString()
      }
    );
  }

  async handleApiError(error) {
    await this.notifier.error(
      `🚨 Shopify API Fehler`,
      `Fehler: ${error.message}\n` +
      `Endpoint: ${error.endpoint}\n` +
      `Status: ${error.status}`,
      {
        error_code: error.code,
        endpoint: error.endpoint,
        timestamp: new Date().toISOString()
      }
    );
  }

  async handleSystemCritical(issue) {
    await this.notifier.critical(
      `🚨 Shopify System-Ausfall`,
      `Problem: ${issue.description}\n` +
      `Auswirkung: Bestellungen können nicht verarbeitet werden`,
      {
        issue_type: issue.type,
        severity: 'critical',
        timestamp: new Date().toISOString()
      }
    );
  }
}

// Beispiel für GitHub Service
class GitHubNotificationService {
  constructor() {
    this.notifier = new NotificationClient({
      botUrl: process.env.TELEGRAM_BOT_URL || 'http://localhost:8000',
      serviceName: 'github'
    });
  }

  async handlePullRequest(pr) {
    await this.notifier.info(
      `🔄 Pull Request #${pr.number}`,
      `Titel: ${pr.title}\n` +
      `Author: ${pr.author.login}\n` +
      `Repo: ${pr.repository.name}`,
      {
        pr_number: pr.number,
        repo: pr.repository.name,
        author: pr.author.login
      }
    );
  }

  async handleDeployment(deployment) {
    await this.notifier.success(
      `🚀 Deployment erfolgreich`,
      `Environment: ${deployment.environment}\n` +
      `Commit: ${deployment.sha.substring(0, 7)}\n` +
      `Repo: ${deployment.repository}`,
      {
        deployment_id: deployment.id,
        environment: deployment.environment,
        commit_sha: deployment.sha
      }
    );
  }

  async handleWorkflowFailure(workflow) {
    await this.notifier.error(
      `❌ Workflow fehlgeschlagen`,
      `Workflow: ${workflow.name}\n` +
      `Branch: ${workflow.head_branch}\n` +
      `Repo: ${workflow.repository}`,
      {
        workflow_id: workflow.id,
        run_number: workflow.run_number,
        failure_reason: workflow.conclusion
      }
    );
  }
}

// Export für direkten Import
export { ShopifyNotificationService, GitHubNotificationService };

// Beispiel-Usage:
/*
import { ShopifyNotificationService } from './external-notification-example.js';

const shopifyNotifier = new ShopifyNotificationService();

// In deinem Shopify Service:
await shopifyNotifier.handleNewOrder(order);
await shopifyNotifier.handleAbandonedCart(checkout);
await shopifyNotifier.handleApiError(error);
*/
