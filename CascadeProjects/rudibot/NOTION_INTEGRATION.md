# Notion API Integration - RudiBot

## 🚀 **Integration Complete!**

### ✅ **Fertiggestellt:**

1. **.env Variablen hinzugefügt:**
   ```bash
   NOTION_API_KEY=secret_YOUR_NOTION_API_KEY_HERE
   NOTION_DATABASE_ID=YOUR_DATABASE_ID_HERE
   ```

2. **API Endpunkte in server.js:**
   - `GET /api/notion/database` - Database Info abrufen
   - `POST /api/notion/page` - Neue Seite erstellen

3. **Test-Script erstellt:** `test-notion-api.js`

## 📋 **Nächste Schritte:**

### 1. **Notion API Key besorgen:**
```
🔗 https://www.notion.so/my-integrations
1. "New integration" erstellen
2. Name: "RudiBot Integration"
3. Icon uploaden (optional)
4. Capabilities: "Read content", "Update content", "Insert content"
5. "Submit" → API Key kopieren
```

### 2. **API Key eintragen:**
```bash
# In .env ersetzen:
NOTION_API_KEY=secret_notion_abc123...
```

### 3. **Database ID besorgen (optional):**
```
1. Notion Database öffnen
2. URL kopieren: https://www.notion.so/your-workspace/Database-Name-a1b2c3d4e5f6...
3. Database ID = a1b2c3d4e5f6...
```

### 4. **Integration testen:**
```bash
# Server starten
node server.js

# In neuem Terminal:
node test-notion-api.js
```

## 🤖 **Bot Commands (geplant):**

```
/notion status    - Database Status anzeigen
/notion create    - Neue Seite erstellen
/notion list      - Letzte Seiten auflisten
/notion search    - Seiten durchsuchen
```

## 🌐 **API Endpunkte:**

### Database Info:
```bash
curl http://localhost:3200/api/notion/database
```

### Seite erstellen:
```bash
curl -X POST http://localhost:3200/api/notion/page \
  -H "Content-Type: application/json" \
  -d '{"title":"Meine neue Seite","content":"Inhalt hier"}'
```

## 📊 **Use Cases:**

- **📝 Projektmanagement** - Aufgaben automatisch erstellen
- **💡 Ideen sammeln** - Brainstorming Sessions dokumentieren  
- **📈 Meeting Notes** - Automatische Protokolle
- **🎯 Goals Tracking** - Ziele und Fortschritt
- **📚 Knowledge Base** - Wissensdatenbank pflegen

## 🔧 **Troubleshooting:**

### ❌ "unauthorized" Fehler:
- API Key prüfen
- Integration in Notion Seiten einladen

### ❌ "database not found" Fehler:
- Database ID prüfen
- Bot zur Database hinzufügen

### ❌ "missing capabilities" Fehler:
- Integration Capabilities erweitern

## 🎯 **Beispiel Integration:**

```javascript
// Automatische Aufgabe erstellen
const createTask = async (title, description) => {
  const response = await fetch('http://localhost:3200/api/notion/page', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: `📋 ${title}`,
      content: description
    })
  });
  return response.json();
};
```

**Notion Integration ist bereit für echten API Key! 🚀**
