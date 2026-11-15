import React from 'react';
import { WhatIfDiff, ScenarioName } from '../types';
import { GitCompare, ArrowRight, ArrowUpRight, ArrowDownRight, Minus, X } from 'lucide-react';

interface WhatIfDiffViewProps {
  diff: WhatIfDiff | null;
  onClose: () => void;
}

const SCENARIO_LABELS: Record<ScenarioName, string> = {
  current: 'Portefeuille actuel',
  as_requested: 'Scénario demandé',
  capped: 'Scénario plafonné',
  profile_baseline: 'Scénario de référence',
};

const METRIC_LABELS: Record<string, string> = {
  volatility_ann: 'Volatilité annuelle',
  max_drawdown: 'Perte max historique',
  stress_2022: 'Stress test 2022',
  top_weight: 'Poids principal',
  sector_concentration_hhi: 'Concentration (HHI)',
  us_exposure: 'Exposition US',
  fee_drag: 'Frais de gestion (RFG)',
};

function formatChangeField(field?: string, value?: unknown): string {
  if (!field) return 'Hypothèse personnalisée';
  switch (field) {
    case 'risk_tolerance':
      return `Tolérance au risque modifiée → ${value}`;
    case 'horizon_years':
      return `Horizon d'investissement modifié → ${value} ans`;
    case 'budget_cad':
      return `Budget modifié → ${value} $ CAD`;
    case 'exclude_ticker':
      return `Actif exclu de l'univers éligible → ${value}`;
    case 'as_of_date':
      return `Date d'analyse modifiée → ${value}`;
    default:
      return `${field} → ${value}`;
  }
}

export const WhatIfDiffView: React.FC<WhatIfDiffViewProps> = ({ diff, onClose }) => {
  if (!diff) return null;

  return (
    <section className="bg-card border-2 border-primary/40 rounded-xl p-5 sm:p-6 mb-6 shadow-xs">
      {/* Header */}
      <div className="flex items-start justify-between pb-3 mb-4 border-b border-border/70">
        <div className="flex items-center gap-2">
          <GitCompare className="w-5 h-5 text-primary" />
          <div>
            <h2 className="text-sm sm:text-base font-bold text-foreground">
              Comparaison Avant / Après (Simulation What-If)
            </h2>
            {/* Exactly which hypothesis changed line */}
            <p className="text-xs font-semibold text-primary flex items-center gap-1.5 mt-0.5">
              <span>Hypothèse modifiée :</span>
              <span className="bg-muted px-2 py-0.5 rounded border border-border text-foreground font-mono">
                {formatChangeField(diff.change?.field, diff.change?.value)}
              </span>
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground p-1 rounded-md transition-colors cursor-pointer"
          aria-label="Fermer la vue comparative"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Summary bullet points */}
      {diff.summary && diff.summary.length > 0 && (
        <div className="bg-muted/40 p-3.5 rounded-lg border border-border mb-5">
          <span className="text-xs font-bold uppercase tracking-wider text-foreground block mb-1">
            Impacts observés sur les allocations :
          </span>
          <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
            {diff.summary.map((line, idx) => (
              <li key={idx} className="font-medium">{line}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Side by side scenario comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {(Object.keys(diff.scenarios) as ScenarioName[]).map((name) => {
          const scDiff = diff.scenarios[name];
          if (!scDiff) return null;

          const weightEntries = Object.entries(scDiff.weights).filter(
            ([_, delta]) => delta.old > 0 || delta.new > 0 || delta.delta !== 0
          );

          return (
            <div key={name} className="bg-card rounded-lg p-4 border border-border shadow-2xs">
              <h3 className="text-sm font-bold text-foreground mb-3 pb-1 border-b border-border/60 flex items-center justify-between">
                <span>{SCENARIO_LABELS[name] || name}</span>
              </h3>

              {/* Weights deltas */}
              <div className="mb-4">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                  Écarts d&apos;allocation
                </span>
                <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                  {weightEntries.map(([ticker, delta]) => {
                    const isIncrease = delta.delta > 0.0001;
                    const isDecrease = delta.delta < -0.0001;
                    const isTSLA = ticker === 'TSLA';

                    return (
                      <div
                        key={ticker}
                        className={`text-xs p-1 rounded flex items-center justify-between ${
                          isTSLA ? 'bg-amber-500/10 font-medium' : ''
                        }`}
                      >
                        <span className="font-mono text-foreground">{ticker}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground text-[11px]">
                            {(delta.old * 100).toFixed(1)}%
                          </span>
                          <ArrowRight className="w-3 h-3 text-muted-foreground/40" />
                          <span className="font-semibold text-foreground text-[11px]">
                            {(delta.new * 100).toFixed(1)}%
                          </span>
                          <span
                            className={`inline-flex items-center text-[10px] font-bold px-1 py-0.5 rounded ${
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
                            {isIncrease ? '+' : ''}
                            {(delta.delta * 100).toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Metrics deltas */}
              <div>
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                  Écarts des indicateurs
                </span>
                <div className="space-y-1 text-xs">
                  {Object.entries(scDiff.metrics).map(([mKey, delta]) => {
                    if (delta.old === null && delta.new === null) return null;
                    const oldStr = delta.old !== null ? `${(delta.old * 100).toFixed(1)}%` : '—';
                    const newStr = delta.new !== null ? `${(delta.new * 100).toFixed(1)}%` : '—';

                    return (
                      <div key={mKey} className="flex justify-between items-center py-0.5 text-foreground">
                        <span className="text-[11px] truncate text-muted-foreground" title={METRIC_LABELS[mKey] || mKey}>
                          {METRIC_LABELS[mKey] || mKey}
                        </span>
                        <div className="flex items-center gap-1.5 text-[11px] shrink-0 font-mono">
                          <span className="text-muted-foreground">{oldStr}</span>
                          <span className="text-muted-foreground/40">→</span>
                          <span className="font-bold text-foreground">{newStr}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};
