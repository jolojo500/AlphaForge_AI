import React from 'react';
import { Scenario, Evidence } from '../types';
import { BarChart3, Star, AlertTriangle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { InfoTooltip } from '@/components/ui/info-tooltip';
import { useLanguage } from '@/context/LanguageContext';
import { humanize } from '@/lib/evidenceText';
import { countWord, metricInfo, scenarioSubtitle, scenarioTitle } from '@/lib/labels';
import { fmtNumber, fmtPct, fmtPoints, type Lang } from '@/lib/format';

interface ScenarioCardsProps {
  scenarios: Scenario[];
  evidence: Record<string, Evidence>;
  mostConsistentName?: string;
  evaluatedTicker?: string | null;
  /** Position in the detailed section, so the numbering stays continuous. */
  sectionNumber?: number;
  /** Opens the full evidence registry at this row. */
  onOpenRegistry?: (id: string) => void;
}

function formatMetricValue(ev: Evidence | undefined, metricKey: string, lang: Lang): string {
  if (!ev) return '—';
  let val = ev.value;
  if (typeof val === 'object' && val !== null && 'value' in val) {
    val = (val as { value: unknown }).value as number | string;
  }
  if (typeof val === 'number') {
    switch (metricInfo(metricKey, lang).kind) {
      case 'pct2':
        return fmtPct(val, lang, 2);
      case 'number':
        return fmtNumber(val, lang, 1);
      case 'text':
        return String(val);
      default:
        return fmtPct(val, lang, 1);
    }
  }
  return String(val);
}

export const ScenarioCards: React.FC<ScenarioCardsProps> = ({
  scenarios,
  evidence,
  mostConsistentName,
  evaluatedTicker,
  sectionNumber,
  onOpenRegistry,
}) => {
  const { language } = useLanguage();
  const lang: Lang = language === 'en' ? 'en' : 'fr';
  const isEn = lang === 'en';

  if (!scenarios || scenarios.length === 0) return null;

  const n = scenarios.length;
  const prefix = sectionNumber ? `${sectionNumber}. ` : '';
  const heading = isEn
    ? `${prefix}The ${countWord(n, 'en')} scenarios compared`
    : `${prefix}Les ${countWord(n, 'fr')} scénarios comparés`;
  const turnoverInfo = metricInfo('turnover', lang);

  return (
    <Card className="bg-card border-border shadow-sm mb-6">
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-primary" />
            <h2 className="text-sm sm:text-base font-semibold text-foreground">{heading}</h2>
          </div>
        </div>

        {(() => {
          const hardGateNotes = Array.from(
            new Set(
              scenarios.flatMap((s) =>
                (s.notes || []).filter(
                  (note) => note.includes('Garde-fou') || note.includes('Avertissement préalable')
                )
              )
            )
          );
          if (hardGateNotes.length === 0) return null;
          return (
            <div className="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-900 dark:text-amber-200 text-xs">
              <div className="font-semibold flex items-center gap-1.5 mb-1.5 text-amber-700 dark:text-amber-300">
                <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                {isEn ? 'Safeguards and financial situation' : 'Garde-fous et situation financière'}
              </div>
              <ul className="list-disc list-inside space-y-1 text-muted-foreground dark:text-amber-200/90">
                {hardGateNotes.map((note, idx) => (
                  <li key={idx} className="leading-relaxed">
                    {humanize(note.replace(/^⚠️\s*/, ''), lang)}
                  </li>
                ))}
              </ul>
            </div>
          );
        })()}

        <div className={`grid grid-cols-1 ${n >= 4 ? 'md:grid-cols-2 xl:grid-cols-4' : 'lg:grid-cols-3'} gap-4`}>
          {scenarios.map((sc) => {
            const isMostConsistent = sc.name === mostConsistentName;
            const sortedWeights = Object.entries(sc.weights).sort((a, b) => b[1] - a[1]);

            return (
              <div
                key={sc.name}
                className={`rounded-xl border p-4 flex flex-col justify-between transition-all relative ${
                  isMostConsistent
                    ? 'border-emerald-500 bg-emerald-500/10 ring-1 ring-emerald-500/30 shadow-xs'
                    : 'border-border bg-card/60 hover:border-border/80'
                }`}
              >
                <div>
                  {/* Header with consistency badge */}
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground">{scenarioTitle(sc.name, lang)}</h3>
                      <p className="text-xs text-muted-foreground">{scenarioSubtitle(sc.name, lang)}</p>
                    </div>
                    {isMostConsistent && (
                      <Badge variant="outline" className="gap-1 border-emerald-500/40 text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 text-[11px] py-0.5 shrink-0">
                        <Star className="w-2.5 h-2.5 fill-emerald-500 text-emerald-500" />
                        {isEn ? 'Most consistent' : 'Le plus cohérent'}
                      </Badge>
                    )}
                    {sc.name === 'current' && (
                      <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300 bg-sky-500/10 text-[11px] py-0.5 shrink-0">
                        {isEn ? 'Starting point' : 'Point de départ'}
                      </Badge>
                    )}
                  </div>

                  {/* Weights breakdown */}
                  <div className="mt-4 mb-5">
                    <h4 className="text-xs font-semibold text-foreground/80 uppercase tracking-wider mb-2">
                      {isEn ? `Allocation (${sortedWeights.length})` : `Répartition (${sortedWeights.length})`}
                    </h4>
                    <div className="space-y-1.5">
                      {sortedWeights.map(([ticker, weight]) => {
                        const isHighlightedTicker = Boolean(evaluatedTicker && ticker === evaluatedTicker);
                        return (
                          <div
                            key={ticker}
                            className={`text-xs p-1.5 rounded-lg transition-colors ${
                              isHighlightedTicker ? 'bg-amber-500/10 border border-amber-500/20' : ''
                            }`}
                          >
                            <div className="flex justify-between items-center text-foreground mb-1">
                              <span className="font-semibold font-mono flex items-center gap-1">
                                {ticker}
                                {isHighlightedTicker && (
                                  <span className="text-[10px] text-amber-600 dark:text-amber-400 font-normal">
                                    {isEn ? '(asset you asked about)' : '(actif de votre demande)'}
                                  </span>
                                )}
                              </span>
                              <span className="font-medium text-foreground">{fmtPct(weight, lang, 1)}</span>
                            </div>
                            <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  isHighlightedTicker
                                    ? 'bg-amber-500'
                                    : isMostConsistent
                                    ? 'bg-emerald-500'
                                    : 'bg-blue-500'
                                }`}
                                style={{ width: `${Math.min(100, Math.max(0, weight * 100))}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Metrics comparison */}
                  <div className="border-t border-border/60 pt-4 mb-4">
                    <h4 className="text-xs font-semibold text-foreground/80 uppercase tracking-wider mb-2">
                      {isEn ? 'Key figures' : 'Chiffres clés'}
                    </h4>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {Object.entries(sc.metrics).map(([metricKey, eid]) => {
                        const ev = evidence[eid];
                        const info = metricInfo(metricKey, lang);
                        const formatted = formatMetricValue(ev, metricKey, lang);
                        const valueTitle = isEn
                          ? `${info.label}: see the evidence ${eid}`
                          : `${info.label} : voir la preuve ${eid}`;
                        return (
                          <div key={metricKey} className="bg-muted/50 p-2.5 rounded-lg border border-border/60 min-w-0">
                            <span className="text-[11px] text-muted-foreground leading-snug flex items-start gap-1">
                              <span className="break-words">{info.label}</span>
                              {info.tip && <InfoTooltip content={info.tip} className="mt-0.5" />}
                            </span>
                            {ev ? (
                              <button
                                type="button"
                                onClick={() => onOpenRegistry?.(eid)}
                                title={valueTitle}
                                aria-label={`${info.label} ${formatted}`}
                                className="font-semibold text-foreground block mt-0.5 underline decoration-dotted decoration-primary/40 underline-offset-2 hover:decoration-solid cursor-pointer text-left"
                              >
                                {formatted}
                              </button>
                            ) : (
                              <span className="font-semibold text-foreground block mt-0.5">{formatted}</span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Turnover and trades from current */}
                  {sc.turnover !== undefined && sc.turnover !== null && (
                    <div className="border-t border-border/60 pt-3 mb-4">
                      <div className="flex items-center justify-between mb-1.5 gap-2">
                        <span className="text-xs font-semibold text-foreground/80 uppercase tracking-wider flex items-center gap-1">
                          {turnoverInfo.label}
                          <InfoTooltip content={turnoverInfo.tip} />
                        </span>
                        <Badge variant="secondary" className="font-mono text-xs font-semibold shrink-0">
                          {fmtPct(sc.turnover, lang, 1)}
                        </Badge>
                      </div>
                      {sc.trades && sc.trades.length > 0 && (
                        <div className="space-y-1 mt-2">
                          <p className="text-[11px] text-muted-foreground font-medium mb-1">
                            {isEn ? `Changes from today (${sc.trades.length}):` : `Écarts par rapport à aujourd'hui (${sc.trades.length})\u00a0:`}
                          </p>
                          <div className="max-h-32 overflow-y-auto space-y-1 pr-0.5">
                            {sc.trades.map((tr) => {
                              const isUp = tr.change > 0;
                              const actionLabel = isEn ? (isUp ? 'MORE' : 'LESS') : (isUp ? 'PLUS' : 'MOINS');
                              return (
                                <div
                                  key={tr.ticker}
                                  className="flex items-center justify-between text-[11px] p-1.5 rounded bg-muted/40 border border-border/40"
                                >
                                  <div className="flex items-center gap-1.5">
                                    <span
                                      className={`px-1 py-0.2 rounded font-semibold text-[10px] ${
                                        isUp
                                          ? 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300'
                                          : 'bg-rose-500/20 text-rose-700 dark:text-rose-300'
                                      }`}
                                    >
                                      {actionLabel}
                                    </span>
                                    <span className="font-mono font-medium">{tr.ticker}</span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <span
                                      className={`font-mono font-semibold ${
                                        isUp ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                                      }`}
                                    >
                                      {fmtPoints(tr.change, lang, 1)}
                                    </span>
                                    {tr.amount_cad !== undefined && (
                                      <span className="text-muted-foreground text-[10px]">
                                        ({tr.amount_cad > 0 ? '+' : ''}
                                        {tr.amount_cad.toLocaleString(isEn ? 'en-CA' : 'fr-CA', { maximumFractionDigits: 0 })}
                                        {'\u00a0$'})
                                      </span>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Historical outcomes over horizon (#122) */}
                  {sc.historical_outcomes && (
                    <div className="border-t border-border/60 pt-4 mb-4">
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-xs font-semibold text-foreground/80 uppercase tracking-wider flex items-center gap-1">
                          {isEn ? 'Past periods' : 'Périodes passées'}
                          <InfoTooltip
                            content={
                              isEn
                                ? 'What this allocation would have returned over every 1-year and 3-year window of the available history. A description of the past, not a forecast.'
                                : "Ce que cette répartition aurait rapporté sur chaque période de 1 an et de 3 ans de l'historique disponible. Une description du passé, pas une prévision."
                            }
                          />
                        </h4>
                        <span className="text-[10px] text-muted-foreground italic">
                          {isEn ? 'historical, not a forecast' : 'historique, pas une prévision'}
                        </span>
                      </div>

                      <div className="space-y-2">
                        {(['1y', '3y'] as const).map((win) => {
                          const stats = sc.historical_outcomes?.[win];
                          if (!stats) return null;
                          const years = win === '1y' ? 1 : 3;
                          return (
                            <div key={win} className="p-2 rounded-lg bg-muted/40 border border-border/50 text-[11px] space-y-1">
                              <div className="flex justify-between items-center font-medium text-foreground">
                                <span>
                                  {isEn
                                    ? `${years}-year windows (${stats.windows_count} obs.)`
                                    : `Périodes de ${years}\u00a0an${years > 1 ? 's' : ''} (${stats.windows_count} obs.)`}
                                </span>
                                <span className="text-muted-foreground font-mono text-[10px]">
                                  {isEn ? 'Losing: ' : 'En perte\u00a0: '}
                                  {fmtPct(stats.loss_share, lang, 0)}
                                </span>
                              </div>
                              <div className="grid grid-cols-3 gap-1 text-[10px] font-mono">
                                <div className="bg-rose-500/10 text-rose-700 dark:text-rose-300 p-1 rounded text-center">
                                  <span className="block text-[9px] text-muted-foreground">{isEn ? 'Worst' : 'Pire'}</span>
                                  {fmtPct(stats.worst, lang, 1)}
                                </div>
                                <div className="bg-blue-500/10 text-blue-700 dark:text-blue-300 p-1 rounded text-center">
                                  <span className="block text-[9px] text-muted-foreground">{isEn ? 'Median' : 'Médiane'}</span>
                                  {fmtPct(stats.median, lang, 1)}
                                </div>
                                <div className="bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 p-1 rounded text-center">
                                  <span className="block text-[9px] text-muted-foreground">{isEn ? 'Best' : 'Meilleure'}</span>
                                  {stats.best > 0 ? '+' : ''}
                                  {fmtPct(stats.best, lang, 1)}
                                </div>
                              </div>
                            </div>
                          );
                        })}

                        {sc.historical_outcomes.horizon_covered === false && sc.historical_outcomes.horizon_years && (
                          <p className="text-[10px] text-amber-600 dark:text-amber-400 leading-tight pt-0.5">
                            {isEn
                              ? `* Your horizon (${sc.historical_outcomes.horizon_years} years) goes beyond the 3-year windows the available 5-year history allows.`
                              : `* Votre horizon (${sc.historical_outcomes.horizon_years}\u00a0ans) dépasse les périodes de 3\u00a0ans que permet l'historique disponible (5\u00a0ans).`}
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* Notes */}
                {sc.notes && sc.notes.length > 0 && (
                  <div className="border-t border-border/60 pt-3 text-xs text-muted-foreground">
                    <ul className="space-y-1 list-disc list-inside">
                      {sc.notes.map((note, nIdx) => (
                        <li key={nIdx} className="leading-snug">{humanize(note, lang)}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
};
