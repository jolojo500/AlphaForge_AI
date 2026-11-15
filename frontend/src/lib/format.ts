/**
 * Number formatting with the typography of each language: French uses a comma for decimals
 * and a non-breaking space before "%"; differences between two ratios are expressed in points
 * ("-3,0 points"), never as a percentage of a percentage.
 */

export type Lang = 'fr' | 'en';

export const NBSP = '\u00a0';

export function fmtNumber(value: number, lang: Lang, digits = 1): string {
  return value.toLocaleString(lang === 'en' ? 'en-CA' : 'fr-CA', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** A ratio (0.123) shown as a percentage ("12,3 %" / "12.3%"). */
export function fmtPct(ratio: number, lang: Lang, digits = 1): string {
  const n = fmtNumber(ratio * 100, lang, digits);
  return lang === 'en' ? `${n}%` : `${n}${NBSP}%`;
}

/** A difference between two ratios, in percentage points ("+2,5 points" / "-3.0 points"). */
export function fmtPoints(delta: number, lang: Lang, digits = 1): string {
  const pts = delta * 100;
  const n = fmtNumber(pts, lang, digits);
  const sign = pts > 0 ? '+' : '';
  const plural = lang === 'en' ? Math.abs(pts) !== 1 : Math.abs(pts) >= 2;
  const unit = plural ? 'points' : 'point';
  return `${sign}${n}${NBSP}${unit}`;
}

/** Minutes with the language's decimal separator ("1,5" / "1.5"). */
export function fmtMinutes(minutes: number, lang: Lang): string {
  const digits = Number.isInteger(minutes) ? 0 : 1;
  return fmtNumber(minutes, lang, digits);
}

/** "2026-11-15T14:03:00" shown as a local date and time. */
export function fmtDateTime(iso: string | undefined | null, lang: Lang): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(lang === 'en' ? 'en-CA' : 'fr-CA', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
