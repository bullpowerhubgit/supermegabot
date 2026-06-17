export function daysUntil(dateString) {
  const now = new Date();
  const target = new Date(dateString);
  const diff = target.getTime() - now.getTime();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

export function isNoticeStillValid(nextRenewalDate, noticeDays) {
  return daysUntil(nextRenewalDate) >= noticeDays;
}
