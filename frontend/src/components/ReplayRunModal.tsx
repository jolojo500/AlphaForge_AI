import React, { useState, useEffect } from 'react';
import { SavedRunSummary } from '../types';
import { fetchSavedRuns } from '../api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  RotateCcw,
  Sparkles,
  CheckCircle2,
  Calendar,
  Loader2,
  AlertCircle,
  FolderOpen,
} from 'lucide-react';

interface ReplayRunModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectRun: (runId: string) => Promise<void> | void;
}

const PERSONA_LABELS: Record<string, { label: string; color: string }> = {
  robert: {
    label: 'Robert · Idée TSLA',
    color: 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/30',
  },
  amira: {
    label: 'Amira · Construction prudente',
    color: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
  },
  mateo: {
    label: 'Mateo · Croissance tech',
    color: 'bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-500/30',
  },
};

export const ReplayRunModal: React.FC<ReplayRunModalProps> = ({
  isOpen,
  onClose,
  onSelectRun,
}) => {
  const [runs, setRuns] = useState<SavedRunSummary[]>([]);
  const [selectedPersona, setSelectedPersona] = useState<string>('all');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [replayingRunId, setReplayingRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    const personaParam = selectedPersona === 'all' ? undefined : selectedPersona;
    fetchSavedRuns(personaParam)
      .then((data) => {
        if (!cancelled) {
          setRuns(data);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, selectedPersona]);

  const handleSelect = async (runId: string) => {
    setReplayingRunId(runId);
    try {
      await onSelectRun(runId);
    } finally {
      setReplayingRunId(null);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col p-6 overflow-hidden">
        <DialogHeader className="shrink-0 pb-2">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <RotateCcw className="w-4 h-4" />
            </div>
            <div>
              <DialogTitle className="text-base sm:text-lg font-semibold">
                Rejouer une analyse
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                Restaurez instantanément les scénarios, explications, preuves et traces sans solliciter le LLM (mode secours démo & audit).
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Persona Filter Tabs */}
        <div className="flex flex-wrap gap-1.5 pt-2 pb-1 border-b border-border/50 shrink-0">
          {[
            { id: 'all', label: 'Toutes les analyses' },
            { id: 'robert', label: 'Robert (TSLA)' },
            { id: 'amira', label: 'Amira (Prudence)' },
            { id: 'mateo', label: 'Mateo (Tech)' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setSelectedPersona(tab.id)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                selectedPersona === tab.id
                  ? 'bg-primary text-primary-foreground shadow-xs'
                  : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Runs List (Scrollable) */}
        <div className="flex-1 overflow-y-auto py-3 space-y-3 pr-1">
          {isLoading && (
            <div className="py-12 flex flex-col items-center justify-center gap-2.5 text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
              <p className="text-xs">Chargement des analyses archivées...</p>
            </div>
          )}

          {error && (
            <div className="p-3 bg-destructive/10 border border-destructive/30 rounded-lg text-xs text-destructive flex items-center gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {!isLoading && !error && runs.length === 0 && (
            <div className="py-12 flex flex-col items-center justify-center gap-2 text-muted-foreground text-center">
              <FolderOpen className="w-8 h-8 opacity-40" />
              <p className="text-xs font-medium">Aucune analyse trouvée pour ce filtre</p>
              <p className="text-[11px] text-muted-foreground/70">
                Essayez un autre profil ou lancez une nouvelle analyse.
              </p>
            </div>
          )}

          {!isLoading &&
            runs.map((run) => {
              const personaInfo = PERSONA_LABELS[run.persona] || {
                label: run.persona,
                color: 'bg-muted text-foreground border-border',
              };
              const isCurrentReplaying = replayingRunId === run.run_id;

              return (
                <div
                  key={run.run_id}
                  className="p-4 rounded-xl border border-border/80 bg-card hover:border-primary/40 hover:shadow-xs transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                >
                  <div className="space-y-2 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge
                        variant="outline"
                        className={`text-[11px] font-medium border ${personaInfo.color}`}
                      >
                        {personaInfo.label}
                      </Badge>

                      {run.is_golden && (
                        <Badge
                          variant="outline"
                          className="bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30 text-[11px] font-medium flex items-center gap-1"
                        >
                          <Sparkles className="w-3 h-3" />
                          <span>Référence officielle</span>
                        </Badge>
                      )}

                      {run.verification_passed && (
                        <Badge
                          variant="outline"
                          className="bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30 text-[11px] font-medium flex items-center gap-1"
                        >
                          <CheckCircle2 className="w-3 h-3" />
                          <span>Vérifié déterministe</span>
                        </Badge>
                      )}

                      {run.as_of_date && (
                        <span className="text-[11px] text-muted-foreground flex items-center gap-1 ml-auto sm:ml-0 font-mono">
                          <Calendar className="w-3 h-3" />
                          <span>{run.as_of_date}</span>
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-foreground/90 leading-relaxed font-normal">
                      « {run.request_text || "Aucune requête textuelle spécifiée"} »
                    </p>

                    <div className="text-[10px] text-muted-foreground/70 font-mono truncate">
                      ID : {run.run_id}
                    </div>
                  </div>

                  <div className="shrink-0 flex sm:flex-col justify-end">
                    <Button
                      size="sm"
                      onClick={() => handleSelect(run.run_id)}
                      disabled={isCurrentReplaying}
                      className="gap-1.5 text-xs font-medium cursor-pointer shadow-xs min-w-[100px]"
                    >
                      {isCurrentReplaying ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Chargement...</span>
                        </>
                      ) : (
                        <>
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>Rejouer</span>
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              );
            })}
        </div>

        {/* Footer info note */}
        <div className="shrink-0 pt-3 border-t border-border/50 flex flex-col sm:flex-row items-center justify-between gap-3 text-[11px] text-muted-foreground">
          <p className="text-muted-foreground/80">
            Les simulations What-If restent actives sur une analyse rejouée (reprise déterministe).
          </p>
          <Button variant="outline" size="sm" onClick={onClose} className="text-xs h-8">
            Fermer
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
