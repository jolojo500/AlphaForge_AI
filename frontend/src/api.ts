import type { Persona, PersonaId, RunEvent, RunResponse, WhatIfField } from '@/types'

// Dev: the API runs on :8000 and allows the Vite origin through CORS.
// Production: the same FastAPI app serves the built frontend, so URLs are relative.
export const API_URL: string =
  import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '')

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = `Erreur ${res.status}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = 'Requête invalide.'
    } catch {
      /* keep the default message */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const getPersonas = () => request<Persona[]>('/personas')

export const createRun = (persona: PersonaId, request_text: string) =>
  request<{ run_id: string }>('/runs', {
    method: 'POST',
    body: JSON.stringify({ persona, request_text }),
  })

export const getRun = (runId: string) => request<RunResponse>(`/runs/${runId}`)

export const answerRun = (runId: string, text: string) =>
  request<{ run_id: string }>(`/runs/${runId}/answer`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  })

export const startWhatIf = (runId: string, field: WhatIfField, value: string | number) =>
  request<{ run_id: string; parent_run_id: string }>(`/runs/${runId}/whatif`, {
    method: 'POST',
    body: JSON.stringify({ field, value }),
  })

/** Open the SSE stream of a run, replaying events after `after`. Returns a close function. */
export function openEvents(
  runId: string,
  after: number,
  onEvent: (e: RunEvent) => void,
  onLost: () => void,
): () => void {
  const source = new EventSource(`${API_URL}/runs/${runId}/events?after=${after}`)
  let closed = false
  const close = () => {
    closed = true
    source.close()
  }
  source.onmessage = (msg) => {
    const event = JSON.parse(msg.data) as RunEvent
    onEvent(event)
    // The server ends the stream at these events; closing here stops EventSource reconnecting.
    if (event.type === 'final' || event.type === 'interrupt' || event.type === 'error') close()
  }
  source.onerror = () => {
    if (closed) return
    close()
    onLost()
  }
  return close
}
