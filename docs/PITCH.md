# AlphaForge AI — Script de présentation (5 minutes)

> **Format :** script oral + plan de diapositives (8–10) + script de démonstration + préparation Q&R.  
> **Contrainte :** simulation éducative uniquement, aucun conseil personnalisé, aucune exécution de transaction. Les explications s’appuient sur des actions observables et des preuves `E#`, sans exposer de chaîne de pensée interne.

## Plan des diapositives (8 à 10)

1. **Titre & promesse** — AlphaForge AI : copilote de simulation d’investissement explicable (BNCD, pré-transaction). Équipe / contexte Datathon PolyFinances 2026.
2. **Problème** — Décisions d’investissement autonomes : besoin de clarté sur données, risques, contraintes de profil et limites ; exigence d’explications vérifiables (pas de chiffres inventés).
3. **Personas contrastés (cas officiel)** — Amira (croissance long terme, tolérance élevée, diversification), Mateo (équilibre, sensibilité ESG), Robert (préservation, horizon court, tentation d’un actif médiatisé risqué). Paramètres chiffrés = **hypothèses d’équipe** documentées.
4. **Architecture agentique** — Streamlit → `run_analysis` (pipeline) → outils déterministes (prix/FX, risque, optimisation, stress 2022) → registre de preuves `E#` → agents Bedrock (interprétation Haiku, orchestration/explication Sonnet, escalade gouvernance Opus) → vérificateur déterministe.
5. **Données & traitements** — Univers de départ 31 actifs (2021-11-12 à 2026-11-12) : Yahoo Finance, Banque du Canada, FRED. Traitements clés : calendrier unifié, conversion USD→CAD as-of, rendements log sur `adj_close`, documentation des anomalies (CNQ.TO), décalage macro, biais du survivant.
6. **Explicabilité & gouvernance** — Trace observable, explication structurée (données, pourquoi, limites, ce qui changerait), alertes (info/attention/bloquant), vérification numérique contre les preuves `E#`.
7. **Démo — cas Robert & TSLA** — Requête d’ajout d’un actif spéculatif : alerte d’incohérence/adéquation, comparaison base / demandé / alternative plafonnée (selon résultats du pipeline), consultation d’une preuve `E#`.
8. **Démo — contraste Amira vs Robert** — Différences de profil, d’allocation et de métriques de risque issues du même moteur déterministe sous contraintes distinctes.
9. **Valeur BNCD & limites** — Copilote pré-transaction (éducation, transparence, préparation) ; limites : biais du survivant, ESG provisoire/partiel, stress historique centré sur 2022, pas de prédiction de rendement, pas d’exécution.
10. **Conclusion & suite** — Prototype fonctionnel (Streamlit + pipeline + preuves/vérification) ; pistes prévues : enrichissement ESG/documentaire, scénarios de stress additionnels, industrialisation API/persistance (**prévus, non implémentés**).

## Script oral (≈ 5 minutes)

### 0:00–0:30 — Ouverture
« Bonjour, nous sommes l’équipe AlphaForge AI. Nous présentons un copilote de simulation d’investissement explicable, conçu pour le courtage direct : il aide à éclairer une décision **avant** toute transaction, en s’appuyant uniquement sur des données publiques historiques. C’est une simulation éducative : pas de conseil personnalisé, pas d’exécution d’ordres. »

### 0:30–1:15 — Problème et besoin
« Le problème n’est pas seulement de proposer une allocation, mais de montrer **d’où viennent les chiffres**, **quelles règles ont été appliquées** et **quelles sont les limites**. Pour un investisseur autonome, la confiance repose sur la traçabilité : quelles données, quels calculs, quelles alertes d’adéquation, et qu’est-ce qui changerait la réponse. »

### 1:15–2:00 — Personas et approche
« Nous couvrons des situations contrastées inspirées du cas : un profil orienté croissance long terme avec goût pour l’innovation, un profil équilibré sensible aux enjeux ESG, et un profil proche de la retraite axé préservation, confronté à la tentation d’un titre très médiatisé. Les seuils numériques que nous avons codés sont des **hypothèses d’équipe** explicites ; le comportement attendu reste aligné avec les objectifs qualitatifs du cas. »

### 2:00–3:00 — Architecture et explicabilité
« Techniquement, le LLM ne fait **aucun calcul financier**. Des outils déterministes chargent et alignent les données en CAD, calculent volatilité, pertes maximales, CVaR, puis construisent une allocation sous contraintes et rejouent le choc de 2022. Chaque sortie d’outil est enregistrée comme preuve `E1`, `E2`, etc. Des agents Bedrock interprètent la demande, orchestrent les outils, appliquent la gouvernance et rédigent une explication structurée. Un vérificateur déterministe contrôle que les identifiants de preuve existent et que les nombres cités correspondent aux preuves. L’utilisateur voit une trace d’exécution observable, pas un raisonnement interne caché. »

### 3:00–4:15 — Démonstration guidée
« En démonstration, nous comparons d’abord Amira et Robert pour illustrer des allocations et niveaux de risque différents à partir du même moteur. Puis nous posons le cas Robert avec une demande d’ajout de Tesla : le système évalue l’adéquation, signale l’incohérence potentielle avec l’horizon de préservation, et présente une comparaison incluant une alternative plafonnée lorsque c’est pertinent. En cliquant sur une preuve `E#`, on affiche l’outil, la source, la date, la devise et le résultat chiffré associé. »

### 4:15–5:00 — Valeur, limites et conclusion
« Pour un courtier comme BNCD, la valeur est un copilote pré-transaction qui rend les compromis lisibles et documentés. Nos limites sont assumées : biais du survivant de l’univers, traitement ESG partiel et provisoire faute de cotes tierces intégrées, stress historique principal centré sur 2022, et absence de prédiction de rendement. La prochaine étape serait d’enrichir les preuves documentaires et les scénarios de stress, puis d’industrialiser l’exposition du service — éléments prévus, non encore implémentés. Merci. »

## Script de démonstration

### Préparation
- Lancer l’interface : `streamlit run frontend/app.py` (avec accès AWS/Bedrock configuré si démonstration des agents LLM).
- Vérifier que le bandeau de simulation éducative est visible.

### Scénario A — Contraste de profils (Amira vs Robert)
1. **Amira** : sélectionner le profil Amira, capital fictif (ex. 100 000 $ CAD), question orientée croissance/innovation (ex. exposition technologie/IA dans le cadre diversifié). Lancer l’analyse.
2. Montrer : carte de métriques (volatilité, rendement réalisé historique, perte max, stress 2022), graphique d’allocation, trace d’exécution (étapes/outils/preuves).
3. **Robert** : sélectionner le profil Robert, même ordre de grandeur de capital, question prudente de préservation. Relancer l’analyse.
4. Mettre en évidence le contraste : composition et niveau de risque cohérents avec le mandat de préservation (selon contraintes implémentées).

### Scénario B — Robert et Tesla (test d’adéquation)
1. Avec le profil **Robert**, saisir une demande explicite d’ajout de Tesla/TSLA (ex. « Je souhaite ajouter 15 % de Tesla (TSLA)… »). Lancer l’analyse.
2. Observer les **alertes de gouvernance** (niveau attention/info selon règles déclenchées) et, si disponible dans le résultat, le bloc de **comparaison** base / demandé / alternative plafonnée.
3. **Clic sur une preuve `E#`** : ouvrir un expandeur de preuve dans les onglets d’explication pour montrer `outil`, `source`, `date`, `devise`, et `résultat` JSON.
4. Lire une affirmation de la section « Pourquoi ce choix ? » ou « Quelles données ? » et pointer les badges `[E#]` correspondants.

### Scénario C — What-if (interaction disponible)
- Le prototype Streamlit actuel ne propose pas de curseurs « what-if » dédiés ; le **what-if** se démontre en modifiant les entrées (profil, capital, formulation de la demande incluant un actif/poids, ou activation de l’option d’escalade gouvernance si pertinente) puis en relançant l’analyse pour comparer les sorties et alertes. (Curseurs interactifs what-if : **prévus**, non implémentés.)

## Préparation Q&R (10 questions probables)

1. **Q : Prédisez-vous les rendements futurs ?**  
   **R :** Non. Le code n’implémente aucune prévision de rendement ; l’optimisation (`optimize.py`) minimise la variance / applique une allocation stratégique sous contraintes à partir de statistiques historiques, et les résultats sont présentés comme simulation.

2. **Q : D’où viennent les chiffres affichés ?**  
   **R :** Des outils déterministes (ex. `prices.py`, `risk.py`, `optimize.py`, `stress.py`) dont les sorties sont enregistrées dans `EvidenceRegistry` (`evidence.py`). L’explicateur doit citer des `E#` et le `verifier.py` valide la cohérence des nombres avec les preuves.

3. **Q : Le LLM peut-il inventer un chiffre ?**  
   **R :** Les sections chiffrées de l’explication sont vérifiées contre les preuves ; en cas d’écart, une régénération corrective est tentée et une sanitation déterministe peut retirer ou neutraliser les affirmations non supportées.

4. **Q : Exposez-vous la chaîne de pensée du modèle ?**  
   **R :** Non. `trace.py` et l’interface journalisent des événements observables (étapes, outils, preuves, alertes, statut de vérification), sans raisonnement interne du modèle.

5. **Q : Comment gérez-vous les devises et les calendriers ?**  
   **R :** `prices.py` construit un calendrier unifié, réaligne les séries, applique un remplissage avant limité, convertit les actifs USD en CAD avec le taux USD/CAD Banque du Canada réaligné as-of (sans anticipation), puis calcule des rendements logarithmiques en CAD.

6. **Q : Que faites-vous du cas Robert qui veut Tesla ?**  
   **R :** L’interpréteur peut extraire la demande (ex. TSLA/poids), l’orchestrateur peut exécuter une évaluation dédiée (`evaluate_asset_addition`) comparant base/demandé/alternative plafonnée, et la gouvernance déclenche des alertes d’adéquation selon le profil et les règles codées.

7. **Q : Les contraintes persona viennent-elles du cas officiel ?**  
   **R :** Les objectifs qualitatifs viennent du cas ; les seuils numériques (plafonds, planchers, bandes de volatilité, exclusions opérationnelles) sont codés dans `personas.py` et marqués comme hypothèses d’équipe.

8. **Q : Comment traitez-vous l’ESG pour Mateo ?**  
   **R :** De façon partielle et provisoire dans le code : exclusions de certains titres fossiles et rôle central d’`ESGV` selon les règles/paramètres définis, avec mention explicite qu’il faut remplacer ces hypothèses par une source ESG dédiée (pas de cotes tierces intégrées).

9. **Q : Quelles sont les principales limites des données ?**  
   **R :** Biais du survivant de l’univers, dépendance à des sources publiques (Yahoo/BoC/FRED) avec leurs limites, anomalie documentée sur CNQ.TO, séries macro mensuelles à utiliser avec décalage de publication, et absence de fondamentaux/nouvelles/cotes ESG intégrés.

10. **Q : Quelle est la valeur pour BNCD et que reste-t-il à faire ?**  
   **R :** Valeur : copilote pré-transaction traçable et pédagogique, sans exécution. Reste notamment (prévu, non implémenté ici) : enrichissement documentaire/ESG sourcé, scénarios de stress supplémentaires, et exposition service (API/persistance) si requis.