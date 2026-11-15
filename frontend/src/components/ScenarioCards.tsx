import React from 'react';
import { Evidence, Scenario, ScenarioName } from '../types';
import { BarChart3, Star } from 'lucide-react';

interface ScenarioCardsProps {
  scenarios: Scenario[];
  evidence: Record<string, Evidence>;
  mostConsistentName?: ScenarioName;
}

const SCENARIO_TITLES: Record<ScenarioName, { title: string; subtitle: string }> = {
  as_requested: {
    title: 'Scénario demandé',
    subtitle: "L'idée telle qu'exprimée par l'investisseur",
  },
  capped: {
    title: 'Scénario plafonné',
    subtitle: "L'idée ajustée selon les plafonds de risque du profil",
  },
  profile_baseline: {
    title: 'Scénario de référence',
    subtitle: 'Allocation prudente et diversifiée sous contraintes',
  },
};

const METRIC_LABELS: Record<string, string> = {
  volatility_ann: 'Volatilité annuelle',
  max_drawdown: 'Perte max historique (DD)',
  stress_2022: 'Stress test (choc 2022)',
  top_weight: 'Poids actif principal',
  sector_concentration_hhi: 'Indice concentration (HHI)',
  us_exposure: 'Exposition géographique US',
};

function formatMetricValue(ev?: Evidence): string {
  if (!ev) return '—';
  let val: unknown = ev.value;
  if (typeof val === 'object' && val !== null && 'value' in val) {
    val = (val as { value: unknown }).value;
  }
  if (typeof val === 'number') {
    // If ratio under 1, format as percent
    if (Math.abs(val) <= 1.0) {
      return `${(val * 100).toFixed(1)} %`;
    }
    return val.toFixed(2);
  }
  return String(val ?? '—');
}

export const ScenarioCards: React.FC<ScenarioCardsProps> = ({
  scenarios,
  evidence,
  mostConsistentName,
}) => {
  if (!scenarios || scenarios.length === 0) return null;

  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-blue-600" />
          <h2 className="text-lg font-semibold text-slate-800">
            3. Comparaison des trois scénarios simulés
          </h2>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {scenarios.map((sc) => {
          const isMostConsistent = sc.name === mostConsistentName;
          const info = SCENARIO_TITLES[sc.name] || {
            title: sc.name,
            subtitle: 'Simulation de portefeuille',
          };

          // Sort allocations descending
          const sortedWeights = Object.entries(sc.weights).sort((a, b) => b[1] - a[1]);

          return (
            <div
              key={sc.name}
              className={`rounded-xl border p-5 flex flex-col justify-between transition-all relative ${
                isMostConsistent
                  ? 'border-emerald-500 bg-emerald-50/20 ring-2 ring-emerald-500/20 shadow-md'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              <div>
                {/* Header with consistency badge */}
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div>
                    <h3 className="text-base font-bold text-slate-900">{info.title}</h3>
                    <p className="text-xs text-slate-500">{info.subtitle}</p>
                  </div>
                  {isMostConsistent && (
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-800 bg-emerald-100 px-2.5 py-0.5 rounded-full border border-emerald-300 shadow-xs">
                      <Star className="w-3 h-3 fill-emerald-600 text-emerald-600" />
                      Plus cohérent
                    </span>
                  )}
                </div>

                {/* Weights breakdown */}
                <div className="mt-4 mb-5">
                  <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                    Répartition des actifs ({sortedWeights.length})
                  </h4>
                  <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                    {sortedWeights.map(([ticker, weight]) => {
                      const pct = (weight * 100).toFixed(1);
                      return (
                        <div key={ticker} className="text-xs">
                          <div className="flex justify-between items-center text-slate-700 mb-0.5">
                            <span className="font-medium font-mono">{ticker}</span>
                            <span>{pct} %</span>
                          </div>
                          <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                isMostConsistent ? 'bg-emerald-600' : 'bg-blue-600'
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
                <div className="border-t border-slate-100 pt-4 mb-4">
                  <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                    Indicateurs clés de risque
                  </h4>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {Object.entries(sc.metrics).map(([metricKey, eid]) => {
                      const ev = evidence[eid];
                      const formatted = formatMetricValue(ev);
                      return (
                        <div key={metricKey} className="bg-slate-50 p-2 rounded border border-slate-100">
                          <span className="text-[11px] text-slate-500 block truncate" title={METRIC_LABELS[metricKey] || metricKey}>
                            {METRIC_LABELS[metricKey] || metricKey}
                          </span>
                          <span className="font-semibold text-slate-900 block mt-0.5">
                            {formatted}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Notes */}
              {sc.notes && sc.notes.length > 0 && (
                <div className="border-t border-slate-100 pt-3 text-xs text-slate-600">
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
    </section>
  );
};
