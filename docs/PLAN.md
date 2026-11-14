# AlphaForge AI — Plan d'équipe (source : conversation Claude de l'équipe, condensée)

## Défi (case officiel : Datathon2026/*.pdf)
- Solution **agentique auto-explicative** qui éclaire une décision d'investissement à partir de données publiques, adaptée à un profil.
- Entrées : persona (Amira, Mateo, Robert) ou profil libre, capital fictif, données publiques (starter pack facultatif).
- Sorties : résultat défendable (allocation fictive, comparaison, scénario) avec sources, hypothèses, facteurs, limites.
- Livrables : prototype + code (README), vidéo ~5 min, documentation technique, one-pager.
- Contraintes : simulation seulement, aucun conseil personnalisé, faits ≠ hypothèses, ne pas exposer la chaîne de pensée du modèle (expliquer via actions observables : appels d'outils, preuves).

### Grille (annexe 1)
| Critère | Poids | Ce qui rapporte |
|---|---|---|
| Solution (pertinence, innovation) | 20 % | question d'investissement précise, cas complet, 2 personas contrastés |
| Agentique + explicabilité | 20 % | agents au rôle clair, trace d'exécution visible |
| Données | 20 % | devises, calendriers, ajustements, validation, visualisations |
| UX/UI | 10 % | trace et sources lisibles |
| Intégration AWS | 15 % | rôle démontrable de Bedrock (sans intégration réelle = inadmissible) |
| Pitch / business | 15 % | récit, valeur pour un courtier (BNCD), démo |

### Pièges
- Ne PAS prédire les rendements (écarté par le case) : décrire et contraindre.
- LLM qui invente chiffres / controverses ESG (aucune cote ESG dans les données).
- Robert demande Tesla : test central du persona → alerte d'incohérence + alternative plafonnée.
- Sur-architecture : « simple, focalisé, vérifiable ».

## Données (starter : Datathon2026/alphaforge_starter/)
- prices_daily.csv : 40 049 lignes, 31 tickers, 2021-11-12 → 2026-11-12 ; BTC/ETH 7j/7 (1 827 jours) vs 1 255.
- assets_universe.csv : 10 actions CA, 10 US, 9 FNB, BTC, ETH (secteur, devise).
- corporate_actions.csv, fx_usdcad_daily.csv (pas de jours fériés CA), macro_rates.csv (IPC/chômage datés au mois de référence, pas à la publication).
- À traiter/documenter : conversion CAD (.TO en CAD, reste USD), adj_close pour rendements (ne pas ré-appliquer les splits), CNQ.TO « split » 1,021 le 2022-08-22 (distribution spéciale probable), décalage de publication macro (no look-ahead), biais du survivant.
- À ajouter : ESG (ESGV méthodo, rapports durabilité), fondamentaux (EDGAR/SEDAR+), nouvelles datées (Robert/Tesla), composition des FNB (chevauchement, ex. XSP/ZEQT).

## Approche : hybride agentique
Principe : **le LLM ne calcule rien**. Chaque chiffre vient d'un outil, stocké comme preuve (E1, E2…). Un vérificateur déterministe contrôle que le texte n'affirme rien d'absent des preuves.

Pipeline : PROFIL → UNIVERS (filtres) → STATS (vol, max DD, CVaR95, corrélations, bêta, contribution au risque, en CAD) → CONSTRUCT (min-variance / parité de risque sous contraintes, cible de vol, sans rendements prévus) → STRESS (2022, fenêtres glissantes, sensibilité) → GOUVERNANCE (règles) → EXPLICATION (preuves + « qu'est-ce qui changerait la réponse ? »).

Contraintes par persona (hypothèses d'équipe à documenter) :
| | Amira | Mateo | Robert |
|---|---|---|---|
| Vol cible | haute | moyenne | basse à moyenne |
| Plafonds | 1 actif ≤ ~10 %, techno ≤ ~35-40 %, crypto ≤ ~10-15 % | énergie plafonnée, spéculatif exclu | crypto = 0, obligations + court terme ≥ ~50 % |
| Particularité | diversification imposée | filtre ESG (ESGV vs SPY, exclusions sourcées) | demande TSLA → alerte + alternative plafonnée |

## Agents
| Agent | Rôle | Modèle (Bedrock) |
|---|---|---|
| Orchestrateur | choisit les outils et l'ordre | global.anthropic.claude-sonnet-5-5 |
| Analyste | appelle outils quant, lit documents | global.anthropic.claude-sonnet-5-5 |
| Gouvernance | règles code d'abord, LLM pour cas ambigus | global.anthropic.claude-opus-5-5 |
| Explicateur | rédige à partir des preuves seulement | global.anthropic.claude-sonnet-5-5 |
+ vérificateur déterministe (Python). Bulk : global.anthropic.claude-haiku-5-5. Embeddings : amazon.titan-embed-text-v2:0. (IDs vérifiés le 2026-11-14.)
Piège : ne pas forcer tool_choice ; demander le JSON dans le prompt et valider avec Pydantic.

Schéma de sortie de l'Explicateur :
```json
{"resume": "<=80 mots",
 "quelles_donnees": [{"claim": "", "evidence_ids": ["E1"]}],
 "pourquoi_ce_choix": [{"claim": "", "evidence_ids": ["E4"]}],
 "limites": [{"text": "", "type": "donnee|methode|hypothese"}],
 "ce_qui_changerait_la_reponse": [""],
 "alertes_gouvernance": [{"niveau": "info|attention|bloquant", "message": "", "evidence_ids": []}]}
```
Anti-hallucination : Pydantic → vérificateur (E# existent, chaque nombre du texte présent dans la preuve citée) → 1 régénération avec erreurs, puis échec propre. ESG/controverses exigent document + page sinon « non vérifié ».

Évaluation : 3 personas + cas adverses (Robert→TSLA, Amira→100 % crypto, Mateo→ENB « pour le rendement »). Métriques : fidélité numérique 100 %, 0 violation de contraintes, couverture des citations, stabilité, sensibilité.

## Backend
Stack : FastAPI + Pydantic v2 (SSE pour la trace), boto3 Converse, pandas/numpy/scipy/cvxpy, pdfplumber, Parquet.
```
alphaforge/
├── app/ main.py config.py schemas.py bedrock.py evidence.py verifier.py personas.py
│   ├── agents/ orchestrator.py analyst.py governance.py explainer.py
│   └── tools/  prices.py risk.py optimize.py stress.py docs_rag.py
├── data/ (raw/, processed/, docs/)
├── tests/ test_tools.py test_verifier.py test_personas.py
├── frontend/
└── README.md
```
Endpoints : POST /api/analyze → {run_id} ; GET /api/runs/{id}/stream (SSE) ; GET /api/runs/{id} ; POST /api/runs/{id}/whatif ; POST /api/documents.
AWS : App Runner/Fargate (FastAPI) → Bedrock (Converse + Guardrails) + Titan Embeddings ; S3 (Parquet, PDF) ; DynamoDB (runs, traces) ; CloudWatch. Guardrails : refuser conseil personnalisé / exécution de transactions.

## Front
Streamlit (recommandé) : sélecteur persona, capital, question → étapes en direct (st.status), allocation (anneau), risque, corrélations, stress 2022, explication Données/Pourquoi/Limites avec [E#] cliquables, what-if (curseurs).

## Différenciation
Refus constructif (Robert), 4 questions BNCD comme structure d'explication, tolérance ≠ capacité, chevauchement FNB, copilote pré-transaction pour courtier direct (jamais d'exécution).

## Échéances
Remise dimanche 15 nov 23 h 59 ; compte AWS détruit lundi 16 nov 13 h 59.
