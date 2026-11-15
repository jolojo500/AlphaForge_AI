/**
 * Typed API client for AlphaForge AI backend (PRD 6).
 */

import { GraphState, PersonaMeta, SavedRunSummary, SSEEvent, WhatIfDiff } from './types';

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
  asOfDate?: string,
  extraPayload?: Partial<BackendRunPayload>
): Promise<{ run_id: string }> {
  const res = await fetch(`${API_BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      persona,
      request_text: requestText,
      as_of_date: asOfDate || null,
      profile_data: extraPayload?.profile_data || null,
      user_profile: extraPayload?.user_profile || null,
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

export async function fetchSavedRuns(persona?: string): Promise<SavedRunSummary[]> {
  const url = persona ? `${API_BASE}/runs?persona=${encodeURIComponent(persona)}` : `${API_BASE}/runs`;
  const res = await fetch(url);
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to fetch saved runs: ${res.statusText}`);
  }
  return res.json();
}

export async function createWhatIf(
  parentId: string,
  field: string,
  value: unknown
): Promise<{ run_id: string; parent_run_id: string }> {
  const res = await fetch(`${API_BASE}/runs/${parentId}/whatif`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field, value }),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to create what-if run: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchRunDiff(childRunId: string): Promise<WhatIfDiff> {
  const res = await fetch(`${API_BASE}/runs/${childRunId}/diff`);
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to fetch what-if diff: ${res.statusText}`);
  }
  return res.json();
}

export async function compareRuns(runA: string, runB: string): Promise<WhatIfDiff> {
  const res = await fetch(
    `${API_BASE}/runs/compare?run_a=${encodeURIComponent(runA)}&run_b=${encodeURIComponent(runB)}`
  );
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to compare runs: ${res.statusText}`);
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

import { UserOnboardingProfile, BackendRunPayload } from './types';

/**
 * Prepares the payload for the AlphaForge multi-agent backend.
 * Integrates questionnaire profile and user question, ready for POST /runs.
 */
export function prepareBackendPayload(
  profile: UserOnboardingProfile,
  requestText: string
): BackendRunPayload {
  let objective = 'capital_preservation';
  if (profile.primaryObjective.includes('équilibrée')) {
    objective = 'balanced';
  } else if (profile.primaryObjective.includes('Croissance')) {
    objective = 'growth';
  } else if (profile.primaryObjective.includes('revenus') || profile.primaryObjective.includes('Revenus')) {
    objective = 'income';
  }

  let horizonYears = 5;
  const matchNum = profile.firstWithdrawalHorizon.match(/\d+/);
  if (matchNum) {
    horizonYears = parseInt(matchNum[0], 10);
  } else if (profile.firstWithdrawalHorizon.includes('Court')) {
    horizonYears = 2;
  } else if (profile.firstWithdrawalHorizon.includes('Long')) {
    horizonYears = 15;
  }

  let riskTolerance = 'low_moderate';
  if (profile.riskTolerance === 'Faible') riskTolerance = 'low';
  else if (profile.riskTolerance === 'Faible à modéré') riskTolerance = 'low_moderate';
  else if (profile.riskTolerance === 'Modéré') riskTolerance = 'moderate';
  else if (profile.riskTolerance === 'Élevé') riskTolerance = 'high';

  let riskCapacity: 'low' | 'moderate' | 'high' = 'low';
  const expensesCovered = profile.essentialExpensesImpact?.includes('couvertes') ?? false;
  const hasEmergencyFund = profile.capitalNeedNext12Months?.includes('urgence') ?? false;
  const noWithdrawalSoon =
    horizonYears >= 3 || (profile.withdrawalMethod && profile.withdrawalMethod.includes('Réinvestissement'));

  if (expensesCovered && hasEmergencyFund) {
    riskCapacity = noWithdrawalSoon ? 'high' : 'moderate';
  } else if (expensesCovered || hasEmergencyFund) {
    riskCapacity = 'moderate';
  }

  const constraints: string[] = [];
  if (profile.cryptoPreference.includes('Exclusion totale') || profile.cryptoPreference.includes('0 %')) {
    constraints.push('no_crypto');
  }
  if (profile.esgImportance.includes('Prioritaire') || profile.esgImportance.includes('strict')) {
    constraints.push('esg_only', 'no_controversies');
  }
  if (profile.excludedCategories) {
    profile.excludedCategories.forEach((ex) => {
      // Only constraints the engine implements are sent (see screening.py).
      if (ex.includes('fossiles')) constraints.push('esg_only', 'no_controversies');
      if (ex.includes('Cryptoactifs')) constraints.push('no_crypto');
    });
  }

  // Map questionnaire labels to the preference tokens the scenario builder understands
  // (PREFERENCE_SECTORS in alphaforge/nodes/scenarios.py); other labels pass through.
  const preferences: string[] = profile.interestedSectors.map((s) =>
    /tech|ia\b/i.test(s) ? 'likes_tech' : s
  );
  if (/modérée|majeurs/i.test(profile.cryptoPreference) && !preferences.includes('likes_crypto')) {
    preferences.push('likes_crypto');
  }

  // Contextual information appended to request_text so Agent 1 and LLM prompt
  // see all investor background, loss tolerance, account type and notes.
  const contextParts: string[] = [];
  if (profile.ageRange && profile.ageRange !== 'Non spécifié') {
    contextParts.push(`Tranche d'âge : ${profile.ageRange}`);
  }
  if (profile.familySituation && profile.familySituation !== 'Non spécifié') {
    contextParts.push(`Situation familiale : ${profile.familySituation}`);
  }
  if (profile.accountType) {
    contextParts.push(`Type de compte : ${profile.accountType}`);
  }
  if (profile.maxLossTolerance) {
    contextParts.push(`Tolérance de perte sur 12 mois : ${profile.maxLossTolerance} %`);
  }
  if (profile.sectorConcentrationLimit) {
    contextParts.push(`Plafond sectoriel : ${profile.sectorConcentrationLimit}`);
  }
  if (profile.additionalNotes?.trim()) {
    contextParts.push(`Remarques libres : ${profile.additionalNotes.trim()}`);
  }

  let fullRequestText = requestText;
  if (contextParts.length > 0) {
    fullRequestText = `${requestText}\n\n[Contexte investisseur]\n${contextParts.join('\n')}`;
  }

  let maxLossPct: number | null = null;
  const parsedLoss = parseFloat(profile.maxLossTolerance);
  if (!isNaN(parsedLoss)) {
    maxLossPct = parsedLoss;
  }

  const payload: BackendRunPayload = {
    persona: 'custom_user',
    request_text: fullRequestText,
    user_profile: profile,
    profile_data: {
      objective,
      horizon_years: horizonYears,
      risk_tolerance: riskTolerance,
      risk_capacity: riskCapacity,
      constraints: Array.from(new Set(constraints)),
      preferences,
      budget_cad: profile.simulatedCapital,
      max_loss_pct: maxLossPct,
      notes: profile.additionalNotes,
    },
  };

  console.log('[AlphaForge] Payload prepared for backend execution:', payload);
  return payload;
}
