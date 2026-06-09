const fs = require('fs');
const path = require('path');

/**
 * Reminder Service — Fristenlogik für Kündigungen und Zahlungen
 * 
 * Funktionen:
 * - Kündigungsfristen berechnen und tracken
 * - Erinnerungen vor Fristablauf
 * - Telegram/E-Mail Benachrichtigungen
 * - Kalender-Integration (ICS-Export)
 * - Wiederkehrende Erinnerungen
 */

class ReminderService {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../../state/reminders');
    this.reminders = [];
    this.sentNotifications = new Map();
    this.notificationChannels = options.notificationChannels || ['console'];
    this.telegramBot = options.telegramBot;
    
    this.reminderDefaults = {
      cancellationWarningDays: [30, 14, 7, 3, 1],  // Warnungen vor Kündigungsfrist
      paymentWarningDays: [7, 3, 1],              // Warnungen vor Zahlungsfrist
      checkInterval: 60 * 60 * 1000              // Prüfung alle Stunde
    };
    
    this.ensureStorageDir();
    this.loadReminders();
    this.startReminderLoop();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  loadReminders() {
    try {
      const filePath = path.join(this.storagePath, 'reminders.json');
      if (fs.existsSync(filePath)) {
        const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        this.reminders = data.reminders || [];
      }
    } catch (err) {
      this.logger.error?.('reminder.load_failed', { error: err.message });
    }
  }

  saveReminders() {
    try {
      fs.writeFileSync(
        path.join(this.storagePath, 'reminders.json'),
        JSON.stringify({
          updatedAt: new Date().toISOString(),
          reminders: this.reminders
        }, null, 2)
      );
    } catch (err) {
      this.logger.error?.('reminder.save_failed', { error: err.message });
    }
  }

  /**
   * Add a reminder for subscription cancellation deadline
   */
  addCancellationReminder(subscription) {
    const { id, name, cancelDeadline, cost, category } = subscription;
    
    if (!cancelDeadline) {
      this.logger.warn?.('reminder.no_deadline', { subscription: name });
      return null;
    }

    const reminder = {
      id: `rem_cancel_${id}_${Date.now()}`,
      type: 'cancellation_deadline',
      subscriptionId: id,
      subscriptionName: name,
      deadline: cancelDeadline,
      cost,
      category: category || 'other',
      createdAt: new Date().toISOString(),
      notifications: [],
      status: 'active'
    };

    this.reminders.push(reminder);
    this.saveReminders();

    this.logger.info?.('reminder.created', {
      id: reminder.id,
      subscription: name,
      deadline: cancelDeadline
    });

    return reminder;
  }

  /**
   * Add payment due reminder
   */
  addPaymentReminder(invoice) {
    const { id, vendor, amount, dueDate, category } = invoice;
    
    if (!dueDate) return null;

    const reminder = {
      id: `rem_payment_${id}_${Date.now()}`,
      type: 'payment_due',
      invoiceId: id,
      vendor,
      amount,
      deadline: dueDate,
      category: category || 'other',
      createdAt: new Date().toISOString(),
      notifications: [],
      status: 'active'
    };

    this.reminders.push(reminder);
    this.saveReminders();

    return reminder;
  }

  /**
   * Add custom reminder
   */
  addCustomReminder(type, title, deadline, details = {}) {
    const reminder = {
      id: `rem_${type}_${Date.now()}`,
      type,
      title,
      deadline,
      details,
      createdAt: new Date().toISOString(),
      notifications: [],
      status: 'active'
    };

    this.reminders.push(reminder);
    this.saveReminders();

    return reminder;
  }

  /**
   * Start background loop for checking reminders
   */
  startReminderLoop() {
    setInterval(() => {
      this.checkReminders();
    }, this.reminderDefaults.checkInterval);

    this.logger.info?.('reminder.loop_started', { interval: this.reminderDefaults.checkInterval });
  }

  /**
   * Check all active reminders and send notifications
   */
  async checkReminders() {
    const now = new Date();
    const activeReminders = this.reminders.filter(r => r.status === 'active');

    for (const reminder of activeReminders) {
      const deadline = new Date(reminder.deadline);
      const daysUntil = Math.floor((deadline - now) / (1000 * 60 * 60 * 24));

      if (daysUntil < 0) {
        // Deadline passed
        reminder.status = 'expired';
        await this.sendNotification(reminder, 'expired', {
          message: `⚠️ FRIST ABGELAUFEN: ${reminder.subscriptionName || reminder.title}\nKündigung nicht mehr möglich ohne neue Periode!`,
          urgency: 'critical'
        });
        continue;
      }

      // Check if we should send notification for this reminder
      const warningDays = reminder.type === 'cancellation_deadline' 
        ? this.reminderDefaults.cancellationWarningDays 
        : this.reminderDefaults.paymentWarningDays;

      for (const warningDay of warningDays) {
        if (daysUntil <= warningDay && !this.hasBeenNotified(reminder.id, warningDay)) {
          await this.sendNotification(reminder, warningDay, {
            message: this.formatReminderMessage(reminder, daysUntil),
            urgency: daysUntil <= 3 ? 'high' : 'medium'
          });
          this.markNotified(reminder.id, warningDay);
          reminder.notifications.push({
            sentAt: new Date().toISOString(),
            daysBefore: warningDay,
            channel: 'console'
          });
        }
      }
    }

    this.saveReminders();
  }

  /**
   * Format reminder message
   */
  formatReminderMessage(reminder, daysUntil) {
    if (reminder.type === 'cancellation_deadline') {
      const cost = reminder.cost ? ` (${reminder.cost}€/Monat)` : '';
      const urgency = daysUntil <= 3 ? '🚨' : daysUntil <= 7 ? '⚠️' : '⏰';
      
      return `${urgency} KÜNDIGUNGSFRIST in ${daysUntil} Tagen${cost}\n` +
             `Abo: ${reminder.subscriptionName}\n` +
             `Deadline: ${reminder.deadline}\n` +
             `Aktion: Sofort kündigen oder Verlängern!`;
    }

    if (reminder.type === 'payment_due') {
      return `💰 ZAHLUNGSFRIST in ${daysUntil} Tagen\n` +
             `Rechnung: ${reminder.vendor}\n` +
             `Betrag: ${reminder.amount}€\n` +
             `Fällig: ${reminder.deadline}`;
    }

    return `⏰ Erinnerung: ${reminder.title}\n` +
           `Frist: ${reminder.deadline} (${daysUntil} Tage)`;
  }

  /**
   * Send notification through configured channels
   */
  async sendNotification(reminder, trigger, { message, urgency }) {
    for (const channel of this.notificationChannels) {
      try {
        switch (channel) {
          case 'console':
            console.log(`\n${'='.repeat(50)}`);
            console.log(`📢 ERINNERUNG — ${urgency.toUpperCase()}`);
            console.log(`${'='.repeat(50)}`);
            console.log(message);
            console.log(`${'='.repeat(50)}\n`);
            break;
          
          case 'telegram':
            if (this.telegramBot) {
              await this.sendTelegramNotification(message);
            }
            break;
          
          case 'email':
            // TODO: Implement email notification
            break;
        }
      } catch (err) {
        this.logger.error?.('reminder.notification_failed', { channel, error: err.message });
      }
    }
  }

  async sendTelegramNotification(message) {
    // Placeholder - would need actual bot integration
    this.logger.info?.('reminder.telegram_sent', { message: message.substring(0, 100) });
  }

  hasBeenNotified(reminderId, daysBefore) {
    const key = `${reminderId}_${daysBefore}`;
    return this.sentNotifications.has(key);
  }

  markNotified(reminderId, daysBefore) {
    const key = `${reminderId}_${daysBefore}`;
    this.sentNotifications.set(key, new Date().toISOString());
  }

  /**
   * Get all active reminders sorted by urgency
   */
  getActiveReminders() {
    return this.reminders
      .filter(r => r.status === 'active')
      .map(r => ({
        ...r,
        daysUntil: this.daysUntil(r.deadline)
      }))
      .sort((a, b) => a.daysUntil - b.daysUntil);
  }

  /**
   * Get upcoming deadlines (next 30 days)
   */
  getUpcomingDeadlines(days = 30) {
    const now = new Date();
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() + days);

    return this.reminders
      .filter(r => {
        if (r.status !== 'active') return false;
        const deadline = new Date(r.deadline);
        return deadline >= now && deadline <= cutoff;
      })
      .map(r => ({
        ...r,
        daysUntil: this.daysUntil(r.deadline)
      }))
      .sort((a, b) => a.daysUntil - b.daysUntil);
  }

  /**
   * Get expired reminders
   */
  getExpiredReminders() {
    return this.reminders.filter(r => r.status === 'expired');
  }

  /**
   * Mark reminder as completed (e.g., after cancellation)
   */
  completeReminder(reminderId) {
    const reminder = this.reminders.find(r => r.id === reminderId);
    if (reminder) {
      reminder.status = 'completed';
      reminder.completedAt = new Date().toISOString();
      this.saveReminders();
      return true;
    }
    return false;
  }

  /**
   * Generate ICS calendar file for reminders
   */
  generateICS() {
    const activeReminders = this.getActiveReminders();
    let ics = 'BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Rudibot//Reminder Service//DE\n';

    for (const reminder of activeReminders) {
      ics += 'BEGIN:VEVENT\n';
      ics += `UID:${reminder.id}@rudibot.local\n`;
      ics += `DTSTART:${reminder.deadline.replace(/-/g, '')}T000000Z\n`;
      ics += `SUMMARY:${reminder.subscriptionName || reminder.title || 'Erinnerung'}\n`;
      ics += `DESCRIPTION:${reminder.type === 'cancellation_deadline' ? 'Kündigungsfrist' : 'Zahlungsfrist'}\n`;
      ics += 'BEGIN:VALARM\n';
      ics += 'ACTION:DISPLAY\n';
      ics += 'TRIGGER:-P3D\n';
      ics += 'END:VALARM\n';
      ics += 'END:VEVENT\n';
    }

    ics += 'END:VCALENDAR';
    
    const filePath = path.join(this.storagePath, 'reminders.ics');
    fs.writeFileSync(filePath, ics);
    
    return filePath;
  }

  /**
   * Get summary statistics
   */
  getSummary() {
    const active = this.reminders.filter(r => r.status === 'active');
    const expired = this.reminders.filter(r => r.status === 'expired');
    const completed = this.reminders.filter(r => r.status === 'completed');

    return {
      total: this.reminders.length,
      active: active.length,
      expired: expired.length,
      completed: completed.length,
      upcoming7Days: this.getUpcomingDeadlines(7).length,
      upcoming30Days: this.getUpcomingDeadlines(30).length,
      critical: active.filter(r => this.daysUntil(r.deadline) <= 3).length
    };
  }

  daysUntil(dateString) {
    if (!dateString) return 999;
    const date = new Date(dateString);
    const now = new Date();
    return Math.floor((date - now) / (1000 * 60 * 60 * 24));
  }
}

module.exports = { ReminderService };
