import React, { useState } from 'react';
import { RunCost, TraceEntry } from '../types';
import { Activity, CheckCircle2, Clock, Cpu, Coins, ExternalLink } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface NodeTraceProps {
  trace: TraceEntry[];
  isRunning: boolean;
  cost?: RunCost;
}

export const NODE_LABELS: Record<string, string> = {
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

// Fallback only, when the server sent no cost block: Anthropic list prices (USD per 1M tokens,
// 2026-11-03) used as an estimate; the server converts with the Bank of Canada USD/CAD rate.
const USD_TO_CAD = 1.40;

function calculateEstimatedCad(trace: TraceEntry[]): number {
  let totalUsd = 0;
  for (const entry of trace) {
    if (!entry.model && !entry.input_tokens) continue;
    const model = (entry.model || '').toLowerCase();
    const inTok = entry.input_tokens || 0;
    const outTok = entry.output_tokens || 0;

    let inRate = 2.0; // Sonnet 5.5
    let outRate = 10.0;
    if (model.includes('opus')) {
      inRate = 4.0;
      outRate = 20.0;
    } else if (model.includes('haiku')) {
      inRate = 0.1;
      outRate = 0.5;
    }
    totalUsd += (inTok * inRate + outTok * outRate) / 1_000_000.0;
  }
  return totalUsd * USD_TO_CAD;
}

export const NodeTrace: React.FC<NodeTraceProps> = ({ trace, isRunning, cost }) => {
  const [showAdvanced, setShowAdvanced] = useState(false);

  if (trace.length === 0 && !isRunning) {
    return null;
  }

  const llmEntries = trace.filter(
    (e) => Boolean(e.model) || (e.input_tokens !== undefined && e.input_tokens > 0) || (e.calls !== undefined && e.calls > 0)
  );

  const totalInputTokens = cost?.input_tokens ?? trace.reduce((sum, e) => sum + (e.input_tokens || 0), 0);
  const totalOutputTokens = cost?.output_tokens ?? trace.reduce((sum, e) => sum + (e.output_tokens || 0), 0);
  const totalTokens = cost?.total_tokens ?? (totalInputTokens + totalOutputTokens);
  const totalLatencyMs = cost?.total_latency_ms ?? trace.reduce((sum, e) => sum + (e.latency_ms || 0), 0);
  const totalCalls = cost?.calls ?? trace.reduce((sum, e) => sum + (e.calls || (e.model ? 1 : 0)), 0);
  const totalCostCad = cost?.cost_cad ?? calculateEstimatedCad(trace);

  return (
    <Card className="bg-card border-border shadow-sm mb-6">
      <CardContent className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3.5">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            <h2 className="text-sm sm:text-base font-semibold text-foreground">
              Traçabilité & Exécution des Agents
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className={cn(
                "text-xs px-2.5 py-1 rounded-md border transition-all flex items-center gap-1.5 font-medium",
                showAdvanced
                  ? "bg-primary text-primary-foreground border-primary shadow-xs"
                  : "bg-muted/60 text-muted-foreground hover:text-foreground border-border hover:bg-muted"
              )}
              title="Afficher la télémétrie LLM, jetons et coût estimé par exécution"
            >
              <Cpu className="w-3.5 h-3.5" />
              <span>{showAdvanced ? "Masquer panneau avancé" : "Panneau avancé (LLM & Coûts)"}</span>
            </button>
            {isRunning && (
              <Badge variant="secondary" className="gap-1.5 animate-pulse text-[11px] py-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-600 dark:bg-blue-400" />
                Exécution en direct
              </Badge>
            )}
          </div>
        </div>

        {/* Standard Client-Facing Node Trace */}
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

        {/* Advanced Trace Panel (Telemetric LLM Node Details & Estimated Cost) */}
        {showAdvanced && (
          <div className="mt-4 pt-4 border-t border-border/80 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <Coins className="w-4 h-4 text-amber-500" />
                <span>Panneau avancé : Télémétrie LLM & Coûts par exécution</span>
              </div>
              <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground">
                Usage interne / Audit
              </Badge>
            </div>

            {/* Per-LLM Node Breakdown: One line per LLM node */}
            <div className="space-y-1.5">
              <div className="text-[11px] font-medium text-muted-foreground px-1">
                Lignes d&apos;exécution par nœud LLM :
              </div>
              {llmEntries.length === 0 ? (
                <div className="p-2.5 rounded-md bg-muted/30 border border-border/50 text-xs text-muted-foreground italic">
                  Aucun appel direct à un modèle de fondation enregistré (mode déterministe ou hors-ligne).
                </div>
              ) : (
                llmEntries.map((entry, idx) => {
                  const nodeTokens = (entry.input_tokens || 0) + (entry.output_tokens || 0);
                  const nodeLat = entry.latency_ms || 0;
                  const nodeModel = entry.model || 'modèle standard';
                  const callsCount = entry.calls || 1;

                  return (
                    <div
                      key={`llm-${entry.node}-${idx}`}
                      className="flex flex-wrap items-center justify-between gap-2 p-2 rounded-md bg-muted/30 border border-border/60 text-xs"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-semibold text-foreground">
                          {NODE_LABELS[entry.node] || entry.node}
                        </span>
                        <span className="text-[11px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">
                          {nodeModel}
                        </span>
                        {callsCount > 1 && (
                          <span className="text-[10px] text-muted-foreground">
                            ({callsCount} appels)
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs shrink-0 font-mono">
                        <span className="text-foreground">
                          {nodeTokens.toLocaleString('fr-CA')} tokens
                          <span className="text-muted-foreground text-[10px] ml-1">
                            ({entry.input_tokens || 0} in / {entry.output_tokens || 0} out)
                          </span>
                        </span>
                        <span className="text-muted-foreground">
                          {nodeLat} ms
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Run Total Summary */}
            <div className="p-3 rounded-lg bg-primary/5 border border-primary/20 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold text-foreground">
                  Total de l&apos;exécution :
                </span>
                <div className="flex flex-wrap items-center gap-4 text-xs">
                  <div>
                    <span className="text-muted-foreground">Appels LLM : </span>
                    <span className="font-semibold text-foreground font-mono">{totalCalls}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Tokens totaux : </span>
                    <span className="font-semibold text-foreground font-mono">
                      {totalTokens.toLocaleString('fr-CA')}
                    </span>
                    <span className="text-muted-foreground text-[10px] ml-1">
                      ({totalInputTokens.toLocaleString('fr-CA')} in / {totalOutputTokens.toLocaleString('fr-CA')} out)
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Latence cumulée : </span>
                    <span className="font-semibold text-foreground font-mono">
                      {totalLatencyMs >= 1000 ? `${(totalLatencyMs / 1000).toFixed(2)} s` : `${totalLatencyMs} ms`}
                    </span>
                  </div>
                  <div className="px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-900 dark:text-amber-300 font-semibold">
                    Coût estimé : {totalCostCad.toFixed(4)} $ CAD
                  </div>
                </div>
              </div>

              {/* Assumption & Source URL Citation (PRD 2, O-6) */}
              <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 pt-1 border-t border-border/40">
                <span>
                  Estimation (hypothèse) : tarifs publics d'Anthropic au 2026-11-03, utilisés comme ordre de grandeur ; Amazon Bedrock facture ses propres tarifs. Conversion au dernier taux USD/CAD de la Banque du Canada.
                </span>
                <a
                  href="https://platform.claude.com/docs/en/about-claude/pricing"
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary hover:underline inline-flex items-center gap-0.5"
                >
                  Tarifs publics <ExternalLink className="w-2.5 h-2.5" />
                </a>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
