import { useCallback, useEffect, useRef, useState } from 'react'

import { answerRun, ApiError, getRun, openEvents } from '@/api'
import type { RunEvent, RunResponse, TraceEntry } from '@/types'

export interface RunView {
  runId: string | null
  trace: TraceEntry[]
  data: RunResponse | null
  question: string | null
  running: boolean
  error: string | null
  answer: (text: string) => Promise<void>
}

interface Snapshot {
  id: string | null
  trace: TraceEntry[]
  data: RunResponse | null
  question: string | null
  running: boolean
  error: string | null
}

const empty = (id: string | null): Snapshot => ({
  id,
  trace: [],
  data: null,
  question: null,
  running: id !== null,
  error: null,
})

/** Follows one run: live trace through SSE, then the final state through GET /runs/{id}. */
export function useRun(runId: string | null): RunView {
  const [snap, setSnap] = useState<Snapshot>(() => empty(runId))
  const lastSeq = useRef(0)
  const closeRef = useRef<(() => void) | null>(null)

  // State belongs to one run id: a new id starts from a clean snapshot without effect resets.
  const view = snap.id === runId ? snap : empty(runId)

  const patch = useCallback((id: string, change: (s: Snapshot) => Partial<Snapshot>) => {
    setSnap((prev) => {
      const base = prev.id === id ? prev : empty(id)
      return { ...base, ...change(base) }
    })
  }, [])

  const connect = useCallback(
    (id: string) => {
      closeRef.current?.()
      const onEvent = (e: RunEvent) => {
        lastSeq.current = e.seq
        if (e.type === 'trace') patch(id, (s) => ({ trace: [...s.trace, e.entry] }))
        else if (e.type === 'interrupt') patch(id, () => ({ question: e.question, running: false }))
        else if (e.type === 'final') {
          getRun(id)
            .then((data) => patch(id, () => ({ data, running: false })))
            .catch((err: unknown) =>
              patch(id, () => ({ error: err instanceof Error ? err.message : 'Erreur', running: false })),
            )
        } else patch(id, () => ({ error: e.message, running: false }))
      }
      const onLost = () => patch(id, () => ({ error: 'Connexion au serveur perdue.', running: false }))
      closeRef.current = openEvents(id, lastSeq.current, onEvent, onLost)
    },
    [patch],
  )

  useEffect(() => {
    lastSeq.current = 0
    if (runId) connect(runId)
    return () => closeRef.current?.()
  }, [runId, connect])

  const answer = useCallback(
    async (text: string) => {
      if (!runId) return
      try {
        await answerRun(runId, text)
        patch(runId, () => ({ question: null, running: true }))
        connect(runId)
      } catch (err) {
        patch(runId, () => ({
          error: err instanceof ApiError ? err.message : 'Impossible d’envoyer la réponse.',
        }))
      }
    },
    [runId, connect, patch],
  )

  return { runId, ...view, answer }
}
