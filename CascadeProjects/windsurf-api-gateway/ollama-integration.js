#!/usr/bin/env node

// 🧠 OLLAMA AI INTEGRATION - Vollautonom
// Mehrere LLM-Modelle, lokale KI, erweiterte Features
// ============================================================

const axios = require('axios');

// 🧠 Ollama Konfiguration
const OLLAMA_CONFIG = {
    url: process.env.OLLAMA_URL || 'http://localhost:11434',
    defaultModel: process.env.OLLAMA_MODEL || 'llama3.2',
    fallbackModels: [
        'llama3.2',
        'mistral',
        'gemma2',
        'codellama',
        'phi3',
        'neural-chat'
    ],
    timeout: 30000,
    maxTokens: 4096
};

// 🧠 Verfügbare Modelle mit Beschreibungen
const AVAILABLE_MODELS = {
    'llama3.2': {
        name: 'Llama 3.2',
        description: 'Meta\'s neuestes Modell - beste Allround-Performance',
        useCase: 'Allgemeine Aufgaben, Chat, Content',
        size: '3B-70B',
        languages: ['de', 'en', 'fr', 'es', 'it'],
        strengths: ['schnell', 'präzise', 'multilingual']
    },
    'mistral': {
        name: 'Mistral',
        description: 'Französisches Open-Source-Modell',
        useCase: 'Textgenerierung, Coding, Analyse',
        size: '7B',
        languages: ['de', 'en', 'fr'],
        strengths: ['effizient', 'kompakt', 'leistungsstark']
    },
    'gemma2': {
        name: 'Gemma 2',
        description: 'Google\'s Open-Source-Modell',
        useCase: 'Research, Fakten, Wissenschaft',
        size: '2B-9B',
        languages: ['de', 'en'],
        strengths: ['faktengenau', 'sicher', 'google-optimiert']
    },
    'codellama': {
        name: 'CodeLlama',
        description: 'Spezialisiert auf Code-Generierung',
        useCase: 'Programmierung, Code-Review, Debugging',
        size: '7B-34B',
        languages: ['en'],
        strengths: ['coding', 'technisch', 'präzise']
    },
    'phi3': {
        name: 'Phi-3',
        description: 'Microsoft\'s kompaktes Modell',
        useCase: 'Mobile, schnelle Antworten, Chat',
        size: '3.8B',
        languages: ['de', 'en'],
        strengths: ['schnell', 'ressourcenschonend', 'qualitativ']
    },
    'neural-chat': {
        name: 'Neural Chat',
        description: 'Optimiert für Konversationen',
        useCase: 'Kundenservice, Chatbots, Dialoge',
        size: '7B',
        languages: ['de', 'en'],
        strengths: ['konversationell', 'natürlich', 'empathisch']
    },
    'mixtral': {
        name: 'Mixtral',
        description: 'Mixture of Experts Architektur',
        useCase: 'Komplexe Aufgaben, Reasoning',
        size: '8x7B',
        languages: ['de', 'en', 'fr'],
        strengths: ['komplex', 'präzise', 'experten-basiert']
    }
};

// 🧠 Autonome Ollama Klasse
class AutonomousOllama {
    constructor() {
        this.config = OLLAMA_CONFIG;
        this.currentModel = this.config.defaultModel;
        this.availableModels = [];
        this.conversationHistory = [];
        this.initialize();
    }

    async initialize() {
        console.log('🧠 AUTONOMOUS OLLAMA SYSTEM INITIALIZED');
        console.log('='.repeat(60));
        
        // Prüfe verfügbare Modelle
        await this.discoverModels();
        
        console.log(`✅ Default Model: ${this.currentModel}`);
        console.log(`📊 Available Models: ${this.availableModels.length}`);
        console.log('');
    }

    // 🔍 Autonome Modell-Erkennung
    async discoverModels() {
        try {
            const response = await axios.get(`${this.config.url}/api/tags`, {
                timeout: 5000
            });
            
            this.availableModels = response.data.models.map(model => ({
                name: model.name,
                size: model.size,
                modified: model.modified_at,
                details: AVAILABLE_MODELS[model.name.split(':')[0]] || {
                    name: model.name,
                    description: 'Custom Model',
                    useCase: 'General'
                }
            }));
            
            console.log(`🔍 Discovered ${this.availableModels.length} models:`);
            this.availableModels.forEach(model => {
                console.log(`   🧠 ${model.name} (${model.details.name})`);
            });
            
        } catch (error) {
            console.log('⚠️ Ollama server not running - using fallback models');
            this.availableModels = this.config.fallbackModels.map(name => ({
                name: name,
                details: AVAILABLE_MODELS[name] || { name, description: 'Fallback' }
            }));
        }
    }

    // 💬 Intelligente Modell-Auswahl
    selectBestModel(task) {
        const taskKeywords = {
            'code': 'codellama',
            'programming': 'codellama',
            'chat': 'neural-chat',
            'conversation': 'neural-chat',
            'research': 'gemma2',
            'facts': 'gemma2',
            'fast': 'phi3',
            'quick': 'phi3',
            'complex': 'mixtral',
            'analysis': 'mixtral',
            'general': 'llama3.2',
            'default': 'llama3.2'
        };

        // Finde passendes Modell
        for (const [keyword, model] of Object.entries(taskKeywords)) {
            if (task.toLowerCase().includes(keyword)) {
                if (this.availableModels.some(m => m.name.includes(model))) {
                    return model;
                }
            }
        }

        return this.currentModel;
    }

    // 🚀 Autonome Text-Generierung
    async generate(prompt, options = {}) {
        const model = options.model || this.selectBestModel(prompt);
        const systemPrompt = options.system || 'Du bist ein hilfreicher KI-Assistent für Rudolf Sarkany.';
        
        try {
            console.log(`🧠 Generating with ${model}...`);
            
            const response = await axios.post(`${this.config.url}/api/generate`, {
                model: model,
                prompt: prompt,
                system: systemPrompt,
                stream: false,
                options: {
                    temperature: options.temperature || 0.7,
                    max_tokens: options.maxTokens || this.config.maxTokens,
                    top_p: options.topP || 0.9
                }
            }, {
                timeout: this.config.timeout
            });

            const result = {
                text: response.data.response,
                model: model,
                prompt: prompt,
                timestamp: new Date().toISOString(),
                metrics: {
                    totalDuration: response.data.total_duration,
                    loadDuration: response.data.load_duration,
                    promptEvalCount: response.data.prompt_eval_count,
                    evalCount: response.data.eval_count
                }
            };

            // Speichere in History
            this.conversationHistory.push(result);
            
            console.log(`✅ Generated ${result.metrics.evalCount} tokens in ${(result.metrics.totalDuration / 1e9).toFixed(2)}s`);
            
            return result;

        } catch (error) {
            console.error('❌ Ollama Error:', error.message);
            
            // Fallback zu anderem Modell
            if (this.availableModels.length > 1) {
                const fallbackModel = this.availableModels.find(m => m.name !== model);
                if (fallbackModel) {
                    console.log(`🔄 Trying fallback model: ${fallbackModel.name}`);
                    return this.generate(prompt, { ...options, model: fallbackModel.name });
                }
            }
            
            throw error;
        }
    }

    // 💬 Autonomer Chat
    async chat(messages, options = {}) {
        const model = options.model || this.currentModel;
        
        try {
            console.log(`💬 Chat with ${model} (${messages.length} messages)`);
            
            const response = await axios.post(`${this.config.url}/api/chat`, {
                model: model,
                messages: messages,
                stream: false,
                options: {
                    temperature: options.temperature || 0.7,
                    max_tokens: options.maxTokens || this.config.maxTokens
                }
            }, {
                timeout: this.config.timeout
            });

            return {
                message: response.data.message,
                model: model,
                done: response.data.done,
                metrics: response.data.metrics
            };

        } catch (error) {
            console.error('❌ Chat Error:', error.message);
            throw error;
        }
    }

    // 🎯 Spezialisierte Aufgaben
    async analyzeText(text, task = 'summarize') {
        const taskPrompts = {
            summarize: `Fasse folgenden Text zusammen:\n\n${text}`,
            translate: `Übersetze folgenden Text ins Deutsche:\n\n${text}`,
            improve: `Verbessere folgenden Text:\n\n${text}`,
            analyze: `Analysiere folgenden Text:\n\n${text}`,
            keywords: `Extrahiere Keywords aus folgendem Text:\n\n${text}`,
            sentiment: `Analysiere die Stimmung:\n\n${text}`
        };

        const prompt = taskPrompts[task] || taskPrompts.summarize;
        return this.generate(prompt, { model: 'llama3.2' });
    }

    // 🔄 Autonomes Modell-Management
    async pullModel(modelName) {
        try {
            console.log(`📥 Pulling model: ${modelName}`);
            
            const response = await axios.post(`${this.config.url}/api/pull`, {
                name: modelName,
                stream: false
            }, {
                timeout: 300000 // 5 Minuten für große Modelle
            });

            console.log(`✅ Model ${modelName} pulled successfully`);
            await this.discoverModels(); // Aktualisiere Liste
            
            return { success: true, model: modelName };

        } catch (error) {
            console.error('❌ Pull Error:', error.message);
            return { success: false, error: error.message };
        }
    }

    // 📊 Modell-Informationen
    getModelInfo(modelName = null) {
        const model = modelName || this.currentModel;
        const info = AVAILABLE_MODELS[model.split(':')[0]];
        
        return {
            name: model,
            info: info || { name: model, description: 'Unknown Model' },
            available: this.availableModels.some(m => m.name.includes(model)),
            current: model === this.currentModel
        };
    }

    // 🗑️ History Management
    clearHistory() {
        this.conversationHistory = [];
        console.log('🗑️ Conversation history cleared');
    }

    getHistory() {
        return this.conversationHistory;
    }
}

// 🚀 Singleton Export
const ollama = new AutonomousOllama();
module.exports = ollama;
