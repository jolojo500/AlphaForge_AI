import React from 'react';
import { Evidence } from '../types';
import { fixScenarioCount, scenarioName } from '@/lib/labels';

/**
 * Plain-language rendering of the verified text.
 *
 * The text itself is never rewritten here: numbers stay exactly as the verifier checked them.
 * Evidence ids such as "[EP3]" become a popover beside the number that carries the detail,
 * and internal identifiers (scenario and metric names) are shown by their display name.
 */

type Lang = 'fr' | 'en';

const SCENARIO_CODES = ['as_requested', 'capped', 'profile_baseline', 'current'];

const METRIC: Record<string, [string, string]> = {
  volatility_ann: ['Amplitude des variations (volatilité annualisée)', 'Size of the swings (annualised volatility)'],
  max_drawdown: ['Pire baisse historique', 'Worst historical fall'],
  stress_2022: ['Résultat pendant le choc de 2022', 'Result during the 2022 shock'],
  stress_2022_drawdown: ['Pire baisse pendant 2022', 'Worst fall during 2022'],
  top_weight: ['Plus grosse position', 'Largest position'],
  sector_concentration_hhi: ['Concentration par secteur', 'Concentration by sector'],
  effective_sectors: ['Nombre de secteurs effectifs', 'Effective number of sectors'],
  us_exposure: ['Part investie aux États-Unis', 'Share invested in the United States'],
  currency_usd_exposure: ['Part en dollars américains', 'Share in US dollars'],
  tax_drag: ['Coût fiscal estimé par an', 'Estimated yearly tax cost'],
  fee_drag: ['Frais des fonds par an', 'Fund fees per year'],
  fx_conversion_cost: ['Coût de conversion de devise', 'Currency conversion cost'],
  all_in_cost: ['Coût total estimé par an', 'Estimated total yearly cost'],
  etf_mer: ['Frais de gestion du fonds', 'Fund management fee'],
  esg_proxy_share: ['Part dans des titres détenus par ESGV', 'Share in securities held by ESGV'],
  caps: ['Plafonds de référence du profil', 'Profile reference caps'],
  correlation: ['Corrélation historique', 'Historical correlation'],
  etf_overlap: ['Chevauchement entre fonds', 'Fund overlap'],
  avg_daily_traded_value_20d_cad: ['Valeur quotidienne moyenne échangée', 'Average daily traded value'],
  turnover: ['Part du portefeuille à remanier', 'Share of the portfolio to reshuffle'],
  rolling_1y_worst: ['Pire période de 1 an (historique)', 'Worst 1-year window (historical)'],
  rolling_1y_median: ['Période médiane de 1 an (historique)', 'Median 1-year window (historical)'],
  rolling_1y_best: ['Meilleure période de 1 an (historique)', 'Best 1-year window (historical)'],
  rolling_1y_loss_share: ['Part des périodes de 1 an en perte', 'Share of losing 1-year windows'],
  rolling_3y_worst: ['Pire période de 3 ans (historique)', 'Worst 3-year window (historical)'],
  rolling_3y_median: ['Période médiane de 3 ans (historique)', 'Median 3-year window (historical)'],
  rolling_3y_best: ['Meilleure période de 3 ans (historique)', 'Best 3-year window (historical)'],
  rolling_3y_loss_share: ['Part des périodes de 3 ans en perte', 'Share of losing 3-year windows'],
  policy_rate_ca: ['Taux directeur, Canada', 'Policy rate, Canada'],
  policy_rate_us: ['Taux directeur, États-Unis', 'Policy rate, United States'],
  yield_2y_ca: ['Taux à 2 ans, Canada', '2-year yield, Canada'],
  yield_10y_ca: ['Taux à 10 ans, Canada', '10-year yield, Canada'],
  yield_2y_us: ['Taux à 2 ans, États-Unis', '2-year yield, United States'],
  yield_10y_us: ['Taux à 10 ans, États-Unis', '10-year yield, United States'],
  curve_slope_ca: ['Pente de la courbe des taux, Canada', 'Yield curve slope, Canada'],
  curve_slope_us: ['Pente de la courbe des taux, États-Unis', 'Yield curve slope, United States'],
  cpi_yoy_ca: ['Inflation sur un an, Canada', 'Year-over-year inflation, Canada'],
  cpi_yoy_us: ['Inflation sur un an, États-Unis', 'Year-over-year inflation, United States'],
  unemployment_ca: ['Taux de chômage, Canada', 'Unemployment rate, Canada'],
  unemployment_us: ['Taux de chômage, États-Unis', 'Unemployment rate, United States'],
  eth_tvl: ['Valeur totale bloquée sur Ethereum', 'Total value locked on Ethereum'],
  eth_tvl_change_30d: ['Variation sur 30 jours de la valeur bloquée sur Ethereum', '30-day change in Ethereum value locked'],
  eth_tvl_change_365d: ['Variation sur un an de la valeur bloquée sur Ethereum', '1-year change in Ethereum value locked'],
  stablecoin_supply_usd: ['Offre totale de cryptomonnaies stables en USD', 'Total USD stablecoin supply'],
  stablecoin_change_30d: ["Variation sur 30 jours de l'offre de cryptomonnaies stables", '30-day change in stablecoin supply'],
  btc_price_defillama: ['Cours du Bitcoin (DefiLlama)', 'Bitcoin price (DefiLlama)'],
  eth_price_defillama: ["Cours de l'Ether (DefiLlama)", 'Ether price (DefiLlama)'],
  btc_price_cross_check: ['Écart entre deux sources pour le cours du Bitcoin', 'Gap between two sources for the Bitcoin price'],
  news: ['Actualité datée', 'Dated news item'],
  news_items_retained: ["Nombre d'actualités retenues", 'Number of news items retained'],
};

const PREFIX: Record<string, [string, string]> = {
  ES: ["Règle d'admissibilité", 'Eligibility rule'],
  EQ: ['Mesure de risque historique', 'Historical risk measure'],
  EM: ['Indicateur économique', 'Economic indicator'],
  EN: ['Actualité datée', 'Dated news item'],
  EP: ['Indicateur de portefeuille', 'Portfolio indicator'],
  EK: ['Information du profil', 'Profile information'],
};

const pick = (pair: [string, string] | undefined, lang: Lang) => (pair ? pair[lang === 'en' ? 1 : 0] : undefined);

/** Readable name of an evidence item: what it measures, and for which scenario or asset. */
export function evidenceLabel(ev: Evidence | undefined, lang: Lang, id?: string): string {
  const eid = ev?.id ?? id ?? '';
  const fallback = pick(PREFIX[eid.slice(0, 2)], lang) ?? (lang === 'en' ? 'Evidence' : 'Preuve');
  if (!ev || typeof ev.value !== 'object' || ev.value === null) return fallback;
  const v = ev.value as Record<string, unknown>;
  const metric = typeof v.metric === 'string' ? v.metric : undefined;
  const base = (metric && pick(METRIC[metric], lang)) ?? fallback;
  const scenario = typeof v.scenario === 'string' ? scenarioName(v.scenario, lang) : undefined;
  const ticker =
    typeof v.ticker === 'string'
      ? v.ticker
      : Array.isArray(v.tickers)
      ? (v.tickers as unknown[]).join(' + ')
      : undefined;
  const detail = scenario ?? ticker;
  return detail ? `${base} · ${detail}` : base;
}

/** Internal identifiers that may appear in the text, shown by their display name. */
export function humanize(text: string, lang: Lang, scenarioCount?: number): string {
  let out = text;
  for (const key of SCENARIO_CODES) {
    const name = scenarioName(key, lang);
    // "le scénario profile_baseline" -> "le profil de référence"; "le scénario capped" -> "la version ajustée à vos limites"
    out = out.replace(new RegExp(`\\b(?:le |the )?(?:scénario|scenario) ${key}\\b`, 'gi'), name);
    out = out.replace(new RegExp(`\\b${key}\\b`, 'g'), name);
  }
  // Older wording of the scenario names, aligned with the explanation.
  if (lang === 'en') {
    out = out.replace(/\b(?:the )?capped scenario\b/gi, scenarioName('capped', 'en'));
    out = out.replace(/\b(?:the )?(?:raw )?requested scenario\b/gi, scenarioName('as_requested', 'en'));
  } else {
    out = out.replace(/\b(?:le |du |au )?sc[ée]nario plafonn[ée]\b/gi, scenarioName('capped', 'fr'));
    out = out.replace(/\b(?:le |du |au )?sc[ée]nario (?:brut )?demand[ée]\b/gi, scenarioName('as_requested', 'fr'));
  }
  for (const [key, pair] of Object.entries(METRIC)) {
    if (!key.includes('_')) continue; // only identifiers, never ordinary words
    out = out.replace(new RegExp(`\\b${key}\\b`, 'g'), pick(pair, lang)!.toLowerCase());
  }
  if (scenarioCount) out = fixScenarioCount(out, scenarioCount, lang);
  return out;
}

// A number (with sign, decimals, unit) directly followed by its evidence id, or a lone id.
const TOKEN = /((?:[-−+]?\d[\d\s.,]*\d|\d)(?:\s?(?:%|\$|CAD|USD|ans|years?))?)\s*\[(E[A-Z]\d+)\]|\[(E[A-Z]\d+)\]/g;

interface RichTextProps {
  text: string;
  evidence: Record<string, Evidence>;
  /** Opens the full evidence registry at this row (the popover's "see it in the registry"). */
  onJump: (id: string) => void;
  lang: Lang;
  /** Number of scenarios shown, so "les trois scénarios" agrees with the cards. */
  scenarioCount?: number;
}

const NUMBER_CLASS =
  'font-medium text-primary underline decoration-dotted decoration-primary/50 underline-offset-2 hover:decoration-solid cursor-pointer whitespace-nowrap';
const LONE_CLASS =
  'text-[11px] text-primary underline decoration-dotted underline-offset-2 hover:decoration-solid cursor-pointer whitespace-nowrap';

/** Text with each evidence reference turned into a popover beside the cited number. */
export const RichText: React.FC<RichTextProps> = ({ text, evidence, onJump, lang, scenarioCount }) => {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  TOKEN.lastIndex = 0;
  while ((m = TOKEN.exec(text)) !== null) {
    if (m.index > last) nodes.push(humanize(text.slice(last, m.index), lang, scenarioCount));
    const id = m[2] ?? m[3];
    const ev = evidence[id];
    const label = evidenceLabel(ev, lang, id);
    const where = ev ? ` — ${ev.source}, ${ev.date}` : '';
    const title = `${label}${where} (${lang === 'en' ? 'see the evidence' : 'voir la preuve'} ${id})`;
    const key = `${id}-${m.index}`;
    const content = m[1]
      ? m[1].trim()
      : `(${lang === 'en' ? `see evidence ${id}` : `voir la preuve ${id}`})`;
    const className = m[1] ? NUMBER_CLASS : LONE_CLASS;
    nodes.push(
      <button
        key={key}
        type="button"
        title={title}
        aria-label={title}
        onClick={() => onJump(id)}
        className={className}
      >
        {content}
      </button>
    );
    last = TOKEN.lastIndex;
  }
  if (last < text.length) nodes.push(humanize(text.slice(last), lang, scenarioCount));
  return <>{nodes}</>;
};
