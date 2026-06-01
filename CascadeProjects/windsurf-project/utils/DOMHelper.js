/**
 * Sichere DOM-Manipulation Helper
 * Verhindert XSS-Angriffe durch sichere Alternativen zu innerHTML
 */

class DOMHelper {
  /**
   * Sicheres Erstellen von HTML-Elementen
   * @param {string} tagName - HTML Tag Name
   * @param {Object} attributes - HTML Attributes
   * @param {string|Node|Array} children - Child elements or text
   * @returns {HTMLElement}
   */
  static createElement(tagName, attributes = {}, children = []) {
    const element = document.createElement(tagName);
    
    // Sicheres Setzen von Attributen
    Object.entries(attributes).forEach(([key, value]) => {
      if (key === 'className') {
        element.className = this.escapeHtml(value);
      } else if (key === 'style' && typeof value === 'object') {
        Object.assign(element.style, value);
      } else if (key.startsWith('data-')) {
        element.setAttribute(key, String(value));
      } else if (key === 'textContent') {
        element.textContent = String(value);
      } else {
        element.setAttribute(key, String(value));
      }
    });
    
    // Sicheres Hinzufügen von Children
    if (typeof children === 'string') {
      element.textContent = children;
    } else if (Array.isArray(children)) {
      children.forEach(child => {
        if (typeof child === 'string') {
          element.appendChild(document.createTextNode(child));
        } else if (child instanceof Node) {
          element.appendChild(child);
        }
      });
    } else if (children instanceof Node) {
      element.appendChild(children);
    }
    
    return element;
  }

  /**
   * Sicheres Ersetzen von HTML-Inhalt
   * @param {HTMLElement} element - Target element
   * @param {string} html - Safe HTML content
   */
  static setHTML(element, html) {
    // HTML sanitization mit DOMParser
    const sanitized = this.sanitizeHTML(html);
    element.innerHTML = sanitized;
  }

  /**
   * HTML Sanitization
   * @param {string} html - Input HTML
   * @returns {string} - Sanitized HTML
   */
  static sanitizeHTML(html) {
    const temp = document.createElement('div');
    temp.textContent = html;
    return temp.innerHTML;
  }

  /**
   * Escaping für HTML-Text
   * @param {string} text - Input text
   * @returns {string} - Escaped text
   */
  static escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  /**
   * Sicheres Erstellen von Listen
   * @param {Array} items - List items
   * @param {Function} renderItem - Render function for each item
   * @param {Object} options - List options
   * @returns {HTMLElement}
   */
  static createList(items, renderItem, options = {}) {
    const { tagName = 'ul', className = '', itemClassName = '' } = options;
    const list = this.createElement(tagName, { className });
    
    items.forEach(item => {
      const listItem = this.createElement('li', { className: itemClassName });
      const content = renderItem(item);
      
      if (typeof content === 'string') {
        listItem.textContent = content;
      } else if (content instanceof Node) {
        listItem.appendChild(content);
      }
      
      list.appendChild(listItem);
    });
    
    return list;
  }

  /**
   * Sicheres Erstellen von Tabellen
   * @param {Array} data - Table data
   * @param {Array} headers - Table headers
   * @param {Object} options - Table options
   * @returns {HTMLElement}
   */
  static createTable(data, headers, options = {}) {
    const { className = '', striped = false } = options;
    const table = this.createElement('table', { className });
    
    // Header
    if (headers.length > 0) {
      const thead = this.createElement('thead');
      const headerRow = this.createElement('tr');
      
      headers.forEach(header => {
        const th = this.createElement('th', {}, header);
        headerRow.appendChild(th);
      });
      
      thead.appendChild(headerRow);
      table.appendChild(thead);
    }
    
    // Body
    const tbody = this.createElement('tbody');
    data.forEach((row, index) => {
      const tr = this.createElement('tr', {
        className: striped && index % 2 === 1 ? 'striped' : ''
      });
      
      row.forEach(cell => {
        const td = this.createElement('td', {}, String(cell));
        tr.appendChild(td);
      });
      
      tbody.appendChild(tr);
    });
    
    table.appendChild(tbody);
    return table;
  }

  /**
   * Sicheres Anzeigen von Status-Meldungen
   * @param {string} message - Message text
   * @param {string} type - Message type (info, success, warning, error)
   * @param {HTMLElement} container - Target container
   */
  static showMessage(message, type = 'info', container) {
    const messageElement = this.createElement('div', {
      className: `message message-${type}`,
      role: 'alert'
    }, message);
    
    // Container leeren und neue Nachricht hinzufügen
    container.textContent = '';
    container.appendChild(messageElement);
    
    // Auto-remove nach 5 Sekunden
    setTimeout(() => {
      if (messageElement.parentNode === container) {
        container.removeChild(messageElement);
      }
    }, 5000);
  }

  /**
   * Sicheres Erstellen von Progress Bars
   * @param {number} value - Progress value (0-100)
   * @param {string} label - Progress label
   * @param {Object} options - Progress options
   * @returns {HTMLElement}
   */
  static createProgressBar(value, label = '', options = {}) {
    const { className = '', showPercentage = true } = options;
    const container = this.createElement('div', { className: `progress-bar ${className}` });
    
    if (label) {
      const labelElement = this.createElement('div', { className: 'progress-label' }, label);
      container.appendChild(labelElement);
    }
    
    const progressBar = this.createElement('div', { className: 'progress-track' });
    const progressFill = this.createElement('div', {
      className: 'progress-fill',
      style: { width: `${Math.min(100, Math.max(0, value))}%` }
    });
    
    progressBar.appendChild(progressFill);
    container.appendChild(progressBar);
    
    if (showPercentage) {
      const percentageElement = this.createElement('div', { className: 'progress-percentage' }, `${value}%`);
      container.appendChild(percentageElement);
    }
    
    return container;
  }
}

// Export für Node.js und Browser
if (typeof module !== 'undefined' && module.exports) {
  module.exports = DOMHelper;
} else if (typeof window !== 'undefined') {
  window.DOMHelper = DOMHelper;
}
