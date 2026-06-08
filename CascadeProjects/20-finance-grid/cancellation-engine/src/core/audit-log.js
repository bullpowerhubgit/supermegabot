import fs from 'fs';

export function writeAuditLog(entry) {
  const line = JSON.stringify({
    timestamp: new Date().toISOString(),
    ...entry
  }) + '\n';

  fs.appendFileSync('logs/cancellation-audit.log', line, 'utf8');
}
