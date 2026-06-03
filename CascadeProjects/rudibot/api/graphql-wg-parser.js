/**
 * GraphQL WG Document Parser
 * Parst Meeting-Agendas und Dokumente aus dem WG Archiv
 */

const fs = require('fs').promises;
const path = require('path');

class GraphQLWGParser {
  constructor(archivePath = '/Users/rudolfsarkany/graphiql') {
    this.archivePath = archivePath;
  }

  // Alle Meeting-Agendas parsen
  async parseAllMeetings() {
    const meetings = [];
    
    try {
      const agendasDir = path.join(this.archivePath, 'working-group/agendas');
      const years = await this.getDirectories(agendasDir);
      
      for (const year of years) {
        const yearPath = path.join(agendasDir, year);
        const months = await this.getDirectories(yearPath);
        
        for (const month of months) {
          const monthPath = path.join(yearPath, month);
          const files = await this.getFiles(monthPath, '.md');
          
          for (const file of files) {
            const meeting = await this.parseMeetingFile(path.join(monthPath, file));
            if (meeting) {
              meetings.push(meeting);
            }
          }
        }
      }
    } catch (error) {
      console.error('GraphQL WG Parser Error:', error);
    }
    
    return meetings.sort((a, b) => new Date(b.date) - new Date(a.date));
  }

  // Einzelne Meeting-Datei parsen
  async parseMeetingFile(filePath) {
    try {
      const content = await fs.readFile(filePath, 'utf-8');
      const filename = path.basename(filePath, '.md');
      
      // Datum aus Dateinamen extrahieren (Format: YYYY-MM-DD oder YYYY-MM-DD-title)
      const dateMatch = filename.match(/(\d{4}-\d{2}-\d{2})/);
      if (!dateMatch) return null;
      
      const date = dateMatch[1];
      
      // Titel aus Content extrahieren
      const titleMatch = content.match(/^#\s+(.+)$/m);
      const title = titleMatch ? titleMatch[1] : `GraphQL WG Meeting ${date}`;
      
      // Agenda Items extrahieren
      const agendaItems = this.extractListItems(content, '## Agenda');
      
      // Attendees extrahieren
      const attendees = this.extractAttendees(content);
      
      // Decisions/Action Items extrahieren
      const decisions = this.extractDecisions(content);
      
      return {
        id: `wg-${filename}`,
        date,
        title,
        agenda: agendaItems.join('\n'),
        attendees,
        decisions,
        filePath: filePath.replace(this.archivePath, ''),
        rawContent: content
      };
    } catch (error) {
      console.error(`Error parsing ${filePath}:`, error);
      return null;
    }
  }

  // Listen-Items aus Markdown extrahieren
  extractListItems(content, sectionHeader) {
    const sectionMatch = content.match(new RegExp(`${sectionHeader}[\\s\\S]*?(?=##|$)`));
    if (!sectionMatch) return [];
    
    const section = sectionMatch[0];
    const items = [];
    
    // Bullet points und numbered lists
    const listRegex = /^[ \t]*[-*+]\s+(.+)$/gm;
    let match;
    
    while ((match = listRegex.exec(section)) !== null) {
      items.push(match[1].trim());
    }
    
    return items;
  }

  // Attendees extrahieren
  extractAttendees(content) {
    const attendees = [];
    
    // Verschiedene Formate für Attendees
    const patterns = [
      /## Attendees[\s\S]*?((?:[-*+]\s+.+[\r\n]*)+)/g,
      /## Participants[\s\S]*?((?:[-*+]\s+.+[\r\n]*)+)/g,
      /### Who[\s\S]*?((?:[-*+]\s+.+[\r\n]*)+)/g
    ];
    
    for (const pattern of patterns) {
      const match = content.match(pattern);
      if (match) {
        const listItems = match[1].match(/^[-*+]\s+(.+)$/gm);
        if (listItems) {
          attendees.push(...listItems.map(item => item.trim()));
        }
      }
    }
    
    return attendees;
  }

  // Decisions/Action Items extrahieren
  extractDecisions(content) {
    const decisions = [];
    
    // Verschiedene Section Headers
    const patterns = [
      /## Decisions[\s\S]*?((?:[-*+]\s+.+[\r\n]*)+)/g,
      /## Action Items[\s\S]*?((?:[-*+]\s+.+[\r\n]*)+)/g,
      /## Outcomes[\s\S]*?((?:[-*+]\s+.+[\r\n]*)+)/g,
      /## Resolutions[\s\S]*?((?:[-*+]\s+.+[\r\n]*)+)/g
    ];
    
    for (const pattern of patterns) {
      const match = content.match(pattern);
      if (match) {
        const listItems = match[1].match(/^[-*+]\s+(.+)$/gm);
        if (listItems) {
          decisions.push(...listItems.map(item => item.trim()));
        }
      }
    }
    
    return decisions;
  }

  // Helper: Directories auflisten
  async getDirectories(dirPath) {
    try {
      const items = await fs.readdir(dirPath, { withFileTypes: true });
      return items
        .filter(item => item.isDirectory())
        .map(item => item.name)
        .sort();
    } catch (error) {
      return [];
    }
  }

  // Helper: Files auflisten
  async getFiles(dirPath, extension = '') {
    try {
      const items = await fs.readdir(dirPath, { withFileTypes: true });
      return items
        .filter(item => item.isFile() && item.name.endsWith(extension))
        .map(item => item.name)
        .sort();
    } catch (error) {
      return [];
    }
  }

  // Suche nach Meetings mit Keywords
  async searchMeetings(keyword) {
    const allMeetings = await this.parseAllMeetings();
    const lowerKeyword = keyword.toLowerCase();
    
    return allMeetings.filter(meeting => 
      meeting.title.toLowerCase().includes(lowerKeyword) ||
      meeting.agenda.toLowerCase().includes(lowerKeyword) ||
      meeting.decisions.some(decision => decision.toLowerCase().includes(lowerKeyword))
    );
  }

  // Meetings nach Jahr/Month filtern
  async getMeetingsByDate(year, month) {
    const allMeetings = await this.parseAllMeetings();
    
    return allMeetings.filter(meeting => {
      const meetingDate = new Date(meeting.date);
      return meetingDate.getFullYear() === parseInt(year) &&
             (month ? meetingDate.getMonth() + 1 === parseInt(month) : true);
    });
  }
}

module.exports = GraphQLWGParser;
