/**
 * Typed API client for AlphaForge AI backend (PRD 6).
 */

import { GraphState, PersonaMeta, SSEEvent, WhatIfDiff } from './types';

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

  let riskCapacity = 'low';
  if (
    profile.essentialExpensesImpact.includes('couvertes') &&
    profile.capitalNeedNext12Months.includes('urgence')
  ) {
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
      if (ex.includes('controverses')) constraints.push('no_controversies');
      if (ex.includes('tabac') || ex.includes('armes')) constraints.push('no_weapons_tobacco');
      if (ex.includes('spéculatifs')) constraints.push('no_speculation');
      if (ex.includes('Cryptoactifs')) constraints.push('no_crypto');
    });
  }

  const preferences: string[] = [...profile.interestedSectors];
  if (profile.currencyPreference.includes('CAD')) {
    preferences.push('prefers_cad');
  }

  const payload: BackendRunPayload = {
    persona: 'custom_user',
    request_text: requestText,
    user_profile: profile,
    profile_data: {
      objective,
      horizon_years: horizonYears,
      risk_tolerance: riskTolerance,
      risk_capacity: riskCapacity,
      constraints,
      preferences,
      budget_cad: profile.simulatedCapital,
      notes: profile.additionalNotes,
    },
  };

  console.log('[AlphaForge] Payload prepared for backend execution:', payload);
  return payload;
}

/**
 * Creates simulated GraphState to preview multi-agent analysis results
 * without requiring the FastAPI backend to be live.
 */
export function createMockAnalysisState(
  profile: UserOnboardingProfile,
  requestText: string
): GraphState {
  const isNvda = requestText.toLowerCase().includes('nvda') || requestText.toLowerCase().includes('nvidia');

  return {
    as_of_date: '2026-02-14',
    persona: 'robert',
    request_text: requestText,
    profile: {
      persona: 'robert',
      objective: 'capital_preservation',
      horizon_years: 4,
      risk_tolerance: 'low_moderate',
      risk_capacity: 'low',
      constraints: ['no_crypto'],
      preferences: profile.interestedSectors,
      budget_cad: profile.simulatedCapital,
      request_type: isNvda ? 'judge' : 'build',
      requested_idea: isNvda ? { ticker: 'NVDA', weight: 0.25 } : null,
      excluded_tickers: ['BTC', 'ETH', 'SOL'],
      conflicts: isNvda
        ? [
            `25% dans NVDA face à une tolérance au risque Faible à modéré et un horizon de 4 ans (${profile.primaryObjective}).`,
            'Volatilité du titre (38%) incohérente avec la préservation du capital à court terme.',
          ]
        : [],
      clarification_needed: null,
    },
    eligible_universe: ['NVDA', 'MSFT', 'XBB.TO', 'VDY.TO', 'ZAG.TO', 'XIU.TO'],
    exclusions: [
      {
        ticker: 'SOL',
        reason: 'Cryptoactif exclu par la contrainte de profil (Exclusion totale 0%).',
        evidence_id: 'ev_rule_crypto',
      },
      {
        ticker: 'BTC',
        reason: 'Cryptoactif exclu par la contrainte de profil (Exclusion totale 0%).',
        evidence_id: 'ev_rule_crypto',
      },
    ],
    evidence: {
      ev_rule_crypto: {
        id: 'ev_rule_crypto',
        value: 'Exclusion crypto 0%',
        source: 'Profil investisseur questionnaire (Étape 04)',
        date: '2026-02-14',
        date_kind: 'observation',
        url: null,
        method: 'Contrainte stricte utilisateur',
        confidence: 'fact',
      },
      ev_nvda_vol: {
        id: 'ev_nvda_vol',
        value: '38.4% annualisée',
        source: 'Données historiques Yahoo Finance / BNCD',
        date: '2026-02-10',
        date_kind: 'observation',
        url: 'https://finance.yahoo.com/quote/NVDA',
        method: 'Écart-type des rendements logarithmiques sur 3 ans',
        confidence: 'fact',
      },
      ev_nvda_stress: {
        id: 'ev_nvda_stress',
        value: '-50.3%',
        source: 'Simulation historique Stress Test 2022',
        date: '2026-02-14',
        date_kind: 'observation',
        url: null,
        method: 'Backtest drawdowns 2022',
        confidence: 'fact',
      },
    },
    events: [
      {
        ticker: 'NVDA',
        headline: 'Croissance des centres de données IA et demande record',
        published_at: '2026-02-12',
        relevant: true,
        kind: 'earnings',
        risk_type: 'market',
        material: true,
        evidence_id: 'ev_nvda_vol',
      },
    ],
    scenarios: [
      {
        name: 'as_requested',
        weights: { NVDA: 0.25, 'XBB.TO': 0.45, 'VDY.TO': 0.30 },
        metrics: {
          volatility_ann: '15.8%',
          max_drawdown: '-22.4%',
          stress_2022: '-18.1%',
          top_weight: '45% (XBB.TO)',
          sector_concentration_hhi: '0.28',
          us_exposure: '25%',
        },
        notes: [
          'Scénario incluant 25% de NVDA tel que demandé.',
          'Dépasse le seuil de volatilité toléré pour une retraite dans 4 ans.',
        ],
      },
      {
        name: 'capped',
        weights: { NVDA: 0.08, 'XBB.TO': 0.52, 'VDY.TO': 0.40 },
        metrics: {
          volatility_ann: '9.2%',
          max_drawdown: '-11.3%',
          stress_2022: '-9.5%',
          top_weight: '52% (XBB.TO)',
          sector_concentration_hhi: '0.22',
          us_exposure: '8%',
        },
        notes: [
          'Exposition NVDA plafonnée à 8% pour respecter la baisse maximale tolérée de 15%.',
          'Pondération renforcée en obligations canadiennes (XBB.TO) et dividendes (VDY.TO).',
        ],
      },
      {
        name: 'profile_baseline',
        weights: { 'XBB.TO': 0.60, 'VDY.TO': 0.30, 'XIU.TO': 0.10 },
        metrics: {
          volatility_ann: '7.1%',
          max_drawdown: '-8.2%',
          stress_2022: '-7.0%',
          top_weight: '60% (XBB.TO)',
          sector_concentration_hhi: '0.20',
          us_exposure: '0%',
        },
        notes: [
          'Portefeuille de référence 100% aligné sur la préservation du capital sans titre individuel volatil.',
        ],
      },
    ],
    objections: [
      {
        scenario: 'as_requested',
        objection:
          'Une pondération de 25% dans une action de croissance technologique fait courir un risque de baisse de 22%, supérieur au seuil toléré de 15%.',
        evidence: ['ev_nvda_vol', 'ev_nvda_stress'],
        severity: 'blocking',
      },
    ],
    explanation: {
      resume:
        'Pour un départ à la retraite prévu dans 4 ans avec un objectif de préservation du capital, allouer 25% à NVIDIA présente un risque excessif face à votre seuil de tolérance (15%). Le scénario plafonné à 8% ou le profil de référence permettent de capter de la croissance tout en protégeant votre capital fictif.',
      quelles_donnees: [
        {
          claim: 'La volatilité historique de NVDA sur 3 ans atteint 38.4% et sa perte en 2022 a été de -50.3%.',
          evidence: ['ev_nvda_vol', 'ev_nvda_stress'],
        },
      ],
      pourquoi_ce_choix: [
        {
          claim: 'Le scénario plafonné (8% NVDA) maintient la perte simulée 2022 sous les 10% tout en participant au secteur IA.',
          evidence: ['ev_nvda_vol'],
        },
      ],
      limites: [
        {
          claim: 'Les simulations reposent sur des données historiques et ne constituent pas un conseil en investissement réglementé.',
          evidence: ['ev_rule_crypto'],
        },
      ],
      ce_qui_changerait_la_reponse: [
        {
          claim: 'Un allongement de votre horizon de retraite au-delà de 8 ans permettrait une part action plus substantielle.',
          evidence: [],
        },
      ],
      incertitude: 'Faible sur le risque de marché; incertitude moyenne sur les gains technologiques futurs.',
      scenario_le_plus_coherent: 'capped',
      avertissement:
        'Simulation pédagogique et second avis automatisé. Aucune transaction réelle ne sera exécutée.',
    },
    verification: {
      passed: true,
      errors: [],
    },
    retries: {},
    trace: [
      {
        node: 'profile',
        started_at: '2026-02-14T10:00:00Z',
        ended_at: '2026-02-14T10:00:01Z',
        summary: 'Profil utilisateur chargé depuis le questionnaire (Horizon: 4 ans, Objectif: Préservation).',
      },
      {
        node: 'screening',
        started_at: '2026-02-14T10:00:01Z',
        ended_at: '2026-02-14T10:00:02Z',
        summary: 'Exclusion des cryptomonnaies (0% crypto). Filtrage univers 6 titres éligibles.',
      },
      {
        node: 'quant',
        started_at: '2026-02-14T10:00:02Z',
        ended_at: '2026-02-14T10:00:03Z',
        summary: 'Calcul des 3 scénarios (as_requested, capped, profile_baseline) et métriques de risque.',
      },
      {
        node: 'red_team',
        started_at: '2026-02-14T10:00:03Z',
        ended_at: '2026-02-14T10:00:04Z',
        summary: 'Alerte objection levée sur as_requested (dépassement perte max 15%).',
      },
      {
        node: 'explain',
        started_at: '2026-02-14T10:00:04Z',
        ended_at: '2026-02-14T10:00:05Z',
        summary: 'Génération de l’explication transparente avec preuves reliées.',
      },
    ],
    run_id: 'run_mock_preview',
  };
}
