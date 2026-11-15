import React from 'react';
import { TraceEntry } from '../types';
import { Activity, CheckCircle2, Clock } from 'lucide-react';

interface NodeTraceProps {
  trace: TraceEntry[];
  isRunning: boolean;
}

const NODE_LABELS: Record<string, string> = {
  profile: 'Profil (Agent 1)',
  screening: 'Filtrage admissibilité',
  quant: 'Métriques quantitatives',
  macro: 'Contexte macroéconomique',
  events: 'Actualités & Événements (Agent 2)',
  scenarios: 'Génération des scénarios',
  red_team: 'Critique contradictoire (Agent 3)',
  explain: 'Explicabilité (Agent 4)',
  verifier: 'Vérificateur déterministe',
};

export const NodeTrace: React.FC<NodeTraceProps> = ({ trace, isRunning }) => {
  if (trace.length === 0 && !isRunning) {
    return null;
  }

  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-600" />
          <h2 className="text-lg font-semibold text-slate-800">2. Traçabilité & Exécution des Agents</h2>
        </div>
        {isRunning && (
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full border border-blue-200 animate-pulse">
            <span className="w-2 h-2 rounded-full bg-blue-600" />
            Exécution en direct
          </span>
        )}
      </div>

      <div className="space-y-2.5">
        {trace.map((entry, idx) => {
          const start = new Date(entry.started_at).getTime();
          const end = new Date(entry.ended_at).getTime();
          const durationMs = Math.max(0, end - start);
          const durationStr = durationMs >= 1000 ? `${(durationMs / 1000).toFixed(2)}s` : `${durationMs}ms`;

          return (
            <div
              key={`${entry.node}-${idx}`}
              className="flex items-start gap-3 p-3 rounded-lg bg-slate-50 border border-slate-100 text-sm hover:bg-slate-100/70 transition-colors"
            >
              <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-900 text-xs uppercase tracking-wider">
                    {NODE_LABELS[entry.node] || entry.node}
                  </span>
                  <span className="text-xs text-slate-400 flex items-center gap-1 shrink-0">
                    <Clock className="w-3 h-3" />
                    {durationStr}
                  </span>
                </div>
                <p className="text-xs text-slate-600 mt-0.5">{entry.summary}</p>
              </div>
            </div>
          );
        })}

        {isRunning && (
          <div className="flex items-center gap-3 p-3 rounded-lg bg-blue-50/50 border border-blue-100 text-sm animate-pulse">
            <div className="w-4 h-4 border-2 border-blue-600/30 border-t-blue-600 rounded-full animate-spin shrink-0" />
            <span className="text-xs font-medium text-blue-800">Traitement du nœud en cours...</span>
          </div>
        )}
      </div>
    </section>
  );
};
