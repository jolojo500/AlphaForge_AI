import { useCallback, useEffect, useState } from 'react'

import { ApiError, createRun, getPersonas, startWhatIf } from '@/api'
import { ClarifyingQuestion } from '@/components/ClarifyingQuestion'
import { DiffView } from '@/components/DiffView'
import { EvidenceTable } from '@/components/EvidenceTable'
import { ExcludedAssets } from '@/components/ExcludedAssets'
import { ExplanationView } from '@/components/ExplanationView'
import { NodeTrace } from '@/components/NodeTrace'
import { PersonaPicker } from '@/components/PersonaPicker'
import { RequestBox } from '@/components/RequestBox'
import { ScenarioCards } from '@/components/ScenarioCards'
import { DISCLAIMER, SimulationBanner } from '@/components/SimulationBanner'
import { WhatIfPanel } from '@/components/WhatIfPanel'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useRun } from '@/hooks/useRun'
import type { Persona, PersonaId, WhatIfField } from '@/types'

const FIELD_LABEL: Record<string, string> = {
  horizon_years: 'Horizon',
  budget_cad: 'Budget',
  risk_tolerance: 'Tolérance',
  exclude_ticker: 'Actif exclu',
  as_of_date: 'Date d’analyse',
}

export default function App() {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [personaId, setPersonaId] = useState<PersonaId | null>(null)
  const [text, setText] = useState('')
  const [runId, setRunId] = useState<string | null>(null)
  const [childId, setChildId] = useState<string | null>(null)
  const [whatIfError, setWhatIfError] = useState<string | null>(null)
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null)

  const run = useRun(runId)
  const child = useRun(childId)

  useEffect(() => {
    getPersonas()
      .then(setPersonas)
      .catch(() => setLoadError('Le serveur est injoignable. Lancez l’API puis rechargez la page.'))
  }, [])

  const persona = personas.find((p) => p.id === personaId) ?? null

  const selectPersona = (id: PersonaId) => {
    setPersonaId(id)
    setText(personas.find((p) => p.id === id)?.example_request ?? '')
  }

  const submit = async () => {
    if (!personaId) return
    setChildId(null)
    setWhatIfError(null)
    setSelectedEvidence(null)
    try {
      const { run_id } = await createRun(personaId, text)
      setRunId(run_id)
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : 'Impossible de lancer l’analyse.')
    }
  }

  const applyWhatIf = useCallback(
    async (field: WhatIfField, value: string | number) => {
      if (!runId) return
      setWhatIfError(null)
      try {
        const { run_id } = await startWhatIf(runId, field, value)
        setChildId(run_id)
      } catch (err) {
        setWhatIfError(err instanceof ApiError ? err.message : 'Impossible de relancer l’analyse.')
      }
    },
    [runId],
  )

  const state = run.data?.state ?? null
  const childState = child.data?.state ?? null

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 pt-6 pb-24">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">AlphaForge AI</h1>
        <p className="text-muted-foreground">
          Un deuxième avis structuré sur une décision de placement : comparer, expliquer, prouver.
        </p>
      </header>

      <SimulationBanner />

      {loadError && (
        <Alert variant="destructive">
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      )}

      <PersonaPicker personas={personas} selected={personaId} disabled={run.running} onSelect={selectPersona} />
      <RequestBox persona={persona} value={text} busy={run.running} onChange={setText} onSubmit={() => void submit()} />

      {runId && <NodeTrace trace={run.trace} running={run.running} />}

      {run.error && (
        <Alert variant="destructive">
          <AlertDescription>{run.error}</AlertDescription>
        </Alert>
      )}

      {run.question && <ClarifyingQuestion question={run.question} onAnswer={run.answer} />}

      {state && state.profile && (
        <>
          {state.profile.conflicts.length > 0 && (
            <Alert className="border-amber-500/50">
              <AlertDescription>
                <p className="mb-1 font-medium text-foreground">Tensions entre la demande et le profil</p>
                <ul className="list-disc pl-4">
                  {state.profile.conflicts.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          <ScenarioCards
            scenarios={state.scenarios}
            evidence={state.evidence}
            mostCoherent={state.explanation?.scenario_le_plus_coherent ?? null}
            selectedEvidence={selectedEvidence}
            onSelectEvidence={setSelectedEvidence}
          />
          <ExplanationView state={state} selectedEvidence={selectedEvidence} onSelectEvidence={setSelectedEvidence} />
          <EvidenceTable evidence={state.evidence} selected={selectedEvidence} />
          <ExcludedAssets
            exclusions={state.exclusions}
            evidence={state.evidence}
            selected={selectedEvidence}
            onSelect={setSelectedEvidence}
          />

          <WhatIfPanel
            profile={state.profile}
            asOf={state.as_of_date}
            eligible={state.eligible_universe}
            busy={child.running}
            error={whatIfError}
            onApply={(f, v) => void applyWhatIf(f, v)}
          />

          {childId && (
            <>
              <NodeTrace trace={child.trace} running={child.running} skipped={['profile']} />
              {child.error && (
                <Alert variant="destructive">
                  <AlertDescription>{child.error}</AlertDescription>
                </Alert>
              )}
              {child.data?.diff && childState && (
                <DiffView
                  diff={child.data.diff}
                  changeLabel={`${FIELD_LABEL[child.data.change?.field ?? ''] ?? 'Hypothèse'} : ${String(child.data.change?.value ?? '')}`}
                />
              )}
            </>
          )}
        </>
      )}

      <footer
        role="contentinfo"
        className="fixed inset-x-0 bottom-0 border-t border-border bg-background/95 px-4 py-2 text-center text-sm backdrop-blur"
      >
        {DISCLAIMER}
      </footer>
    </div>
  )
}
