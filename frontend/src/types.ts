/**
 * Mirrors alphaforge/state.py and API contracts (PRD 3.3, 6).
 */

export type PersonaId = 'amira' | 'mateo' | 'robert' | 'custom_user' | string;
export type ScenarioName = 'as_requested' | 'capped' | 'profile_baseline' | 'current';

export const SCENARIO_NAMES: ScenarioName[] = ['as_requested', 'capped', 'profile_baseline'];

export const SCENARIO_METRIC_LABELS: Record<string, string> = {
  volatility_ann: 'Volatilité annuelle',
  max_drawdown: 'Perte max historique',
  stress_2022: 'Stress test 2022',
  top_weight: 'Poids principal',
  sector_concentration_hhi: 'Concentration (HHI)',
  us_exposure: 'Exposition US',
  tax_drag: 'Friction fiscale estimée',
  fee_drag: 'Frais de gestion (RFG)',
};

export interface KycField {
  name: string;
  label?: string;
  required: boolean;
  collected: boolean;
  source: 'persona' | 'questionnaire' | 'text' | 'assumption';
  value?: unknown;
  assumption_note?: string | null;
  evidence_id?: string | null;
}

export interface KycCompleteness {
  is_complete: boolean;
  score: number;
  required_fields: string[];
  optional_fields: string[];
  missing_fields: string[];
  fields: Record<string, KycField>;
}

export interface Profile {
  persona: PersonaId;
  objective: string;
  horizon_years: number;
  risk_tolerance: 'low' | 'low_moderate' | 'moderate' | 'high';
  risk_capacity: 'low' | 'moderate' | 'high';
  account_type?: 'tfsa' | 'rrsp' | 'fhsa' | 'non_registered' | 'mixed';
  constraints: string[];
  preferences: string[];
  budget_cad: number | null;
  request_type: 'build' | 'judge';
  requested_idea: { ticker: string; weight: number } | null;
  excluded_tickers: string[];
  conflicts: string[];
  clarification_needed: string | null;

  // Extra KYC fields (#117)
  has_emergency_fund?: boolean | null;
  has_high_interest_debt?: boolean | null;
  debt_level?: string | null;
  net_worth_share?: number | string | null;
  net_worth_cad?: number | null;
  liquidity_need_12m?: string | number | null;
  current_holdings?: string[];
  investment_knowledge?: string | null;
  withdrawal_plan?: string | null;
  income_stability?: string | null;
  kyc_completeness?: KycCompleteness | null;
  hard_gate_notes?: string[];
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

export interface Trade {
  ticker: string;
  current_weight: number;
  target_weight: number;
  change: number;
  action: string;
  action_en?: string;
  amount_cad?: number;
}

export interface HistoricalWindowStats {
  worst: number;
  median: number;
  best: number;
  loss_share: number;
  windows_count: number;
  window_years: number;
}

export interface HistoricalOutcomes {
  '1y'?: HistoricalWindowStats;
  '3y'?: HistoricalWindowStats;
  horizon_years?: number;
  horizon_covered?: boolean;
  disclaimer: string;
}

export interface Scenario {
  name: ScenarioName;
  weights: Record<string, number>;
  metrics: Record<string, string>;
  notes: string[];
  turnover?: number;
  trades?: Trade[];
  historical_outcomes?: HistoricalOutcomes;
}

export interface TraceEntry {
  node: string;
  started_at: string;
  ended_at: string;
  summary: string;
  model?: string;
  calls?: number;
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number;
}

export interface RunCostModel {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  latency_ms: number;
  cost_usd: number;
  cost_cad: number;
}

export interface RunCost {
  cost_cad: number;
  cost_usd: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  total_latency_ms: number;
  calls: number;
  is_estimate: boolean;
  pricing_source: string;
  pricing_date: string;
  usd_to_cad_rate: number;
  confidence: string;
  models: Record<string, RunCostModel>;
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
  /** Set on a what-if run (the server fills it when it lists runs). */
  parent_run_id?: string | null;
  /** The what-if change, when this run is one. */
  change?: WhatIfChange | null;
  /** Short profile summary for the history list ("Horizon 10 ans · tolérance modérée · CELI"). */
  profile_summary?: string | null;
  horizon_years?: number | null;
  risk_tolerance?: string | null;
  account_type?: string | null;
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
  cost?: RunCost;
  run_id?: string;
  // Advisor review & sign-off (#121)
  reviewed?: boolean;
  reviewer_id?: string | null;
  reviewed_at?: string | null;
  chosen_scenario?: string | null;
  advisor_rationale?: string | null;
  edited_assumptions?: Record<string, unknown> | null;
}

export interface SuitabilityRecord {
  run_id: string;
  reviewer_id: string;
  reviewed_at: string;
  chosen_scenario: string;
  rationale: string;
  edited_assumptions?: Record<string, unknown> | null;
  kyc_snapshot?: Record<string, unknown>;
  scenarios?: Scenario[];
  model_ids?: Record<string, string>;
  data_dates?: Record<string, string>;
  verifier_result?: Record<string, unknown>;
  pdf_s3_key?: string;
  pdf_s3_bucket?: string;
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
  run_a_id?: string;
  run_b_id?: string;
}

/**
 * Questionnaire answers. Every option is stored as a code (see lib/questionnaireCodes.ts);
 * legacy French labels from older saved profiles are still accepted by `codeOf`.
 */
export interface UserOnboardingProfile {
  // Step 1: Identité, situation & expérience
  ageRange: string;
  familySituation: string;
  investmentExperience: string;
  businessModelsUnderstanding: string | string[];

  // Step 2: Objectifs & paramètres financiers
  primaryObjective: string;
  firstWithdrawalHorizon: string;
  withdrawalMethod: string;
  simulatedCapital: number;
  simulatedCapitalFormatted: string;
  accountType: string;
  netWorthShare?: string;

  // Step 3: Tolérance au risque & garde-fous
  riskTolerance: string;
  maxLossTolerance: string;
  sectorConcentrationLimit: string;
  capitalNeedNext12Months: string;
  essentialExpensesImpact: string;
  debtLevel?: string;
  incomeStability?: string;

  // Step 4: Préférences & exclusions
  interestedSectors: string[];
  cryptoPreference: string;
  esgImportance: string;
  excludedCategories?: string[];
  currencyPreference?: string;

  // Step 5: Informations supplémentaires & Portefeuille existant
  additionalNotes: string;
  currentHoldingsCsv?: string;
  /** Per ticker: fraction of the portfolio (holdingsUnit "pct") or an amount in CAD ("cad"). */
  currentHoldings?: Record<string, number>;
  hasExistingHoldings?: 'none' | 'some' | '';
  holdingsUnit?: 'pct' | 'cad';
  /** Tickers outside the universe the user confirmed as "non analysé". */
  unanalysedConfirmed?: string[];
  fictionalCapitalAcknowledged: boolean;

  /** Version of the saved server profile this questionnaire corresponds to (#170). */
  profileVersion?: number | null;
  completedAt: string;
}

export interface BackendRunPayload {
  persona: string;
  request_text: string;
  language?: 'fr' | 'en';
  user_profile?: UserOnboardingProfile;
  current_holdings?: Record<string, number>;
  profile_data?: {
    objective: string;
    horizon_years: number;
    risk_tolerance: string;
    risk_capacity: string;
    account_type?: 'tfsa' | 'rrsp' | 'fhsa' | 'non_registered' | 'mixed';
    constraints: string[];
    preferences: string[];
    budget_cad: number | null;
    max_loss_pct?: number | null;
    notes?: string;
    current_holdings?: Record<string, number> | string[];
    has_emergency_fund?: boolean | null;
    has_high_interest_debt?: boolean | null;
    debt_level?: string | null;
    net_worth_share?: number | string | null;
    liquidity_need_12m?: string | null;
    investment_knowledge?: string | null;
    withdrawal_plan?: string | null;
    income_stability?: string | null;
    // Declared limits read by `declared_limits` on the server (#186)
    age_band?: string | null;
    currency_preference?: string | null;
    sector_cap_pct?: number | string | null;
    crypto_preference?: string | null;
    esg_level?: string | null;
    // Questionnaire-only answers, as codes, exported in the dossier (#170)
    objective_detail?: string;
    account_type_detail?: string;
    net_worth_share_band?: string;
    family_situation?: string | null;
    asset_familiarity?: string[];
    capital_need_12m?: string | null;
    essential_expenses_impact?: string | null;
    exclusions?: string[];
    has_existing_holdings?: string;
    holdings_unit?: string;
    holdings_unanalysed_confirmed?: string[];
    profile_version?: number | null;
    /** The raw questionnaire, kept on the server so a login restores it (#170). */
    questionnaire?: UserOnboardingProfile;
  };
}

export interface ProfileHistoryEntry {
  version: number;
  updated_at: string;
  changes: Record<string, { old: unknown; new: unknown }>;
}

export interface ProfileSummaryRow {
  key: string;
  label: string;
  value: string;
}

export interface UniverseAsset {
  ticker: string;
  name: string;
  asset_class: string;
}

export interface AuthUser {
  user_id: string;
  username: string;
  email?: string | null;
  groups?: string[];
  is_advisor?: boolean;
}

export interface UserProfileData {
  user_id: string;
  username: string;
  email?: string | null;
  profile: Record<string, unknown>;
  account_type?: string | null;
  current_holdings?: Record<string, unknown> | null;
  is_advisor?: boolean;
  updated_at?: string;
  profile_version?: number;
  profile_history?: ProfileHistoryEntry[];
  /** Every saved field with its French label, from the server's one label map (#170). */
  profile_summary?: ProfileSummaryRow[];
}

export interface LoginResponse {
  access_token: string;
  id_token?: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}
