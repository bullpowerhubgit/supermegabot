import fs from 'fs';
import { providers } from './config/providers.js';
import { checkEligibility } from './core/eligibility-engine.js';
import { executeCancellation } from './core/execution-engine.js';
import { writeAuditLog } from './core/audit-log.js';

async function run() {
  const raw = fs.readFileSync('src/data/sample-contracts.json', 'utf8');
  const contracts = JSON.parse(raw);

  for (const contract of contracts) {
    const provider = providers[contract.provider];

    if (!provider) {
      writeAuditLog({
        provider: contract.provider,
        contractName: contract.contractName,
        status: 'failed',
        reason: 'Unknown provider'
      });
      continue;
    }

    const eligibility = checkEligibility(contract, provider);

    writeAuditLog({
      provider: contract.provider,
      contractName: contract.contractName,
      status: eligibility.status,
      reason: eligibility.reason
    });

    if (!eligibility.eligible) continue;

    const result = await executeCancellation(provider, contract);

    writeAuditLog({
      provider: contract.provider,
      contractName: contract.contractName,
      status: result.success ? 'submitted' : 'failed',
      channel: result.channel,
      reason: result.message || 'Cancellation submitted'
    });
  }
}

run().catch((error) => {
  writeAuditLog({
    status: 'failed',
    reason: error.message
  });
});
