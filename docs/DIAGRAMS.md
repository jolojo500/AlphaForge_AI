# AlphaForge AI — Diagrammes

Trois vues du système tel qu'il est dans `main` : le flux de travail des agents, la séquence complète d'une analyse, et le modèle de données (UML). Le détail des nœuds est dans [TECHNICAL.md](TECHNICAL.md), les contrats dans [PRD.md](PRD.md).

## 1. Flux de travail (graphe LangGraph)

Le graphe est défini dans [`alphaforge/graph.py`](../alphaforge/graph.py). Les trois analyses tournent en parallèle ; les deux boucles sont bornées par `MAX_RED_TEAM_LOOPS` et `MAX_EXPLAIN_RETRIES`.

```mermaid
flowchart TD
    START([Question + profil]) --> ENTRY{Profil déjà résolu ?}
    ENTRY -- "non" --> PROFILE["Agent 1 · Profil<br/>extraction, KYC, conflits"]
    ENTRY -- "oui (what-if)" --> SCREEN
    PROFILE --> CLAR{Information essentielle manquante ?}
    CLAR -- "oui" --> ASK[/"interrupt() : une question de précision"/]
    ASK -- "réponse de l'utilisateur" --> PROFILE
    CLAR -- "non" --> SCREEN["Filtrage d'admissibilité<br/>contraintes, exclusions (ES)"]

    SCREEN --> QUANT["Métriques quantitatives<br/>risque historique en CAD (EQ)"]
    SCREEN --> MACRO["Contexte macroéconomique<br/>indicateurs datés (EM)"]
    SCREEN --> EVENTS["Agent 2 · Actualités<br/>événements sourcés (EN)"]

    QUANT --> SCEN
    MACRO --> SCEN
    EVENTS --> SCEN
    SCEN["Scénarios<br/>demandé, plafonné, référence (EP)"] --> RED["Agent 3 · Critique contradictoire<br/>objections sourcées"]

    RED --> BLOCK{Objection bloquante<br/>et boucle restante ?}
    BLOCK -- "oui" --> SCEN
    BLOCK -- "non" --> EXPLAIN["Agent 4 · Explication<br/>quatre questions BNCD"]

    EXPLAIN --> VERIF["Vérificateur déterministe<br/>ids, chiffres, formulation, sections"]
    VERIF --> OK{Vérification réussie<br/>ou plus d'essai ?}
    OK -- "échec, essai restant" --> EXPLAIN
    OK -- "oui" --> FIN([Résultat affiché])

    FIN -.-> WHATIF["What-if : un paramètre modifié"]
    WHATIF -.-> ENTRY
    FIN -.-> ADVISOR["Revue du conseiller<br/>signature, dossier de revue PDF"]
```

## 2. Séquence complète d'une analyse

De la création du compte au dossier dans S3. Les étapes de compte sont facultatives : un utilisateur anonyme suit la même séquence sans les appels à Cognito, à la table des utilisateurs ni à S3.

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant FE as Interface React
    participant API as API FastAPI
    participant COG as Cognito
    participant G as Graphe LangGraph
    participant BR as Bedrock (Claude)
    participant DDB as DynamoDB
    participant S3 as S3

    rect rgb(240, 245, 250)
    Note over U,S3: Compte et profil (facultatif)
    U->>FE: Créer un compte
    FE->>API: POST /auth/register
    API->>COG: SignUp, confirmation, connexion
    COG-->>API: Jetons JWT
    API->>S3: Créer users/{nom}/dossier.md
    API-->>FE: Jeton + utilisateur
    U->>FE: Remplir le questionnaire
    FE->>FE: Profil dans localStorage
    FE->>API: PUT /user/profile
    API->>DDB: Table alphaforge-users
    API->>S3: Ajouter « Mise à jour du profil »
    end

    rect rgb(245, 250, 240)
    Note over U,S3: Analyse
    U->>FE: Poser une question
    FE->>API: POST /runs (question, profil, X-Client-Id, jeton)
    API->>API: Limites de débit, propriétaire du run
    API-->>FE: run_id
    FE->>API: GET /runs/{id}/events (SSE)
    API->>G: Lancer le graphe (fil d'exécution borné)
    G->>BR: Agent 1 : comprendre la demande
    BR-->>G: Profil, idée demandée, conflits

    opt Information essentielle manquante
        G-->>API: interrupt(question)
        API-->>FE: événement « interrupt »
        FE-->>U: Question de précision
        U->>FE: Réponse
        FE->>API: POST /runs/{id}/answer
        API->>G: Reprise depuis le point de contrôle
    end

    G->>G: Filtrage d'admissibilité
    par Analyses en parallèle
        G->>G: Métriques quantitatives
    and
        G->>G: Contexte macroéconomique
    and
        G->>BR: Agent 2 : trier les actualités
    end
    G->>G: Construire les trois scénarios
    G->>BR: Agent 3 : critique contradictoire
    BR-->>G: Objections sourcées
    loop Objection bloquante (borné)
        G->>G: Ajuster les scénarios
    end
    G->>BR: Agent 4 : explication
    BR-->>G: Explication avec ids de preuve
    G->>G: Vérificateur déterministe
    loop Échec de vérification (borné)
        G->>BR: Agent 4 : nouvelle rédaction
    end

    loop À chaque nœud terminé
        G->>DDB: Point de contrôle (alphaforge-checkpoints)
        G-->>API: Entrée de trace
        API-->>FE: événement « trace »
    end
    G-->>API: État final
    API->>DDB: Trace du run (alphaforge-traces)
    API->>S3: Ajouter la décision au dossier (utilisateur connecté)
    API-->>FE: événement « final »
    FE->>API: GET /runs/{id}
    API-->>FE: État complet
    FE-->>U: Synthèse, trois scénarios, preuves, trace
    end

    rect rgb(250, 245, 240)
    Note over U,S3: Suites possibles
    U->>FE: What-if (un paramètre)
    FE->>API: POST /runs/{id}/whatif puis GET /runs/{id}/diff
    API-->>FE: Écarts de poids et d'indicateurs
    U->>FE: Revue du conseiller
    FE->>API: POST /runs/{id}/review
    API->>DDB: Dossier de revue, écriture unique (alphaforge-suitability)
    API->>S3: Ajouter la revue au dossier
    U->>FE: Télécharger mon dossier
    FE->>API: GET /users/me/dossier
    API->>S3: Lire users/{nom}/dossier.md
    API-->>FE: Markdown
    end
```

## 3. Modèle de données (UML)

Les modèles Pydantic sont dans [`alphaforge/state.py`](../alphaforge/state.py). `GraphState` est le seul objet qui circule entre les nœuds ; chaque chiffre affiché renvoie à une `Evidence` par son identifiant.

```mermaid
classDiagram
    direction LR

    class GraphState {
        +date as_of_date
        +str persona
        +dict persona_data
        +str owner
        +str request_text
        +str language
        +list~str~ eligible_universe
        +list~dict~ exclusions
        +list~dict~ events
        +list~dict~ objections
        +dict explanation
        +dict verification
        +dict retries
        +list~dict~ trace
        +bool reviewed
        +str reviewer_id
        +str chosen_scenario
        +str advisor_rationale
    }

    class Profile {
        +str persona
        +str objective
        +int horizon_years
        +str risk_tolerance
        +str risk_capacity
        +list~str~ constraints
        +list~str~ preferences
        +float budget_cad
        +str account_type
        +str request_type
        +dict requested_idea
        +list~str~ excluded_tickers
        +list~str~ conflicts
        +dict current_holdings
        +str clarification_needed
    }

    class KycCompleteness {
        +bool is_complete
        +float score
        +list~str~ required_fields
        +list~str~ missing_fields
    }

    class KycField {
        +str name
        +str label
        +bool required
        +bool collected
        +str source
        +any value
        +str assumption_note
        +str evidence_id
    }

    class Evidence {
        +str id
        +any value
        +str source
        +date date
        +str date_kind
        +str url
        +str method
        +str confidence
    }

    class Scenario {
        +str name
        +dict weights
        +dict metrics
        +list~str~ notes
        +float turnover
        +list~dict~ trades
        +dict historical_outcomes
    }

    class Run {
        +str run_id
        +str owner
        +str status
        +str question
        +GraphState state
    }

    class User {
        +str user_id
        +str username
        +str email
        +list~str~ groups
        +is_advisor() bool
    }

    class UserDossierStore {
        <<interface>>
        +dossier_exists(username) bool
        +read_dossier(username) str
        +write_dossier(username, content)
    }
    class S3UserDossierStore
    class LocalUserDossierStore

    GraphState "1" *-- "0..1" Profile : profile
    GraphState "1" *-- "0..*" Evidence : evidence par id
    GraphState "1" *-- "0..3" Scenario : scenarios
    Profile "1" *-- "0..1" KycCompleteness : kyc_completeness
    KycCompleteness "1" *-- "0..*" KycField : fields
    Scenario ..> Evidence : metrics renvoie aux ids
    KycField ..> Evidence : evidence_id
    Run "1" o-- "0..1" GraphState : state
    Run ..> User : owner = u + username
    UserDossierStore <|.. S3UserDossierStore
    UserDossierStore <|.. LocalUserDossierStore
    User ..> UserDossierStore : un dossier par utilisateur
```

### Préfixes des identifiants de preuve

| Préfixe | Produit par | Contenu |
|---|---|---|
| `ES` | Filtrage | Exclusions et règles d'admissibilité |
| `EQ` | Métriques quantitatives | Statistiques de risque par actif |
| `EM` | Contexte macroéconomique | Indicateurs datés |
| `EN` | Agent 2 | Actualités et événements |
| `EP` | Scénarios | Indicateurs de portefeuille, plafonds, frais, fiscalité |
| `EK` | Agent 1 | Champs KYC et hypothèses |

### Où vit chaque donnée

| Donnée | Emplacement |
|---|---|
| Profil du questionnaire (anonyme) | `localStorage` du navigateur |
| Profil du compte, avoirs | DynamoDB `alphaforge-users` |
| État du graphe à chaque nœud | DynamoDB `alphaforge-checkpoints` |
| Trace et résultat d'un run | DynamoDB `alphaforge-traces` |
| Dossier de revue du conseiller | DynamoDB `alphaforge-suitability` |
| Dossier de l'utilisateur (profil, décisions) | S3 `users/<nom>/dossier.md` |
| Comptes et groupes | Cognito |
