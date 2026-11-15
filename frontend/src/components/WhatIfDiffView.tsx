import React from 'react';
import { WhatIfDiff, ScenarioName } from '../types';
import { GitCompare, ArrowRight, ArrowUpRight, ArrowDownRight, Minus, X } from 'lucide-react';

interface WhatIfDiffViewProps {
  diff: WhatIfDiff | null;
  onClose: () => void;
}

const SCENARIO_LABELS: Record<ScenarioName, string> = {
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
    <section className="bg-indigo-50/40 border-2 border-indigo-200 rounded-xl p-6 mb-6 shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between pb-3 mb-4 border-b border-indigo-100">
        <div className="flex items-center gap-2">
          <GitCompare className="w-5 h-5 text-indigo-700" />
          <div>
            <h2 className="text-base font-bold text-indigo-950">
              Comparaison Avant / Après (Simulation What-If)
            </h2>
            {/* Exactly which hypothesis changed line */}
            <p className="text-xs font-semibold text-indigo-800 flex items-center gap-1.5 mt-0.5">
              <span>Hypothèse modifiée :</span>
              <span className="bg-white px-2 py-0.5 rounded border border-indigo-200 text-indigo-900 font-mono">
                {formatChangeField(diff.change?.field, diff.change?.value)}
              </span>
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="text-indigo-400 hover:text-indigo-700 p-1 rounded-lg transition-colors cursor-pointer"
          aria-label="Fermer la vue comparative"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Summary bullet points */}
      {diff.summary && diff.summary.length > 0 && (
        <div className="bg-white/80 p-3.5 rounded-lg border border-indigo-100 mb-5">
          <span className="text-xs font-bold uppercase tracking-wider text-indigo-900 block mb-1">
            Impacts observés sur les allocations :
          </span>
          <ul className="text-xs text-indigo-950 space-y-1 list-disc list-inside">
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
            <div key={name} className="bg-white rounded-lg p-4 border border-indigo-100 shadow-2xs">
              <h3 className="text-sm font-bold text-slate-900 mb-3 pb-1 border-b border-slate-100 flex items-center justify-between">
                <span>{SCENARIO_LABELS[name] || name}</span>
              </h3>

              {/* Weights deltas */}
              <div className="mb-4">
                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">
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
                          isTSLA ? 'bg-amber-50 font-medium' : ''
                        }`}
                      >
                        <span className="font-mono text-slate-800">{ticker}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-slate-500 text-[11px]">
                            {(delta.old * 100).toFixed(1)}%
                          </span>
                          <ArrowRight className="w-3 h-3 text-slate-300" />
                          <span className="font-semibold text-slate-900 text-[11px]">
                            {(delta.new * 100).toFixed(1)}%
                          </span>
                          <span
                            className={`inline-flex items-center text-[10px] font-bold px-1 py-0.5 rounded ${
                              isIncrease
                                ? 'bg-emerald-100 text-emerald-800'
                                : isDecrease
                                ? 'bg-red-100 text-red-800'
                                : 'bg-slate-100 text-slate-600'
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
                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">
                  Écarts des indicateurs
                </span>
                <div className="space-y-1 text-xs">
                  {Object.entries(scDiff.metrics).map(([mKey, delta]) => {
                    if (delta.old === null && delta.new === null) return null;
                    const oldStr = delta.old !== null ? `${(delta.old * 100).toFixed(1)}%` : '—';
                    const newStr = delta.new !== null ? `${(delta.new * 100).toFixed(1)}%` : '—';

                    return (
                      <div key={mKey} className="flex justify-between items-center py-0.5 text-slate-700">
                        <span className="text-[11px] truncate" title={METRIC_LABELS[mKey] || mKey}>
                          {METRIC_LABELS[mKey] || mKey}
                        </span>
                        <div className="flex items-center gap-1.5 text-[11px] shrink-0 font-mono">
                          <span>{oldStr}</span>
                          <span className="text-slate-300">→</span>
                          <span className="font-bold text-slate-900">{newStr}</span>
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
