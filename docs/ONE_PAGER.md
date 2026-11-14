# AlphaForge AI — One-Pager (Datathon PolyFinances 2026)

## Problème
Les investisseurs autonomes doivent arbitrer entre rendement perçu, risque, horizon et préférences personnelles (ex. ESG, actifs médiatisés), souvent sans trace claire reliant les chiffres présentés aux données et aux règles appliquées. Le défi demande une solution agentique auto-explicative qui éclaire une décision d’investissement simulée, adaptée au profil, sans exécuter de transaction ni fournir de conseil personnalisé.

## Approche agentique
AlphaForge AI combine un **cœur quantitatif déterministe** et des **agents LLM via Amazon Bedrock (API Converse)** :
- **Interprétation** des demandes en langage naturel (Claude Haiku 3.5) vers des intentions/actifs structurés.
- **Orchestration** (Claude Sonnet 3.5) avec boucle d’outils et exécution de calculs Python : chargement/alignement des données, métriques de risque, optimisation de portefeuille à deux niveaux sous contraintes, test de résistance (épisode 2022).
- **Gouvernance** : règles déterministes (adéquation, interdictions/plafonds, avis de simulation) avec escalade possible vers Claude Opus 3.5 pour cas ambigus.
- **Explication** (Claude Sonnet 3.5) produisant un JSON structuré fondé sur des preuves.

Chaque résultat chiffré issu des outils est enregistré dans un **registre de preuves `E1…En`** ; un **vérificateur déterministe** contrôle la présence des identifiants cités et la cohérence des nombres avant restitution. Une **trace d’exécution observable** (étapes, appels d’outils, preuves, alertes) est exposée sans chaîne de pensée interne.

## Originalité
- **Séparation stricte calcul / langage** : le LLM ne calcule pas les métriques financières.
- **Refus constructif et adéquation** : demandes incohérentes avec le profil (ex. actif très volatil pour horizon court/préservation du capital) traitent le conflit et proposent des alternatives plafonnées selon les règles et évaluations codées.
- **Différenciation par poches stratégiques et contraintes** : profils contrastés (croissance long terme, équilibre ESG, préservation proche retraite) traduits en bandes de risque et contraintes documentées comme hypothèses d’équipe.

## Sources de données
Jeu de départ `Datathon2026/alphaforge_starter/` (2021-11-12 à 2026-11-12, extraction 2026-11-13) : prix/volumes et opérations sur titres (Yahoo Finance via `yfinance`), taux USD/CAD et séries macro Canada (Banque du Canada, API Valet), séries macro US (FRED). Métadonnées, limites et conditions détaillées dans `sources_metadata.csv` et le README.

## Explicabilité
L’interface Streamlit présente allocation, indicateurs de risque, comparaison au choc 2022, alertes de gouvernance et explication structurée (données, justification, limites, facteurs de changement) avec **preuves [E#] consultables** (outil, source, date, devise, résultat).

## Valeur pour un courtier direct (BNCD)
Copilote **pré-transaction** pour l’investisseur autonome : aide à comprendre risque, contraintes et compromis avant toute décision, avec traçabilité des chiffres et alertes d’adéquation — **simulation uniquement, jamais d’exécution d’ordres**.