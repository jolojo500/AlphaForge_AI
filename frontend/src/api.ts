/**
 * Typed API client for AlphaForge AI backend (PRD 6).
 */

import { GraphState, PersonaMeta, SSEEvent } from './types';

const API_BASE = '';

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function fetchPersonas(): Promise<Record<string, PersonaMeta>> {
  const res = await fetch(`${API_BASE}/personas`);
  if (!res.ok) throw new Error(`Failed to fetch personas: ${res.statusText}`);
  return res.json();
}

export async function createRun(
  persona: string,
  requestText: string,
  asOfDate?: string
): Promise<{ run_id: string }> {
  const res = await fetch(`${API_BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      persona,
      request_text: requestText,
      as_of_date: asOfDate || null,
    }),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to create run: ${res.statusText}`);
  }
  return res.json();
}

export async function answerRun(runId: string, text: string): Promise<{ run_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/runs/${runId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to answer run: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchRunState(runId: string): Promise<GraphState> {
  const res = await fetch(`${API_BASE}/runs/${runId}`);
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to fetch run state: ${res.statusText}`);
  }
  return res.json();
}

export function subscribeRunEvents(
  runId: string,
  onEvent: (event: SSEEvent) => void,
  onError?: (error: unknown) => void
): () => void {
  const source = new EventSource(`${API_BASE}/runs/${runId}/events`);

  source.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data) as SSEEvent;
      onEvent(parsed);
      if (parsed.type === 'final' || parsed.type === 'error') {
        source.close();
      }
    } catch (err) {
      if (onError) onError(err);
    }
  };

  source.onerror = (err) => {
    if (onError) onError(err);
  };

  return () => {
    source.close();
  };
}
