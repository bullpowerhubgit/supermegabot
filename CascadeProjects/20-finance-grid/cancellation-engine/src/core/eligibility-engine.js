import { isNoticeStillValid } from '../utils/date-utils.js';
import { validateContract } from '../utils/validation-utils.js';

export function checkEligibility(contract, provider) {
  const validation = validateContract(contract, provider);
  if (!validation.valid) {
    return {
      eligible: false,
      status: 'invalid',
      reason: validation.errors.join(', ')
    };
  }

  const noticeOk = isNoticeStillValid(contract.nextRenewalDate, provider.noticeDays);
  if (!noticeOk) {
    return {
      eligible: false,
      status: 'missed_notice_window',
      reason: 'Notice period no longer valid'
    };
  }

  return {
    eligible: true,
    status: 'ready_to_cancel',
    reason: 'Contract can be processed'
  };
}
