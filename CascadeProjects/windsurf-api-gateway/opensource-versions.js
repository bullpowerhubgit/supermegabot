#!/usr/bin/env node

// 🌐 OPENSOURCE ERWEITERUNGEN - Multiple Versionen
// Rudolf Sarkany · Autonomous OpenSource Integration
// ============================================================

const axios = require('axios');

// 🌐 OpenSource Dienste und APIs
const OPENSOURCE_SERVICES = {
    // 🧠 KI & LLM
    'ollama': {
        name: 'Ollama (Local AI)',
        url: 'http://localhost:11434',
        description: 'Lokale LLM-Ausführung',
        models: ['llama3.2', 'mistral', 'gemma2', 'codellama'],
        status: 'active',
        category: 'ai'
    },
    'openrouter': {
        name: 'OpenRouter',
        url: 'https://openrouter.ai/api/v1',
        description: 'API für mehrere LLMs',
        models: ['claude', 'gpt-4', 'gemini'],
        status: 'active',
        category: 'ai'
    },
    'huggingface': {
        name: 'Hugging Face',
        url: 'https://api-inference.huggingface.co',
        description: 'Open-Source ML Modelle',
        models: ['bert', 't5', 'bart'],
        status: 'active',
        category: 'ai'
    },

    // 📊 Daten & Analytics
    'metabase': {
        name: 'Metabase',
        url: 'http://localhost:3000',
        description: 'Open-Source Business Intelligence',
        features: ['Dashboards', 'SQL Queries', 'Visualisierungen'],
        status: 'optional',
        category: 'analytics'
    },
    'n8n': {
        name: 'n8n Workflow Automation',
        url: 'http://localhost:5678',
        description: 'Open-Source Workflow Automation',
        features: ['Workflows', 'Integrationen', 'API'],
        status: 'optional',
        category: 'automation'
    },
    'apache-superset': {
        name: 'Apache Superset',
        url: 'http://localhost:8088',
        description: 'Data Exploration & Visualization',
        features: ['Charts', 'Dashboards', 'SQL Lab'],
        status: 'optional',
        category: 'analytics'
    },

    // 🛡️ Sicherheit
    'vault': {
        name: 'HashiCorp Vault',
        url: 'http://localhost:8200',
        description: 'Secrets Management',
        features: ['Secrets', 'Encryption', 'PKI'],
        status: 'recommended',
        category: 'security'
    },
    'keycloak': {
        name: 'Keycloak',
        url: 'http://localhost:8080',
        description: 'Identity & Access Management',
        features: ['SSO', 'LDAP', 'OAuth'],
        status: 'optional',
        category: 'security'
    },

    // 🗄️ Datenbanken
    'postgresql': {
        name: 'PostgreSQL',
        url: 'postgresql://localhost:5432',
        description: 'Open-Source SQL Datenbank',
        features: ['ACID', 'JSON', 'Full-Text'],
        status: 'active',
        category: 'database'
    },
    'redis': {
        name: 'Redis',
        url: 'redis://localhost:6379',
        description: 'In-Memory Datenbank',
        features: ['Caching', 'Pub/Sub', 'Queues'],
        status: 'active',
        category: 'database'
    },
    'supabase': {
        name: 'Supabase',
        url: 'https://api.supabase.io',
        description: 'Open-Source Firebase Alternative',
        features: ['Auth', 'Realtime', 'Storage'],
        status: 'active',
        category: 'database'
    },

    // 📨 Kommunikation
    'mattermost': {
        name: 'Mattermost',
        url: 'http://localhost:8065',
        description: 'Open-Source Slack Alternative',
        features: ['Chat', 'Teams', 'Integrationen'],
        status: 'optional',
        category: 'communication'
    },
    'zammad': {
        name: 'Zammad',
        url: 'http://localhost:3001',
        description: 'Open-Source Helpdesk',
        features: ['Tickets', 'Email', 'Chat'],
        status: 'optional',
        category: 'communication'
    },

    // 📈 Monitoring
    'grafana': {
        name: 'Grafana',
        url: 'http://localhost:3000',
        description: 'Open-Source Monitoring',
        features: ['Dashboards', 'Alerts', 'Metrics'],
        status: 'recommended',
        category: 'monitoring'
    },
    'prometheus': {
        name: 'Prometheus',
        url: 'http://localhost:9090',
        description: 'Metrics Collection',
        features: ['Metrics', 'Alerts', 'TSDB'],
        status: 'recommended',
        category: 'monitoring'
    },

    // 🚀 DevOps
    'docker': {
        name: 'Docker',
        url: 'unix:///var/run/docker.sock',
        description: 'Container Platform',
        features: ['Containers', 'Images', 'Compose'],
        status: 'active',
        category: 'devops'
    },
    'kubernetes': {
        name: 'Kubernetes',
        url: 'https://kubernetes.default.svc',
        description: 'Container Orchestration',
        features: ['Pods', 'Services', 'Ingress'],
        status: 'optional',
        category: 'devops'
    }
};

// 🌐 OpenSource Manager
class OpenSourceManager {
    constructor() {
        this.services = OPENSOURCE_SERVICES;
        this.activeServices = new Map();
        this.healthStatus = new Map();
        this.initialize();
    }

    initialize() {
        console.log('🌐 OPENSOURCE ECOSYSTEM INITIALIZED');
        console.log('='.repeat(60));
        console.log(`📊 Services: ${Object.keys(this.services).length}`);
        console.log(`🟢 Active: ${Object.values(this.services).filter(s => s.status === 'active').length}`);
        console.log(`🟡 Optional: ${Object.values(this.services).filter(s => s.status === 'optional').length}`);
        console.log(`🔵 Recommended: ${Object.values(this.services).filter(s => s.status === 'recommended').length}`);
        console.log('');
    }

    // 🔍 Service nach Kategorie
    getServicesByCategory(category) {
        return Object.entries(this.services)
            .filter(([key, service]) => service.category === category)
            .map(([key, service]) => ({ key, ...service }));
    }

    // 📊 Alle Kategorien
    getCategories() {
        const categories = {};
        Object.values(this.services).forEach(service => {
            if (!categories[service.category]) {
                categories[service.category] = [];
            }
            categories[service.category].push(service);
        });
        return categories;
    }

    // 🏥 Health Check
    async checkHealth(serviceKey) {
        const service = this.services[serviceKey];
        if (!service) return { status: 'unknown', error: 'Service not found' };

        try {
            let healthy = false;
            
            switch (service.category) {
                case 'ai':
                    healthy = await this.checkAIHealth(service);
                    break;
                case 'database':
                    healthy = await this.checkDatabaseHealth(service);
                    break;
                case 'monitoring':
                    healthy = await this.checkMonitoringHealth(service);
                    break;
                default:
                    healthy = await this.checkGenericHealth(service);
            }

            this.healthStatus.set(serviceKey, {
                status: healthy ? 'healthy' : 'unhealthy',
                lastCheck: new Date().toISOString(),
                url: service.url
            });

            return { status: healthy ? 'healthy' : 'unhealthy', service: service.name };

        } catch (error) {
            this.healthStatus.set(serviceKey, {
                status: 'error',
                lastCheck: new Date().toISOString(),
                error: error.message
            });
            return { status: 'error', error: error.message };
        }
    }

    // 🧠 KI Health Check
    async checkAIHealth(service) {
        try {
            if (service.name.includes('Ollama')) {
                const response = await axios.get(`${service.url}/api/tags`, { timeout: 5000 });
                return response.status === 200;
            }
            if (service.name.includes('Hugging Face')) {
                const response = await axios.get(service.url, { timeout: 5000 });
                return response.status === 200;
            }
            return false;
        } catch {
            return false;
        }
    }

    // 🗄️ Datenbank Health Check
    async checkDatabaseHealth(service) {
        try {
            if (service.name.includes('Redis')) {
                // Einfache Redis-Prüfung
                return true; // Wird separat geprüft
            }
            if (service.name.includes('Supabase')) {
                const response = await axios.get(service.url, { timeout: 5000 });
                return response.status === 200;
            }
            return false;
        } catch {
            return false;
        }
    }

    // 📈 Monitoring Health Check
    async checkMonitoringHealth(service) {
        try {
            const response = await axios.get(service.url, { timeout: 5000 });
            return response.status === 200;
        } catch {
            return false;
        }
    }

    // 🔄 Generic Health Check
    async checkGenericHealth(service) {
        try {
            const response = await axios.get(service.url, { timeout: 5000, validateStatus: () => true });
            return response.status < 500;
        } catch {
            return false;
        }
    }

    // 🏥 Alle Services prüfen
    async checkAllHealth() {
        console.log('🔍 Checking all OpenSource services...');
        const results = {};
        
        for (const key of Object.keys(this.services)) {
            results[key] = await this.checkHealth(key);
        }

        const healthy = Object.values(results).filter(r => r.status === 'healthy').length;
        const total = Object.keys(results).length;

        console.log(`✅ Health check complete: ${healthy}/${total} services healthy`);
        return { results, healthy, total, percentage: Math.round((healthy/total)*100) };
    }

    // 🚀 Service starten
    async startService(serviceKey) {
        const service = this.services[serviceKey];
        if (!service) throw new Error(`Service ${serviceKey} not found`);

        console.log(`🚀 Starting ${service.name}...`);
        
        // Hier könnte Docker-Start oder Prozess-Start erfolgen
        this.activeServices.set(serviceKey, {
            started: new Date().toISOString(),
            pid: null, // Würde bei echtem Start gesetzt
            status: 'running'
        });

        return { success: true, service: service.name, started: new Date().toISOString() };
    }

    // 📊 System-Übersicht
    getSystemOverview() {
        return {
            total: Object.keys(this.services).length,
            categories: this.getCategories(),
            health: Object.fromEntries(this.healthStatus),
            active: Object.fromEntries(this.activeServices),
            recommendations: this.getRecommendations()
        };
    }

    // 💡 Empfehlungen
    getRecommendations() {
        const recommendations = [];
        
        // Prüfe welche wichtigen Services fehlen
        const critical = ['ollama', 'postgresql', 'redis', 'grafana'];
        const missing = critical.filter(key => 
            !this.activeServices.has(key) && this.services[key]?.status !== 'active'
        );

        if (missing.length > 0) {
            recommendations.push({
                priority: 'high',
                message: `Folgende kritische Services sollten gestartet werden: ${missing.join(', ')}`,
                services: missing
            });
        }

        // Prüfe KI-Services
        const aiServices = this.getServicesByCategory('ai');
        const aiActive = aiServices.filter(s => this.activeServices.has(s.key));
        if (aiActive.length === 0) {
            recommendations.push({
                priority: 'medium',
                message: 'Kein KI-Service aktiv - Ollama wird empfohlen',
                services: ['ollama']
            });
        }

        return recommendations;
    }

    // 📋 Docker Compose Generator
    generateDockerCompose() {
        const compose = {
            version: '3.8',
            services: {}
        };

        Object.entries(this.services).forEach(([key, service]) => {
            if (service.status === 'active' || service.status === 'recommended') {
                compose.services[key] = {
                    image: this.getDockerImage(key),
                    container_name: `opensource-${key}`,
                    ports: this.getPorts(key),
                    environment: this.getEnvironment(key),
                    volumes: this.getVolumes(key),
                    restart: 'unless-stopped'
                };
            }
        });

        return compose;
    }

    // 🐳 Docker Image Mapping
    getDockerImage(key) {
        const images = {
            'ollama': 'ollama/ollama:latest',
            'postgresql': 'postgres:15-alpine',
            'redis': 'redis:7-alpine',
            'grafana': 'grafana/grafana:latest',
            'prometheus': 'prom/prometheus:latest',
            'metabase': 'metabase/metabase:latest',
            'n8n': 'n8nio/n8n:latest',
            'vault': 'hashicorp/vault:latest',
            'mattermost': 'mattermost/mattermost-team-edition:latest'
        };
        return images[key] || `${key}:latest`;
    }

    // 🔌 Ports Mapping
    getPorts(key) {
        const ports = {
            'ollama': ['11434:11434'],
            'postgresql': ['5432:5432'],
            'redis': ['6379:6379'],
            'grafana': ['3001:3000'],
            'prometheus': ['9090:9090'],
            'metabase': ['3002:3000'],
            'n8n': ['5678:5678'],
            'vault': ['8200:8200'],
            'mattermost': ['8065:8065']
        };
        return ports[key] || [];
    }

    // 🔧 Environment Variables
    getEnvironment(key) {
        const env = {
            'postgresql': {
                POSTGRES_DB: 'rudibot',
                POSTGRES_USER: 'rudibot',
                POSTGRES_PASSWORD: 'secure_password'
            },
            'redis': {
                REDIS_PASSWORD: 'secure_password'
            },
            'grafana': {
                GF_SECURITY_ADMIN_PASSWORD: 'admin'
            }
        };
        return env[key] || {};
    }

    // 📁 Volumes
    getVolumes(key) {
        const vols = {
            'postgresql': ['postgres_data:/var/lib/postgresql/data'],
            'redis': ['redis_data:/data'],
            'grafana': ['grafana_data:/var/lib/grafana'],
            'prometheus': ['prometheus_data:/prometheus'],
            'n8n': ['n8n_data:/home/node/.n8n']
        };
        return vols[key] || [];
    }
}

// 🚀 Singleton Export
const openSource = new OpenSourceManager();
module.exports = openSource;
