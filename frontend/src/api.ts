/**
 * Typed API client for AlphaForge AI backend (PRD 6).
 */

import {
  AuthUser,
  GraphState,
  LoginResponse,
  PersonaMeta,
  SavedRunSummary,
  SSEEvent,
  SuitabilityRecord,
  UserProfileData,
  WhatIfDiff,
} from './types';

const API_BASE = '';

const TOKEN_KEY = 'alphaforge_auth_token';
const USER_KEY = 'alphaforge_auth_user';

export function getAuthToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    // ignore
  }
}

export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user: AuthUser | null): void {
  try {
    if (user) {
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(USER_KEY);
    }
  } catch {
    // ignore
  }
}

export function clearAuth(): void {
  setAuthToken(null);
  setStoredUser(null);
}

/** Random per-browser session id: the server only shows a run to the session that started it. */
function clientId(): string {
  try {
    let id = localStorage.getItem('alphaforge_client_id');
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem('alphaforge_client_id', id);
    }
    return id;
  } catch {
    return 'anonymous';
  }
}

export function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('X-Client-Id', clientId());
  const token = getAuthToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return fetch(url, { ...init, headers });
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const res = await apiFetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Nom d’utilisateur ou mot de passe incorrect.');
  }
  const data = (await res.json()) as LoginResponse;
  setAuthToken(data.access_token || data.id_token || '');
  setStoredUser(data.user);
  return data;
}

export async function register(
  username: string,
  password: string,
  email?: string
): Promise<LoginResponse> {
  const res = await apiFetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, email: email || undefined }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Échec lors de la création du compte.');
  }
  const data = (await res.json()) as LoginResponse;
  setAuthToken(data.access_token || data.id_token || '');
  setStoredUser(data.user);
  return data;
}

export function logout(): void {
  clearAuth();
}

export async function fetchCurrentUser(): Promise<{ user: AuthUser; profile?: Record<string, unknown> }> {
  const res = await apiFetch(`${API_BASE}/auth/me`);
  if (!res.ok) {
    clearAuth();
    throw new Error('Non authentifié');
  }
  const data = await res.json();
  if (data.user) {
    setStoredUser(data.user);
  }
  return data;
}

export async function fetchUserProfile(): Promise<UserProfileData> {
  const res = await apiFetch(`${API_BASE}/user/profile`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Impossible de récupérer le profil.');
  }
  return res.json();
}

export async function updateUserProfile(payload: {
  profile: Record<string, unknown>;
  account_type?: string | null;
  current_holdings?: Record<string, unknown> | null;
}): Promise<UserProfileData> {
  const res = await apiFetch(`${API_BASE}/user/profile`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Impossible de mettre à jour le profil.');
  }
  return res.json();
}

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await apiFetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function fetchPersonas(): Promise<Record<string, PersonaMeta>> {
  const res = await apiFetch(`${API_BASE}/personas`);
  if (!res.ok) throw new Error(`Failed to fetch personas: ${res.statusText}`);
  return res.json();
}

export async function createRun(
  persona: string,
  requestText: string,
  asOfDate?: string,
  extraPayload?: Partial<BackendRunPayload>
): Promise<{ run_id: string }> {
  const res = await apiFetch(`${API_BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      persona,
      request_text: requestText,
      language: extraPayload?.language || null,
      as_of_date: asOfDate || null,
      profile_data: extraPayload?.profile_data || null,
      user_profile: extraPayload?.user_profile || null,
      current_holdings:
        extraPayload?.current_holdings || extraPayload?.profile_data?.current_holdings || null,
    }),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to create run: ${res.statusText}`);
  }
  return res.json();
}

export async function answerRun(runId: string, text: string): Promise<{ run_id: string; status: string }> {
  const res = await apiFetch(`${API_BASE}/runs/${runId}/answer`, {
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
  const res = await apiFetch(`${API_BASE}/runs/${runId}`);
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to fetch run state: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchSavedRuns(persona?: string): Promise<SavedRunSummary[]> {
  const url = persona ? `${API_BASE}/runs?persona=${encodeURIComponent(persona)}` : `${API_BASE}/runs`;
  const res = await apiFetch(url);
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
  const res = await apiFetch(`${API_BASE}/runs/${parentId}/whatif`, {
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
  const res = await apiFetch(`${API_BASE}/runs/${childRunId}/diff`);
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to fetch what-if diff: ${res.statusText}`);
  }
  return res.json();
}

export async function reviewRun(
  runId: string,
  chosenScenario: string,
  rationale: string,
  editedAssumptions?: Record<string, unknown> | null
): Promise<{ status: string; run_id: string; reviewer_id: string; reviewed_at: string; chosen_scenario: string }> {
  const res = await apiFetch(`${API_BASE}/runs/${runId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chosen_scenario: chosenScenario,
      rationale,
      edited_assumptions: editedAssumptions || null,
    }),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Échec de la validation du conseiller: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchSuitabilityRecord(runId: string): Promise<SuitabilityRecord> {
  const res = await apiFetch(`${API_BASE}/runs/${runId}/suitability`);
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Dossier de convenance introuvable: ${res.statusText}`);
  }
  return res.json();
}

export function getSuitabilityPdfUrl(runId: string): string {
  const token = getAuthToken();
  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${API_BASE}/runs/${runId}/suitability/pdf${tokenParam}`;
}

export function subscribeRunEvents(
  runId: string,
  onEvent: (event: SSEEvent) => void,
  onError?: (error: unknown) => void
): () => void {
  const token = getAuthToken();
  const tokenParam = token ? `&token=${encodeURIComponent(token)}` : '';
  const source = new EventSource(
    `${API_BASE}/runs/${runId}/events?client=${encodeURIComponent(clientId())}${tokenParam}`
  );

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

import { UserOnboardingProfile, BackendRunPayload, UniverseAsset } from './types';
import { toProfileData, UNIVERSE_FALLBACK } from './lib/questionnaireCodes';

/** The 31-asset universe for ticker autocomplete (#175); the bundled copy when offline. */
export async function fetchUniverse(): Promise<UniverseAsset[]> {
  try {
    const res = await apiFetch(`${API_BASE}/universe`);
    if (!res.ok) return UNIVERSE_FALLBACK;
    const rows = (await res.json()) as UniverseAsset[];
    return Array.isArray(rows) && rows.length > 0 ? rows : UNIVERSE_FALLBACK;
  } catch {
    return UNIVERSE_FALLBACK;
  }
}

/**
 * Saves the questionnaire as the user's one server profile (#170): the engine profile derived
 * by `toProfileData` plus the raw questionnaire, so a later login restores it. The server
 * assigns the version number and appends the dated diff to the dossier.
 */
export async function saveQuestionnaire(profile: UserOnboardingProfile): Promise<UserProfileData> {
  const data = toProfileData(profile);
  return updateUserProfile({
    profile: { ...data, questionnaire: profile },
    account_type: data.account_type || null,
    current_holdings: (data.current_holdings as Record<string, number> | undefined) || null,
  });
}

/** The questionnaire stored in a server profile, if any (restored on login, #170). */
export function questionnaireOf(data: UserProfileData | null | undefined): UserOnboardingProfile | null {
  const q = data?.profile?.questionnaire as UserOnboardingProfile | undefined;
  if (!q || typeof q !== 'object' || !q.primaryObjective) return null;
  return { ...q, profileVersion: data?.profile_version ?? q.profileVersion ?? null };
}

/**
 * Prepares the payload for the AlphaForge multi-agent backend (POST /runs).
 * `profile_data` is exactly what `saveQuestionnaire` stored: codes only, limits included.
 */
export function prepareBackendPayload(
  profile: UserOnboardingProfile,
  requestText: string,
  language?: 'fr' | 'en'
): BackendRunPayload {
  const profileData = toProfileData(profile);
  const payload: BackendRunPayload = {
    persona: 'custom_user',
    request_text: requestText.trim(),
    language,
    user_profile: profile,
    current_holdings: profileData.current_holdings as Record<string, number> | undefined,
    profile_data: profileData,
  };
  return payload;
}
