chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'execute') {
    const { prompt, tabId } = request;
    
    chrome.storage.local.get(['apiKey', 'provider'], async (data) => {
      const apiKey = data.apiKey || process.env.OPENAI_API_KEY;
      const provider = data.provider || 'openai';
      
      if (!apiKey) {
        sendResponse({ error: 'API Key nicht gesetzt' });
        return;
      }
      
      try {
        const response = await fetch('https://api.openai.com/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${apiKey}`,
          },
          body: JSON.stringify({
            model: 'gpt-4o',
            messages: [
              { role: 'system', content: 'Du bist ein hilfreicher KI-Assistent für Browser-Automatisierung.' },
              { role: 'user', content: prompt },
            ],
          }),
        });
        
        const data = await response.json();
        const result = data.choices[0].message.content;
        sendResponse({ result });
      } catch (error) {
        sendResponse({ error: error.message });
      }
    });
    
    return true;
  }
});
