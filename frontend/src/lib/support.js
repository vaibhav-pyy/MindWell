// Helpline details come from the single shared file (also read by the backend).
// Bundled at build time so the helpline works even if the API is unreachable.
import support from '@shared/support-config.json';

export const SUPPORT = support;
export const HELPLINE = support.helpline;
export const EMERGENCY = support.emergency_services;

export function telHref(number) {
  const digits = String(number || '').replace(/[^\d+]/g, '');
  return /^\+?\d{3,15}$/.test(digits) ? `tel:${digits}` : null;
}
