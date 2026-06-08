chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'navigate') {
    window.location.href = request.url;
    sendResponse({ success: true });
  } else if (request.action === 'click') {
    const element = document.querySelector(request.selector);
    if (element) {
      element.click();
      sendResponse({ success: true });
    } else {
      sendResponse({ success: false, error: 'Element nicht gefunden' });
    }
  } else if (request.action === 'type') {
    const element = document.querySelector(request.selector);
    if (element) {
      element.value = request.text;
      element.dispatchEvent(new Event('input', { bubbles: true }));
      sendResponse({ success: true });
    } else {
      sendResponse({ success: false, error: 'Element nicht gefunden' });
    }
  } else if (request.action === 'extract') {
    const element = document.querySelector(request.selector);
    if (element) {
      sendResponse({ success: true, text: element.textContent });
    } else {
      sendResponse({ success: false, error: 'Element nicht gefunden' });
    }
  } else if (request.action === 'screenshot') {
    sendResponse({ success: true, screenshot: 'Screenshot im Content Script nicht verfügbar' });
  }
  return true;
});
