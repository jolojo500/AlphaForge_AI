import React from 'react';
import { WhatIfDiff, ScenarioName, GraphState } from '../types';
import { GitCompare, ArrowRight, ArrowUpRight, ArrowDownRight, Minus, X } from 'lucide-react';
import { useLanguage } from '@/context/LanguageContext';
import { RichText } from '@/lib/evidenceText';
import { metricLabel, scenarioTitle, whatIfFieldLabel, whatIfValueLabel } from '@/lib/labels';
import { fmtPct, fmtPoints, type Lang } from '@/lib/format';

interface WhatIfDiffViewProps {
  diff: WhatIfDiff | null;
  onClose: () => void;
  /** The run before the assumption changed: its answer stays on screen, on the left. */
  before?: GraphState | null;
  /** The run with the changed assumption, on the right. */
  after?: GraphState | null;
  onJump?: (id: string) => void;
}

const SCENARIO_ORDER: ScenarioName[] = ['current', 'as_requested', 'capped', 'profile_baseline'];

function DeltaBadge({ delta, lang }: { delta: number; lang: Lang }) {
  const isIncrease = delta > 0.0001;
  const isDecrease = delta < -0.0001;
  return (
    <span
      className={`inline-flex items-center text-[10px] font-bold px-1 py-0.5 rounded whitespace-nowrap ${
        isIncrease
          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
          : isDecrease
          ? 'bg-red-500/10 text-red-600 dark:text-red-400'
          : 'bg-muted text-muted-foreground'
      }`}
    >
      {isIncrease ? (
        <ArrowUpRight className="w-2.5 h-2.5 mr-0.5" />
      ) : isDecrease ? (
        <ArrowDownRight className="w-2.5 h-2.5 mr-0.5" />
      ) : (
        <Minus className="w-2.5 h-2.5 mr-0.5" />
      )}
      {fmtPoints(delta, lang, 1)}
    </span>
  );
}

export const WhatIfDiffView: React.FC<WhatIfDiffViewProps> = ({ diff, onClose, before, after, onJump }) => {
  const { language } = useLanguage();
  const lang: Lang = language === 'en' ? 'en' : 'fr';
  const en = lang === 'en';
  if (!diff) return null;

  const field = diff.change?.field;
  const hypothesis = `${whatIfFieldLabel(field, lang)}\u00a0: ${whatIfValueLabel(field, diff.change?.value, lang)}`;
  const beforeLabel = en ? 'Before' : 'Avant';
  const afterLabel = en ? 'After' : 'Après';
  const scenarioNames = SCENARIO_ORDER.filter((s) => diff.scenarios[s]);
  const beforeResume = before?.explanation?.resume;
  const afterResume = after?.explanation?.resume;
  const noop = () => undefined;

  return (
    <section className="bg-card border-2 border-primary/40 rounded-xl p-5 sm:p-6 mb-6 shadow-xs" aria-label={en ? 'Before / after comparison' : 'Comparaison avant / après'}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 pb-3 mb-4 border-b border-border/70">
        <div className="flex items-start gap-2 min-w-0">
          <GitCompare className="w-5 h-5 text-primary shrink-0 mt-0.5" />
          <div className="min-w-0">
            <h2 className="text-sm sm:text-base font-bold text-foreground">
              {en ? 'Before / After: one assumption changed' : 'Avant / Après : une hypothèse modifiée'}
            </h2>
            <p className="text-xs text-primary flex flex-wrap items-center gap-1.5 mt-1">
              <span className="font-semibold uppercase tracking-wider text-[10px]">{en ? 'Hypothesis' : 'Hypothèse'}</span>
              <span className="bg-primary/10 px-2 py-0.5 rounded border border-primary/30 text-foreground font-medium">
                {hypothesis}
              </span>
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground p-1 rounded-md transition-colors cursor-pointer shrink-0"
          aria-label={en ? 'Close the before / after comparison' : 'Fermer la comparaison avant / après'}
          title={en ? 'Close' : 'Fermer'}
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* The two answers, side by side: the original stays on screen. */}
      {(beforeResume || afterResume) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
          <div className="rounded-lg border border-border bg-muted/30 p-3.5">
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
              {beforeLabel} · {en ? 'original answer' : "réponse d'origine"}
            </div>
            <div className="text-xs text-foreground leading-relaxed space-y-2">
              {(beforeResume || '').split('\n\n').map((p, i) => (
                <p key={i}>
                  <RichText text={p} evidence={before?.evidence || {}} onJump={noop} lang={lang} scenarioCount={before?.scenarios?.length} />
                </p>
              ))}
              {!beforeResume && <p className="text-muted-foreground italic">—</p>}
            </div>
          </div>
          <div className="rounded-lg border-2 border-primary/40 bg-primary/5 p-3.5">
            <div className="text-[10px] font-bold uppercase tracking-wider text-primary mb-1.5">
              {afterLabel} · {en ? 'hypothesis' : 'hypothèse'}&nbsp;: {whatIfValueLabel(field, diff.change?.value, lang)}
            </div>
            <div className="text-xs text-foreground leading-relaxed space-y-2">
              {(afterResume || '').split('\n\n').map((p, i) => (
                <p key={i}>
                  <RichText text={p} evidence={after?.evidence || {}} onJump={onJump ?? noop} lang={lang} scenarioCount={after?.scenarios?.length} />
                </p>
              ))}
              {!afterResume && <p className="text-muted-foreground italic">—</p>}
            </div>
          </div>
        </div>
      )}

      {/* Summary bullet points */}
      {diff.summary && diff.summary.length > 0 && (
        <div className="bg-muted/40 p-3.5 rounded-lg border border-border mb-5">
          <span className="text-xs font-bold uppercase tracking-wider text-foreground block mb-1">
            {en ? 'What changed in the allocations' : 'Ce qui change dans les répartitions'}
          </span>
          <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
            {diff.summary.map((line, idx) => (
              <li key={idx} className="font-medium">
                <RichText text={line} evidence={after?.evidence || {}} onJump={onJump ?? noop} lang={lang} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Per scenario: weights and figures, before on the left, after on the right, gap in points */}
      <div className={`grid grid-cols-1 ${scenarioNames.length >= 4 ? 'md:grid-cols-2 xl:grid-cols-4' : 'lg:grid-cols-3'} gap-4`}>
        {scenarioNames.map((name) => {
          const scDiff = diff.scenarios[name];
          if (!scDiff) return null;

          const weightEntries = Object.entries(scDiff.weights).filter(
            ([, delta]) => delta.old > 0 || delta.new > 0 || delta.delta !== 0
          );

          return (
            <div key={name} className="bg-card rounded-lg p-4 border border-border shadow-2xs">
              <h3 className="text-sm font-bold text-foreground mb-3 pb-1 border-b border-border/60">
                {scenarioTitle(name, lang)}
              </h3>

              <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-2 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
                <span>{en ? 'Allocation' : 'Répartition'}</span>
                <span className="text-right">{beforeLabel}</span>
                <span className="text-right">{afterLabel}</span>
                <span className="text-right">{en ? 'Gap' : 'Écart'}</span>
              </div>
              <div className="space-y-1 max-h-48 overflow-y-auto pr-1 mb-4">
                {weightEntries.length === 0 && (
                  <p className="text-[11px] text-muted-foreground italic">{en ? 'No change' : 'Aucun changement'}</p>
                )}
                {weightEntries.map(([ticker, delta]) => (
                  <div key={ticker} className="grid grid-cols-[1fr_auto_auto_auto] gap-x-2 items-center text-xs p-1 rounded">
                    <span className="font-mono text-foreground">{ticker}</span>
                    <span className="text-muted-foreground text-[11px] text-right">{fmtPct(delta.old, lang, 1)}</span>
                    <span className="font-semibold text-foreground text-[11px] text-right">{fmtPct(delta.new, lang, 1)}</span>
                    <span className="text-right">
                      <DeltaBadge delta={delta.delta} lang={lang} />
                    </span>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-[1fr_auto_auto] gap-x-2 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
                <span>{en ? 'Key figures' : 'Chiffres clés'}</span>
                <span className="text-right">
                  {beforeLabel} <ArrowRight className="inline w-3 h-3 text-muted-foreground/50" /> {afterLabel}
                </span>
                <span className="text-right">{en ? 'Gap' : 'Écart'}</span>
              </div>
              <div className="space-y-1 text-xs">
                {Object.entries(scDiff.metrics).map(([mKey, delta]) => {
                  if (delta.old === null && delta.new === null) return null;
                  const digits = mKey === 'fee_drag' || mKey === 'tax_drag' || mKey === 'all_in_cost' ? 2 : 1;
                  const oldStr = delta.old !== null ? fmtPct(delta.old, lang, digits) : '—';
                  const newStr = delta.new !== null ? fmtPct(delta.new, lang, digits) : '—';
                  const d = delta.delta ?? (delta.old !== null && delta.new !== null ? delta.new - delta.old : null);
                  return (
                    <div key={mKey} className="grid grid-cols-[1fr_auto_auto] gap-x-2 items-center py-0.5 text-foreground">
                      <span className="text-[11px] text-muted-foreground leading-snug">{metricLabel(mKey, lang)}</span>
                      <span className="text-[11px] font-mono whitespace-nowrap text-right">
                        <span className="text-muted-foreground">{oldStr}</span>
                        <span className="text-muted-foreground/40 mx-1">→</span>
                        <span className="font-bold text-foreground">{newStr}</span>
                      </span>
                      <span className="text-right">{d !== null ? <DeltaBadge delta={d} lang={lang} /> : '—'}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};
