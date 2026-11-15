/**
 * Plain-language names for everything the engine identifies by a code: scenarios, metrics,
 * profile values, graph nodes, and the calculation methods recorded on evidence items.
 * French first; English for the EN toggle.
 */

import type { Lang } from './format';

const pick = (pair: [string, string], lang: Lang) => pair[lang === 'en' ? 1 : 0];
const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

// ------------------------------------------------------------------------------- scenarios
// The same names the explanation uses, so a card and the answer never call a scenario two things.
const SCENARIO_NAME: Record<string, [string, string]> = {
  as_requested: ['votre demande telle quelle', 'your request as is'],
  capped: ['la version ajustée à vos limites', 'the version adjusted to your limits'],
  profile_baseline: ['le profil de référence', 'the reference profile'],
  current: ['votre portefeuille actuel', 'your current portfolio'],
};

const SCENARIO_SUBTITLE: Record<string, [string, string]> = {
  as_requested: ['Votre idée intégrée sans ajustement', 'Your idea included without adjustment'],
  capped: ['La même idée, ramenée dans vos garde-fous', 'The same idea, brought within your limits'],
  profile_baseline: ['Allocation type pour votre profil, sans votre idée', 'Standard allocation for your profile, without your idea'],
  current: ['Les positions que vous avez déclarées', 'The holdings you declared'],
};

/** Lower-case form for use inside a sentence ("… dans la version ajustée à vos limites"). */
export function scenarioName(code: string, lang: Lang): string {
  const pair = SCENARIO_NAME[code];
  return pair ? pick(pair, lang) : code;
}

/** Capitalised form for a card or column title. */
export function scenarioTitle(code: string, lang: Lang): string {
  return cap(scenarioName(code, lang));
}

export function scenarioSubtitle(code: string, lang: Lang): string {
  const pair = SCENARIO_SUBTITLE[code];
  return pair ? pick(pair, lang) : lang === 'en' ? 'Portfolio simulation' : 'Simulation de portefeuille';
}

const COUNT_FR = ['zéro', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf'];
const COUNT_EN = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];

/** "trois" / "three" for a count of scenarios; digits beyond nine. */
export function countWord(n: number, lang: Lang): string {
  const words = lang === 'en' ? COUNT_EN : COUNT_FR;
  return n >= 0 && n < words.length ? words[n] : String(n);
}

/** Make "les trois scénarios" agree with the number of scenarios actually shown. */
export function fixScenarioCount(text: string, n: number, lang: Lang): string {
  if (n < 2 || n > 9) return text;
  const words = lang === 'en' ? COUNT_EN : COUNT_FR;
  const wrong = words.filter((_, i) => i >= 2 && i !== n);
  const noun = lang === 'en' ? 'scenarios?' : 'scénarios?';
  const re = new RegExp(`\\b(${wrong.join('|')})(\\s+)(${noun})\\b`, 'gi');
  return text.replace(re, (_m, w: string, sp: string, nn: string) => {
    const word = words[n];
    return `${w[0] === w[0].toUpperCase() ? cap(word) : word}${sp}${nn}`;
  });
}

// --------------------------------------------------------------------------------- metrics
export interface MetricInfo {
  label: string;
  tip: string;
  /** How the raw value is shown: a ratio as "%", a plain number, or a ratio in basis of 2 decimals. */
  kind: 'pct' | 'pct2' | 'number' | 'text';
}

const METRIC_INFO: Record<string, { fr: [string, string]; en: [string, string]; kind: MetricInfo['kind'] }> = {
  volatility_ann: {
    fr: [
      'Amplitude des variations (volatilité)',
      "Écart-type annualisé des rendements quotidiens sur l'historique disponible, en dollars canadiens. Plus le chiffre est élevé, plus la valeur a bougé d'un jour à l'autre.",
    ],
    en: [
      'Size of the swings (volatility)',
      'Annualised standard deviation of daily returns over the available history, in Canadian dollars. The higher the number, the more the value moved from one day to the next.',
    ],
    kind: 'pct',
  },
  max_drawdown: {
    fr: [
      'Pire baisse historique',
      "Plus grande chute entre un sommet et un creux de la valeur du portefeuille sur l'historique disponible (environ 5 ans), en dollars canadiens.",
    ],
    en: [
      'Worst historical fall',
      'Largest fall from a peak to a trough of the portfolio value over the available history (about 5 years), in Canadian dollars.',
    ],
    kind: 'pct',
  },
  stress_2022: {
    fr: [
      'Résultat pendant le choc de 2022',
      'Rendement total en dollars canadiens du 3 janvier au 30 décembre 2022, une année de hausse rapide des taux où actions et obligations ont baissé ensemble.',
    ],
    en: [
      'Result during the 2022 shock',
      'Total return in Canadian dollars from 3 January to 30 December 2022, a year of fast rate rises where stocks and bonds fell together.',
    ],
    kind: 'pct',
  },
  stress_2022_drawdown: {
    fr: ['Pire baisse pendant 2022', 'Plus grande chute entre un sommet et un creux au cours de 2022, en dollars canadiens.'],
    en: ['Worst fall during 2022', 'Largest fall from a peak to a trough during 2022, in Canadian dollars.'],
    kind: 'pct',
  },
  top_weight: {
    fr: ['Plus grosse position', "Poids de la ligne la plus importante. Une position lourde concentre le risque sur un seul titre."],
    en: ['Largest position', 'Weight of the biggest line. A heavy position concentrates the risk on a single security.'],
    kind: 'pct',
  },
  sector_concentration_hhi: {
    fr: [
      'Concentration par secteur',
      "Indice de Herfindahl des poids par secteur, de 0 à 100 %. Proche de 0 : réparti entre beaucoup de secteurs ; proche de 100 % : un seul secteur.",
    ],
    en: [
      'Concentration by sector',
      'Herfindahl index of the weights by sector, from 0 to 100%. Near 0: spread across many sectors; near 100%: a single sector.',
    ],
    kind: 'pct',
  },
  effective_sectors: {
    fr: ['Nombre de secteurs effectifs', "Inverse de la concentration par secteur : combien de secteurs « comptent vraiment » dans le portefeuille."],
    en: ['Effective number of sectors', 'Inverse of the sector concentration: how many sectors really count in the portfolio.'],
    kind: 'number',
  },
  us_exposure: {
    fr: ['Part investie aux États-Unis', 'Poids des actifs cotés aux États-Unis. Les cryptomonnaies ne sont pas comptées.'],
    en: ['Share invested in the United States', 'Weight of US-listed assets. Cryptocurrencies are not counted.'],
    kind: 'pct',
  },
  currency_usd_exposure: {
    fr: ['Part en dollars américains', 'Poids des actifs cotés en dollars américains (BTC et ETH comptés en USD). Cette part subit les variations du taux de change.'],
    en: ['Share in US dollars', 'Weight of assets priced in US dollars (BTC and ETH count as USD). This share moves with the exchange rate.'],
    kind: 'pct',
  },
  tax_drag: {
    fr: [
      'Coût fiscal estimé par an',
      "Impôt annuel estimé sur les dividendes et les intérêts, selon le type de compte (CELI, REER, non enregistré) et les rendements historiques. Une estimation, pas un calcul fiscal personnel.",
    ],
    en: [
      'Estimated yearly tax cost',
      'Estimated yearly tax on dividends and interest, given the account type (TFSA, RRSP, non-registered) and historical yields. An estimate, not personal tax advice.',
    ],
    kind: 'pct2',
  },
  fee_drag: {
    fr: ['Frais des fonds par an', 'Moyenne pondérée des ratios de frais de gestion (RFG) des fonds détenus. Les actions et cryptomonnaies détenues en direct comptent 0.'],
    en: ['Fund fees per year', 'Weighted average of the management expense ratios (MER) of the funds held. Directly held stocks and crypto count as 0.'],
    kind: 'pct2',
  },
  fx_conversion_cost: {
    fr: ['Coût de conversion de devise', 'Coût ponctuel estimé pour convertir en dollars américains la part du portefeuille cotée en USD.'],
    en: ['Currency conversion cost', 'Estimated one-time cost to convert the USD-priced share of the portfolio into US dollars.'],
    kind: 'pct2',
  },
  all_in_cost: {
    fr: ['Coût total estimé par an', 'Frais des fonds + coût de conversion de devise sur la part en USD + coût fiscal estimé.'],
    en: ['Estimated total yearly cost', 'Fund fees + currency conversion cost on the USD share + estimated tax cost.'],
    kind: 'pct2',
  },
  esg_proxy_share: {
    fr: [
      'Part dans des titres détenus par ESGV',
      "Part du portefeuille placée dans des actions américaines présentes dans le fonds ESGV. Indicateur indirect : ce n'est pas une note ESG, et les actions canadiennes, les obligations et l'or ne sont pas couverts.",
    ],
    en: [
      'Share in securities held by ESGV',
      'Share of the portfolio in US stocks that the ESGV fund holds. An indirect indicator: not an ESG score, and Canadian stocks, bonds and gold are not covered.',
    ],
    kind: 'pct',
  },
  turnover: {
    fr: ['Part du portefeuille à remanier', 'Moitié de la somme des écarts entre les poids actuels et les poids cibles : la part du portefeuille qui changerait de main.'],
    en: ['Share of the portfolio to reshuffle', 'Half the sum of the gaps between current and target weights: the share of the portfolio that would change hands.'],
    kind: 'pct',
  },
};

export function metricInfo(code: string, lang: Lang): MetricInfo {
  const m = METRIC_INFO[code];
  if (!m) return { label: code.replace(/_/g, ' '), tip: '', kind: 'pct' };
  const [label, tip] = lang === 'en' ? m.en : m.fr;
  return { label, tip, kind: m.kind };
}

export function metricLabel(code: string, lang: Lang): string {
  return metricInfo(code, lang).label;
}

// -------------------------------------------------------------------------- profile values
const TOLERANCE: Record<string, [string, string]> = {
  low: ['faible', 'low'],
  low_moderate: ['faible à modérée', 'low to moderate'],
  moderate: ['modérée', 'moderate'],
  high: ['élevée', 'high'],
};

const ACCOUNT: Record<string, [string, string]> = {
  tfsa: ['CELI', 'TFSA'],
  rrsp: ['REER', 'RRSP'],
  fhsa: ['CELIAPP', 'FHSA'],
  resp: ['REEE', 'RESP'],
  non_registered: ['non enregistré', 'non-registered'],
  mixed: ['mixte (plusieurs comptes)', 'mixed (several accounts)'],
};

const OBJECTIVE: Record<string, [string, string]> = {
  growth: ['croissance', 'growth'],
  balanced: ['équilibré', 'balanced'],
  capital_preservation: ['préservation du capital', 'capital preservation'],
  income: ['revenus réguliers', 'regular income'],
};

export function toleranceLabel(code: string | null | undefined, lang: Lang): string {
  if (!code) return '—';
  const pair = TOLERANCE[code];
  return pair ? pick(pair, lang) : code;
}

export function accountLabel(code: string | null | undefined, lang: Lang): string {
  if (!code) return '—';
  const pair = ACCOUNT[code];
  return pair ? pick(pair, lang) : code;
}

export function objectiveLabel(code: string | null | undefined, lang: Lang): string {
  if (!code) return '—';
  const pair = OBJECTIVE[code];
  return pair ? pick(pair, lang) : code;
}

/** The value of a what-if change, in words ("modérée", "CELI", "12 ans"). */
export function whatIfValueLabel(field: string | undefined, value: unknown, lang: Lang): string {
  const v = value == null ? '' : String(value);
  switch (field) {
    case 'risk_tolerance':
      return toleranceLabel(v, lang);
    case 'account_type':
      return accountLabel(v, lang);
    case 'horizon_years':
      return lang === 'en' ? `${v} years` : `${v} ans`;
    case 'budget_cad': {
      const n = Number(value);
      return Number.isFinite(n)
        ? `${n.toLocaleString(lang === 'en' ? 'en-CA' : 'fr-CA', { maximumFractionDigits: 0 })}\u00a0$`
        : v;
    }
    default:
      return v;
  }
}

/** The field of a what-if change, in words ("Tolérance au risque"). */
export function whatIfFieldLabel(field: string | undefined, lang: Lang): string {
  const names: Record<string, [string, string]> = {
    risk_tolerance: ['Tolérance au risque', 'Risk tolerance'],
    account_type: ['Type de compte', 'Account type'],
    horizon_years: ['Horizon de placement', 'Investment horizon'],
    budget_cad: ['Budget simulé', 'Simulated budget'],
    exclude_ticker: ['Actif exclu', 'Excluded asset'],
    as_of_date: ["Date d'analyse", 'Analysis date'],
  };
  if (!field) return lang === 'en' ? 'Custom assumption' : 'Hypothèse personnalisée';
  const pair = names[field];
  return pair ? pick(pair, lang) : field.replace(/_/g, ' ');
}

// ---------------------------------------------------------------------------- graph nodes
export const NODE_ORDER = [
  'profile',
  'screening',
  'quant',
  'macro',
  'events',
  'scenarios',
  'red_team',
  'explain',
  'verifier',
] as const;

/** Fixed time budget per node, in seconds, for the remaining-time estimate while a run streams. */
export const NODE_BUDGET_S: Record<string, number> = {
  profile: 15,
  screening: 2,
  quant: 2,
  macro: 2,
  events: 15,
  scenarios: 15,
  red_team: 15,
  explain: 15,
  verifier: 2,
};

const NODE_NAME: Record<string, [string, string]> = {
  profile: ['Lecture de votre profil et de votre demande', 'Reading your profile and request'],
  screening: ['Filtrage des actifs admissibles', 'Screening eligible assets'],
  quant: ['Mesures de risque historiques', 'Historical risk measures'],
  macro: ['Contexte économique', 'Economic context'],
  events: ['Actualités récentes', 'Recent news'],
  scenarios: ['Construction des scénarios', 'Building the scenarios'],
  red_team: ['Relecture critique', 'Critical second reading'],
  explain: ["Rédaction de l'explication", 'Writing the explanation'],
  verifier: ['Vérification des chiffres', 'Checking the numbers'],
};

export function nodeLabel(node: string, lang: Lang): string {
  const pair = NODE_NAME[node];
  return pair ? pick(pair, lang) : node;
}

// ------------------------------------------------------------------------ evidence methods
// The engine records how each number was computed, mostly in English. Known phrases are
// shown in French; anything unknown stays as recorded so nothing is hidden.
const METHOD_PATTERNS: Array<[RegExp, string]> = [
  [/^annualised std of daily log returns of the scenario rebalanced daily, CAD/i, 'écart-type annualisé des rendements quotidiens du scénario (rééquilibré chaque jour), en CAD'],
  [/^largest peak-to-trough fall of the scenario value, CAD/i, 'plus grande baisse entre un sommet et un creux de la valeur du scénario, en CAD'],
  [/^largest peak-to-trough fall of the CAD price/i, 'plus grande baisse du cours en CAD entre un sommet et un creux'],
  [/^total return of the scenario in CAD over 2022-01-03\.\.2022-12-30/i, 'rendement total du scénario en CAD du 3 janvier au 30 décembre 2022'],
  [/^max drawdown in CAD within 2022-01-03\.\.2022-12-30/i, 'baisse maximale en CAD entre le 3 janvier et le 30 décembre 2022'],
  [/^largest single weight in the scenario/i, 'poids de la plus grosse position du scénario'],
  [/^Herfindahl index of the weights by universe sector label/i, 'indice de Herfindahl des poids par secteur'],
  [/^1 \/ Herfindahl index of the weights by universe sector label/i, "inverse de l'indice de Herfindahl des poids par secteur"],
  [/^weight in US-listed assets \(crypto not counted\)/i, 'poids des actifs cotés aux États-Unis (cryptomonnaies non comptées)'],
  [/^estimated annual tax drag based on historical dividend\/interest yields and account tax rules/i, "coût fiscal annuel estimé d'après les rendements historiques en dividendes et intérêts et les règles du compte"],
  [/^weighted average management expense ratio \(MER\) across holdings/i, 'moyenne pondérée des ratios de frais de gestion (RFG) des titres détenus'],
  [/^share of the weights in assets priced in USD \(BTC-USD and ETH-USD count as USD\)/i, 'part des poids dans des actifs cotés en USD (BTC-USD et ETH-USD comptés en USD)'],
  [/^fee drag \+ one-time FX conversion cost on the USD-priced share \+ estimated annual tax drag/i, 'frais des fonds + coût ponctuel de conversion de devise sur la part en USD + coût fiscal annuel estimé'],
  [/^caps for the lower of tolerance \((\w+)\) and capacity \((\w+)\)/i, 'plafonds selon le plus prudent de la tolérance ($1) et de la capacité ($2)'],
  [/^scenario retry rule \(PRD 5\.8 loop contract\)/i, 'règle de nouvelle tentative du scénario'],
  [/^requested ticker kept for comparison/i, 'titre demandé conservé pour la comparaison'],
  [/^mapping of non-universe assets to closest 31-asset equivalent/i, "correspondance des actifs hors univers avec l'équivalent le plus proche parmi les 31 actifs analysés"],
  [/^assets outside the 31-asset universe without proxy are kept at their declared/i, 'actifs hors des 31 analysés et sans équivalent : conservés à leur poids déclaré, non analysés'],
  [/^largest lines kept, then closest portfolio under the same caps with a minimum line size/i, 'plus grosses lignes conservées, puis portefeuille le plus proche sous les mêmes plafonds avec une taille minimale par ligne'],
  [/^declared weights, never rescaled: analysed part, not-analysed part, cash remainder/i, "poids déclarés, jamais remis à l'échelle : part analysée, part non analysée, reste en liquidités"],
  [/^check that every requested asset and weight is present in as_requested/i, 'vérification que chaque actif et poids demandés figurent dans votre demande telle quelle'],
  [/^requested_allocation \/ requested_idea mapped to universe tickers/i, 'allocation ou idée demandée rapportée aux titres de l’univers analysé'],
  [/^baseline calibration for a high-risk growth profile \(middle of the equity band\)/i, "calibrage de référence pour un profil croissance à risque élevé (milieu de la fourchette d'actions)"],
  [/^Rolling (\d)-year historical window \((\d+) windows\), CAD\. Historique, pas une prévision\./i, 'fenêtres glissantes de $1 an(s) sur l’historique ($2 fenêtres), en CAD. Historique, pas une prévision.'],
  [/^0\.5 \* \(sum\(abs\(target_weight - current_weight\)\) \+ cash used\)/i, 'moitié de la somme des écarts absolus entre poids cibles et poids actuels (+ liquidités utilisées)'],
  [/^scope of the tax-drag estimate/i, "portée de l'estimation du coût fiscal"],
  [/^persona default account type/i, 'type de compte par défaut du profil'],
  [/^average close price times reported volume on the latest available (\d+) common trading days, converted to CAD/i, 'cours de clôture moyen × volume déclaré sur les $1 derniers jours de bourse communs, converti en CAD'],
  [/^sum over shared holdings of min\(weight in A, weight in B\)/i, 'somme, sur les titres communs aux deux fonds, du plus petit des deux poids'],
  [/^holdings are a single recent snapshot, not point-in-time/i, "les positions proviennent d'un seul relevé récent, pas d'un historique daté"],
  [/^known limitation of the starter dataset/i, 'limite connue du jeu de données de départ'],
  [/^minimum (\d+) daily returns required/i, 'au moins $1 rendements quotidiens requis'],
  [/^as-of filter with assumed publication lags/i, "filtre à la date d'analyse avec des délais de publication supposés"],
  [/^coverage of the starter dataset/i, 'couverture du jeu de données de départ'],
  [/^classified by (\S+): (\w+), (\w+), material=(\w+)/i, 'classée par $1 : $2, $3, importante = $4'],
  [/^count of news items kept after the as-of filter and classification/i, "nombre d'actualités conservées après le filtre de date et la classification"],
  [/^warning recorded during live news retrieval or fallback to cache/i, 'avertissement lors de la récupération des actualités en direct, ou repli sur le cache'],
  [/^esg_only: energy sector excluded \(fossil-fuel exposure\)/i, "critère ESG : secteur de l'énergie exclu (exposition aux énergies fossiles)"],
  [/^screening coverage note/i, 'note sur la couverture du filtrage'],
];

// Word-level replacements for recorded phrases that are built from several parts.
const METHOD_TOKENS: Array<[RegExp, string]> = [
  [/, historical backtest of fictional weights, /gi, ', test historique de poids fictifs, '],
  [/, historical backtest of client's current holdings, /gi, ', test historique des positions actuelles du client, '],
  [/\bEthereum chain Total Value Locked \(TVL\) from DefiLlama as-of\b/gi, 'valeur totale bloquée (TVL) sur la chaîne Ethereum selon DefiLlama au'],
  [/\b30-day relative change in Ethereum Total Value Locked \(TVL\) from DefiLlama\b/gi, 'variation relative sur 30 jours de la valeur totale bloquée (TVL) sur Ethereum, selon DefiLlama'],
  [/\b365-day relative change in Ethereum Total Value Locked \(TVL\) from DefiLlama\b/gi, 'variation relative sur 365 jours de la valeur totale bloquée (TVL) sur Ethereum, selon DefiLlama'],
  [/\bTotal circulating USD stablecoin supply from DefiLlama as-of\b/gi, 'offre totale en circulation de cryptomonnaies stables en USD, selon DefiLlama au'],
  [/\b30-day relative change in total circulating USD stablecoin supply from DefiLlama\b/gi, "variation relative sur 30 jours de l'offre totale de cryptomonnaies stables en USD, selon DefiLlama"],
  [/\bBitcoin \(BTC\) price in USD from DefiLlama as-of\b/gi, 'cours du Bitcoin (BTC) en USD selon DefiLlama au'],
  [/\bEther \(ETH\) price in USD from DefiLlama as-of\b/gi, "cours de l'Ether (ETH) en USD selon DefiLlama au"],
  [/\bCross-check: DefiLlama BTC price\b/gi, 'recoupement : cours du BTC selon DefiLlama'],
  [/\bvs provider BTC close\b/gi, 'contre la clôture du BTC chez le fournisseur'],
  [/; observation /gi, ' ; observation du '],
  [/\bassumed published\b/gi, 'publication supposée le'],
  [/\blatest value known on\b/gi, 'dernière valeur connue au'],
  [/\b% change y\/y\b/gi, 'variation sur un an en %'],
  [/\bU\.S\. CPI\b/g, 'IPC américain'],
  [/\bcomputed from the SA index\b/gi, "calculée à partir de l'indice désaisonnalisé"],
  [/\bwindows\b/gi, 'fenêtres'],
  [/\bas-of\b/gi, "à la date d'analyse"],
];

/** The calculation method of an evidence item, in the language of the UI when known. */
export function methodLabel(method: string | undefined | null, lang: Lang): string {
  const raw = (method || '').trim();
  if (!raw || lang === 'en') return raw;
  for (const [re, repl] of METHOD_PATTERNS) {
    if (re.test(raw)) {
      let out = raw.replace(re, repl);
      for (const [tre, trepl] of METHOD_TOKENS) out = out.replace(tre, trepl);
      return out;
    }
  }
  let out = raw;
  for (const [tre, trepl] of METHOD_TOKENS) out = out.replace(tre, trepl);
  // Tolerance and capacity codes inside a sentence ("tolerance (moderate)").
  out = out.replace(/\((low_moderate|moderate|low|high)\)/g, (_m, c: string) => `(${toleranceLabel(c, 'fr')})`);
  return out;
}

export function dateKindLabel(kind: string | undefined, lang: Lang): string {
  if (kind === 'publication') return lang === 'en' ? 'published' : 'publication';
  if (kind === 'observation') return lang === 'en' ? 'observed' : 'observation';
  return kind || '';
}

export function confidenceLabel(confidence: string | undefined, lang: Lang): string {
  switch (confidence) {
    case 'fact':
      return lang === 'en' ? 'Verified fact' : 'Fait vérifié';
    case 'assumption':
      return lang === 'en' ? 'Assumption' : 'Hypothèse';
    case 'fictional':
      return lang === 'en' ? 'Fictional (simulation)' : 'Fictif (simulation)';
    default:
      return confidence || '';
  }
}
