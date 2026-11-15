import React, { useEffect, useState, useCallback, useRef } from 'react';
import { GraphState, PersonaMeta, TraceEntry } from './types';
import {
  fetchPersonas,
  createRun,
  subscribeRunEvents,
  answerRun,
  fetchRunState,
} from './api';
import { SimulationBanner } from './components/SimulationBanner';
import { PersonaPicker } from './components/PersonaPicker';
import { ConflictsAlert } from './components/ConflictsAlert';
import { NodeTrace } from './components/NodeTrace';
import { ClarificationBox } from './components/ClarificationBox';
import { ScenarioCards } from './components/ScenarioCards';
import { ExplanationSection } from './components/ExplanationSection';
import { ExclusionsCard } from './components/ExclusionsCard';
import { EvidenceTable } from './components/EvidenceTable';
import { EvidenceModal } from './components/EvidenceModal';
import { Compass, AlertTriangle } from 'lucide-react';

export const App: React.FC = () => {
  const [personas, setPersonas] = useState<Record<string, PersonaMeta>>({});
  const [selectedPersona, setSelectedPersona] = useState<string>('robert');
  const [requestText, setRequestText] = useState<string>('');
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [isAnswering, setIsAnswering] = useState<boolean>(false);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [interruptQuestion, setInterruptQuestion] = useState<string | null>(null);
  const [runState, setRunState] = useState<GraphState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);

  const unsubRef = useRef<(() => void) | null>(null);

  // Load personas on mount
  useEffect(() => {
    fetchPersonas()
      .then((data) => {
        setPersonas(data);
        if (data['robert']) {
          setRequestText(data['robert'].example_request);
        }
      })
      .catch((err) => {
        console.error('Error fetching personas:', err);
        setError('Impossible de joindre le serveur FastAPI. Vérifiez que le backend tourne sur le port 8000.');
      });
  }, []);

  // Update example request text when selected persona changes
  const handleSelectPersona = (id: string) => {
    setSelectedPersona(id);
    if (personas[id]) {
      setRequestText(personas[id].example_request);
    }
  };

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (unsubRef.current) {
        unsubRef.current();
      }
    };
  }, []);

  const handleStartRun = useCallback(async () => {
    setError(null);
    setTrace([]);
    setInterruptQuestion(null);
    setRunState(null);
    setSelectedEvidenceId(null);
    setIsRunning(true);

    if (unsubRef.current) {
      unsubRef.current();
      unsubRef.current = null;
    }

    try {
      const { run_id } = await createRun(selectedPersona, requestText);
      setRunId(run_id);

      const unsubscribe = subscribeRunEvents(
        run_id,
        (ev) => {
          if (ev.type === 'trace') {
            setTrace((prev) => [...prev, ev.entry]);
          } else if (ev.type === 'interrupt') {
            setInterruptQuestion(ev.question);
            setIsRunning(false);
          } else if (ev.type === 'final') {
            setIsRunning(false);
            setInterruptQuestion(null);
            fetchRunState(ev.run_id)
              .then((state) => {
                setRunState(state);
                if (state.trace && state.trace.length > 0) {
                  setTrace(state.trace);
                }
              })
              .catch((err) => {
                setError(`Erreur lors de la récupération du résultat: ${err.message}`);
              });
          } else if (ev.type === 'error') {
            setIsRunning(false);
            setError(ev.error || 'Erreur pendant l’exécution de l’analyse');
          }
        },
        (err) => {
          console.error('SSE Error:', err);
        }
      );

      unsubRef.current = unsubscribe;
    } catch (err: unknown) {
      setIsRunning(false);
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Échec du lancement : ${msg}`);
    }
  }, [selectedPersona, requestText]);

  const handleAnswerClarification = useCallback(async (answer: string) => {
    if (!runId) return;
    setIsAnswering(true);
    setError(null);

    try {
      await answerRun(runId, answer);
      setInterruptQuestion(null);
      setIsRunning(true);
      setIsAnswering(false);
    } catch (err: unknown) {
      setIsAnswering(false);
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Échec de la réponse : ${msg}`);
    }
  }, [runId]);

  const activeEvidence = selectedEvidenceId && runState?.evidence
    ? runState.evidence[selectedEvidenceId] || null
    : null;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <SimulationBanner />

      {/* Main Header */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-sm">
              <Compass className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-slate-900 tracking-tight">AlphaForge AI</h1>
                <span className="text-xs font-semibold px-2 py-0.5 rounded bg-blue-100 text-blue-800">
                  Datathon PolyFinances 2026
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Moteur de second avis d&apos;investissement · Architecture multi-agents vérifiable
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        {error && (
          <div className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5 shrink-0" />
            <div className="text-sm">
              <span className="font-semibold block">Erreur rencontrée</span>
              <span>{error}</span>
            </div>
          </div>
        )}

        <PersonaPicker
          personas={personas}
          selectedPersona={selectedPersona}
          onSelectPersona={handleSelectPersona}
          requestText={requestText}
          onChangeRequestText={setRequestText}
          onRun={handleStartRun}
          isRunning={isRunning}
        />

        {/* Profile conflicts shown near the top if detected */}
        {runState?.profile?.conflicts && (
          <ConflictsAlert conflicts={runState.profile.conflicts} />
        )}

        {interruptQuestion && (
          <ClarificationBox
            question={interruptQuestion}
            onAnswer={handleAnswerClarification}
            isSubmitting={isAnswering}
          />
        )}

        <NodeTrace trace={trace} isRunning={isRunning} />

        {runState && (
          <>
            <ScenarioCards
              scenarios={runState.scenarios}
              evidence={runState.evidence}
              mostConsistentName={runState.explanation?.scenario_le_plus_coherent}
            />

            <ExplanationSection
              explanation={runState.explanation}
              verification={runState.verification}
              evidence={runState.evidence}
              onSelectEvidence={setSelectedEvidenceId}
            />

            <ExclusionsCard
              exclusions={runState.exclusions}
              evidence={runState.evidence}
              onSelectEvidence={setSelectedEvidenceId}
            />

            <EvidenceTable
              evidence={runState.evidence}
              onSelectEvidence={setSelectedEvidenceId}
            />
          </>
        )}
      </main>

      {/* Evidence detail modal */}
      <EvidenceModal
        evidence={activeEvidence}
        onClose={() => setSelectedEvidenceId(null)}
      />

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 py-6 mt-auto text-center text-xs text-slate-500">
        <p>
          AlphaForge AI — Projet pour le Datathon PolyFinances 2026 (BNCD & AWS).
        </p>
        <p className="mt-1 text-slate-400">
          Simulation éducative. Aucun conseil personnalisé ni promesse de rendement financier.
        </p>
      </footer>
    </div>
  );
};

export default App;
