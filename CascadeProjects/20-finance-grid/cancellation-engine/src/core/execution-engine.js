import { cancelByEmail } from '../channels/cancel-by-email.js';
import { cancelByApi } from '../channels/cancel-by-api.js';
import { cancelByWeb } from '../channels/cancel-by-web.js';
import { createManualLetter } from '../channels/create-manual-letter.js';

export async function executeCancellation(provider, contract) {
  if (provider.supportsOnlineCancel) {
    return cancelByWeb(provider, contract);
  }

  switch (provider.channel) {
    case 'email':
      return cancelByEmail(provider, contract);
    case 'api':
      return cancelByApi(provider, contract);
    case 'manual-letter':
      return createManualLetter(provider, contract);
    default:
      return {
        success: false,
        channel: 'unknown',
        message: 'No execution path found'
      };
  }
}
