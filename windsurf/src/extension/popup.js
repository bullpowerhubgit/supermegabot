document.getElementById('send').addEventListener('click', async () => {
  const prompt = document.getElementById('prompt').value;
  const responseDiv = document.getElementById('response');
  
  if (!prompt) return;
  
  responseDiv.textContent = '...';
  
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  
  chrome.runtime.sendMessage({ action: 'execute', prompt, tabId: tab.id }, (response) => {
    responseDiv.textContent = response.result || 'Fehler: ' + response.error;
  });
});
