/**
 * Questionnaire options as codes (#178): every answer is stored and sent as a code, never as a
 * French label. `codeOf` also accepts the legacy labels still present in old localStorage
 * profiles and in the demo personas; `labelOf` renders a code for display.
 *
 * The backend mirror of this map is `alphaforge/questionnaire.py` (dossier export labels).
 */

import { UserOnboardingProfile, BackendRunPayload } from '../types';

export interface Option {
  code: string;
  label: string;
  info?: string;
  /** Regex on the lower-cased, accent-free legacy label (first match wins). */
  legacy?: RegExp;
}

export const AGE_OPTIONS: Option[] = [
  { code: '18-29', label: '18–29 ans' },
  { code: '30-44', label: '30–44 ans' },
  { code: '45-59', label: '45–59 ans' },
  { code: '60+', label: '60 ans et plus' },
];

export const FAMILY_OPTIONS: Option[] = [
  { code: 'single', label: 'Célibataire', legacy: /celibataire/ },
  { code: 'couple_no_children', label: 'En couple (sans enfant)', legacy: /couple|marie\(e\), sans/ },
  { code: 'family_dependents', label: 'Famille avec personnes à charge', legacy: /famille|charge|enfants? a charge/ },
  { code: 'retired_independent', label: 'Retraité / Enfants indépendants', legacy: /retrait|independant/ },
];

export const EXPERIENCE_OPTIONS: Option[] = [
  { code: 'beginner', label: 'Débutant', legacy: /debutant/ },
  { code: 'intermediate', label: 'Intermédiaire', legacy: /intermediaire/ },
  { code: 'advanced', label: 'Avancé', legacy: /avance/ },
];

export const ASSET_FAMILIARITY_OPTIONS: Option[] = [
  { code: 'listed_equities', label: 'Actions cotées en bourse', legacy: /actions/ },
  { code: 'etfs_index', label: 'FNB & Fonds indiciels', legacy: /fnb|indiciel/ },
  { code: 'bonds_fixed_income', label: 'Obligations & Titres à revenu fixe', legacy: /obligation|revenu fixe/ },
  { code: 'tech_growth', label: 'Technologies & Forte croissance', legacy: /techno|croissance/ },
  { code: 'crypto', label: 'Cryptoactifs & Actifs numériques', legacy: /crypto/ },
];

export const OBJECTIVE_OPTIONS: Option[] = [
  { code: 'growth', label: 'Croissance du capital', legacy: /^croissance du capital|^growth/ },
  { code: 'balanced', label: 'Croissance équilibrée & stabilité', legacy: /equilibr|balanced/ },
  { code: 'capital_preservation', label: 'Préservation du capital', legacy: /preservation/ },
  { code: 'income', label: 'Génération de revenus réguliers', legacy: /revenu|income/ },
  { code: 'project', label: 'Financement d’un projet spécifique', legacy: /projet/ },
];

export const WITHDRAWAL_OPTIONS: Option[] = [
  { code: 'none', label: 'Réinvestissement total (Aucun retrait)', legacy: /reinvest|aucun retrait/ },
  { code: 'regular_income', label: 'Retraits progressifs périodiques', legacy: /progressif|periodi|regulier|echelonn/ },
  { code: 'lump_sum', label: 'Décaissement unique à terme', legacy: /unique/ },
];

export const ACCOUNT_OPTIONS: Option[] = [
  {
    code: 'tfsa',
    label: "CELI · Libre d'impôt",
    info: "Compte d'épargne libre d'impôt. Tous les gains, dividendes et retraits sont 100 % non imposables au Canada. Plafond cumulatif annuel sans pénalité de retrait.",
    legacy: /^celi\b(?!app)|tfsa/,
  },
  {
    code: 'rrsp',
    label: 'REER · Épargne-retraite',
    info: "Régime enregistré d'épargne-retraite. Les cotisations sont déductibles de votre revenu imposable. La croissance est à l'abri de l'impôt jusqu'au retrait à la retraite.",
    legacy: /reer|rrsp/,
  },
  {
    code: 'fhsa',
    label: 'CELIAPP · Achat première propriété',
    info: "Compte combinant les atouts du REER et du CELI : cotisations déductibles d'impôt et retraits non taxés pour l'achat d'une première habitation (max 40 000 $).",
    legacy: /celiapp|fhsa/,
  },
  {
    code: 'non_registered',
    label: 'Non enregistré · Comptant / Marge',
    info: "Compte imposable ordinaire sans plafond de dépôt. 50 % des gains en capital sont imposables, crédits d'impôt sur dividendes canadiens admissibles.",
    legacy: /non enregistre|imposable|non.registered/,
  },
  {
    code: 'mixed',
    label: 'Portefeuille mixte · Enregistré & Imposable',
    info: "Combinaison de comptes enregistrés (REER/CELI) et non enregistrés permettant l'optimisation fiscale de la localisation des actifs (asset location).",
    legacy: /mixte|mixed/,
  },
  {
    code: 'lira_rrif',
    label: 'CRI / FERR · Revenu de retraite',
    info: 'Compte de retraite immobilisé (CRI) ou Fonds Enregistré de Revenu de Retraite (FERR) soumis à des retraits annuels obligatoires calculés selon l’âge.',
    legacy: /\bcri\b|ferr/,
  },
];

export const NET_WORTH_OPTIONS: Option[] = [
  { code: 'lt_25', label: 'Moins de 25 % · Part modérée', legacy: /moins de 25/ },
  { code: '25_50', label: 'Entre 25 % et 50 % · Part significative', legacy: /25 % et 50|25.*50/ },
  { code: 'gt_50', label: 'Plus de 50 % · Majorité du patrimoine', legacy: /plus de 50|majorite/ },
];

export const TOLERANCE_OPTIONS: Option[] = [
  { code: 'low', label: 'Faible', legacy: /^faible$|^low$/ },
  { code: 'low_moderate', label: 'Faible à modéré', legacy: /faible a modere|low_moderate/ },
  { code: 'moderate', label: 'Modéré', legacy: /^modere$|^moderate$/ },
  { code: 'high', label: 'Élevé', legacy: /eleve|^high$/ },
];

export const MAX_LOSS_OPTIONS: Option[] = [
  { code: '5', label: "Jusqu'à 5 %" },
  { code: '15', label: "Jusqu'à 15 %" },
  { code: '25', label: "Jusqu'à 25 %" },
  { code: '35', label: '35 % ou plus', legacy: /35/ },
];

export const SECTOR_CAP_OPTIONS: Option[] = [
  { code: '25', label: 'Diversification stricte · Max 25 % par secteur', legacy: /25|20 %/ },
  { code: '40', label: 'Diversification modérée · Max 40 % par secteur', legacy: /40|30 %/ },
  { code: 'none', label: 'Concentration sectorielle assumée · Sans plafond strict', legacy: /sans plafond|pas de plafond|assumee/ },
];

export const CAPITAL_NEED_OPTIONS: Option[] = [
  { code: 'reserve_separate', label: "Non, réserve d'urgence séparée", legacy: /non|aucun besoin|urgence/ },
  { code: 'need_liquidity', label: 'Oui, une partie doit rester liquide', legacy: /oui|liquide/ },
  { code: 'unknown', label: 'Indéterminé', legacy: /indetermine/ },
];

export const ESSENTIAL_EXPENSES_OPTIONS: Option[] = [
  { code: 'covered', label: 'Non, dépenses couvertes par ailleurs', legacy: /couvert|^non/ },
  { code: 'sensitive', label: 'Oui, sensible aux pertes durables', legacy: /sensible|^oui/ },
  { code: 'unknown', label: 'Indéterminé', legacy: /indetermine/ },
];

export const DEBT_OPTIONS: Option[] = [
  { code: 'none', label: 'Aucune dette ou dettes remboursées', legacy: /aucune|rembours|^none$/ },
  { code: 'mortgage_only', label: 'Prêt hypothécaire uniquement', legacy: /hypothec/ },
  { code: 'high_interest', label: 'Dettes à taux élevé (cartes de crédit, marge)', legacy: /taux eleve|carte|marge|high_interest/ },
];

export const INCOME_OPTIONS: Option[] = [
  { code: 'stable', label: 'Revenus stables (salarié permanent)', legacy: /stable/ },
  { code: 'variable', label: 'Revenus variables ou travailleur autonome', legacy: /variable|autonome/ },
  { code: 'retired_fixed', label: 'Retraité (revenu fixe de rente)', legacy: /retrait|rente/ },
];

// Sector codes are the engine's preference codes (alphaforge/personas.py PREFERENCE_CODES).
export const SECTOR_OPTIONS: Option[] = [
  { code: 'likes_tech', label: 'Technologies & IA', legacy: /techno|\bia\b/ },
  { code: 'likes_financials', label: 'Banques & Finance', legacy: /banque|financ/ },
  { code: 'likes_dividends', label: 'Dividendes & Services publics', legacy: /dividende|services publics/ },
  { code: 'likes_healthcare', label: 'Santé & Consommation', legacy: /sante|consommation/ },
  { code: 'likes_bonds', label: 'Obligations & Revenu fixe', legacy: /obligation|revenu fixe/ },
  { code: 'likes_gold', label: 'Or & Valeurs refuges', legacy: /\bor\b|refuge/ },
  { code: 'likes_energy', label: 'Énergie & Ressources', legacy: /energie|ressource/ },
  { code: 'esg_tilt', label: 'Investissement responsable & ESG (tilt)', legacy: /responsable|esg/ },
];

export const CRYPTO_OPTIONS: Option[] = [
  { code: 'none', label: 'Exclusion totale (0 % crypto)', legacy: /exclusion|0 %|aucun/ },
  { code: '1-5', label: 'Exposition prudente / modérée (1 à 5 %)', legacy: /1 a 5|prudente|moderee/ },
  { code: '5-15', label: 'Favorable / Ouvert (5 à 15 %)', legacy: /5 a 15|favorable \/ ouvert|ouvert/ },
  { code: '15+', label: 'Très favorable / Offensif (15 % et plus)', legacy: /15 % et plus|offensif|tres favorable/ },
];

export const ESG_OPTIONS: Option[] = [
  { code: 'strict', label: 'Prioritaire · Filtres stricts', legacy: /prioritaire|strict/ },
  { code: 'tilt', label: 'Secondaire · Favoriser les mieux notés', legacy: /secondaire|favoriser|tilt/ },
  { code: 'neutral', label: 'Neutre · Performance financière pure', legacy: /neutre|neutral/ },
];

export const EXCLUSION_OPTIONS: Option[] = [
  { code: 'fossil_fuels', label: 'Énergies fossiles & controverses climatiques', legacy: /fossile|climat/ },
  { code: 'crypto', label: 'Cryptoactifs & devises virtuelles', legacy: /crypto/ },
];

export const CURRENCY_OPTIONS: Option[] = [
  { code: 'cad', label: 'Priorité CAD (Dollar canadien)', legacy: /priorite cad|canadien/ },
  { code: 'mixed', label: 'Mixte CAD / USD (Canadien & Américain)', legacy: /mixte|mixed/ },
  { code: 'none', label: 'Sans contrainte de devise', legacy: /sans contrainte|aucune/ },
];

export const HOLDINGS_PRESENCE_OPTIONS: Option[] = [
  { code: 'none', label: 'Aucun avoir à déclarer' },
  { code: 'some', label: 'Oui, voici mes positions' },
];

export type QuestionField =
  | 'ageRange'
  | 'familySituation'
  | 'investmentExperience'
  | 'businessModelsUnderstanding'
  | 'primaryObjective'
  | 'withdrawalMethod'
  | 'accountType'
  | 'netWorthShare'
  | 'riskTolerance'
  | 'maxLossTolerance'
  | 'sectorConcentrationLimit'
  | 'capitalNeedNext12Months'
  | 'essentialExpensesImpact'
  | 'debtLevel'
  | 'incomeStability'
  | 'interestedSectors'
  | 'cryptoPreference'
  | 'esgImportance'
  | 'excludedCategories'
  | 'currencyPreference'
  | 'hasExistingHoldings';

export const OPTIONS: Record<QuestionField, Option[]> = {
  ageRange: AGE_OPTIONS,
  familySituation: FAMILY_OPTIONS,
  investmentExperience: EXPERIENCE_OPTIONS,
  businessModelsUnderstanding: ASSET_FAMILIARITY_OPTIONS,
  primaryObjective: OBJECTIVE_OPTIONS,
  withdrawalMethod: WITHDRAWAL_OPTIONS,
  accountType: ACCOUNT_OPTIONS,
  netWorthShare: NET_WORTH_OPTIONS,
  riskTolerance: TOLERANCE_OPTIONS,
  maxLossTolerance: MAX_LOSS_OPTIONS,
  sectorConcentrationLimit: SECTOR_CAP_OPTIONS,
  capitalNeedNext12Months: CAPITAL_NEED_OPTIONS,
  essentialExpensesImpact: ESSENTIAL_EXPENSES_OPTIONS,
  debtLevel: DEBT_OPTIONS,
  incomeStability: INCOME_OPTIONS,
  interestedSectors: SECTOR_OPTIONS,
  cryptoPreference: CRYPTO_OPTIONS,
  esgImportance: ESG_OPTIONS,
  excludedCategories: EXCLUSION_OPTIONS,
  currencyPreference: CURRENCY_OPTIONS,
  hasExistingHoldings: HOLDINGS_PRESENCE_OPTIONS,
};

const plain = (s: string): string =>
  s
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim();

/** The code of an answer: a code is returned as is, a legacy label is mapped, else null. */
export function codeOf(field: QuestionField, value: string | undefined | null): string | null {
  if (!value) return null;
  const options = OPTIONS[field];
  const raw = String(value).trim();
  const exact = options.find((o) => o.code === raw || o.label === raw);
  if (exact) return exact.code;
  const p = plain(raw);
  if (field === 'ageRange') {
    const nums = p.match(/\d+/g);
    if (!nums) return null;
    if (nums.length >= 2) return `${nums[0]}-${nums[1]}`;
    return /plus|\+|over/.test(p) ? `${nums[0]}+` : nums[0];
  }
  if (field === 'maxLossTolerance') {
    const n = parseFloat(p.replace(',', '.'));
    if (!isNaN(n)) return String(n >= 35 ? 35 : n);
  }
  const hit = options.find((o) => o.legacy && o.legacy.test(p));
  return hit ? hit.code : null;
}

export function codesOf(field: QuestionField, values: string[] | string | undefined | null): string[] {
  const list = Array.isArray(values) ? values : values ? String(values).split(', ') : [];
  const out: string[] = [];
  list.forEach((v) => {
    const c = codeOf(field, v);
    if (c && !out.includes(c)) out.push(c);
  });
  return out;
}

/** The French label of a code (or of a legacy label); unknown values are shown as typed. */
export function labelOf(field: QuestionField, value: string | undefined | null): string {
  if (!value) return 'Non renseigné';
  const code = codeOf(field, value);
  const opt = OPTIONS[field].find((o) => o.code === code);
  return opt ? opt.label : String(value);
}

export function labelsOf(field: QuestionField, values: string[] | string | undefined | null): string {
  const list = Array.isArray(values) ? values : values ? String(values).split(', ') : [];
  return list.map((v) => labelOf(field, v)).join(', ') || 'Non renseigné';
}

export function horizonYearsOf(profile: UserOnboardingProfile): number {
  const m = (profile.firstWithdrawalHorizon || '').match(/\d+/);
  if (m) return Math.min(50, Math.max(1, parseInt(m[0], 10)));
  const p = plain(profile.firstWithdrawalHorizon || '');
  if (p.includes('court')) return 2;
  if (p.includes('long')) return 15;
  return 5;
}

/** Share of the whole portfolio per ticker (fractions) from what the questionnaire stored. */
export function holdingsAsFractions(profile: UserOnboardingProfile): Record<string, number> | undefined {
  const h = profile.currentHoldings;
  if (!h || Object.keys(h).length === 0) return undefined;
  if (profile.holdingsUnit === 'cad') {
    const total = Object.values(h).reduce((a, b) => a + (b > 0 ? b : 0), 0);
    if (total <= 0) return undefined;
    const out: Record<string, number> = {};
    Object.entries(h).forEach(([t, v]) => {
      if (v > 0) out[t] = Math.round((v / total) * 1e6) / 1e6;
    });
    return out;
  }
  return h;
}

export type EngineProfileData = NonNullable<BackendRunPayload['profile_data']>;

/**
 * The engine profile (codes only) derived from the questionnaire: the single function used
 * both when the profile is saved (PUT /user/profile) and when a run is started (POST /runs),
 * so what is sent with a run is exactly what was saved (#170).
 */
export function toProfileData(profile: UserOnboardingProfile): EngineProfileData {
  const objectiveCode = codeOf('primaryObjective', profile.primaryObjective) || 'balanced';
  const objective = objectiveCode === 'project' ? 'capital_preservation' : objectiveCode;
  const horizonYears = horizonYearsOf(profile);
  const riskTolerance = codeOf('riskTolerance', profile.riskTolerance) || 'moderate';
  const knowledge = codeOf('investmentExperience', profile.investmentExperience) || 'intermediate';
  const withdrawalPlan = codeOf('withdrawalMethod', profile.withdrawalMethod) || 'none';
  const capitalNeed = codeOf('capitalNeedNext12Months', profile.capitalNeedNext12Months);
  const expenses = codeOf('essentialExpensesImpact', profile.essentialExpensesImpact);
  const debtLevel = codeOf('debtLevel', profile.debtLevel) || 'none';
  const incomeStability = codeOf('incomeStability', profile.incomeStability) || 'stable';
  const netWorthBand = codeOf('netWorthShare', profile.netWorthShare);
  const netWorthShare = netWorthBand === 'lt_25' ? 0.2 : netWorthBand === '25_50' ? 0.35 : netWorthBand === 'gt_50' ? 0.65 : null;
  const accountCode = codeOf('accountType', profile.accountType) || 'non_registered';
  const accountType = (accountCode === 'lira_rrif' ? 'rrsp' : accountCode) as EngineProfileData['account_type'];
  const maxLossCode = codeOf('maxLossTolerance', profile.maxLossTolerance);
  const maxLossPct = maxLossCode ? parseFloat(maxLossCode) : null;
  const sectorCapCode = codeOf('sectorConcentrationLimit', profile.sectorConcentrationLimit);
  const sectorCapPct = sectorCapCode && sectorCapCode !== 'none' ? parseFloat(sectorCapCode) : sectorCapCode;
  const cryptoPreference = codeOf('cryptoPreference', profile.cryptoPreference);
  const esgLevel = codeOf('esgImportance', profile.esgImportance);
  const exclusions = codesOf('excludedCategories', profile.excludedCategories);
  const currencyPreference = codeOf('currencyPreference', profile.currencyPreference);
  const sectors = codesOf('interestedSectors', profile.interestedSectors);
  const assetFamiliarity = codesOf('businessModelsUnderstanding', profile.businessModelsUnderstanding);

  const hasEmergencyFund = capitalNeed === 'reserve_separate' ? true : capitalNeed === 'need_liquidity' ? false : null;
  const expensesCovered = expenses === 'covered';
  const hasHighInterestDebt = debtLevel === 'high_interest';
  const noWithdrawalSoon = horizonYears >= 3 || withdrawalPlan === 'none';
  let riskCapacity: 'low' | 'moderate' | 'high' = 'low';
  if (expensesCovered && hasEmergencyFund && !hasHighInterestDebt) {
    riskCapacity = noWithdrawalSoon ? 'high' : 'moderate';
  } else if (hasHighInterestDebt || hasEmergencyFund === false) {
    riskCapacity = 'low';
  } else if (expensesCovered || hasEmergencyFund) {
    riskCapacity = 'moderate';
  }

  const constraints: string[] = [];
  if (cryptoPreference === 'none' || exclusions.includes('crypto')) constraints.push('no_crypto');
  if (esgLevel === 'strict' || exclusions.includes('fossil_fuels')) constraints.push('esg_only', 'no_controversies');

  const preferences = [...sectors];
  if (esgLevel === 'tilt' && !preferences.includes('esg_tilt')) preferences.push('esg_tilt');
  if (cryptoPreference && cryptoPreference !== 'none' && !preferences.includes('likes_crypto')) {
    preferences.push('likes_crypto');
  }

  const unanalysed = (profile.unanalysedConfirmed || []).filter(Boolean);

  return {
    objective,
    objective_detail: objectiveCode === 'project' ? 'project' : undefined,
    horizon_years: horizonYears,
    risk_tolerance: riskTolerance,
    risk_capacity: riskCapacity,
    account_type: accountType,
    account_type_detail: accountCode === 'lira_rrif' ? 'lira_rrif' : undefined,
    constraints: Array.from(new Set(constraints)),
    preferences,
    budget_cad: profile.simulatedCapital || null,
    max_loss_pct: maxLossPct,
    notes: profile.additionalNotes,
    current_holdings: holdingsAsFractions(profile),
    has_emergency_fund: hasEmergencyFund,
    has_high_interest_debt: hasHighInterestDebt,
    debt_level: debtLevel,
    net_worth_share: netWorthShare,
    net_worth_share_band: netWorthBand || undefined,
    investment_knowledge: knowledge,
    withdrawal_plan: withdrawalPlan,
    income_stability: incomeStability,
    // Declared limits (#186): the codes `declared_limits` reads on the server.
    age_band: codeOf('ageRange', profile.ageRange),
    currency_preference: currencyPreference,
    sector_cap_pct: sectorCapPct ?? null,
    crypto_preference: cryptoPreference,
    esg_level: esgLevel,
    // Questionnaire-only answers, as codes, for the dossier export (#170).
    family_situation: codeOf('familySituation', profile.familySituation),
    asset_familiarity: assetFamiliarity,
    capital_need_12m: capitalNeed,
    essential_expenses_impact: expenses,
    exclusions,
    has_existing_holdings: profile.hasExistingHoldings || (profile.currentHoldings && Object.keys(profile.currentHoldings).length ? 'some' : 'none'),
    holdings_unit: profile.holdingsUnit || 'pct',
    holdings_unanalysed_confirmed: unanalysed,
    profile_version: profile.profileVersion ?? null,
  };
}

/** Contradictions between answers, shown inline in the questionnaire (#175). */
export function questionnaireWarnings(p: {
  riskTolerance?: string;
  maxLossTolerance?: string;
  cryptoPreference?: string;
  excludedCategories?: string[];
  interestedSectors?: string[];
  esgImportance?: string;
  hasExistingHoldings?: string;
  holdingsCount?: number;
}): string[] {
  const out: string[] = [];
  const tol = codeOf('riskTolerance', p.riskTolerance);
  const loss = codeOf('maxLossTolerance', p.maxLossTolerance);
  if (tol === 'high' && loss === '5') {
    out.push('Tolérance « Élevée » mais perte maximale de 5 % : une tolérance élevée suppose d’accepter des baisses bien plus fortes.');
  }
  if (tol === 'low' && loss === '35') {
    out.push('Tolérance « Faible » mais perte acceptée de 35 % ou plus : ces deux réponses se contredisent.');
  }
  const crypto = codeOf('cryptoPreference', p.cryptoPreference);
  const excl = codesOf('excludedCategories', p.excludedCategories);
  if (crypto && crypto !== 'none' && excl.includes('crypto')) {
    out.push('Les cryptoactifs sont exclus mais une exposition crypto est souhaitée : l’exclusion l’emportera (0 % crypto).');
  }
  const sectors = codesOf('interestedSectors', p.interestedSectors);
  if (sectors.includes('likes_energy') && excl.includes('fossil_fuels')) {
    out.push('Intérêt pour « Énergie & Ressources » mais exclusion des énergies fossiles : seuls les titres non controversés seront retenus.');
  }
  if (codeOf('esgImportance', p.esgImportance) === 'strict' && sectors.includes('likes_energy')) {
    out.push('Filtres ESG stricts et intérêt pour l’énergie : plusieurs titres du secteur seront écartés.');
  }
  if (p.hasExistingHoldings === 'none' && (p.holdingsCount || 0) > 0) {
    out.push('« Aucun avoir à déclarer » est coché alors que des positions sont listées : retirez les positions ou changez la réponse.');
  }
  return out;
}

/** Fallback copy of the 31-asset universe, used when GET /universe is unreachable. */
export const UNIVERSE_FALLBACK: { ticker: string; name: string; asset_class: string }[] = [
  { ticker: 'RY.TO', name: 'Royal Bank of Canada', asset_class: 'equity' },
  { ticker: 'TD.TO', name: 'Toronto-Dominion Bank', asset_class: 'equity' },
  { ticker: 'MFC.TO', name: 'Manulife Financial', asset_class: 'equity' },
  { ticker: 'ENB.TO', name: 'Enbridge', asset_class: 'equity' },
  { ticker: 'CNQ.TO', name: 'Canadian Natural Resources', asset_class: 'equity' },
  { ticker: 'CNR.TO', name: 'Canadian National Railway', asset_class: 'equity' },
  { ticker: 'FTS.TO', name: 'Fortis', asset_class: 'equity' },
  { ticker: 'ATD.TO', name: 'Alimentation Couche-Tard', asset_class: 'equity' },
  { ticker: 'SHOP.TO', name: 'Shopify', asset_class: 'equity' },
  { ticker: 'CSU.TO', name: 'Constellation Software', asset_class: 'equity' },
  { ticker: 'AAPL', name: 'Apple', asset_class: 'equity' },
  { ticker: 'MSFT', name: 'Microsoft', asset_class: 'equity' },
  { ticker: 'NVDA', name: 'NVIDIA', asset_class: 'equity' },
  { ticker: 'GOOGL', name: 'Alphabet', asset_class: 'equity' },
  { ticker: 'AMZN', name: 'Amazon', asset_class: 'equity' },
  { ticker: 'TSLA', name: 'Tesla', asset_class: 'equity' },
  { ticker: 'JPM', name: 'JPMorgan Chase', asset_class: 'equity' },
  { ticker: 'JNJ', name: 'Johnson & Johnson', asset_class: 'equity' },
  { ticker: 'PG', name: 'Procter & Gamble', asset_class: 'equity' },
  { ticker: 'XOM', name: 'Exxon Mobil', asset_class: 'equity' },
  { ticker: 'XIU.TO', name: 'iShares S&P/TSX 60', asset_class: 'etf_equity' },
  { ticker: 'SPY', name: 'SPDR S&P 500', asset_class: 'etf_equity' },
  { ticker: 'QQQ', name: 'Invesco QQQ', asset_class: 'etf_equity' },
  { ticker: 'ESGV', name: 'Vanguard ESG U.S. Stock', asset_class: 'etf_equity' },
  { ticker: 'XBB.TO', name: 'iShares Core Canadian Universe Bond', asset_class: 'etf_bond' },
  { ticker: 'ZST.TO', name: 'BMO Ultra Short-Term Bond', asset_class: 'etf_bond' },
  { ticker: 'AGG', name: 'iShares Core U.S. Aggregate Bond', asset_class: 'etf_bond' },
  { ticker: 'TLT', name: 'iShares 20+ Year Treasury Bond', asset_class: 'etf_bond' },
  { ticker: 'GLD', name: 'SPDR Gold Shares', asset_class: 'etf_commodity' },
  { ticker: 'BTC-USD', name: 'Bitcoin', asset_class: 'crypto' },
  { ticker: 'ETH-USD', name: 'Ethereum', asset_class: 'crypto' },
];
