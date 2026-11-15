import React from 'react';
import { TraceEntry } from '../types';
import { Activity, CheckCircle2, Clock } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

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
    <Card className="bg-card border-border shadow-sm mb-6">
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-3.5">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            <h2 className="text-sm sm:text-base font-semibold text-foreground">
              Traçabilité & Exécution des Agents
            </h2>
          </div>
          {isRunning && (
            <Badge variant="secondary" className="gap-1.5 animate-pulse text-[11px] py-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-600 dark:bg-blue-400" />
              Exécution en direct
            </Badge>
          )}
        </div>

        <div className="space-y-2">
          {trace.map((entry, idx) => {
            const start = new Date(entry.started_at).getTime();
            const end = new Date(entry.ended_at).getTime();
            const durationMs = Math.max(0, end - start);
            const durationStr = durationMs >= 1000 ? `${(durationMs / 1000).toFixed(2)}s` : `${durationMs}ms`;

            return (
              <div
                key={`${entry.node}-${idx}`}
                className="flex items-start gap-2.5 p-2.5 rounded-lg bg-muted/40 border border-border/70 text-xs hover:bg-muted/70 transition-colors"
              >
                <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-foreground text-xs uppercase tracking-wider">
                      {NODE_LABELS[entry.node] || entry.node}
                    </span>
                    <span className="text-xs text-muted-foreground flex items-center gap-1 shrink-0">
                      <Clock className="w-3 h-3" />
                      {durationStr}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{entry.summary}</p>
                </div>
              </div>
            );
          })}

          {isRunning && (
            <div className="flex items-center gap-3 p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-sm animate-pulse">
              <div className="w-4 h-4 border-2 border-blue-600/30 border-t-blue-600 rounded-full animate-spin shrink-0" />
              <span className="text-xs font-medium text-blue-800 dark:text-blue-300">
                Traitement du nœud en cours...
              </span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};
