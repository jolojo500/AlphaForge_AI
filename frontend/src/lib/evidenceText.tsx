import React from 'react';
import { Evidence } from '../types';

/**
 * Plain-language rendering of the verified text.
 *
 * The text itself is never rewritten here: numbers stay exactly as the verifier checked them.
 * Evidence ids such as "[EP3]" become links that carry a readable label and jump to the
 * evidence detail, and internal identifiers (scenario and metric names) are shown by their
 * display name.
 */

type Lang = 'fr' | 'en';

const SCENARIO: Record<string, [string, string]> = {
  as_requested: ['scénario demandé', 'requested scenario'],
  capped: ['scénario plafonné', 'capped scenario'],
  profile_baseline: ['profil de référence', 'reference profile'],
  current: ['portefeuille actuel', 'current portfolio'],
};

const METRIC: Record<string, [string, string]> = {
  volatility_ann: ['Volatilité annualisée historique', 'Historical annualized volatility'],
  max_drawdown: ['Baisse maximale historique', 'Historical maximum drawdown'],
  stress_2022: ['Rendement pendant le choc de 2022', 'Return during the 2022 stress'],
  stress_2022_drawdown: ['Baisse maximale pendant 2022', 'Maximum drawdown during 2022'],
  top_weight: ['Poids de la plus grosse ligne', 'Largest position weight'],
  sector_concentration_hhi: ['Concentration sectorielle (indice HHI)', 'Sector concentration (HHI index)'],
  us_exposure: ['Exposition aux États-Unis', 'U.S. exposure'],
  tax_drag: ['Friction fiscale estimée', 'Estimated tax drag'],
  fee_drag: ['Frais de gestion pondérés', 'Weighted management fees'],
  etf_mer: ['Frais de gestion du fonds', 'Fund management fee'],
  esg_proxy_share: ['Part dans des titres du fonds ESGV (indicateur indirect)', 'Share in ESGV fund holdings (indirect indicator)'],
  caps: ['Plafonds de référence du profil', 'Profile reference caps'],
  correlation: ['Corrélation historique', 'Historical correlation'],
  etf_overlap: ['Chevauchement entre fonds', 'Fund overlap'],
  avg_daily_traded_value_20d_cad: ['Valeur quotidienne moyenne échangée', 'Average daily traded value'],
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
  EM: ['Indicateur macroéconomique', 'Macroeconomic indicator'],
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
  const scenario = typeof v.scenario === 'string' ? pick(SCENARIO[v.scenario], lang) : undefined;
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
export function humanize(text: string, lang: Lang): string {
  let out = text;
  for (const [key, pair] of Object.entries(SCENARIO)) {
    const name = pick(pair, lang)!;
    // "le scénario profile_baseline" -> "le profil de référence"; "le scénario capped" -> "le scénario plafonné"
    out = out.replace(new RegExp(`\\b(?:scénario|scenario) ${key}\\b`, 'gi'), name);
    out = out.replace(new RegExp(`\\b${key}\\b`, 'g'), name);
  }
  for (const [key, pair] of Object.entries(METRIC)) {
    if (!key.includes('_')) continue; // only identifiers, never ordinary words
    out = out.replace(new RegExp(`\\b${key}\\b`, 'g'), pick(pair, lang)!.toLowerCase());
  }
  return out;
}

// A number (with sign, decimals, unit) directly followed by its evidence id, or a lone id.
const TOKEN = /((?:[-−+]?\d[\d\s.,]*\d|\d)(?:\s?(?:%|\$|CAD|USD|ans|years?))?)\s*\[(E[A-Z]\d+)\]|\[(E[A-Z]\d+)\]/g;

interface RichTextProps {
  text: string;
  evidence: Record<string, Evidence>;
  onJump: (id: string) => void;
  lang: Lang;
}

/** Text with each evidence reference turned into a readable link to its detail. */
export const RichText: React.FC<RichTextProps> = ({ text, evidence, onJump, lang }) => {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  TOKEN.lastIndex = 0;
  while ((m = TOKEN.exec(text)) !== null) {
    if (m.index > last) nodes.push(humanize(text.slice(last, m.index), lang));
    const id = m[2] ?? m[3];
    const ev = evidence[id];
    const label = evidenceLabel(ev, lang, id);
    const where = ev ? ` — ${ev.source}, ${ev.date}` : '';
    const title = `${label}${where} (${lang === 'en' ? 'see the detail' : 'voir le détail'}, ${id})`;
    if (m[1]) {
      nodes.push(
        <a
          key={`${id}-${m.index}`}
          href={`#evidence-row-${id}`}
          title={title}
          aria-label={title}
          onClick={(e) => {
            e.preventDefault();
            onJump(id);
          }}
          className="font-medium text-primary underline decoration-dotted decoration-primary/50 underline-offset-2 hover:decoration-solid cursor-pointer whitespace-nowrap"
        >
          {m[1].trim()}
        </a>
      );
    } else {
      nodes.push(
        <a
          key={`${id}-${m.index}`}
          href={`#evidence-row-${id}`}
          title={title}
          aria-label={title}
          onClick={(e) => {
            e.preventDefault();
            onJump(id);
          }}
          className="text-[11px] text-primary underline decoration-dotted underline-offset-2 hover:decoration-solid cursor-pointer whitespace-nowrap"
        >
          ({lang === 'en' ? 'detail' : 'détail'})
        </a>
      );
    }
    last = TOKEN.lastIndex;
  }
  if (last < text.length) nodes.push(humanize(text.slice(last), lang));
  return <>{nodes}</>;
};
