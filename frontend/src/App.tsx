import React, { useState, useEffect, useRef } from 'react';
import {
  GraphState,
  UserOnboardingProfile,
  BackendRunPayload,
  TraceEntry,
  WhatIfDiff,
} from './types';
import {
  createRun,
  subscribeRunEvents,
  fetchRunState,
  answerRun,
  createWhatIf,
  fetchRunDiff,
  createMockAnalysisState,
} from './api';
import { ThemeProvider } from './components/ThemeProvider';
import { ThemeToggle } from './components/ThemeToggle';
import { WelcomeScreen } from './components/WelcomeScreen';
import { OnboardingFlow } from './components/onboarding/OnboardingFlow';
import { QueryScreen } from './components/QueryScreen';
import { ScenarioCards } from './components/ScenarioCards';
import { ExplanationSection } from './components/ExplanationSection';
import { ExclusionsCard } from './components/ExclusionsCard';
import { EvidenceTable } from './components/EvidenceTable';
import { EvidenceModal } from './components/EvidenceModal';
import { NodeTrace } from './components/NodeTrace';
import { ConflictsAlert } from './components/ConflictsAlert';
import { SimulationBanner } from './components/SimulationBanner';
import { ClarificationBox } from './components/ClarificationBox';
import { WhatIfControls } from './components/WhatIfControls';
import { WhatIfDiffView } from './components/WhatIfDiffView';
import {
  ArrowLeft,
  SlidersHorizontal,
  AlertCircle,
  RefreshCw,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { Logo } from './components/Logo';
import { Button } from './components/ui/button';
import { Badge } from './components/ui/badge';

const STORAGE_KEY = 'alphaforge_user_profile';

type AppView = 'welcome' | 'onboarding' | 'query' | 'analysis_results';

export const AppContent: React.FC = () => {
  const [view, setView] = useState<AppView>('welcome');
  const [userProfile, setUserProfile] = useState<UserOnboardingProfile | null>(null);
  const [runState, setRunState] = useState<GraphState | null>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [lastPayload, setLastPayload] = useState<BackendRunPayload | null>(null);

  // Live Backend execution state
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [activeTrace, setActiveTrace] = useState<TraceEntry[]>([]);
  const [clarificationQuestion, setClarificationQuestion] = useState<string | null>(null);
  const [isSubmittingAnswer, setIsSubmittingAnswer] = useState<boolean>(false);
  const [runError, setRunError] = useState<string | null>(null);

  // What-If state
  const [whatIfDiff, setWhatIfDiff] = useState<WhatIfDiff | null>(null);
  const [isWhatIfRunning, setIsWhatIfRunning] = useState<boolean>(false);

  // Unsubscribe ref for SSE stream
  const unsubscribeRef = useRef<(() => void) | null>(null);

  // Check localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as UserOnboardingProfile;
        setUserProfile(parsed);
        setView('query');
      } else {
        setView('welcome');
      }
    } catch (e) {
      console.warn('Error reading localStorage:', e);
      setView('welcome');
    }
  }, []);

  // Cleanup SSE stream on unmount
  useEffect(() => {
    return () => {
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
        unsubscribeRef.current = null;
      }
    };
  }, []);

  // Handle questionnaire completion
  const handleOnboardingComplete = (profile: UserOnboardingProfile) => {
    setUserProfile(profile);
    setView('query');
  };

  // Reset user profile & localStorage
  const handleResetProfile = () => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      console.warn('Error clearing localStorage:', e);
    }
    setUserProfile(null);
    setView('welcome');
  };

  // Launch live multi-agent backend execution
  const handleStartRun = async (payload: BackendRunPayload) => {
    setLastPayload(payload);
    setView('analysis_results');
    setIsRunning(true);
    setRunError(null);
    setClarificationQuestion(null);
    setActiveTrace([]);
    setRunState(null);
    setWhatIfDiff(null);

    // Cancel existing stream if any
    if (unsubscribeRef.current) {
      unsubscribeRef.current();
      unsubscribeRef.current = null;
    }

    try {
      const { run_id } = await createRun(
        payload.persona,
        payload.request_text,
        undefined,
        payload
      );
      setCurrentRunId(run_id);

      const unsub = subscribeRunEvents(
        run_id,
        (event) => {
          if (event.type === 'trace' && event.entry) {
            setActiveTrace((prev) => {
              const existingIdx = prev.findIndex((e) => e.node === event.entry?.node);
              if (existingIdx >= 0) {
                const copy = [...prev];
                copy[existingIdx] = event.entry!;
                return copy;
              }
              return [...prev, event.entry!];
            });
          } else if (event.type === 'interrupt') {
            setIsRunning(false);
            setClarificationQuestion(event.question);
          } else if (event.type === 'final') {
            setIsRunning(false);
            setClarificationQuestion(null);
            fetchRunState(run_id)
              .then((state) => {
                setRunState(state);
                if (state.trace) setActiveTrace(state.trace);
              })
              .catch((err) => {
                setRunError(err.message || 'Erreur lors de la récupération des résultats');
              });
          } else if (event.type === 'error') {
            setIsRunning(false);
            setRunError(event.error || "Une erreur est survenue lors de l'exécution");
          }
        },
        (err) => {
          console.warn('SSE stream notice:', err);
        }
      );
      unsubscribeRef.current = unsub;
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      console.warn('Backend call failed, using fallback mode:', errorMessage);
      if (userProfile) {
        setRunError(
          `Connexion au backend impossible (${errorMessage}). Affichage des résultats prévisionnels en mode secours.`
        );
        const fallbackState = createMockAnalysisState(userProfile, payload.request_text);
        setRunState(fallbackState);
      } else {
        setRunError(errorMessage || 'Erreur lors du démarrage du calcul');
      }
      setIsRunning(false);
    }
  };

  // Answer clarifying question (interrupt)
  const handleAnswerClarification = async (answerText: string) => {
    if (!currentRunId) return;
    setIsSubmittingAnswer(true);
    setRunError(null);
    try {
      await answerRun(currentRunId, answerText);
      setClarificationQuestion(null);
      setIsRunning(true);
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      setRunError(errorMessage || "Erreur lors de l'envoi de la réponse");
    } finally {
      setIsSubmittingAnswer(false);
    }
  };

  // Run What-If simulation
  const handleRunWhatIf = async (field: string, value: unknown) => {
    if (!currentRunId) return;
    setIsWhatIfRunning(true);
    setWhatIfDiff(null);
    try {
      const { run_id: childId } = await createWhatIf(currentRunId, field, value);
      const unsub = subscribeRunEvents(
        childId,
        (event) => {
          if (event.type === 'trace' && event.entry) {
            setActiveTrace((prev) => {
              const existingIdx = prev.findIndex((e) => e.node === event.entry?.node);
              if (existingIdx >= 0) {
                const copy = [...prev];
                copy[existingIdx] = event.entry!;
                return copy;
              }
              return [...prev, event.entry!];
            });
          } else if (event.type === 'final') {
            setIsWhatIfRunning(false);
            Promise.all([fetchRunDiff(childId), fetchRunState(childId)])
              .then(([diff, state]) => {
                setWhatIfDiff(diff);
                setRunState(state);
                setCurrentRunId(childId);
              })
              .catch((err) => {
                console.error('What-If state error:', err);
              });
          } else if (event.type === 'error') {
            setIsWhatIfRunning(false);
            setRunError(event.error || 'Erreur lors du calcul What-If');
          }
        },
        (err) => {
          console.warn('What-If SSE notice:', err);
          setIsWhatIfRunning(false);
        }
      );
      unsubscribeRef.current = unsub;
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      setIsWhatIfRunning(false);
      setRunError(errorMessage || 'Erreur lors du lancement de la simulation What-If');
    }
  };

  const activeEvidence =
    selectedEvidenceId && runState?.evidence
      ? runState.evidence[selectedEvidenceId] || null
      : null;

  // View 1: Welcome screen (First time user with no localStorage)
  if (view === 'welcome') {
    return <WelcomeScreen onStart={() => setView('onboarding')} />;
  }

  // View 2: Onboarding Questionnaire (5 steps)
  if (view === 'onboarding') {
    return (
      <OnboardingFlow
        initialProfile={userProfile}
        onComplete={handleOnboardingComplete}
        onCancel={userProfile ? () => setView('query') : undefined}
      />
    );
  }

  // View 3: Query Screen (Existing user with saved profile in localStorage)
  if (view === 'query' && userProfile) {
    return (
      <QueryScreen
        profile={userProfile}
        onEditProfile={() => setView('onboarding')}
        onResetProfile={handleResetProfile}
        onRunQuery={handleStartRun}
      />
    );
  }

  // View 4: Live Analysis Results
  return (
    <div className="min-h-screen bg-background flex flex-col font-sans transition-colors">
      <SimulationBanner />

      {/* Top Header */}
      <header className="bg-card border-b border-border sticky top-0 z-20 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setView('query')}
              className="gap-1.5 text-xs sm:text-sm font-medium cursor-pointer"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Poser une autre question</span>
            </Button>
            <Logo size="sm" />
          </div>

          <div className="flex items-center gap-3">
            {userProfile && (
              <Badge
                variant="secondary"
                className="hidden sm:inline-flex items-center gap-1.5 py-1 px-2.5 font-normal"
              >
                <SlidersHorizontal className="w-3.5 h-3.5 text-muted-foreground" />
                <span>
                  {userProfile.simulatedCapitalFormatted} · {userProfile.riskTolerance}
                </span>
              </Badge>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setView('onboarding')}
              className="text-xs cursor-pointer"
            >
              Modifier profil
            </Button>

            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Main Results View */}
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-6">
        {/* Error notification if any */}
        {runError && (
          <div className="p-4 bg-destructive/10 border border-destructive/30 rounded-lg text-xs text-destructive flex items-start justify-between gap-3 shadow-xs">
            <div className="flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold block">Notification système</span>
                <p className="mt-0.5 leading-relaxed">{runError}</p>
              </div>
            </div>
            {lastPayload && !isRunning && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleStartRun(lastPayload)}
                className="h-8 text-xs gap-1.5 shrink-0"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Réessayer</span>
              </Button>
            )}
          </div>
        )}

        {/* Live Loading banner while running */}
        {isRunning && !runState && (
          <div className="p-4 bg-primary/10 border border-primary/20 rounded-lg text-xs text-foreground flex items-center justify-between gap-3 shadow-xs animate-pulse">
            <div className="flex items-center gap-2.5">
              <Loader2 className="w-4 h-4 text-primary animate-spin" />
              <div>
                <span className="font-semibold text-primary">
                  Orchestration multi-agents en direct...
                </span>
                <p className="text-muted-foreground mt-0.5">
                  Question : « {lastPayload?.request_text} » · Exécution des agents et calcul des scénarios
                </p>
              </div>
            </div>
            <Badge variant="outline" className="text-[11px] font-mono border-primary/30">
              {activeTrace.length} / 9 étapes
            </Badge>
          </div>
        )}

        {/* Success banner when complete */}
        {runState && !isRunning && (
          <div className="p-3.5 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-emerald-950 dark:text-emerald-200 flex items-start justify-between gap-2.5 shadow-xs">
            <div className="flex items-start gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" />
              <div className="text-xs">
                <div className="font-semibold">
                  Analyse complétée avec succès · 9 agents coordonnés
                </div>
                <p className="mt-0.5 text-xs text-emerald-900/80 dark:text-emerald-300">
                  Requête traitée : « {lastPayload?.request_text || runState?.request_text} » avec votre profil ({userProfile?.primaryObjective}, {userProfile?.firstWithdrawalHorizon}).
                </p>
              </div>
            </div>
            {runState.verification?.passed && (
              <Badge variant="outline" className="bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-500/40 text-[10px] shrink-0 font-medium">
                Vérifié déterministe
              </Badge>
            )}
          </div>
        )}

        {/* Clarification Box (Agent 1 interrupt) */}
        {clarificationQuestion && (
          <ClarificationBox
            question={clarificationQuestion}
            onAnswer={handleAnswerClarification}
            isSubmitting={isSubmittingAnswer}
          />
        )}

        {/* Node Trace (Real-time agent execution) */}
        {(activeTrace.length > 0 || isRunning) && (
          <NodeTrace
            trace={activeTrace.length > 0 ? activeTrace : (runState?.trace || [])}
            isRunning={isRunning || isWhatIfRunning}
          />
        )}

        {/* Conflicts Alert */}
        {runState?.profile?.conflicts && runState.profile.conflicts.length > 0 && (
          <ConflictsAlert conflicts={runState.profile.conflicts} />
        )}

        {/* What-If Module */}
        {runState && (
          <>
            <WhatIfDiffView diff={whatIfDiff} onClose={() => setWhatIfDiff(null)} />
            <WhatIfControls
              currentProfile={runState.profile}
              asOfDate={runState.as_of_date}
              eligibleTickers={runState.eligible_universe}
              onRunWhatIf={handleRunWhatIf}
              isRunning={isWhatIfRunning}
            />
          </>
        )}

        {/* Scenarios */}
        {runState?.scenarios && (
          <ScenarioCards
            scenarios={runState.scenarios}
            evidence={runState.evidence}
            mostConsistentName={runState.explanation?.scenario_le_plus_coherent}
          />
        )}

        {/* Explanation */}
        {runState?.explanation && (
          <ExplanationSection
            explanation={runState.explanation}
            verification={runState.verification}
            evidence={runState.evidence}
            onSelectEvidence={setSelectedEvidenceId}
          />
        )}

        {/* Exclusions */}
        {runState?.exclusions && (
          <ExclusionsCard
            exclusions={runState.exclusions}
            evidence={runState.evidence}
            onSelectEvidence={setSelectedEvidenceId}
          />
        )}

        {/* Evidence Table */}
        {runState?.evidence && (
          <EvidenceTable
            evidence={runState.evidence}
            onSelectEvidence={setSelectedEvidenceId}
          />
        )}
      </main>

      {/* Modal for evidence detail */}
      <EvidenceModal
        evidence={activeEvidence}
        onClose={() => setSelectedEvidenceId(null)}
      />

      {/* Footer */}
      <footer className="bg-card border-t border-border py-6 mt-auto text-center text-xs text-muted-foreground">
        <p>AlphaForge AI — Architecture multi-agents vérifiable · PolyFinances 2026</p>
        <p className="mt-1 text-muted-foreground/70">
          Les performances passées ne garantissent pas les résultats futurs.
        </p>
      </footer>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <ThemeProvider defaultTheme="light" storageKey="alphaforge_theme">
      <AppContent />
    </ThemeProvider>
  );
};

export default App;
