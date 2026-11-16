import React, { useState, useEffect, useRef } from 'react';
import {
  GraphState,
  UserOnboardingProfile,
  BackendRunPayload,
  TraceEntry,
  WhatIfDiff,
  AuthUser,
} from './types';
import {
  createRun,
  subscribeRunEvents,
  fetchRunState,
  answerRun,
  createWhatIf,
  fetchRunDiff,
  getStoredUser,
  setStoredUser,
  setAuthToken,
  clearAuth,
  fetchCurrentUser,
  logout,
  getAuthToken,
  saveQuestionnaire,
  fetchUserProfile,
  questionnaireOf,
} from './api';
import { ThemeProvider } from './components/ThemeProvider';
import { LanguageProvider, useLanguage } from './context/LanguageContext';
import { WelcomeScreen } from './components/WelcomeScreen';
import { OnboardingFlow } from './components/onboarding/OnboardingFlow';
import { QueryScreen } from './components/QueryScreen';
import { LoadingScreen } from './components/LoadingScreen';
import { ClarificationScreen } from './components/ClarificationScreen';
import { ResponseScreen } from './components/ResponseScreen';
import { EvidenceModal } from './components/EvidenceModal';
import { ReplayRunModal } from './components/ReplayRunModal';
import { AuthModal } from './components/AuthModal';
import { ProfileModal } from './components/ProfileModal';
import { AppHeader } from './components/AppHeader';
import { DEMO_PERSONAS } from './lib/demoProfiles';
import { Button } from './components/ui/button';
import { ArrowLeft, RefreshCw } from 'lucide-react';

const STORAGE_KEY = 'alphaforge_user_profile';

type AppView = 'welcome' | 'onboarding' | 'query' | 'analysis_results';
type PersonaChoice = 'custom' | 'robert' | 'amira' | 'mateo';

export const AppContent: React.FC = () => {
  const { language } = useLanguage();
  const [view, setView] = useState<AppView>('welcome');
  const [customProfile, setCustomProfile] = useState<UserOnboardingProfile | null>(null);
  const [activePersonaId, setActivePersonaId] = useState<PersonaChoice>('custom');
  const [initialQuery, setInitialQuery] = useState<string>('');

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
  // The run before the what-if: its answer stays on screen beside the new one (#180).
  const [whatIfBaseline, setWhatIfBaseline] = useState<GraphState | null>(null);

  // Simulation History (formerly Replay) modal state
  const [isReplayModalOpen, setIsReplayModalOpen] = useState<boolean>(false);

  // Authentication state
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(() => getStoredUser());
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);
  // Read-only versioned profile view (history, dossier download, #170/#192); edits go through the questionnaire.
  const [isProfileModalOpen, setIsProfileModalOpen] = useState<boolean>(false);

  // Unsubscribe ref for SSE stream
  const unsubscribeRef = useRef<(() => void) | null>(null);

  /**
   * The saved server profile is the one profile (#170): when it holds a questionnaire, it
   * replaces the local copy and the user lands on the query screen instead of the questionnaire.
   */
  const hydrateProfileFromServer = async (): Promise<boolean> => {
    try {
      const data = await fetchUserProfile();
      const q = questionnaireOf(data);
      if (!q) return false;
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(q));
      } catch (e) {
        console.warn('Error saving to localStorage:', e);
      }
      setCustomProfile(q);
      setActivePersonaId('custom');
      setView((v) => (v === 'welcome' || v === 'onboarding' ? 'query' : v));
      return true;
    } catch (e) {
      console.warn('Server profile fetch error:', e);
      return false;
    }
  };

  const handleAuthSuccess = (user: AuthUser) => {
    setCurrentUser(user);
    void hydrateProfileFromServer();
  };

  // Verify auth session on mount, then restore the server profile (#170)
  useEffect(() => {
    const stored = getStoredUser();
    if (stored) {
      setCurrentUser(stored);
    }
    if (getAuthToken()) {
      fetchCurrentUser()
        .then((res) => {
          setCurrentUser(res.user);
          setStoredUser(res.user);
          void hydrateProfileFromServer();
        })
        .catch(() => {
          clearAuth();
          setCurrentUser(null);
        });
    }
  }, []);

  const handleLogout = () => {
    logout();
    clearAuth();
    setCurrentUser(null);
    setCustomProfile(null);
    setActivePersonaId('custom');
    setInitialQuery('');
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      console.warn('Error clearing localStorage:', e);
    }
    setView('welcome');
  };

  // Check localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as UserOnboardingProfile;
        setCustomProfile(parsed);
        setActivePersonaId('custom');
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

  // Active profile resolved from custom or demo
  const activeProfile: UserOnboardingProfile = (() => {
    if (activePersonaId === 'custom' && customProfile) {
      return customProfile;
    }
    const demo = activePersonaId !== 'custom' ? DEMO_PERSONAS[activePersonaId] : null;
    if (demo) {
      return demo.profile;
    }
    return customProfile || DEMO_PERSONAS.robert.profile;
  })();

  // Handle questionnaire completion: save locally and, when logged in, as the one server
  // profile (full questionnaire + engine profile + holdings); the server returns the version.
  const persistProfile = (profile: UserOnboardingProfile) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
    } catch (e) {
      console.warn('Error saving to localStorage:', e);
    }
    setCustomProfile(profile);
  };

  const handleOnboardingComplete = (profile: UserOnboardingProfile) => {
    persistProfile(profile);
    setActivePersonaId('custom');
    if (getAuthToken()) {
      saveQuestionnaire(profile)
        .then((res) => {
          persistProfile({ ...profile, profileVersion: res.profile_version ?? profile.profileVersion ?? null });
        })
        .catch((e) => console.warn('Server profile sync error:', e));
    }
    setView('query');
  };

  // Pick demo persona: shortcut to authenticate as this preconfigured profile, leave question empty, navigate to query
  const handleSelectDemo = (personaId: 'robert' | 'amira' | 'mateo') => {
    setActivePersonaId(personaId);
    setInitialQuery(''); // Question input field is intentionally left empty

    const demo = DEMO_PERSONAS[personaId];
    const demoUser: AuthUser = {
      user_id: `demo-${personaId}`,
      username: demo.name,
      email: `${personaId}@alphaforge.demo`,
      is_advisor: false,
    };
    setCurrentUser(demoUser);
    setStoredUser(demoUser);
    setAuthToken(`demo-${personaId}`);

    setView('query');
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
    setWhatIfBaseline(null);

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
        { ...payload, language: payload.language || language }
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
      setRunError(
        `Connexion au moteur d'analyse impossible (${errorMessage}). Aucun résultat n'est affiché : réessayez.`
      );
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
    // Keep the answer the reader is looking at: it becomes the "before" column.
    const baseline = whatIfBaseline ?? runState;
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
                setWhatIfBaseline(baseline);
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

  // Inspect saved past run from history without running new calculation
  const handleReplayRun = async (runId: string) => {
    try {
      setRunError(null);
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
        unsubscribeRef.current = null;
      }
      const state = await fetchRunState(runId);
      setCurrentRunId(runId);
      setRunState(state);
      setActiveTrace(state.trace || []);
      setIsRunning(false);
      setClarificationQuestion(null);
      setWhatIfDiff(null);
      setWhatIfBaseline(null);
      setLastPayload({
        persona: state.persona,
        request_text: state.request_text,
      });
      setIsReplayModalOpen(false);
      setView('analysis_results');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setRunError(`Impossible de consulter l'analyse (${msg}).`);
    }
  };

  const handleCancelRun = () => {
    if (unsubscribeRef.current) {
      unsubscribeRef.current();
      unsubscribeRef.current = null;
    }
    setIsRunning(false);
    setClarificationQuestion(null);
    setView('query');
  };

  const activeEvidence =
    selectedEvidenceId && runState?.evidence
      ? runState.evidence[selectedEvidenceId] || null
      : null;

  // View 1: Welcome screen (First time user with no localStorage)
  if (view === 'welcome') {
    return (
      <>
        <WelcomeScreen
          onStart={() => setView('onboarding')}
          onSelectDemo={handleSelectDemo}
          onOpenHistory={currentUser ? () => setIsReplayModalOpen(true) : undefined}
          currentUser={currentUser}
          onOpenAuth={() => setIsAuthModalOpen(true)}
          onEditProfile={() => setView('onboarding')}
          onOpenProfile={currentUser ? () => setIsProfileModalOpen(true) : undefined}
          onLogout={handleLogout}
        />
        <ReplayRunModal
          isOpen={isReplayModalOpen}
          onClose={() => setIsReplayModalOpen(false)}
          onSelectRun={handleReplayRun}
          activePersonaId={activePersonaId}
        />
        <AuthModal
          isOpen={isAuthModalOpen}
          onClose={() => setIsAuthModalOpen(false)}
          onSuccess={handleAuthSuccess}
        />
        <ProfileModal
          isOpen={isProfileModalOpen}
          onClose={() => setIsProfileModalOpen(false)}
          currentUser={currentUser}
          onEditQuestionnaire={() => setView('onboarding')}
        />
      </>
    );
  }

  // View 2: Onboarding Questionnaire (5 steps)
  if (view === 'onboarding') {
    return (
      <OnboardingFlow
        initialProfile={customProfile || activeProfile}
        onComplete={handleOnboardingComplete}
        onCancel={customProfile || currentUser ? () => setView('query') : () => setView('welcome')}
      />
    );
  }

  // View 3: Query Screen (Existing user with saved profile in localStorage)
  if (view === 'query') {
    return (
      <>
        <QueryScreen
          profile={activeProfile}
          customProfile={customProfile}
          activePersonaId={activePersonaId}
          onEditProfile={() => setView('onboarding')}
          onOpenProfile={currentUser ? () => setIsProfileModalOpen(true) : undefined}
          onRunQuery={handleStartRun}
          onOpenHistory={() => setIsReplayModalOpen(true)}
          currentUser={currentUser}
          onOpenAuth={() => setIsAuthModalOpen(true)}
          onLogout={handleLogout}
          initialQuery={initialQuery}
        />
        <ReplayRunModal
          isOpen={isReplayModalOpen}
          onClose={() => setIsReplayModalOpen(false)}
          onSelectRun={handleReplayRun}
          activePersonaId={activePersonaId}
        />
        <AuthModal
          isOpen={isAuthModalOpen}
          onClose={() => setIsAuthModalOpen(false)}
          onSuccess={handleAuthSuccess}
        />
        <ProfileModal
          isOpen={isProfileModalOpen}
          onClose={() => setIsProfileModalOpen(false)}
          currentUser={currentUser}
          onEditQuestionnaire={() => setView('onboarding')}
        />
      </>
    );
  }

  // View 4: Live Analysis Results
  if (view === 'analysis_results') {
    // 4.1 Clarification Screen (Agent 1 interrupt)
    if (clarificationQuestion) {
      return (
        <>
          <ClarificationScreen
            question={clarificationQuestion}
            onAnswer={handleAnswerClarification}
            isSubmitting={isSubmittingAnswer}
          />
          <EvidenceModal
            evidence={activeEvidence}
            onClose={() => setSelectedEvidenceId(null)}
          />
        </>
      );
    }

    // 4.2 Loading Screen while agents are orchestrating
    if (isRunning && !runState) {
      return (
        <>
          <LoadingScreen onCancel={handleCancelRun} trace={activeTrace} />
          <EvidenceModal
            evidence={activeEvidence}
            onClose={() => setSelectedEvidenceId(null)}
          />
        </>
      );
    }

    // 4.3 Error State
    if (runError && !runState) {
      return (
        <div className="min-h-screen bg-background flex flex-col justify-between px-4 py-5 sm:py-8 font-sans transition-colors">
          <AppHeader />
          <div className="w-full max-w-md mx-auto flex flex-col items-center justify-center my-auto space-y-5 text-center">
            <h1 className="text-sm sm:text-base font-medium text-foreground tracking-tight">
              Une anomalie est survenue
            </h1>
            <div className="p-4 bg-card border border-border rounded-xl text-xs text-muted-foreground leading-relaxed w-full">
              {runError}
            </div>
            <div className="w-full space-y-2 flex flex-col items-center">
              {lastPayload && (
                <Button
                  type="button"
                  onClick={() => handleStartRun(lastPayload)}
                  className="w-full h-10 text-xs sm:text-sm font-medium flex items-center justify-center gap-2 cursor-pointer"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Réessayer l'analyse</span>
                </Button>
              )}
              <Button
                type="button"
                variant="outline"
                onClick={() => setView('query')}
                className="w-full h-10 text-xs sm:text-sm font-medium flex items-center justify-center gap-1.5 cursor-pointer"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Modifier ma question</span>
              </Button>
            </div>
          </div>
          <footer className="w-full max-w-4xl mx-auto pt-6 text-center text-[11px] text-muted-foreground border-t border-border/40 select-none">
            Simulation éducative · Aucun conseil réglementé · Les performances passées ne garantissent pas les résultats futurs
          </footer>
        </div>
      );
    }

    // 4.4 Response Screen with all verified results rendered
    if (runState) {
      return (
        <>
          <ResponseScreen
            runState={runState}
            userProfile={activeProfile}
            customProfile={customProfile}
            activePersonaId={activePersonaId}
            requestText={lastPayload?.request_text || runState.request_text}
            onAskAnother={() => setView('query')}
            onEditProfile={() => setView('onboarding')}
            onOpenProfile={currentUser ? () => setIsProfileModalOpen(true) : undefined}
            onSelectEvidence={setSelectedEvidenceId}
            whatIfDiff={whatIfDiff}
            whatIfBaseline={whatIfBaseline}
            onCloseWhatIfDiff={() => {
              setWhatIfDiff(null);
              setWhatIfBaseline(null);
            }}
            onRunWhatIf={handleRunWhatIf}
            isWhatIfRunning={isWhatIfRunning}
            onOpenHistory={() => setIsReplayModalOpen(true)}
            currentUser={currentUser}
            onOpenAuth={() => setIsAuthModalOpen(true)}
            onLogout={handleLogout}
            onReviewed={(updated) => {
              setRunState((prev) => (prev ? { ...prev, ...updated } : null));
            }}
          />
          <EvidenceModal
            evidence={activeEvidence}
            onClose={() => setSelectedEvidenceId(null)}
          />
          <ReplayRunModal
            isOpen={isReplayModalOpen}
            onClose={() => setIsReplayModalOpen(false)}
            onSelectRun={handleReplayRun}
            activePersonaId={activePersonaId}
          />
          <AuthModal
            isOpen={isAuthModalOpen}
            onClose={() => setIsAuthModalOpen(false)}
            onSuccess={handleAuthSuccess}
          />
          <ProfileModal
            isOpen={isProfileModalOpen}
            onClose={() => setIsProfileModalOpen(false)}
            currentUser={currentUser}
            onEditQuestionnaire={() => setView('onboarding')}
          />
        </>
      );
    }
  }

  return null;
};

export const App: React.FC = () => {
  return (
    <ThemeProvider defaultTheme="light" storageKey="alphaforge_theme">
      <LanguageProvider>
        <AppContent />
      </LanguageProvider>
    </ThemeProvider>
  );
};

export default App;
