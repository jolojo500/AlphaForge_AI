import React from 'react';
import { Scenario, Evidence } from '../types';
import { BarChart3, Star, AlertTriangle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useLanguage } from '@/context/LanguageContext';

interface ScenarioCardsProps {
  scenarios: Scenario[];
  evidence: Record<string, Evidence>;
  mostConsistentName?: string;
  evaluatedTicker?: string | null;
}

const SCENARIO_TITLES_FR: Record<string, { title: string; subtitle: string }> = {
  current: {
    title: 'Portefeuille actuel',
    subtitle: 'Positions déclarées par le client',
  },
  as_requested: {
    title: 'Scénario brut demandé',
    subtitle: 'Intégration directe de votre idée',
  },
  capped: {
    title: 'Scénario plafonné',
    subtitle: 'Ajusté selon vos garde-fous',
  },
  profile_baseline: {
    title: 'Profil de référence',
    subtitle: 'Allocation type sans titre spéculatif',
  },
};

const SCENARIO_TITLES_EN: Record<string, { title: string; subtitle: string }> = {
  current: {
    title: 'Current Portfolio',
    subtitle: 'Declared client holdings',
  },
  as_requested: {
    title: 'Raw Requested Scenario',
    subtitle: 'Direct integration of your proposed idea',
  },
  capped: {
    title: 'Capped Scenario',
    subtitle: 'Adjusted to fit your suitability limits',
  },
  profile_baseline: {
    title: 'Reference Baseline',
    subtitle: 'Standard allocation without speculative tilt',
  },
};

const METRIC_LABELS_FR: Record<string, string> = {
  volatility_ann: 'Volatilité annuelle',
  max_drawdown: 'Perte historique max',
  stress_2022: 'Stress test 2022',
  top_weight: 'Poids principal',
  sector_concentration_hhi: 'Concentration (HHI)',
  us_exposure: 'Exposition US',
  tax_drag: 'Friction fiscale estimée',
  fee_drag: 'Frais de gestion (RFG)',
  esg_proxy_share: 'Part proxy ESG (ESGV)',
};

const METRIC_LABELS_EN: Record<string, string> = {
  volatility_ann: 'Annualized Volatility',
  max_drawdown: 'Historical Max Loss',
  stress_2022: '2022 Stress Test',
  top_weight: 'Top Holding Weight',
  sector_concentration_hhi: 'Concentration (HHI)',
  us_exposure: 'US Exposure',
  tax_drag: 'Estimated Tax Drag',
  fee_drag: 'Management Fees (MER)',
  esg_proxy_share: 'ESG Proxy Share (ESGV)',
};

function formatMetricValue(ev: Evidence | undefined, metricKey?: string): string {
  if (!ev) return '—';
  let val = ev.value;
  if (typeof val === 'object' && val !== null && 'value' in val) {
    val = (val as { value: unknown }).value as number | string;
  }
  if (typeof val === 'number') {
    if (metricKey === 'fee_drag' || metricKey === 'tax_drag') {
      return `${(val * 100).toFixed(2)} %`;
    }
    return `${(val * 100).toFixed(1)} %`;
  }
  return String(val);
}

export const ScenarioCards: React.FC<ScenarioCardsProps> = ({
  scenarios,
  evidence,
  mostConsistentName,
  evaluatedTicker,
}) => {
  const { language } = useLanguage();
  const isEn = language === 'en';
  const scenarioTitles = isEn ? SCENARIO_TITLES_EN : SCENARIO_TITLES_FR;
  const metricLabels = isEn ? METRIC_LABELS_EN : METRIC_LABELS_FR;

  if (!scenarios || scenarios.length === 0) return null;

  return (
    <Card className="bg-card border-border shadow-sm mb-6">
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-primary" />
            <h2 className="text-sm sm:text-base font-semibold text-foreground">
              {isEn
                ? `3. Comparison of Simulated Scenarios (${scenarios.length})`
                : `3. Comparaison des scénarios simulés (${scenarios.length})`}
            </h2>
          </div>
        </div>

        {(() => {
          const hardGateNotes = Array.from(
            new Set(
              scenarios.flatMap((s) =>
                (s.notes || []).filter(
                  (n) => n.includes('Garde-fou') || n.includes('Avertissement préalable')
                )
              )
            )
          );
          if (hardGateNotes.length === 0) return null;
          return (
            <div className="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-900 dark:text-amber-200 text-xs">
              <div className="font-semibold flex items-center gap-1.5 mb-1.5 text-amber-700 dark:text-amber-300">
                <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                Garde-fous prudentiels & Situation financière
              </div>
              <ul className="list-disc list-inside space-y-1 text-muted-foreground dark:text-amber-200/90">
                {hardGateNotes.map((note, idx) => (
                  <li key={idx} className="leading-relaxed">
                    {note.replace(/^⚠️\s*/, '')}
                  </li>
                ))}
              </ul>
            </div>
          );
        })()}

        <div className={`grid grid-cols-1 ${scenarios.length >= 4 ? 'md:grid-cols-2 lg:grid-cols-4' : 'lg:grid-cols-3'} gap-4`}>
          {scenarios.map((sc) => {
            const isMostConsistent = sc.name === mostConsistentName;
            const info = scenarioTitles[sc.name] || {
              title: sc.name,
              subtitle: isEn ? 'Portfolio simulation' : 'Simulation de portefeuille',
            };

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
                      <h3 className="text-sm font-semibold text-foreground">{info.title}</h3>
                      <p className="text-xs text-muted-foreground">{info.subtitle}</p>
                    </div>
                    {isMostConsistent && (
                      <Badge variant="outline" className="gap-1 border-emerald-500/40 text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 text-[11px] py-0.5">
                        <Star className="w-2.5 h-2.5 fill-emerald-500 text-emerald-500" />
                        {isEn ? 'Most consistent' : 'Plus cohérent'}
                      </Badge>
                    )}
                    {sc.name === 'current' && (
                      <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300 bg-sky-500/10 text-[11px] py-0.5">
                        {isEn ? 'Starting point' : 'Point de départ'}
                      </Badge>
                    )}
                  </div>

                  {/* Weights breakdown */}
                  <div className="mt-4 mb-5">
                    <h4 className="text-xs font-semibold text-foreground/80 uppercase tracking-wider mb-2">
                      {isEn
                        ? `Asset Allocation (${sortedWeights.length})`
                        : `Répartition des actifs (${sortedWeights.length})`}
                    </h4>
                    <div className="space-y-1.5">
                      {sortedWeights.map(([ticker, weight]) => {
                        const pct = (weight * 100).toFixed(1);
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
                                    {isEn ? '(evaluated asset)' : '(actif évalué)'}
                                  </span>
                                )}
                              </span>
                              <span className="font-medium text-foreground">{pct} %</span>
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
                      {isEn ? 'Key Risk Indicators' : 'Indicateurs clés de risque'}
                    </h4>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {Object.entries(sc.metrics).map(([metricKey, eid]) => {
                        const ev = evidence[eid];
                        const formatted = formatMetricValue(ev, metricKey);
                        return (
                          <div key={metricKey} className="bg-muted/50 p-2.5 rounded-lg border border-border/60">
                            <span className="text-[11px] text-muted-foreground block truncate" title={metricLabels[metricKey] || metricKey}>
                              {metricLabels[metricKey] || metricKey}
                            </span>
                            <span className="font-semibold text-foreground block mt-0.5">
                              {formatted}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Turnover and trades from current */}
                  {sc.turnover !== undefined && sc.turnover !== null && (
                    <div className="border-t border-border/60 pt-3 mb-4">
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-semibold text-foreground/80 uppercase tracking-wider">
                          {isEn ? 'Required Turnover' : 'Rotation requise (Turnover)'}
                        </span>
                        <Badge variant="secondary" className="font-mono text-xs font-semibold">
                          {(sc.turnover * 100).toFixed(1)} %
                        </Badge>
                      </div>
                      {sc.trades && sc.trades.length > 0 && (
                        <div className="space-y-1 mt-2">
                          <p className="text-[11px] text-muted-foreground font-medium mb-1">
                            {isEn ? `Rebalancing Orders (${sc.trades.length}):` : `Ordres d'arbitrage (${sc.trades.length}) :`}
                          </p>
                          <div className="max-h-32 overflow-y-auto space-y-1 pr-0.5">
                            {sc.trades.map((tr) => {
                              const isBuy = tr.change > 0;
                              const actionLabel = isEn
                                ? (isBuy ? 'BUY' : 'SELL')
                                : (isBuy ? 'ACHAT' : 'VENTE');
                              return (
                                <div
                                  key={tr.ticker}
                                  className="flex items-center justify-between text-[11px] p-1.5 rounded bg-muted/40 border border-border/40"
                                >
                                  <div className="flex items-center gap-1.5">
                                    <span
                                      className={`px-1 py-0.2 rounded font-semibold text-[10px] ${
                                        isBuy
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
                                        isBuy ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                                      }`}
                                    >
                                      {isBuy ? '+' : ''}
                                      {(tr.change * 100).toFixed(1)} %
                                    </span>
                                    {tr.amount_cad !== undefined && (
                                      <span className="text-muted-foreground text-[10px]">
                                        ({tr.amount_cad > 0 ? '+' : ''}
                                        {tr.amount_cad.toLocaleString(isEn ? 'en-CA' : 'fr-CA', { maximumFractionDigits: 0 })} $)
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
                        <h4 className="text-xs font-semibold text-foreground/80 uppercase tracking-wider">
                          {isEn ? 'Rolling Returns' : 'Rendements glissants'}
                        </h4>
                        <span className="text-[10px] text-muted-foreground italic">
                          {isEn ? 'historical, not a forecast' : 'historique, pas une prévision'}
                        </span>
                      </div>

                      <div className="space-y-2">
                        {sc.historical_outcomes['1y'] && (
                          <div className="p-2 rounded-lg bg-muted/40 border border-border/50 text-[11px] space-y-1">
                            <div className="flex justify-between items-center font-medium text-foreground">
                              <span>
                                {isEn
                                  ? `1-Year Windows (${sc.historical_outcomes['1y'].windows_count} obs.)`
                                  : `Fenêtres de 1 an (${sc.historical_outcomes['1y'].windows_count} obs.)`}
                              </span>
                              <span className="text-muted-foreground font-mono text-[10px]">
                                {isEn ? 'Loss: ' : 'Perte : '}
                                {(sc.historical_outcomes['1y'].loss_share * 100).toFixed(0)} %
                              </span>
                            </div>
                            <div className="grid grid-cols-3 gap-1 text-[10px] font-mono">
                              <div className="bg-rose-500/10 text-rose-700 dark:text-rose-300 p-1 rounded text-center">
                                <span className="block text-[9px] text-muted-foreground">{isEn ? 'Worst' : 'Pire'}</span>
                                {(sc.historical_outcomes['1y'].worst * 100).toFixed(1)} %
                              </div>
                              <div className="bg-blue-500/10 text-blue-700 dark:text-blue-300 p-1 rounded text-center">
                                <span className="block text-[9px] text-muted-foreground">{isEn ? 'Median' : 'Médiane'}</span>
                                {(sc.historical_outcomes['1y'].median * 100).toFixed(1)} %
                              </div>
                              <div className="bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 p-1 rounded text-center">
                                <span className="block text-[9px] text-muted-foreground">{isEn ? 'Best' : 'Meilleur'}</span>
                                +{(sc.historical_outcomes['1y'].best * 100).toFixed(1)} %
                              </div>
                            </div>
                          </div>
                        )}

                        {sc.historical_outcomes['3y'] && (
                          <div className="p-2 rounded-lg bg-muted/40 border border-border/50 text-[11px] space-y-1">
                            <div className="flex justify-between items-center font-medium text-foreground">
                              <span>
                                {isEn
                                  ? `3-Year Windows (${sc.historical_outcomes['3y'].windows_count} obs.)`
                                  : `Fenêtres de 3 ans (${sc.historical_outcomes['3y'].windows_count} obs.)`}
                              </span>
                              <span className="text-muted-foreground font-mono text-[10px]">
                                {isEn ? 'Loss: ' : 'Perte : '}
                                {(sc.historical_outcomes['3y'].loss_share * 100).toFixed(0)} %
                              </span>
                            </div>
                            <div className="grid grid-cols-3 gap-1 text-[10px] font-mono">
                              <div className="bg-rose-500/10 text-rose-700 dark:text-rose-300 p-1 rounded text-center">
                                <span className="block text-[9px] text-muted-foreground">{isEn ? 'Worst' : 'Pire'}</span>
                                {(sc.historical_outcomes['3y'].worst * 100).toFixed(1)} %
                              </div>
                              <div className="bg-blue-500/10 text-blue-700 dark:text-blue-300 p-1 rounded text-center">
                                <span className="block text-[9px] text-muted-foreground">{isEn ? 'Median' : 'Médiane'}</span>
                                {(sc.historical_outcomes['3y'].median * 100).toFixed(1)} %
                              </div>
                              <div className="bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 p-1 rounded text-center">
                                <span className="block text-[9px] text-muted-foreground">{isEn ? 'Best' : 'Meilleur'}</span>
                                +{(sc.historical_outcomes['3y'].best * 100).toFixed(1)} %
                              </div>
                            </div>
                          </div>
                        )}

                        {sc.historical_outcomes.horizon_covered === false && sc.historical_outcomes.horizon_years && (
                          <p className="text-[10px] text-amber-600 dark:text-amber-400 leading-tight pt-0.5">
                            {isEn
                              ? `* Declared horizon (${sc.historical_outcomes.horizon_years} years): not covered beyond 3 years by available 5-year history.`
                              : `* Horizon déclaré (${sc.historical_outcomes.horizon_years} ans) : non couvert au-delà de 3 ans par l'historique disponible (5 ans).`}
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
                        <li key={nIdx} className="leading-snug">{note}</li>
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
