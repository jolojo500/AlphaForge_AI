/**
 * Mirrors alphaforge/state.py and API contracts (PRD 3.3, 6).
 */

export type PersonaId = 'amira' | 'mateo' | 'robert' | 'custom_user' | string;
export type ScenarioName = 'as_requested' | 'capped' | 'profile_baseline';

export const SCENARIO_NAMES: ScenarioName[] = ['as_requested', 'capped', 'profile_baseline'];

export const SCENARIO_METRIC_LABELS: Record<string, string> = {
  volatility_ann: 'Volatilité annuelle',
  max_drawdown: 'Perte max historique',
  stress_2022: 'Stress test 2022',
  top_weight: 'Poids principal',
  sector_concentration_hhi: 'Concentration (HHI)',
  us_exposure: 'Exposition US',
};

export interface Profile {
  persona: PersonaId;
  objective: string;
  horizon_years: number;
  risk_tolerance: 'low' | 'low_moderate' | 'moderate' | 'high';
  risk_capacity: 'low' | 'moderate' | 'high';
  constraints: string[];
  preferences: string[];
  budget_cad: number | null;
  request_type: 'build' | 'judge';
  requested_idea: { ticker: string; weight: number } | null;
  excluded_tickers: string[];
  conflicts: string[];
  clarification_needed: string | null;
}

export interface Evidence {
  id: string;
  value: number | string | Record<string, unknown>;
  source: string;
  date: string;
  date_kind: 'observation' | 'publication';
  url: string | null;
  method: string;
  confidence: 'fact' | 'assumption' | 'fictional';
}

export interface Scenario {
  name: ScenarioName;
  weights: Record<string, number>;
  metrics: Record<string, string>;
  notes: string[];
}

export interface TraceEntry {
  node: string;
  started_at: string;
  ended_at: string;
  summary: string;
}

export interface SavedRunSummary {
  run_id: string;
  persona: string;
  as_of_date: string;
  request_text: string;
  created_at: string;
  status: string;
  verification_passed?: boolean;
  is_golden?: boolean;
}

export interface Exclusion {
  ticker: string;
  reason: string;
  evidence_id: string;
}

export interface EventItem {
  ticker?: string;
  headline: string;
  published_at: string;
  relevant: boolean;
  kind: string;
  risk_type: string;
  material: boolean;
  evidence_id: string;
}

export interface Objection {
  scenario: string;
  objection: string;
  evidence: string[];
  severity: 'blocking' | 'warning';
}

export interface ClaimWithEvidence {
  claim: string;
  evidence: string[];
}

export interface Explanation {
  resume: string;
  quelles_donnees: ClaimWithEvidence[];
  pourquoi_ce_choix: ClaimWithEvidence[];
  limites: ClaimWithEvidence[];
  ce_qui_changerait_la_reponse: ClaimWithEvidence[];
  incertitude: string;
  scenario_le_plus_coherent: ScenarioName;
  avertissement: string;
}

export interface Verification {
  passed: boolean;
  errors: string[];
}

export interface GraphState {
  as_of_date: string;
  persona: PersonaId;
  request_text: string;
  profile: Profile | null;
  eligible_universe: string[];
  exclusions: Exclusion[];
  evidence: Record<string, Evidence>;
  events: EventItem[];
  scenarios: Scenario[];
  objections: Objection[];
  explanation: Explanation | null;
  verification: Verification | null;
  retries: Record<string, number>;
  trace: TraceEntry[];
  run_id?: string;
}

export interface PersonaMeta {
  label: string;
  objective: string;
  horizon_years: number;
  risk_tolerance: string;
  risk_capacity: string;
  constraints: string[];
  preferences: string[];
  budget_cad: number | null;
  example_request: string;
}

export type SSEEvent =
  | { type: 'trace'; entry: TraceEntry }
  | { type: 'interrupt'; question: string }
  | { type: 'final'; run_id: string }
  | { type: 'error'; error: string; message?: string };

export interface WhatIfChange {
  field: string;
  value: unknown;
}

export interface WeightDelta {
  old: number;
  new: number;
  delta: number;
}

export interface MetricDelta {
  old: number | null;
  new: number | null;
  delta: number | null;
  old_eid?: string;
  new_eid?: string;
}

export interface ScenarioDiff {
  weights: Record<string, WeightDelta>;
  metrics: Record<string, MetricDelta>;
  notes: {
    old: string[];
    new: string[];
  };
}

export interface WhatIfDiff {
  scenarios: Record<ScenarioName, ScenarioDiff>;
  summary: string[];
  change?: WhatIfChange;
  parent_run_id?: string;
  child_run_id?: string;
}

export interface UserOnboardingProfile {
  // Step 1: Identité, situation & expérience
  ageRange: string;
  familySituation: string;
  investmentExperience: 'Débutant' | 'Intermédiaire' | 'Avancé' | '';
  businessModelsUnderstanding: string | string[];

  // Step 2: Objectifs & paramètres financiers
  primaryObjective: string;
  firstWithdrawalHorizon: string;
  withdrawalMethod: string;
  simulatedCapital: number;
  simulatedCapitalFormatted: string;
  accountType: string;

  // Step 3: Tolérance au risque & garde-fous
  riskTolerance: 'Faible' | 'Faible à modéré' | 'Modéré' | 'Élevé' | '';
  maxLossTolerance: string;
  sectorConcentrationLimit: string;
  capitalNeedNext12Months: string;
  essentialExpensesImpact: string;

  // Step 4: Préférences & exclusions
  interestedSectors: string[];
  cryptoPreference: string;
  esgImportance: string;
  excludedCategories?: string[];
  currencyPreference?: string;

  // Step 5: Informations supplémentaires
  additionalNotes: string;
  fictionalCapitalAcknowledged: boolean;

  completedAt: string;
}

export interface BackendRunPayload {
  persona: string;
  request_text: string;
  user_profile?: UserOnboardingProfile;
  profile_data?: {
    objective: string;
    horizon_years: number;
    risk_tolerance: string;
    risk_capacity: string;
    constraints: string[];
    preferences: string[];
    budget_cad: number | null;
    max_loss_pct?: number | null;
    notes?: string;
  };
}
