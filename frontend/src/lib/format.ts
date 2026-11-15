import type { Evidence, MetricName, ScenarioName, Tolerance } from '@/types'

export const SCENARIO_LABEL: Record<ScenarioName, string> = {
  as_requested: 'Tel que demandé',
  capped: 'Plafonné',
  profile_baseline: 'Référence du profil',
}

export const SCENARIO_HELP: Record<ScenarioName, string> = {
  as_requested: 'Votre idée telle quelle, le reste du portefeuille suivant le profil.',
  capped: 'Votre idée avec les plafonds de concentration du profil.',
  profile_baseline: 'Allocation à risque minimal sous les contraintes du profil.',
}

export const METRIC_LABEL: Record<MetricName, string> = {
  volatility_ann: 'Volatilité annualisée',
  max_drawdown: 'Perte maximale',
  stress_2022: 'Stress 2022',
  top_weight: 'Plus grosse position',
  sector_concentration_hhi: 'Concentration sectorielle (HHI)',
  us_exposure: 'Exposition États-Unis',
}

export const TOLERANCE_LABEL: Record<Tolerance, string> = {
  low: 'Faible',
  low_moderate: 'Faible à modérée',
  moderate: 'Modérée',
  high: 'Élevée',
}

export const CAPACITY_LABEL = { low: 'Faible', moderate: 'Modérée', high: 'Élevée' } as const

export const NODE_LABEL: Record<string, string> = {
  profile: 'Profil',
  screening: 'Filtrage',
  quant: 'Statistiques',
  macro: 'Macro',
  events: 'Actualités',
  scenarios: 'Scénarios',
  red_team: 'Relecture critique',
  explain: 'Explication',
  verifier: 'Vérification',
}
export const NODE_ORDER = Object.keys(NODE_LABEL)

export const CONFIDENCE_LABEL = {
  fact: 'Fait',
  assumption: 'Hypothèse',
  fictional: 'Fictif',
} as const

export const CONSTRAINT_LABEL: Record<string, string> = {
  no_crypto: 'Pas de crypto',
  esg_only: 'ESG uniquement',
  no_controversies: 'Sans controverse',
}

export const PREFERENCE_LABEL: Record<string, string> = {
  likes_tech: 'Aime la techno',
  likes_crypto: 'Aime la crypto',
  wants_diversification: 'Veut se diversifier',
  wants_balance: 'Veut un équilibre',
}

export const humanize = (tag: string, dict: Record<string, string>) =>
  dict[tag] ?? tag.replace(/_/g, ' ')

/** The number carried by an evidence entry, if any. */
export function evidenceNumber(ev: Evidence | undefined): number | null {
  if (!ev) return null
  const v = ev.value
  if (typeof v === 'number') return v
  if (typeof v === 'object' && v !== null && typeof v.value === 'number') return v.value
  return null
}

export function evidenceText(ev: Evidence): string {
  const v = ev.value
  if (typeof v === 'object' && v !== null) {
    const parts = [v.metric, v.scenario, v.ticker, Array.isArray(v.tickers) ? v.tickers.join('/') : null]
      .filter(Boolean)
      .join(' ')
    const val = typeof v.value === 'number' ? fmtNumber(v.value) : String(v.value ?? '')
    return `${parts} = ${val}${v.unit && v.unit !== 'ratio' ? ` ${String(v.unit)}` : ''}`
  }
  return typeof v === 'number' ? fmtNumber(v) : String(v)
}

export const fmtNumber = (n: number) =>
  new Intl.NumberFormat('fr-CA', { maximumSignificantDigits: 4 }).format(n)

export const fmtPct = (n: number, digits = 1) =>
  new Intl.NumberFormat('fr-CA', { style: 'percent', minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n)

export function fmtMetric(metric: MetricName | string, value: number | null): string {
  if (value === null) return '—'
  return metric === 'sector_concentration_hhi' ? value.toFixed(2) : fmtPct(value)
}

export const fmtMoney = (n: number) =>
  new Intl.NumberFormat('fr-CA', { style: 'currency', currency: 'CAD', maximumFractionDigits: 0 }).format(n)
