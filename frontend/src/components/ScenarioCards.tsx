import React from 'react';
import { Scenario, Evidence } from '../types';
import { BarChart3, Star } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface ScenarioCardsProps {
  scenarios: Scenario[];
  evidence: Record<string, Evidence>;
  mostConsistentName?: string;
}

const SCENARIO_TITLES: Record<string, { title: string; subtitle: string }> = {
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

const METRIC_LABELS: Record<string, string> = {
  volatility_ann: 'Volatilité annuelle',
  max_drawdown: 'Perte historique max',
  stress_2022: 'Stress test 2022',
  top_weight: 'Poids principal',
  sector_concentration_hhi: 'Concentration (HHI)',
  us_exposure: 'Exposition US',
  tax_drag: 'Friction fiscale estimée',
};

function formatMetricValue(ev: Evidence | undefined): string {
  if (!ev) return '—';
  let val = ev.value;
  if (typeof val === 'object' && val !== null && 'value' in val) {
    val = (val as { value: unknown }).value as number | string;
  }
  if (typeof val === 'number') {
    return `${(val * 100).toFixed(1)} %`;
  }
  return String(val);
}

export const ScenarioCards: React.FC<ScenarioCardsProps> = ({
  scenarios,
  evidence,
  mostConsistentName,
}) => {
  if (!scenarios || scenarios.length === 0) return null;

  return (
    <Card className="bg-card border-border shadow-sm mb-6">
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-primary" />
            <h2 className="text-sm sm:text-base font-semibold text-foreground">
              3. Comparaison des scénarios simulés ({scenarios.length})
            </h2>
          </div>
        </div>

        <div className={`grid grid-cols-1 ${scenarios.length >= 4 ? 'md:grid-cols-2 lg:grid-cols-4' : 'lg:grid-cols-3'} gap-4`}>
          {scenarios.map((sc) => {
            const isMostConsistent = sc.name === mostConsistentName;
            const info = SCENARIO_TITLES[sc.name] || {
              title: sc.name,
              subtitle: 'Simulation de portefeuille',
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
                        Plus cohérent
                      </Badge>
                    )}
                    {sc.name === 'current' && (
                      <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300 bg-sky-500/10 text-[11px] py-0.5">
                        Point de départ
                      </Badge>
                    )}
                  </div>

                  {/* Weights breakdown */}
                  <div className="mt-4 mb-5">
                    <h4 className="text-xs font-semibold text-foreground/80 uppercase tracking-wider mb-2">
                      Répartition des actifs ({sortedWeights.length})
                    </h4>
                    <div className="space-y-1.5">
                      {sortedWeights.map(([ticker, weight]) => {
                        const pct = (weight * 100).toFixed(1);
                        const isHighlightedTicker = ticker === 'TSLA' || ticker === 'NVDA';
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
                                    (actif évalué)
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
                      Indicateurs clés de risque
                    </h4>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {Object.entries(sc.metrics).map(([metricKey, eid]) => {
                        const ev = evidence[eid];
                        const formatted = formatMetricValue(ev);
                        return (
                          <div key={metricKey} className="bg-muted/50 p-2.5 rounded-lg border border-border/60">
                            <span className="text-[11px] text-muted-foreground block truncate" title={METRIC_LABELS[metricKey] || metricKey}>
                              {METRIC_LABELS[metricKey] || metricKey}
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
                          Rotation requise (Turnover)
                        </span>
                        <Badge variant="secondary" className="font-mono text-xs font-semibold">
                          {(sc.turnover * 100).toFixed(1)} %
                        </Badge>
                      </div>
                      {sc.trades && sc.trades.length > 0 && (
                        <div className="space-y-1 mt-2">
                          <p className="text-[11px] text-muted-foreground font-medium mb-1">
                            Ordres d'arbitrage ({sc.trades.length}) :
                          </p>
                          <div className="max-h-32 overflow-y-auto space-y-1 pr-0.5">
                            {sc.trades.map((tr) => {
                              const isBuy = tr.change > 0;
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
                                      {isBuy ? 'ACHAT' : 'VENTE'}
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
                                        {tr.amount_cad.toLocaleString('fr-CA', { maximumFractionDigits: 0 })} $)
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
