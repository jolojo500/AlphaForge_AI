export type Language = 'fr' | 'en';

export const translations: Record<Language, Record<string, string>> = {
  fr: {
    // Top Bar & App Navigation
    'banner.disclaimer': 'Simulation éducative · Aucun conseil personnalisé d’investissement',
    'app.ask_another': 'Poser une autre question',
    'app.modify_profile': 'Modifier profil',
    'app.replay_analysis': 'Rejouer une analyse',
    'app.replay_short': 'Rejouer',
    'app.login': 'Connexion',
    'app.logout': 'Déconnexion',
    'app.advisor': 'Conseiller',
    'app.footer': 'AlphaForge AI — Architecture multi-agents vérifiable · PolyFinances 2026',
    'nav.profile': 'Questionnaire profil',
    'nav.edit_profile': 'Éditer le profil',
    'nav.new_query': 'Nouvelle analyse',
    'nav.replay': 'Rejouer simulations',
    'nav.whatif': 'Simulation What-If',
    'nav.results': 'Résultats de simulation',

    // Welcome Screen
    'welcome.title': 'AlphaForge AI',
    'welcome.subtitle': 'Assistant éducatif de simulation de portefeuille et d’analyse de risque selon les règles de gouvernance BNCD.',
    'welcome.start_questionnaire': 'Commencer le questionnaire profil',
    'welcome.use_demo_persona': 'Ou explorer avec un profil démo',
    'welcome.amira_title': 'Amira, 26 ans',
    'welcome.amira_desc': 'Croissance dynamique · Horizon 15+ ans · Crypto & Techno · 100 000 $ CAD',
    'welcome.mateo_title': 'Mateo, 41 ans',
    'welcome.mateo_desc': 'Profil équilibré · Horizon 10 ans · ESG strict · Zéro controverse',
    'welcome.robert_title': 'Robert, 59 ans',
    'welcome.robert_desc': 'Préservation du capital · Horizon 4 ans · Prudence pré-retraite',

    // Query Screen
    'query.title': 'Que souhaitez-vous explorer aujourd’hui ?',
    'query.subtitle': 'Formulez une idée d’investissement, une demande d’allocation ou une modification de stratégie.',
    'query.placeholder': 'Ex: Je veux mettre 25 % de mon portefeuille dans TSLA, ou construire une allocation diversifiée...',
    'query.btn_run': 'Lancer la simulation',
    'query.btn_running': 'Analyse multi-agents en cours...',
    'query.suggested': 'Suggestions de requêtes',
    'query.sugg_1': 'Je veux investir 25 % de mon portefeuille dans TSLA.',
    'query.sugg_2': 'Construire un portefeuille équilibré et diversifié avec des ETF à faible coût.',
    'query.sugg_3': 'Ajouter 10 % de BTC-USD pour dynamiser le rendement de mon portefeuille.',

    // Scenarios Section
    'scenarios.section_title': 'Comparaison quantitative des scénarios simulés',
    'scenarios.most_consistent': 'Plus cohérent',
    'scenarios.weights_title': 'Répartition des actifs',
    'scenarios.metrics_title': 'Indicateurs clés de risque',
    'scenarios.asset_evaluated': '(actif évalué)',
    'scenarios.as_requested_title': 'Votre demande telle quelle',
    'scenarios.as_requested_sub': 'Votre idée intégrée sans ajustement',
    'scenarios.capped_title': 'La version ajustée à vos limites',
    'scenarios.capped_sub': 'La même idée, ramenée dans vos garde-fous',
    'scenarios.baseline_title': 'Le profil de référence',
    'scenarios.baseline_sub': 'Allocation type pour votre profil, sans votre idée',
    'scenarios.current_title': 'Votre portefeuille actuel',
    'scenarios.current_sub': 'Les positions que vous avez déclarées',

    // Metrics labels
    'metric.volatility_ann': 'Amplitude des variations (volatilité)',
    'metric.max_drawdown': 'Pire baisse historique',
    'metric.stress_2022': 'Résultat pendant le choc de 2022',
    'metric.top_weight': 'Plus grosse position',
    'metric.sector_concentration_hhi': 'Concentration par secteur',
    'metric.us_exposure': 'Part investie aux États-Unis',
    'metric.tax_drag': 'Coût fiscal estimé par an',

    // Explanation Section
    'explain.title': 'Pourquoi cette réponse ? Données, choix, limites et sensibilité',
    'explain.subtitle': 'Les quatre questions que tout conseiller doit pouvoir documenter, chacune appuyée sur des chiffres vérifiés.',
    'explain.what_data': 'Quelles données avons-nous utilisées ?',
    'explain.what_data_sub': 'Séries de prix historiques ajustées, contexte économique et actualités datées.',
    'explain.why_choice': 'Pourquoi ce choix ?',
    'explain.why_choice_sub': 'Cohérence avec vos objectifs, votre tolérance et votre capacité déclarés.',
    'explain.limits': 'Quelles sont les limites ?',
    'explain.limits_sub': 'Ce que l’historique ne peut pas dire et les hypothèses retenues.',
    'explain.what_change': 'Qu’est-ce qui changerait la réponse ?',
    'explain.what_change_sub': 'Sensibilité aux chocs de taux, aux récessions ou à un changement d’horizon.',
    'explain.summary': 'Synthèse de l’analyse :',
    'explain.uncertainty': 'Note sur l’incertitude :',
    'explain.most_consistent_scenario': 'Scénario le plus cohérent avec le profil',
    'explain.verification_passed': 'Chiffres vérifiés',
    'explain.verification_failed': 'La vérification des chiffres a échoué',
    'explain.verification_failed_desc': 'L’explication rédigée par le modèle a été rejetée : un chiffre ne correspond pas aux preuves, ou une formulation s’apparente à un conseil.',

    // Profile Card
    'profile.card_title': 'Hypothèses du profil investisseur',
    'profile.verified_by_a1': 'Profil vérifié',
    'profile.in_progress': 'En cours',
    'profile.objective': 'Objectif',
    'profile.horizon': 'Horizon d’investissement',
    'profile.tolerance': 'Tolérance au risque',
    'profile.capacity': 'Capacité financière',
    'profile.constraints': 'Garde-fous & Contraintes',
    'profile.preferences': 'Préférences déclarées',
    'profile.no_constraints': 'Aucune contrainte stricte',
    'profile.neutral': 'Neutre',
    'profile.budget': 'Budget indicatif',
    'profile.idea': 'Idée analysée',
    'profile.account_type': 'Compte fiscal',
    'profile.status': 'Statut profil',
    'profile.growth': 'Croissance du capital',
    'profile.balanced': 'Équilibré & responsable',
    'profile.capital_preservation': 'Préservation du capital',
    'profile.income': 'Revenus réguliers',
    'profile.high': 'Élevée',
    'profile.moderate': 'Modérée',
    'profile.low_moderate': 'Faible à modérée',
    'profile.low': 'Faible',
    'profile.download_dossier': 'Télécharger mon dossier',
    'profile.downloading_dossier': 'Téléchargement...',
    'profile.dossier_not_found': 'Aucun dossier trouvé pour ce compte.',
    'profile.dossier_error': 'Erreur lors du téléchargement du dossier.',

    // Conflicts & Clarification
    'conflicts.title': 'Conflit ou incohérence détecté dans la demande',
    'conflicts.sub': 'L’analyse s’est poursuivie en comparant votre demande telle quelle à la version ajustée à vos limites.',
    'clarification.title': 'Précision requise pour poursuivre l’analyse',
    'clarification.label': 'Votre réponse :',
    'clarification.placeholder': 'Précisez votre choix ou votre objectif...',
    'clarification.btn_send': 'Répondre et continuer',
    'clarification.sending': 'Envoi...',

    // Exclusions
    'exclusions.title': 'Filtres et exclusions d’univers',
    'exclusions.none': 'Aucun actif exclu pour ce profil.',

    // Common
    'common.years': 'ans',
    'common.year': 'an',
    'common.loading': 'Chargement...',
    'common.error': 'Une erreur est survenue',
  },
  en: {
    // Top Bar & App Navigation
    'banner.disclaimer': 'Educational simulation · No personalized investment advice',
    'app.ask_another': 'Ask another question',
    'app.modify_profile': 'Edit profile',
    'app.replay_analysis': 'Replay an analysis',
    'app.replay_short': 'Replay',
    'app.login': 'Log in',
    'app.logout': 'Log out',
    'app.advisor': 'Advisor',
    'app.footer': 'AlphaForge AI — Verifiable multi-agent architecture · PolyFinances 2026',
    'nav.profile': 'Profile Questionnaire',
    'nav.edit_profile': 'Edit Profile',
    'nav.new_query': 'New Analysis',
    'nav.replay': 'Replay Runs',
    'nav.whatif': 'What-If Simulation',
    'nav.results': 'Simulation Results',

    // Welcome Screen
    'welcome.title': 'AlphaForge AI',
    'welcome.subtitle': 'Educational portfolio simulation and risk analysis assistant aligned with BNCD governance standards.',
    'welcome.start_questionnaire': 'Start Investor Questionnaire',
    'welcome.use_demo_persona': 'Or explore with a demo persona',
    'welcome.amira_title': 'Amira, 26 yo',
    'welcome.amira_desc': 'Dynamic growth · 15+ yr horizon · Crypto & Tech · $100,000 CAD',
    'welcome.mateo_title': 'Mateo, 41 yo',
    'welcome.mateo_desc': 'Balanced profile · 10 yr horizon · Strict ESG · Zero controversy',
    'welcome.robert_title': 'Robert, 59 yo',
    'welcome.robert_desc': 'Capital preservation · 4 yr horizon · Pre-retirement prudence',

    // Query Screen
    'query.title': 'What would you like to explore today?',
    'query.subtitle': 'Formulate an investment idea, allocation request, or strategy adjustment.',
    'query.placeholder': 'E.g.: I want to put 25% of my portfolio in TSLA, or build a diversified portfolio...',
    'query.btn_run': 'Run Simulation',
    'query.btn_running': 'Multi-agent analysis running...',
    'query.suggested': 'Suggested Queries',
    'query.sugg_1': 'I want to invest 25% of my portfolio in TSLA.',
    'query.sugg_2': 'Build a balanced, diversified portfolio using low-cost ETFs.',
    'query.sugg_3': 'Add 10% BTC-USD to boost overall portfolio return.',

    // Scenarios Section
    'scenarios.section_title': 'Quantitative Comparison of Simulated Scenarios',
    'scenarios.most_consistent': 'Most consistent',
    'scenarios.weights_title': 'Asset Allocation',
    'scenarios.metrics_title': 'Key Risk Indicators',
    'scenarios.asset_evaluated': '(evaluated asset)',
    'scenarios.as_requested_title': 'Your request as is',
    'scenarios.as_requested_sub': 'Your idea included without adjustment',
    'scenarios.capped_title': 'The version adjusted to your limits',
    'scenarios.capped_sub': 'The same idea, brought within your limits',
    'scenarios.baseline_title': 'The reference profile',
    'scenarios.baseline_sub': 'Standard allocation for your profile, without your idea',
    'scenarios.current_title': 'Your current portfolio',
    'scenarios.current_sub': 'The holdings you declared',

    // Metrics labels
    'metric.volatility_ann': 'Size of the swings (volatility)',
    'metric.max_drawdown': 'Worst historical fall',
    'metric.stress_2022': 'Result during the 2022 shock',
    'metric.top_weight': 'Largest position',
    'metric.sector_concentration_hhi': 'Concentration by sector',
    'metric.us_exposure': 'Share invested in the United States',
    'metric.tax_drag': 'Estimated yearly tax cost',

    // Explanation Section
    'explain.title': 'Why this answer? Data, choice, limits and sensitivity',
    'explain.subtitle': 'The four questions any advisor must be able to document, each backed by checked figures.',
    'explain.what_data': 'What data did we use?',
    'explain.what_data_sub': 'Adjusted historical price series, economic context, and dated news.',
    'explain.why_choice': 'Why this choice?',
    'explain.why_choice_sub': 'Consistency with your stated objectives, risk tolerance, and capacity.',
    'explain.limits': 'What are the limits?',
    'explain.limits_sub': 'What the history cannot tell, and the assumptions made.',
    'explain.what_change': 'What would change the answer?',
    'explain.what_change_sub': 'Sensitivity to interest rate shocks, recessions, or a change of horizon.',
    'explain.summary': 'Summary of the analysis:',
    'explain.uncertainty': 'Uncertainty note:',
    'explain.most_consistent_scenario': 'Scenario most consistent with your profile',
    'explain.verification_passed': 'Figures checked',
    'explain.verification_failed': 'The check of the figures failed',
    'explain.verification_failed_desc': 'The explanation written by the model was rejected: a figure does not match the evidence, or a wording reads like advice.',

    // Profile Card
    'profile.card_title': 'Investor Profile Hypotheses',
    'profile.verified_by_a1': 'Profile checked',
    'profile.in_progress': 'In Progress',
    'profile.objective': 'Objective',
    'profile.horizon': 'Investment Horizon',
    'profile.tolerance': 'Risk Tolerance',
    'profile.capacity': 'Financial Capacity',
    'profile.constraints': 'Safeguards & Constraints',
    'profile.preferences': 'Declared Preferences',
    'profile.no_constraints': 'No strict constraint',
    'profile.neutral': 'Neutral',
    'profile.budget': 'Simulated Capital',
    'profile.idea': 'Analyzed Idea',
    'profile.account_type': 'Tax Account Type',
    'profile.status': 'Profile Status',
    'profile.growth': 'Capital Growth',
    'profile.balanced': 'Balanced & Responsible',
    'profile.capital_preservation': 'Capital Preservation',
    'profile.income': 'Regular Income',
    'profile.high': 'High',
    'profile.moderate': 'Moderate',
    'profile.low_moderate': 'Low to Moderate',
    'profile.low': 'Low',
    'profile.download_dossier': 'Download my record',
    'profile.downloading_dossier': 'Downloading...',
    'profile.dossier_not_found': 'No record found for this account.',
    'profile.dossier_error': 'Error downloading record.',

    // Conflicts & Clarification
    'conflicts.title': 'Tension or Inconsistency Identified in Request',
    'conflicts.sub': 'The analysis continued by comparing your request as is with the version adjusted to your limits.',
    'clarification.title': 'Clarification Required to Proceed',
    'clarification.label': 'Your answer:',
    'clarification.placeholder': 'Clarify your choice or objective...',
    'clarification.btn_send': 'Submit and Continue',
    'clarification.sending': 'Sending...',

    // Exclusions
    'exclusions.title': 'Universe Screening & Exclusions',
    'exclusions.none': 'No assets excluded for this profile.',

    // Common
    'common.years': 'years',
    'common.year': 'year',
    'common.loading': 'Loading...',
    'common.error': 'An error occurred',
  },
};

export function t(lang: Language, key: string, fallback?: string): string {
  const dict = translations[lang] || translations.fr;
  if (key in dict) {
    return dict[key];
  }
  const frDict = translations.fr;
  if (key in frDict) {
    return frDict[key];
  }
  return fallback ?? key;
}
