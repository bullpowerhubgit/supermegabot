import React, { useState } from 'react';
import { BarChart3, Moon, Sun, Zap, CheckCircle, Terminal, Rocket, Download, Activity, DollarSign, Hash, Cpu, Mail, Users, Briefcase, CreditCard } from 'lucide-react';

const PRICE_INPUT_PER_M = 3.0;
const PRICE_OUTPUT_PER_M = 15.0;

const calcCost = (inp, out) => (inp / 1_000_000) * PRICE_INPUT_PER_M + (out / 1_000_000) * PRICE_OUTPUT_PER_M;

const CostDashboard = ({ stats, darkMode: dm }) => {
  if (!stats) return (
    <div className={`rounded-xl border p-4 mt-4 ${dm ? 'bg-gray-900 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
      <div className="flex items-center gap-2 mb-2">
        <Activity size={13} className="text-purple-400" />
        <span className="text-xs font-bold text-purple-400 uppercase tracking-wider">API Usage</span>
      </div>
      <p className={`text-xs ${dm ? 'text-gray-500' : 'text-gray-400'}`}>Noch nicht generiert – klicke auf "System Generieren" um Verbrauch zu sehen.</p>
    </div>
  );
  const bg = dm ? 'bg-gray-900 border-gray-700' : 'bg-gray-50 border-gray-200';
  const cardBg = dm ? 'bg-gray-800' : 'bg-white';
  const sub = dm ? 'text-gray-400' : 'text-gray-500';
  return (
    <div className={`rounded-xl border p-4 mt-4 ${bg}`}>
      <div className="flex items-center gap-2 mb-3">
        <Activity size={13} className="text-purple-400" />
        <span className="text-xs font-bold text-purple-400 uppercase tracking-wider">API Usage – letzte Generierung</span>
      </div>
      <div className="grid grid-cols-4 gap-2">
        {[
          { icon: Hash, color: 'text-blue-400', label: 'API Calls', value: stats.calls },
          { icon: Cpu, color: 'text-yellow-400', label: 'Input Tokens', value: stats.inputTokens.toLocaleString() },
          { icon: Zap, color: 'text-green-400', label: 'Output Tokens', value: stats.outputTokens.toLocaleString() },
          { icon: DollarSign, color: 'text-pink-400', label: 'Kosten', value: `$${stats.cost.toFixed(4)}` },
        ].map(({ icon: Icon, color, label, value }) => (
          <div key={label} className={`rounded-lg p-3 ${cardBg}`}>
            <div className={`flex items-center gap-1 mb-1`}>
              <Icon size={11} className={color} />
              <span className={`text-xs ${sub}`}>{label}</span>
            </div>
            <div className={`text-base font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>
      <div className={`mt-2 text-xs ${sub} flex gap-3 flex-wrap`}>
        <span>Modell: claude-sonnet-4-20250514</span>
        <span>In: ${PRICE_INPUT_PER_M}/M · Out: ${PRICE_OUTPUT_PER_M}/M</span>
        <span>Total: {(stats.inputTokens + stats.outputTokens).toLocaleString()} Tokens</span>
      </div>
    </div>
  );
};

const QuickCashSystem = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [darkMode, setDarkMode] = useState(true);
  const [toolOutput, setToolOutput] = useState([]);
  const [runningTools, setRunningTools] = useState(new Set());
  const [toolConfigs, setToolConfigs] = useState({});
  const [generatedAssets, setGeneratedAssets] = useState({});
  const [toolStats, setToolStats] = useState({});
  const [sessionStats, setSessionStats] = useState({});
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('quickcash_api_key') || '');
  const [backendUrl, setBackendUrl] = useState(() => localStorage.getItem('quickcash_backend_url') || 'http://localhost:3001');

  const handleApiKeyChange = (value) => {
    setApiKey(value);
    localStorage.setItem('quickcash_api_key', value);
  };

  const handleBackendUrlChange = (value) => {
    setBackendUrl(value);
    localStorage.setItem('quickcash_backend_url', value);
  };

  const quickCashTools = [
    {
      id: 1, name: 'AI Service Arbitrage', category: 'Freelancing',
      timeToFirstDollar: '24-48h', weeklyPotential: '$200-800', effort: 'Mittel',
      description: 'Verkaufe AI-Services (Logos, Content, Design) auf Fiverr mit 500%+ Markup',
      platforms: ['Fiverr', 'Upwork', 'Freelancer'],
      fields: [
        { name: 'service', label: 'Service', type: 'select', options: ['Logo Design', 'Content Writing', 'Social Media Posts', 'Business Names', 'Presentations'] },
        { name: 'price', label: 'Dein Preis ($)', type: 'number', placeholder: '50' },
        { name: 'turnaround', label: 'Lieferzeit (Stunden)', type: 'number', placeholder: '24' }
      ]
    },
    {
      id: 2, name: 'Local Lead Generator', category: 'Lead Generation',
      timeToFirstDollar: '3-7 Tage', weeklyPotential: '$300-1000', effort: 'Hoch',
      description: 'Generiere Leads für lokale Businesses und verkaufe für $10-50/Lead',
      platforms: ['Apollo.io', 'Clearbit', 'Direkt'],
      fields: [
        { name: 'industry', label: 'Industrie', type: 'select', options: ['Immobilien', 'Versicherungen', 'Handwerker', 'Zahnärzte', 'Anwälte'] },
        { name: 'location', label: 'Stadt/Region', type: 'text', placeholder: 'München' },
        { name: 'leadPrice', label: 'Preis pro Lead ($)', type: 'number', placeholder: '20' }
      ]
    },
    {
      id: 3, name: 'Upwork Gig Automation', category: 'Freelancing',
      timeToFirstDollar: '2-5 Tage', weeklyPotential: '$400-1200', effort: 'Hoch',
      description: 'Automatisiere Upwork-Bewerbungen und liefere mit AI',
      platforms: ['Upwork', 'Freelancer.com'],
      fields: [
        { name: 'skill', label: 'Skill', type: 'select', options: ['Writing', 'Data Entry', 'Virtual Assistant', 'Research', 'Transcription'] },
        { name: 'hourlyRate', label: 'Stundensatz ($)', type: 'number', placeholder: '25' },
        { name: 'hoursPerWeek', label: 'Stunden/Woche', type: 'number', placeholder: '20' }
      ]
    },
    {
      id: 4, name: 'Cold Outreach Machine', category: 'Client Acquisition',
      timeToFirstDollar: '5-10 Tage', weeklyPotential: '$500-2000', effort: 'Sehr Hoch',
      description: 'Automatisiere Cold Outreach für hochpreisige Services',
      platforms: ['Email', 'LinkedIn', 'SendGrid'],
      fields: [
        { name: 'targetRole', label: 'Ziel-Position', type: 'text', placeholder: 'Marketing Manager' },
        { name: 'serviceOffered', label: 'Dein Service', type: 'text', placeholder: 'SEO Audit' },
        { name: 'price', label: 'Preis ($)', type: 'number', placeholder: '500' },
        { name: 'emailTemplate', label: 'Email Template', type: 'textarea', placeholder: 'Ihr Betreff hier...' }
      ]
    }
  ];

  const addOutput = (toolId, message, type) =>
    setToolOutput(prev => [...prev, { toolId, message, type: type || 'info', timestamp: new Date().toLocaleTimeString() }]);

  const recordStats = (toolId, inp, out) => {
    const cost = calcCost(inp, out);
    const s = { calls: 1, inputTokens: inp, outputTokens: out, cost };
    setToolStats(prev => ({ ...prev, [toolId]: s }));
    setSessionStats(prev => {
      const e = prev[toolId] || { calls: 0, inputTokens: 0, outputTokens: 0, cost: 0 };
      return { ...prev, [toolId]: { calls: e.calls + 1, inputTokens: e.inputTokens + inp, outputTokens: e.outputTokens + out, cost: e.cost + cost } };
    });
  };

  const downloadFile = (filename, content) => {
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  };

  const callBackendApi = async (endpoint, data) => {
    if (!apiKey) {
      throw new Error('Bitte zuerst API Key eingeben');
    }
    
    const response = await fetch(`${backendUrl}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey
      },
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'API-Fehler');
    }

    return response.json();
  };

  const runTool = async (tool) => {
    const config = toolConfigs[tool.id] || {};
    const missing = tool.fields.filter(f => !config[f.name]);
    if (missing.length) { 
      addOutput(tool.id, 'Bitte ausfüllen: ' + missing.map(f => f.label).join(', '), 'error'); 
      return; 
    }
    
    setRunningTools(prev => new Set([...prev, tool.id]));
    try {
      let prompt = '';
      let apiData = {};
      
      if (tool.id === 1) {
        addOutput(1, `🚀 Generiere Fiverr Gig für: ${config.service}`, 'info');
        prompt = `Create Fiverr gig for: ${config.service}, price $${config.price}, ${config.turnaround}h turnaround.\nGenerate: 1) Title <80 chars 2) Description 300w 3) 3 pricing tiers 4) 3 FAQ 5) 5 tags`;
      } else if (tool.id === 2) {
        addOutput(2, `🎯 Lead-Gen für ${config.industry} in ${config.location}`, 'info');
        prompt = `Lead gen system for ${config.industry} in ${config.location}, $${config.leadPrice}/lead.\nGenerate: 1) Criteria 2) Sources 3) Cold email 4) Sales pitch 5) Packages`;
        
        // Apollo.io API call
        try {
          addOutput(2, `🔍 Suche Leads mit Apollo.io...`, 'info');
          const leadsResponse = await callBackendApi('/api/apollo-leads', {
            industry: config.industry,
            location: config.location,
            limit: 5
          });
          addOutput(2, `✅ ${leadsResponse.leads.length} Leads gefunden`, 'success');
          apiData.leads = leadsResponse.leads;
        } catch (err) {
          addOutput(2, `⚠️ Apollo.io Fehler: ${err.message}`, 'error');
        }
      } else if (tool.id === 3) {
        addOutput(3, `💼 Upwork System für: ${config.skill}`, 'info');
        prompt = `Upwork system: ${config.skill}, $${config.hourlyRate}/hr, ${config.hoursPerWeek}h/week.\nGenerate: 1) Profile tips 2) 3 proposals 3) AI delivery shortcuts 4) Pricing`;
        
        // Upwork API call
        try {
          addOutput(3, `🔍 Suche Upwork Jobs...`, 'info');
          const jobsResponse = await callBackendApi('/api/upwork-jobs', {
            skill: config.skill,
            limit: 5
          });
          addOutput(3, `✅ ${jobsResponse.jobs.length} Jobs gefunden`, 'success');
          apiData.jobs = jobsResponse.jobs;
        } catch (err) {
          addOutput(3, `⚠️ Upwork Fehler: ${err.message}`, 'error');
        }
      } else if (tool.id === 4) {
        addOutput(4, `📧 Cold Outreach für: ${config.serviceOffered}`, 'info');
        prompt = `Cold outreach: target ${config.targetRole}, service ${config.serviceOffered}, $${config.price}.\nGenerate: 1) LinkedIn msg 2) 3-email sequence 3) Objections 4) Prospect sources`;
        
        // SendGrid Email Test
        try {
          addOutput(4, `📧 Teste SendGrid Integration...`, 'info');
          const emailResponse = await callBackendApi('/api/send-email', {
            to: 'test@example.com',
            subject: `Cold Outreach: ${config.serviceOffered}`,
            content: config.emailTemplate || 'Test email template',
            from: 'noreply@quickcash.system'
          });
          addOutput(4, `✅ Email gesendet (ID: ${emailResponse.messageId})`, 'success');
        } catch (err) {
          addOutput(4, `⚠️ SendGrid Fehler: ${err.message}`, 'error');
        }
      }
      
      // Claude API call for content generation
      const { text, inputTokens, outputTokens } = await callBackendApi('/api/claude', {
        prompt: prompt,
        model: 'claude-sonnet-4-20250514',
        maxTokens: 1000
      });
      
      recordStats(tool.id, inputTokens, outputTokens);
      
      // Combine AI content with API data
      let finalContent = text;
      if (Object.keys(apiData).length > 0) {
        finalContent += '\n\n=== API DATEN ===\n' + JSON.stringify(apiData, null, 2);
      }
      
      setGeneratedAssets(prev => ({ 
        ...prev, 
        [tool.id]: { 
          [`${tool.name.toLowerCase().replace(/ /g, '-')}.txt`]: finalContent 
        } 
      }));
      
      addOutput(tool.id, `✅ ${tool.name} komplett!`, 'success');
      addOutput(tool.id, `📊 Tokens: ${inputTokens} in / ${outputTokens} out | Kosten: $${calcCost(inputTokens, outputTokens).toFixed(4)}`, 'info');
    } catch (err) {
      addOutput(tool.id, 'Fehler: ' + err.message, 'error');
    } finally {
      setRunningTools(prev => { 
        const s = new Set(prev); 
        s.delete(tool.id); 
        return s; 
      });
    }
  };

  const updateConfig = (toolId, field, value) =>
    setToolConfigs(prev => ({ ...prev, [toolId]: { ...prev[toolId], [field]: value } }));

  const dm = darkMode;
  const card = dm ? 'bg-gray-800' : 'bg-white';
  const sub = dm ? 'text-gray-400' : 'text-gray-600';

  const totalSession = Object.values(sessionStats).reduce((acc, s) => ({
    calls: acc.calls + s.calls,
    tokens: acc.tokens + s.inputTokens + s.outputTokens,
    cost: acc.cost + s.cost
  }), { calls: 0, tokens: 0, cost: 0 });

  const tabs = [
    { id: 'dashboard', icon: BarChart3, label: 'Dashboard' },
    { id: 'tools', icon: Rocket, label: 'Quick Cash Tools' },
    { id: 'downloads', icon: Download, label: 'Downloads' },
    { id: 'settings', icon: Cpu, label: 'API Settings' }
  ];

  return (
    <div className={dm ? 'h-screen flex flex-col bg-gray-900 text-white' : 'h-screen flex flex-col bg-gray-50 text-gray-900'}>
      <header className={dm ? 'bg-gray-800 border-b border-gray-700 px-6 py-3 flex items-center justify-between' : 'bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between'}>
        <div className="flex items-center gap-3">
          <Zap className="text-green-500 animate-pulse" size={28} />
          <div>
            <h1 className="text-lg font-bold bg-gradient-to-r from-green-500 via-blue-500 to-purple-500 bg-clip-text text-transparent">Quick Cash System</h1>
            <p className={`text-xs ${sub}`}>Erste $100-500 in 1-4 Wochen</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* API Key Input */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${dm ? 'bg-gray-700' : 'bg-gray-100'}`}>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => handleApiKeyChange(e.target.value)}
              placeholder="Backend API Key"
              className={`text-xs bg-transparent border-none outline-none ${dm ? 'text-white placeholder-gray-500' : 'text-gray-900 placeholder-gray-400'} w-32`}
            />
            {apiKey && <CheckCircle size={14} className="text-green-500" />}
          </div>
          {/* Session total in header */}
          {totalSession.calls > 0 && (
            <div className={`flex items-center gap-3 px-3 py-1.5 rounded-lg text-xs ${dm ? 'bg-gray-700' : 'bg-gray-100'}`}>
              <span className={sub}>Session:</span>
              <span className="text-blue-400 font-medium">{totalSession.calls} Calls</span>
              <span className="text-green-400 font-medium">{totalSession.tokens.toLocaleString()} Tokens</span>
              <span className="text-pink-400 font-bold">${totalSession.cost.toFixed(4)}</span>
            </div>
          )}
          <button onClick={() => setDarkMode(!dm)} className={dm ? 'bg-gray-700 hover:bg-gray-600 p-2 rounded-lg' : 'bg-gray-200 hover:bg-gray-300 p-2 rounded-lg'}>
            {dm ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <aside className={dm ? 'bg-gray-800 border-r border-gray-700 w-52 p-4 flex flex-col gap-2' : 'bg-white border-r border-gray-200 w-52 p-4 flex flex-col gap-2'}>
          {tabs.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={activeTab === tab.id ? 'flex items-center gap-3 px-3 py-2.5 rounded-lg bg-gradient-to-r from-green-600 to-blue-600 text-white text-sm'
                : dm ? 'flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-700 text-sm' : 'flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-100 text-sm'}>
              <tab.icon size={16} />{tab.label}
            </button>
          ))}

          <div className={dm ? 'mt-3 p-3 rounded-lg bg-green-900/20 border border-green-500/30' : 'mt-3 p-3 rounded-lg bg-green-50 border border-green-200'}>
            <p className="text-xs font-bold text-green-500 mb-1">⚡ Realistische Zahlen</p>
            {['$0-200', '$100-500', '$300-800', '$500-1200'].map((v, i) => (
              <div key={i} className={`text-xs ${sub}`}>Woche {i + 1}: {v}</div>
            ))}
          </div>

          {/* Per-tool session summary in sidebar */}
          {Object.keys(sessionStats).length > 0 && (
            <div className={`mt-2 p-3 rounded-lg border ${dm ? 'bg-purple-900/20 border-purple-500/30' : 'bg-purple-50 border-purple-200'}`}>
              <p className="text-xs font-bold text-purple-400 mb-2">📊 Session Verbrauch</p>
              {Object.entries(sessionStats).map(([tid, s]) => {
                const t = quickCashTools.find(x => x.id === parseInt(tid));
                return (
                  <div key={tid} className={`text-xs ${sub} mb-1`}>
                    <span className="font-medium">{t?.name.split(' ')[0]}:</span> {s.calls}× · <span className="text-pink-400">${s.cost.toFixed(4)}</span>
                  </div>
                );
              })}
              <div className={`text-xs border-t ${dm ? 'border-gray-700' : 'border-gray-200'} mt-1 pt-1 font-bold text-pink-400`}>
                Total: ${totalSession.cost.toFixed(4)}
              </div>
            </div>
          )}
        </aside>

        <main className="flex-1 overflow-y-auto p-6">
          {activeTab === 'dashboard' && (
            <div className="space-y-5">
              <div>
                <h2 className="text-2xl font-bold mb-1">Dashboard</h2>
                <p className={sub}>Service-basierte Systeme für schnelles Geld</p>
              </div>
              <div className={dm ? 'rounded-xl p-5 border-2 border-yellow-500/30 bg-yellow-900/20' : 'rounded-xl p-5 border-2 border-yellow-400/40 bg-yellow-50'}>
                <h3 className="font-bold mb-3">⚠️ Kein passives Income!</h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {['Aktive Arbeit erforderlich', '10-30h/Woche', 'Service-Verkauf', 'Schneller als SaaS/SEO'].map(t => (
                    <div key={t} className="flex items-center gap-2"><CheckCircle className="text-green-500 shrink-0" size={15} />{t}</div>
                  ))}
                </div>
              </div>
              <div className={`${card} rounded-xl p-5`}>
                <h3 className="font-bold mb-3">Live Output</h3>
                <div className={dm ? 'bg-gray-900 rounded-lg p-4 h-72 overflow-y-auto font-mono text-xs' : 'bg-gray-50 rounded-lg p-4 h-72 overflow-y-auto font-mono text-xs'}>
                  {toolOutput.length === 0 ? (
                    <div className="text-center mt-12 text-gray-500"><Rocket className="mx-auto mb-3" size={36} /><p>Bereit. Wähle ein Quick Cash Tool.</p></div>
                  ) : toolOutput.map((o, i) => (
                    <div key={i} className={o.type === 'error' ? 'text-red-400' : o.type === 'success' ? 'text-green-400' : 'text-gray-300'}>
                      [{o.timestamp}] {o.message}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'tools' && (
            <div className="space-y-5">
              <div>
                <h2 className="text-2xl font-bold mb-1">Quick Cash Tools</h2>
                <p className={sub}>Erste $ in 24-48h möglich</p>
              </div>
              {quickCashTools.map(tool => (
                <div key={tool.id} className={`${card} rounded-xl p-5 shadow-lg`}>
                  <h3 className="text-base font-bold mb-1">{tool.name}</h3>
                  <p className={`text-sm ${sub} mb-3`}>{tool.description}</p>
                  <div className="flex gap-2 flex-wrap mb-3">
                    <span className={dm ? 'px-2 py-0.5 rounded-full text-xs bg-green-900/30 text-green-400' : 'px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700'}>⏱️ {tool.timeToFirstDollar}</span>
                    <span className={dm ? 'px-2 py-0.5 rounded-full text-xs bg-blue-900/30 text-blue-400' : 'px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700'}>💰 {tool.weeklyPotential}/Woche</span>
                    <span className={dm ? 'px-2 py-0.5 rounded-full text-xs bg-orange-900/30 text-orange-400' : 'px-2 py-0.5 rounded-full text-xs bg-orange-100 text-orange-700'}>{tool.effort} Aufwand</span>
                  </div>
                  <p className={`text-xs ${sub} mb-3`}>Plattformen: {tool.platforms.join(', ')}</p>

                  <div className="grid grid-cols-2 gap-3 mb-4">
                    {tool.fields.map(f => (
                      <div key={f.name}>
                        <label className="block text-xs font-medium mb-1">{f.label}</label>
                        {f.type === 'select' ? (
                          <select value={toolConfigs[tool.id]?.[f.name] || ''} onChange={e => updateConfig(tool.id, f.name, e.target.value)}
                            className={dm ? 'w-full px-3 py-2 rounded-lg bg-gray-700 border border-gray-600 text-sm' : 'w-full px-3 py-2 rounded-lg bg-gray-50 border border-gray-300 text-sm'}>
                            <option value="">Wähle...</option>
                            {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                          </select>
                        ) : f.type === 'textarea' ? (
                          <textarea value={toolConfigs[tool.id]?.[f.name] || ''} onChange={e => updateConfig(tool.id, f.name, e.target.value)}
                            placeholder={f.placeholder}
                            rows={3}
                            className={dm ? 'w-full px-3 py-2 rounded-lg bg-gray-700 border border-gray-600 text-sm' : 'w-full px-3 py-2 rounded-lg bg-gray-50 border border-gray-300 text-sm'} />
                        ) : (
                          <input type={f.type} value={toolConfigs[tool.id]?.[f.name] || ''} onChange={e => updateConfig(tool.id, f.name, e.target.value)}
                            placeholder={f.placeholder}
                            className={dm ? 'w-full px-3 py-2 rounded-lg bg-gray-700 border border-gray-600 text-sm' : 'w-full px-3 py-2 rounded-lg bg-gray-50 border border-gray-300 text-sm'} />
                        )}
                      </div>
                    ))}
                  </div>

                  <button onClick={() => runTool(tool)} disabled={runningTools.has(tool.id)}
                    className="w-full py-2.5 bg-gradient-to-r from-green-600 to-blue-600 text-white rounded-lg hover:from-green-700 hover:to-blue-700 font-medium disabled:opacity-50 flex items-center justify-center gap-2 text-sm">
                    {runningTools.has(tool.id) ? <><Terminal className="animate-spin" size={15} />Generiert...</> : <><Zap size={15} />System Generieren</>}
                  </button>

                  {/* ── MINI COST DASHBOARD ── */}
                  <CostDashboard stats={toolStats[tool.id]} darkMode={dm} />

                  {/* Multi-run session row */}
                  {sessionStats[tool.id] && sessionStats[tool.id].calls > 1 && (
                    <div className={`mt-2 flex gap-3 text-xs ${sub} px-1`}>
                      <span className="text-purple-400 font-medium">Session ({sessionStats[tool.id].calls}× generiert):</span>
                      <span>{(sessionStats[tool.id].inputTokens + sessionStats[tool.id].outputTokens).toLocaleString()} Tokens</span>
                      <span className="text-pink-400 font-bold">${sessionStats[tool.id].cost.toFixed(4)}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {activeTab === 'downloads' && (
            <div className="space-y-5">
              <h2 className="text-2xl font-bold mb-1">Generierte Assets</h2>
              <p className={sub}>Download deine Quick Cash Systeme</p>
              {Object.keys(generatedAssets).length === 0 ? (
                <div className="text-center py-20 text-gray-500">
                  <Download className="mx-auto mb-4" size={52} />
                  <p>Noch keine Systeme generiert</p>
                  <p className="text-sm mt-1">Gehe zu Quick Cash Tools und starte ein System</p>
                </div>
              ) : Object.entries(generatedAssets).map(([toolId, assets]) => {
                const tool = quickCashTools.find(t => t.id === parseInt(toolId));
                const s = sessionStats[toolId];
                return (
                  <div key={toolId} className={`${card} rounded-xl p-5`}>
                    <h3 className="font-bold mb-1">{tool?.name}</h3>
                    {s && <p className={`text-xs ${sub} mb-3`}>{s.calls} Generierung(en) · {(s.inputTokens + s.outputTokens).toLocaleString()} Tokens · <span className="text-pink-400">${s.cost.toFixed(4)}</span></p>}
                    <div className="grid grid-cols-2 gap-3">
                      {Object.entries(assets).map(([name, content]) => (
                        <button key={name} onClick={() => downloadFile(name, content)}
                          className="flex items-center gap-3 p-3 bg-gradient-to-r from-green-600 to-blue-600 text-white rounded-lg hover:from-green-700 hover:to-blue-700">
                          <Download size={16} />
                          <div className="text-left">
                            <p className="text-sm font-medium">{name}</p>
                            <p className="text-xs opacity-75">Klick zum Download</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="space-y-5">
              <h2 className="text-2xl font-bold mb-1">API Settings</h2>
              <p className={sub}>Backend Konfiguration</p>
              
              <div className={`${card} rounded-xl p-5`}>
                <h3 className="font-bold mb-4">Backend Connection</h3>
                
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">Backend URL</label>
                    <input
                      type="text"
                      value={backendUrl}
                      onChange={(e) => handleBackendUrlChange(e.target.value)}
                      placeholder="http://localhost:3001"
                      className={`w-full px-4 py-2 rounded-lg border ${dm ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300'}`}
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium mb-2">API Key</label>
                    <input
                      type="password"
                      value={apiKey}
                      onChange={(e) => handleApiKeyChange(e.target.value)}
                      placeholder="Backend API Key"
                      className={`w-full px-4 py-2 rounded-lg border ${dm ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300'}`}
                    />
                  </div>
                  
                  <div className={`p-4 rounded-lg ${dm ? 'bg-gray-700' : 'bg-gray-100'}`}>
                    <p className="text-sm font-medium mb-2">Required Backend APIs:</p>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="flex items-center gap-2">
                        <Mail size={12} className="text-blue-400" />
                        <span>SendGrid (Email)</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Users size={12} className="text-green-400" />
                        <span>Apollo.io (Leads)</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Briefcase size={12} className="text-yellow-400" />
                        <span>Upwork (Jobs)</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <CreditCard size={12} className="text-pink-400" />
                        <span>Stripe (Payments)</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className={`${card} rounded-xl p-5`}>
                <h3 className="font-bold mb-4">Environment Variables</h3>
                <div className={`font-mono text-xs p-4 rounded-lg ${dm ? 'bg-gray-900' : 'bg-gray-100'}`}>
                  <p>QUICKCASH_API_KEY=your_api_key_here</p>
                  <p>SENDGRID_API_KEY=your_sendgrid_key</p>
                  <p>APOLLO_API_KEY=your_apollo_key</p>
                  <p>CLEARBIT_API_KEY=your_clearbit_key</p>
                  <p>UPWORK_ACCESS_TOKEN=your_upwork_token</p>
                  <p>STRIPE_SECRET_KEY=your_stripe_key</p>
                  <p>ANTHROPIC_API_KEY=your_anthropic_key</p>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default QuickCashSystem;
