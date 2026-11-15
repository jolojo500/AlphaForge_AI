// Hand-written mirror of alphaforge/state.py and the API payloads (PRD 6).
// Keep in sync when the contract changes.

export type PersonaId = 'amira' | 'mateo' | 'robert'
export type ScenarioName = 'as_requested' | 'capped' | 'profile_baseline'
export type Tolerance = 'low' | 'low_moderate' | 'moderate' | 'high'

export const SCENARIO_NAMES: ScenarioName[] = ['as_requested', 'capped', 'profile_baseline']
export const SCENARIO_METRICS = [
  'volatility_ann',
  'max_drawdown',
  'stress_2022',
  'top_weight',
  'sector_concentration_hhi',
  'us_exposure',
] as const
export type MetricName = (typeof SCENARIO_METRICS)[number]

export interface Persona {
  id: PersonaId
  label: string
  objective: string
  horizon_years: number
  risk_tolerance: Tolerance
  risk_capacity: 'low' | 'moderate' | 'high'
  constraints: string[]
  preferences: string[]
  budget_cad: number | null
  example_request: string
}

export interface Profile {
  persona: PersonaId
  objective: string
  horizon_years: number
  risk_tolerance: Tolerance
  risk_capacity: 'low' | 'moderate' | 'high'
  constraints: string[]
  preferences: string[]
  budget_cad: number | null
  request_type: 'build' | 'judge'
  requested_idea: { ticker: string; weight: number } | null
  excluded_tickers: string[]
  conflicts: string[]
  clarification_needed: string | null
}

export interface Evidence {
  id: string
  value: number | string | Record<string, unknown>
  source: string
  date: string
  date_kind: 'observation' | 'publication'
  url: string | null
  method: string
  confidence: 'fact' | 'assumption' | 'fictional'
}

export interface Scenario {
  name: ScenarioName
  weights: Record<string, number>
  metrics: Record<string, string>
  notes: string[]
}

export interface Claim {
  claim: string
  evidence: string[]
}

export interface Explanation {
  resume: string
  quelles_donnees: Claim[]
  pourquoi_ce_choix: Claim[]
  limites: Claim[]
  ce_qui_changerait_la_reponse: Claim[]
  incertitude: string
  scenario_le_plus_coherent: ScenarioName
  avertissement: string
}

export interface Exclusion {
  ticker: string
  reason: string
  evidence_id: string
}

export interface Objection {
  scenario: ScenarioName
  objection: string
  evidence: string[]
  severity: 'blocking' | 'warning'
}

export interface TraceEntry {
  node: string
  started_at: string
  ended_at: string
  summary: string
}

export interface GraphState {
  as_of_date: string
  persona: PersonaId
  request_text: string
  profile: Profile | null
  eligible_universe: string[]
  exclusions: Exclusion[]
  evidence: Record<string, Evidence>
  events: Record<string, unknown>[]
  scenarios: Scenario[]
  objections: Objection[]
  explanation: Explanation | null
  verification: { passed: boolean; errors: string[] } | null
  retries: Record<string, number>
  trace: TraceEntry[]
}

export type RunEvent =
  | { seq: number; type: 'trace'; entry: TraceEntry }
  | { seq: number; type: 'interrupt'; question: string }
  | { seq: number; type: 'final'; run_id: string }
  | { seq: number; type: 'error'; message: string }

export type RunStatus = 'running' | 'waiting' | 'done' | 'error'

export interface MetricDiff {
  old: number | null
  new: number | null
  delta: number | null
  old_evidence: string | null
  new_evidence: string | null
}

export interface Diff {
  profile: Record<string, { old: unknown; new: unknown }>
  eligible_universe: { added: string[]; removed: string[] }
  scenarios: Record<
    string,
    {
      weights: Record<string, { old: number; new: number; delta: number }>
      metrics: Record<string, MetricDiff>
    }
  >
  most_coherent: { old: ScenarioName | null; new: ScenarioName | null; changed: boolean }
  verification: { old: boolean | null; new: boolean | null }
}

export interface RunResponse {
  run_id: string
  parent_run_id: string | null
  status: RunStatus
  question: string | null
  error: string | null
  persona: PersonaId
  request_text: string
  as_of_date: string
  change: { field: string; value: unknown } | null
  state: GraphState | null
  diff: Diff | null
}

export type WhatIfField =
  | 'horizon_years'
  | 'budget_cad'
  | 'risk_tolerance'
  | 'exclude_ticker'
  | 'as_of_date'
