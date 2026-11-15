import { TraceEntry } from '../types';
import { NODE_BUDGET_S, NODE_ORDER } from './labels';
import { fmtMinutes, type Lang } from './format';

export const TOTAL_STEPS = NODE_ORDER.length;

/** Step counter and remaining time from a fixed per-node budget: the sum of the unfinished nodes. */
export function runProgress(trace: TraceEntry[]): { step: number; remainingS: number; currentNode: string | null } {
  const done = new Set(trace.map((e) => e.node));
  const finished = NODE_ORDER.filter((n) => done.has(n)).length;
  const step = Math.min(TOTAL_STEPS, finished + 1);
  const remainingS = NODE_ORDER.filter((n) => !done.has(n)).reduce((s, n) => s + (NODE_BUDGET_S[n] ?? 5), 0);
  const currentNode = NODE_ORDER.find((n) => !done.has(n)) ?? null;
  return { step, remainingS, currentNode };
}

/** "environ 1,5 min restante" / "moins de 30 s restantes", rounded to the half minute. */
export function remainingLabel(remainingS: number, lang: Lang): string {
  if (remainingS <= 30) {
    return lang === 'en' ? 'under 30 s left' : 'moins de 30\u00a0s restantes';
  }
  const halfMinutes = Math.max(1, Math.round(remainingS / 30));
  const minutes = halfMinutes / 2;
  const m = fmtMinutes(minutes, lang);
  return lang === 'en' ? `about ${m} min left` : `environ ${m}\u00a0min restante${minutes > 1 ? 's' : ''}`;
}
