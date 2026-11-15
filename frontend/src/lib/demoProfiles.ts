import { UserOnboardingProfile } from '../types';

export interface DemoPersonaMeta {
  id: 'robert' | 'amira' | 'mateo';
  name: string;
  age: number;
  role: string;
  badge: string;
  summary: string;
  tagline: string;
  canonicalQuestion: string;
  defaultQuestion: string;
  profile: UserOnboardingProfile;
}

export type DemoPersonaId = 'robert' | 'amira' | 'mateo';

export const DEMO_PERSONAS: Record<DemoPersonaId, DemoPersonaMeta> = {
  robert: {
    id: 'robert',
    name: 'Robert',
    age: 59,
    role: 'Professionnel de la santé',
    badge: 'Robert · Prudent (59 ans)',
    summary: 'Préserver le capital acquis, horizon 3 à 5 ans, tenté par les valeurs médiatisées.',
    tagline: '59 ans · Retraite dans 4 ans · Prudent',
    canonicalQuestion: 'Je m’intéresse à NVIDIA (NVDA) à hauteur de 25 %, mais je prends ma retraite dans 4 ans. Est-ce cohérent avec mon objectif de préservation du capital ?',
    defaultQuestion: 'Je m’intéresse à NVIDIA (NVDA) à hauteur de 25 %, mais je prends ma retraite dans 4 ans. Est-ce cohérent avec mon objectif de préservation du capital ?',
    profile: {
      ageRange: '50-64 ans',
      familySituation: 'Marié(e), enfants indépendants',
      investmentExperience: 'Avancé',
      businessModelsUnderstanding: 'Compréhension avancée des modèles d’affaires',
      primaryObjective: 'Préservation du capital',
      firstWithdrawalHorizon: '3 à 5 ans',
      withdrawalMethod: 'Retraits échelonnés réguliers',
      simulatedCapital: 100000,
      simulatedCapitalFormatted: '100 000 $',
      accountType: 'REER (Régime enregistré d’épargne-retraite)',
      riskTolerance: 'Faible à modéré',
      maxLossTolerance: '15',
      sectorConcentrationLimit: '20 % maximum par secteur',
      capitalNeedNext12Months: 'Aucun besoin prévu (fonds d’urgence suffisant)',
      essentialExpensesImpact: 'Mes dépenses essentielles sont entièrement couvertes',
      interestedSectors: ['Services financiers', 'Santé', 'Énergie & Services publics'],
      cryptoPreference: 'Exclusion totale (0 % crypto)',
      esgImportance: 'Neutre · Performance financière pure',
      excludedCategories: ['Cryptoactifs & devises virtuelles'],
      additionalNotes: 'Proche de la retraite, cherche de la stabilité et un second avis sur ses choix.',
      fictionalCapitalAcknowledged: true,
      completedAt: '2026-02-14T10:00:00Z',
    },
  },
  amira: {
    id: 'amira',
    name: 'Amira',
    age: 26,
    role: 'Ingénieure logicielle',
    badge: 'Amira · Audacieuse (26 ans)',
    summary: 'Faire croître son capital à long terme, ouverte à la volatilité et l’IA sans délaisser la diversification.',
    tagline: '26 ans · Horizon 15+ ans · Croissance & IA',
    canonicalQuestion: 'J’ai 100 000 $ CAD, un horizon de 15 ans et plus. J’aime la techno et la crypto mais je veux rester diversifiée.',
    defaultQuestion: 'J’ai 100 000 $ CAD, un horizon de 15 ans et plus. J’aime la techno et la crypto mais je veux rester diversifiée.',
    profile: {
      ageRange: '18-29 ans',
      familySituation: 'Célibataire sans personne à charge',
      investmentExperience: 'Intermédiaire',
      businessModelsUnderstanding: 'Bonne compréhension générale',
      primaryObjective: 'Croissance du capital',
      firstWithdrawalHorizon: '15 ans ou plus',
      withdrawalMethod: 'Réinvestissement total (Aucun retrait)',
      simulatedCapital: 100000,
      simulatedCapitalFormatted: '100 000 $',
      accountType: 'CELI — Compte d’épargne libre d’impôt',
      riskTolerance: 'Élevé',
      maxLossTolerance: '35',
      sectorConcentrationLimit: 'Pas de plafond strict',
      capitalNeedNext12Months: 'Aucun besoin prévu (fonds d’urgence suffisant)',
      essentialExpensesImpact: 'Mes dépenses essentielles sont entièrement couvertes',
      interestedSectors: ['Technologies & IA', 'Énergie & Ressources'],
      cryptoPreference: 'Exposition modérée (1 à 5 %)',
      esgImportance: 'Secondaire · Favoriser les mieux notés',
      excludedCategories: ['Aucune exclusion particulière'],
      additionalNotes: 'Ingénieure logicielle, ouverte à la volatilité mais souhaite rester diversifiée.',
      fictionalCapitalAcknowledged: true,
      completedAt: '2026-02-14T10:00:00Z',
    },
  },
  mateo: {
    id: 'mateo',
    name: 'Mateo',
    age: 41,
    role: 'Gestionnaire des opérations',
    badge: 'Mateo · Équilibré ESG (41 ans)',
    summary: 'Croissance équilibrée, horizon 8 à 12 ans, importance stricte aux critères environnementaux et sociaux.',
    tagline: '41 ans · Horizon 10 ans · Équilibré & ESG',
    canonicalQuestion: 'Je veux un portefeuille équilibré et responsable sur environ 10 ans, sans entreprises controversées.',
    defaultQuestion: 'Je veux un portefeuille équilibré et responsable sur environ 10 ans, sans entreprises controversées.',
    profile: {
      ageRange: '30-49 ans',
      familySituation: 'En couple avec enfant(s)',
      investmentExperience: 'Intermédiaire',
      businessModelsUnderstanding: 'Bonne compréhension générale',
      primaryObjective: 'Croissance équilibrée & stabilité',
      firstWithdrawalHorizon: '8 à 12 ans',
      withdrawalMethod: 'Retraits progressifs périodiques',
      simulatedCapital: 100000,
      simulatedCapitalFormatted: '100 000 $',
      accountType: 'CELIAPP — Première propriété',
      riskTolerance: 'Modéré',
      maxLossTolerance: '20',
      sectorConcentrationLimit: '25 % maximum par secteur',
      capitalNeedNext12Months: 'Aucun besoin prévu (fonds d’urgence suffisant)',
      essentialExpensesImpact: 'Mes dépenses essentielles sont entièrement couvertes',
      interestedSectors: ['Santé & Consommation', 'Technologies & IA', 'Obligations & Revenu fixe'],
      cryptoPreference: 'Exclusion totale (0 % crypto)',
      esgImportance: 'Prioritaire · Filtres stricts',
      excludedCategories: ['Énergies fossiles & controverses climatiques', 'Cryptoactifs & devises virtuelles'],
      additionalNotes: 'Gestionnaire des opérations, recherche un équilibre durable sans entreprises controversées.',
      fictionalCapitalAcknowledged: true,
      completedAt: '2026-02-14T10:00:00Z',
    },
  },
};

export const DEMO_ORDER: Array<DemoPersonaId> = ['robert', 'amira', 'mateo'];

export function isDemoPersonaId(id: string): id is DemoPersonaId {
  return id === 'robert' || id === 'amira' || id === 'mateo';
}

export function getDemoPersona(id: string): DemoPersonaMeta | null {
  if (isDemoPersonaId(id)) {
    return DEMO_PERSONAS[id];
  }
  return null;
}
