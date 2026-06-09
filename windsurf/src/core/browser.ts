import { chromium, Browser, Page, BrowserContext } from 'playwright';
import { BrowserAction } from './types.js';

export class BrowserController {
  private browser?: Browser;
  private context?: BrowserContext;
  private page?: Page;

  async init(headless: boolean = true): Promise<void> {
    this.browser = await chromium.launch({ headless });
    this.context = await this.browser.newContext();
    this.page = await this.context.newPage();
  }

  async execute(action: BrowserAction): Promise<string> {
    if (!this.page) throw new Error('Browser not initialized');

    switch (action.action) {
      case 'navigate':
        if (!action.url) throw new Error('URL required for navigate');
        await this.page.goto(action.url);
        return `Navigated to ${action.url}`;

      case 'click':
        if (!action.selector) throw new Error('Selector required for click');
        await this.page.click(action.selector);
        return `Clicked ${action.selector}`;

      case 'type':
        if (!action.selector || !action.text) throw new Error('Selector and text required for type');
        await this.page.fill(action.selector, action.text);
        return `Typed into ${action.selector}`;

      case 'screenshot':
        const screenshot = await this.page.screenshot();
        const base64 = screenshot.toString('base64');
        return `data:image/png;base64,${base64}`;

      case 'scroll':
        const direction = action.direction || 'down';
        await this.page.evaluate((dir) => {
          window.scrollBy(0, dir === 'down' ? 500 : -500);
        }, direction);
        return `Scrolled ${direction}`;

      case 'extract':
        if (!action.selector) throw new Error('Selector required for extract');
        const text = await this.page.textContent(action.selector);
        return text || '';

      case 'close':
        await this.close();
        return 'Browser closed';

      default:
        throw new Error(`Unknown action: ${action.action}`);
    }
  }

  async close(): Promise<void> {
    if (this.page) await this.page.close();
    if (this.context) await this.context.close();
    if (this.browser) await this.browser.close();
    this.page = undefined;
    this.context = undefined;
    this.browser = undefined;
  }
}
