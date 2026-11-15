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
  History,
  Sparkles,
  CheckCircle2,
  Calendar,
  Loader2,
  AlertCircle,
  FolderOpen,
  ArrowRight,
} from 'lucide-react';
import { useLanguage } from '@/context/LanguageContext';

interface ReplayRunModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectRun: (runId: string) => Promise<void> | void;
  activePersonaId?: 'custom' | 'robert' | 'amira' | 'mateo';
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
  custom: {
    label: 'Mon profil',
    color: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
  },
  custom_user: {
    label: 'Mon profil',
    color: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
  },
};

export const ReplayRunModal: React.FC<ReplayRunModalProps> = ({
  isOpen,
  onClose,
  onSelectRun,
  activePersonaId = 'custom',
}) => {
  const { language } = useLanguage();
  const isEn = language === 'en';

  const [runs, setRuns] = useState<SavedRunSummary[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [replayingRunId, setReplayingRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    const personaParam = activePersonaId === 'custom' ? 'custom_user' : activePersonaId;
    fetchSavedRuns(personaParam)
      .then((data) => {
        if (!cancelled) {
          // If custom user, show runs matching custom or custom_user or created by user
          const filtered =
            activePersonaId === 'custom'
              ? data.filter(
                  (r) =>
                    r.persona === 'custom' ||
                    r.persona === 'custom_user' ||
                    !['robert', 'amira', 'mateo'].includes(r.persona)
                )
              : data.filter((r) => r.persona === activePersonaId);
          setRuns(filtered.length > 0 ? filtered : data.filter((r) => !['robert', 'amira', 'mateo'].includes(r.persona) || r.persona === personaParam));
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
  }, [isOpen, activePersonaId]);

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
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <History className="w-4 h-4" />
            </div>
            <div>
              <DialogTitle className="text-base sm:text-lg font-semibold">
                {isEn ? 'Simulation History' : 'Historique des simulations'}
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                {isEn
                  ? 'Consult the results and trace of past simulations without re-running calculations.'
                  : 'Consultez les résultats et preuves d’analyses précédentes sans relancer de calcul.'}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Runs List (Scrollable) */}
        <div className="flex-1 overflow-y-auto py-3 space-y-2.5 pr-1">
          {isLoading && (
            <div className="py-12 flex flex-col items-center justify-center gap-2.5 text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
              <p className="text-xs">{isEn ? 'Loading history...' : 'Chargement des analyses archivées...'}</p>
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
              <p className="text-xs font-medium">
                {isEn ? 'No simulations found for this filter' : 'Aucune analyse trouvée pour ce filtre'}
              </p>
              <p className="text-[11px] text-muted-foreground/70">
                {isEn ? 'Try another filter or submit a question.' : 'Essayez un autre profil ou posez une question.'}
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
                  className="p-3.5 rounded-xl border border-border/80 bg-card hover:border-primary/40 hover:shadow-xs transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge
                        variant="outline"
                        className={`text-[10px] font-medium border ${personaInfo.color}`}
                      >
                        {personaInfo.label}
                      </Badge>

                      {run.is_golden && (
                        <Badge
                          variant="outline"
                          className="bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30 text-[10px] font-medium flex items-center gap-1"
                        >
                          <Sparkles className="w-3 h-3" />
                          <span>{isEn ? 'Official Reference' : 'Référence officielle'}</span>
                        </Badge>
                      )}

                      {run.verification_passed && (
                        <Badge
                          variant="outline"
                          className="bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30 text-[10px] font-medium flex items-center gap-1"
                        >
                          <CheckCircle2 className="w-3 h-3" />
                          <span>{isEn ? 'Deterministic Verified' : 'Vérifié déterministe'}</span>
                        </Badge>
                      )}

                      {run.as_of_date && (
                        <span className="text-[10px] text-muted-foreground flex items-center gap-1 ml-auto sm:ml-0 font-mono">
                          <Calendar className="w-3 h-3" />
                          <span>{run.as_of_date}</span>
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-foreground leading-snug line-clamp-2">
                      « {run.request_text || (isEn ? 'No request text specified' : 'Aucune requête textuelle spécifiée')} »
                    </p>

                    <div className="text-[10px] text-muted-foreground/60 font-mono truncate">
                      ID : {run.run_id}
                    </div>
                  </div>

                  <div className="shrink-0 flex justify-end">
                    <Button
                      size="sm"
                      onClick={() => handleSelect(run.run_id)}
                      disabled={isCurrentReplaying}
                      className="gap-1.5 text-xs font-medium cursor-pointer h-8 px-3"
                    >
                      {isCurrentReplaying ? (
                        <>
                          <Loader2 className="w-3 h-3 animate-spin" />
                          <span>{isEn ? 'Loading...' : 'Chargement...'}</span>
                        </>
                      ) : (
                        <>
                          <span>{isEn ? 'View Analysis' : 'Consulter'}</span>
                          <ArrowRight className="w-3 h-3" />
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              );
            })}
        </div>

        {/* Footer info note */}
        <div className="shrink-0 pt-3 border-t border-border/50 text-[11px] text-muted-foreground">
          <p className="text-muted-foreground/70 text-center sm:text-left">
            {isEn
              ? 'Past simulations load verified state and scenarios instantly.'
              : 'Les simulations archivées restituent instantanément les scénarios et preuves vérifiées.'}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
};
