import React, { useState, useEffect } from 'react';
import {
  GraphState,
  UserOnboardingProfile,
  WhatIfDiff,
  ScenarioName,
  SCENARIO_NAMES,
  SCENARIO_METRIC_LABELS,
  PersonaMeta,
} from '../types';
import {
  createRun,
  fetchRunState,
  subscribeRunEvents,
  compareRuns,
  fetchPersonas,
  prepareBackendPayload,
} from '../api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import {
  ArrowLeft,
  Columns2,
  Play,
  Loader2,
  AlertCircle,
  Clock,
  Shield,
  Target,
  Sparkles,
  FileText,
  AlertTriangle,
} from 'lucide-react';

interface PersonaComparisonViewProps {
  onBack: () => void;
  userProfile?: UserOnboardingProfile | null;
  onSelectEvidence?: (evidenceId: string) => void;
}

interface PersonaChoice {
  id: string;
  label: string;
  description: string;
  horizon: number;
  tolerance: string;
  capacity: string;
  isCustom?: boolean;
}

const DEFAULT_PERSONAS: PersonaChoice[] = [
  {
    id: 'robert',
    label: 'Robert, 59 ans',
    description: 'Horizon 4 ans · Tolérance faible à modérée · Préservation du capital',
    horizon: 4,
    tolerance: 'Faible à modérée',
    capacity: 'Faible',
  },
  {
    id: 'amira',
    label: 'Amira, 26 ans',
    description: 'Horizon 15 ans · Tolérance élevée · Croissance & crypto contrôlée',
    horizon: 15,
    tolerance: 'Élevée',
    capacity: 'Élevée',
  },
  {
    id: 'mateo',
    label: 'Mateo, 41 ans',
    description: 'Horizon 10 ans · Tolérance modérée · Équilibré & filtre ESG strict',
    horizon: 10,
    tolerance: 'Modérée',
    capacity: 'Modérée',
  },
];

const PRESET_REQUESTS = [
  {
    label: 'Idée TSLA 25 % (Jury test)',
    text: 'Je veux mettre 25 % de mon portefeuille dans TSLA.',
  },
  {
    label: 'Croissance diversifiée',
    text: "J'ai 100 000 $ CAD, un horizon long terme. J'aime la techno et la crypto mais je veux rester diversifié.",
  },
  {
    label: 'Allocation équilibrée ESG',
    text: 'Je veux un portefeuille équilibré et responsable sur environ 10 ans, sans entreprises controversées.',
  },
];

const SCENARIO_TITLES: Record<ScenarioName, string> = {
  current: 'Portefeuille actuel',
  capped: 'Scénario plafonné',
  as_requested: 'Scénario demandé',
  profile_baseline: 'Scénario de référence du profil',
};

const TOLERANCE_FR: Record<string, string> = {
  low: 'Faible',
  low_moderate: 'Faible à modérée',
  moderate: 'Modérée',
  high: 'Élevée',
};

const OBJECTIVE_FR: Record<string, string> = {
  growth: 'Croissance',
  balanced: 'Équilibre',
  capital_preservation: 'Préservation du capital',
};

const fr = (map: Record<string, string>, v?: string | null) => (v ? map[v] ?? v : '');

/** Evidence values are either a number or a dict {metric, value, unit}. */
const evidenceNumber = (value: unknown): number | null => {
  const raw = value !== null && typeof value === 'object' ? (value as { value?: unknown }).value : value;
  const n = typeof raw === 'number' ? raw : Number(raw);
  return Number.isFinite(n) ? n : null;
};

export const PersonaComparisonView: React.FC<PersonaComparisonViewProps> = ({
  onBack,
  userProfile,
  onSelectEvidence,
}) => {
  const [personaA, setPersonaA] = useState<string>('robert');
  const [personaB, setPersonaB] = useState<string>('amira');
  const [requestText, setRequestText] = useState<string>(
    'Je veux mettre 25 % de mon portefeuille dans TSLA.'
  );

  const [availablePersonas, setAvailablePersonas] = useState<PersonaChoice[]>(DEFAULT_PERSONAS);
  const [selectedScenario, setSelectedScenario] = useState<ScenarioName>('capped');

  // Execution state
  const [isComparing, setIsComparing] = useState<boolean>(false);
  const [statusA, setStatusA] = useState<string>('');
  const [statusB, setStatusB] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  // Completed run states and comparison diff
  const [stateA, setStateA] = useState<GraphState | null>(null);
  const [stateB, setStateB] = useState<GraphState | null>(null);
  const [diff, setDiff] = useState<WhatIfDiff | null>(null);

  // Load backend personas and optionally include custom profile
  useEffect(() => {
    fetchPersonas()
      .then((personasMeta: Record<string, PersonaMeta>) => {
        const list: PersonaChoice[] = Object.entries(personasMeta).map(([id, meta]) => ({
          id,
          label: meta.label || id,
          description: `${meta.horizon_years} ans · ${fr(TOLERANCE_FR, meta.risk_tolerance)} · ${fr(OBJECTIVE_FR, meta.objective)}`,
          horizon: meta.horizon_years,
          tolerance: meta.risk_tolerance,
          capacity: meta.risk_capacity,
        }));

        if (userProfile) {
          list.push({
            id: 'custom_user',
            label: 'Mon profil personnalisé',
            description: `${userProfile.firstWithdrawalHorizon} · ${userProfile.riskTolerance} · ${userProfile.primaryObjective}`,
            horizon: parseInt(userProfile.firstWithdrawalHorizon.match(/\d+/)?.[0] || '5', 10),
            tolerance: userProfile.riskTolerance,
            capacity: 'Profil utilisateur',
            isCustom: true,
          });
        }
        setAvailablePersonas(list);
      })
      .catch(() => {
        // Fallback to DEFAULT_PERSONAS
        if (userProfile) {
          setAvailablePersonas([
            ...DEFAULT_PERSONAS,
            {
              id: 'custom_user',
              label: 'Mon profil personnalisé',
              description: `${userProfile.firstWithdrawalHorizon} · ${userProfile.riskTolerance}`,
              horizon: 5,
              tolerance: userProfile.riskTolerance,
              capacity: 'Profil utilisateur',
              isCustom: true,
            },
          ]);
        }
      });
  }, [userProfile]);

  // Execute two runs simultaneously and compute diff
  const handleRunComparison = async () => {
    if (!requestText.trim()) return;
    setIsComparing(true);
    setError(null);
    setStateA(null);
    setStateB(null);
    setDiff(null);
    setStatusA('Démarrage...');
    setStatusB('Démarrage...');

    try {
      // Build payloads
      const payloadA =
        personaA === 'custom_user' && userProfile
          ? prepareBackendPayload(userProfile, requestText)
          : { persona: personaA, request_text: requestText };

      const payloadB =
        personaB === 'custom_user' && userProfile
          ? prepareBackendPayload(userProfile, requestText)
          : { persona: personaB, request_text: requestText };

      // Helper to run one persona to completion
      const executeOne = (
        payload: { persona: string; request_text: string; profile_data?: unknown; user_profile?: unknown },
        setStatus: (msg: string) => void
      ): Promise<GraphState> => {
        return new Promise<GraphState>((resolve, reject) => {
          createRun(payload.persona, payload.request_text, undefined, payload as Parameters<typeof createRun>[3])
            .then(({ run_id }) => {
              setStatus('Analyse en cours (agents)...');
              const unsub = subscribeRunEvents(
                run_id,
                (event) => {
                  if (event.type === 'trace' && event.entry) {
                    setStatus(`Agent : ${event.entry.node}`);
                  } else if (event.type === 'final') {
                    unsub();
                    fetchRunState(run_id).then(resolve).catch(reject);
                  } else if (event.type === 'error') {
                    unsub();
                    reject(new Error(event.error || "Erreur lors de l'exécution"));
                  }
                },
                (err) => {
                  unsub();
                  reject(err);
                }
              );
            })
            .catch(reject);
        });
      };

      // Run both in parallel
      const [resA, resB] = await Promise.all([
        executeOne(payloadA, setStatusA),
        executeOne(payloadB, setStatusB),
      ]);

      setStateA(resA);
      setStateB(resB);
      setStatusA('Terminé');
      setStatusB('Terminé');

      // Fetch diff from backend if run_ids available, or compute client-side
      if (resA.run_id && resB.run_id) {
        try {
          const compDiff = await compareRuns(resA.run_id, resB.run_id);
          setDiff(compDiff);
        } catch (diffErr) {
          console.warn('Could not fetch backend diff, computing client-side:', diffErr);
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Erreur lors de la comparaison : ${msg}`);
    } finally {
      setIsComparing(false);
    }
  };

  const choiceA = availablePersonas.find((p) => p.id === personaA);
  const choiceB = availablePersonas.find((p) => p.id === personaB);

  // Extract scenario objects for selected scenario
  const scA = stateA?.scenarios?.find((s) => s.name === selectedScenario);
  const scB = stateB?.scenarios?.find((s) => s.name === selectedScenario);

  // Union of all tickers in the selected scenario
  const allTickers = Array.from(
    new Set([...Object.keys(scA?.weights || {}), ...Object.keys(scB?.weights || {})])
  ).sort();

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-border">
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={onBack}
            className="gap-1.5 text-xs font-medium cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Retour à l&apos;analyse</span>
          </Button>
          <div className="flex items-center gap-2">
            <Columns2 className="w-5 h-5 text-primary" />
            <h1 className="text-base sm:text-lg font-bold text-foreground tracking-tight">
              Comparaison côte à côte · Même question, 2 profils
            </h1>
          </div>
        </div>

        <Badge variant="secondary" className="text-xs py-1 px-3">
          PolyFinances 2026 · Test du jury
        </Badge>
      </div>

      {/* Control Panel: Persona Pickers & Request Box */}
      <Card className="border-border bg-card shadow-xs">
        <CardContent className="p-4 sm:p-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Persona A Selector */}
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1.5">
                Profil A (Colonne de gauche) :
              </label>
              <div className="grid grid-cols-1 gap-1.5">
                {availablePersonas.map((p) => {
                  const isSel = p.id === personaA;
                  return (
                    <button
                      key={p.id}
                      type="button"
                      disabled={isComparing}
                      onClick={() => setPersonaA(p.id)}
                      className={`p-2.5 rounded-lg text-left text-xs transition-all border ${
                        isSel
                          ? 'border-primary bg-primary/10 font-medium text-foreground'
                          : 'border-border/60 hover:border-border text-muted-foreground bg-muted/20'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-foreground">{p.label}</span>
                        <Badge variant={isSel ? 'default' : 'outline'} className="text-[10px] py-0 px-1.5">
                          Profil A
                        </Badge>
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-1">
                        {p.description}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Persona B Selector */}
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1.5">
                Profil B (Colonne de droite) :
              </label>
              <div className="grid grid-cols-1 gap-1.5">
                {availablePersonas.map((p) => {
                  const isSel = p.id === personaB;
                  return (
                    <button
                      key={p.id}
                      type="button"
                      disabled={isComparing}
                      onClick={() => setPersonaB(p.id)}
                      className={`p-2.5 rounded-lg text-left text-xs transition-all border ${
                        isSel
                          ? 'border-blue-500 bg-blue-500/10 font-medium text-foreground'
                          : 'border-border/60 hover:border-border text-muted-foreground bg-muted/20'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-foreground">{p.label}</span>
                        <Badge variant={isSel ? 'default' : 'outline'} className="text-[10px] py-0 px-1.5">
                          Profil B
                        </Badge>
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-1">
                        {p.description}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Shared Request Input */}
          <div className="pt-2 border-t border-border/50 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="block text-xs font-semibold text-foreground">
                Question / Requête commune à soumettre aux deux profils :
              </label>
              <div className="flex flex-wrap gap-1.5">
                {PRESET_REQUESTS.map((preset) => (
                  <Button
                    key={preset.label}
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isComparing}
                    onClick={() => setRequestText(preset.text)}
                    className="h-6 text-[11px] px-2 text-primary hover:bg-primary/10"
                  >
                    {preset.label}
                  </Button>
                ))}
              </div>
            </div>

            <Textarea
              rows={2}
              value={requestText}
              onChange={(e) => setRequestText(e.target.value)}
              disabled={isComparing}
              placeholder="Entrez une question d'investissement pour comparer les réponses..."
              className="text-xs bg-card"
            />

            <div className="flex justify-end pt-1">
              <Button
                type="button"
                onClick={handleRunComparison}
                disabled={isComparing || !requestText.trim()}
                className="gap-2 text-xs font-semibold px-4"
              >
                {isComparing ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Calcul comparatif en cours...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-current" />
                    <span>Lancer la comparaison côte à côte</span>
                  </>
                )}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Error notification */}
      {error && (
        <div className="p-3.5 bg-destructive/10 border border-destructive/30 rounded-lg text-xs text-destructive flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Loading Progress while running */}
      {isComparing && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 animate-pulse">
          <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg text-xs text-foreground flex items-center gap-3">
            <Loader2 className="w-4 h-4 animate-spin text-primary shrink-0" />
            <div>
              <span className="font-semibold block">{choiceA?.label}</span>
              <span className="text-muted-foreground text-[11px]">{statusA}</span>
            </div>
          </div>
          <div className="p-4 bg-blue-500/5 border border-blue-500/20 rounded-lg text-xs text-foreground flex items-center gap-3">
            <Loader2 className="w-4 h-4 animate-spin text-blue-500 shrink-0" />
            <div>
              <span className="font-semibold block">{choiceB?.label}</span>
              <span className="text-muted-foreground text-[11px]">{statusB}</span>
            </div>
          </div>
        </div>
      )}

      {/* Results View: Two Columns Side-by-Side */}
      {stateA && stateB && !isComparing && (
        <div className="space-y-5">
          {/* Summary / Differences Banner */}
          {diff?.summary && diff.summary.length > 0 && (
            <div className="p-3.5 bg-muted/40 border border-border rounded-lg text-xs text-foreground space-y-1.5">
              <div className="flex items-center gap-2 font-semibold text-primary">
                <Sparkles className="w-4 h-4" />
                <span>Différences majeures d&apos;allocation calculées par le moteur :</span>
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-muted-foreground text-[11px]">
                {diff.summary.map((line, idx) => (
                  <li key={idx}>{line}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Scenario Tab Switcher */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-2 bg-muted/30 rounded-lg border border-border/60">
            <span className="text-xs font-semibold text-foreground px-2">Scénario visualisé :</span>
            <div className="flex flex-wrap gap-1.5">
              {SCENARIO_NAMES.map((sName) => (
                <Button
                  key={sName}
                  type="button"
                  variant={selectedScenario === sName ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedScenario(sName)}
                  className="h-7 text-xs"
                >
                  {SCENARIO_TITLES[sName]}
                </Button>
              ))}
            </div>
          </div>

          {/* TWO COLUMNS SIDE BY SIDE */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* COLUMN A */}
            <div className="space-y-4">
              {/* Persona A Header Card */}
              <Card className="border-primary/40 bg-card shadow-xs ring-1 ring-primary/20">
                <CardContent className="p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-sm text-foreground">{choiceA?.label}</span>
                    <Badge variant="default" className="text-xs">
                      Profil A
                    </Badge>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-[11px] pt-1">
                    <div className="flex items-center gap-1 text-muted-foreground">
                      <Clock className="w-3 h-3 text-primary shrink-0" />
                      <span>{stateA.profile?.horizon_years ?? choiceA?.horizon} ans</span>
                    </div>
                    <div className="flex items-center gap-1 text-muted-foreground">
                      <Shield className="w-3 h-3 text-amber-500 shrink-0" />
                      <span className="truncate">{fr(TOLERANCE_FR, stateA.profile?.risk_tolerance || choiceA?.tolerance)}</span>
                    </div>
                    <div className="flex items-center gap-1 text-muted-foreground">
                      <Target className="w-3 h-3 text-emerald-500 shrink-0" />
                      <span className="truncate">{fr(OBJECTIVE_FR, stateA.profile?.objective) || 'Objectif'}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Conflicts if any */}
              {stateA.profile?.conflicts && stateA.profile.conflicts.length > 0 && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs text-amber-950 dark:text-amber-200">
                  <div className="flex items-center gap-1.5 font-semibold text-amber-800 dark:text-amber-300 mb-1">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>Contradiction détectée :</span>
                  </div>
                  <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                    {stateA.profile.conflicts.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Scenario Weights & Metrics Card */}
              <Card className="border-border bg-card shadow-xs">
                <CardContent className="p-4 space-y-3">
                  <h4 className="text-xs font-bold text-foreground uppercase tracking-wider">
                    Allocation d&apos;actifs · {SCENARIO_TITLES[selectedScenario]}
                  </h4>

                  {/* Weights Table */}
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead>
                        <tr className="border-b border-border/60 text-muted-foreground text-[11px]">
                          <th className="py-1.5 font-medium">Actif</th>
                          <th className="py-1.5 font-medium text-right">Poids A</th>
                          <th className="py-1.5 font-medium text-right">Écart vs B</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/30">
                        {allTickers.map((ticker) => {
                          const wA = scA?.weights?.[ticker] || 0;
                          const wB = scB?.weights?.[ticker] || 0;
                          const delta = wA - wB;

                          if (wA === 0 && wB === 0) return null;

                          return (
                            <tr key={ticker} className="hover:bg-muted/20">
                              <td className="py-1.5 font-semibold text-foreground flex items-center gap-1.5">
                                <span>{ticker}</span>
                                {wA === 0 && (
                                  <Badge variant="outline" className="text-[9px] py-0 px-1 text-muted-foreground">
                                    0 %
                                  </Badge>
                                )}
                              </td>
                              <td className="py-1.5 text-right font-mono font-medium">
                                {(wA * 100).toFixed(1)} %
                              </td>
                              <td className="py-1.5 text-right font-mono text-[11px]">
                                {Math.abs(delta) > 1e-4 ? (
                                  <span
                                    className={
                                      delta > 0
                                        ? 'text-emerald-600 dark:text-emerald-400 font-semibold'
                                        : 'text-amber-600 dark:text-amber-400 font-semibold'
                                    }
                                  >
                                    {delta > 0 ? '+' : ''}
                                    {(delta * 100).toFixed(1)} %
                                  </span>
                                ) : (
                                  <span className="text-muted-foreground/60">=</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Metrics Section */}
                  <div className="pt-2 border-t border-border/50">
                    <span className="text-[11px] font-semibold text-foreground block mb-2">
                      Métriques quantitatives :
                    </span>
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      {Object.entries(SCENARIO_METRIC_LABELS).map(([mKey, mLabel]) => {
                        const eidA = scA?.metrics?.[mKey];
                        const evA = eidA && stateA.evidence ? stateA.evidence[eidA] : null;
                        const valA = evA ? evidenceNumber(evA.value) : null;

                        return (
                          <div key={mKey} className="p-2 rounded-md bg-muted/30 border border-border/40">
                            <span className="text-muted-foreground block text-[10px] truncate" title={mLabel}>
                              {mLabel}
                            </span>
                            <span className="font-mono font-semibold text-foreground block mt-0.5">
                              {valA != null
                                ? mKey.includes('hhi')
                                  ? valA.toFixed(3)
                                  : `${(valA * 100).toFixed(1)} %`
                                : 'n.d.'}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* 4-Question Explanation for Column A */}
              {stateA.explanation && (
                <Card className="border-border bg-card shadow-xs">
                  <CardContent className="p-4 space-y-3 text-xs">
                    <div className="flex items-center gap-1.5 font-bold text-foreground pb-2 border-b border-border/60">
                      <FileText className="w-4 h-4 text-primary" />
                      <span>Explication en 4 questions (Profil A)</span>
                    </div>

                    {/* Résumé */}
                    <div>
                      <span className="font-semibold text-foreground block text-[11px]">
                        1. Synthèse globale :
                      </span>
                      <p className="mt-1 text-muted-foreground leading-relaxed">
                        {stateA.explanation.resume}
                      </p>
                    </div>

                    {/* Quelles données */}
                    <div>
                      <span className="font-semibold text-foreground block text-[11px]">
                        2. Quelles données ont été prises en compte ?
                      </span>
                      <ul className="mt-1 space-y-1 text-muted-foreground">
                        {stateA.explanation.quelles_donnees?.slice(0, 2).map((item, i) => (
                          <li key={i} className="flex flex-wrap items-start gap-1">
                            <span className="text-primary">•</span>
                            <span>{item.claim}</span>
                            {item.evidence?.map((eid) => (
                              <button
                                key={eid}
                                type="button"
                                onClick={() => onSelectEvidence?.(eid)}
                                className="inline-flex items-center text-[10px] px-1 py-0.5 rounded bg-primary/10 text-primary hover:bg-primary/20 font-mono cursor-pointer"
                              >
                                {eid}
                              </button>
                            ))}
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Pourquoi ce choix */}
                    <div>
                      <span className="font-semibold text-foreground block text-[11px]">
                        3. Pourquoi ce choix de scénario ?
                      </span>
                      <p className="mt-1 text-muted-foreground">
                        Scénario le plus cohérent :{' '}
                        <strong className="text-foreground">
                          {stateA.explanation.scenario_le_plus_coherent}
                        </strong>
                      </p>
                    </div>

                    {/* Limites */}
                    <div>
                      <span className="font-semibold text-foreground block text-[11px]">
                        4. Limites & ce qui changerait la réponse :
                      </span>
                      <p className="mt-1 text-muted-foreground leading-relaxed">
                        {stateA.explanation.incertitude || stateA.explanation.avertissement}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* COLUMN B */}
            <div className="space-y-4">
              {/* Persona B Header Card */}
              <Card className="border-blue-500/40 bg-card shadow-xs ring-1 ring-blue-500/20">
                <CardContent className="p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-sm text-foreground">{choiceB?.label}</span>
                    <Badge variant="secondary" className="text-xs bg-blue-500/10 text-blue-700 dark:text-blue-300">
                      Profil B
                    </Badge>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-[11px] pt-1">
                    <div className="flex items-center gap-1 text-muted-foreground">
                      <Clock className="w-3 h-3 text-blue-500 shrink-0" />
                      <span>{stateB.profile?.horizon_years ?? choiceB?.horizon} ans</span>
                    </div>
                    <div className="flex items-center gap-1 text-muted-foreground">
                      <Shield className="w-3 h-3 text-amber-500 shrink-0" />
                      <span className="truncate">{fr(TOLERANCE_FR, stateB.profile?.risk_tolerance || choiceB?.tolerance)}</span>
                    </div>
                    <div className="flex items-center gap-1 text-muted-foreground">
                      <Target className="w-3 h-3 text-emerald-500 shrink-0" />
                      <span className="truncate">{fr(OBJECTIVE_FR, stateB.profile?.objective) || 'Objectif'}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Conflicts if any */}
              {stateB.profile?.conflicts && stateB.profile.conflicts.length > 0 && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs text-amber-950 dark:text-amber-200">
                  <div className="flex items-center gap-1.5 font-semibold text-amber-800 dark:text-amber-300 mb-1">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>Contradiction détectée :</span>
                  </div>
                  <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                    {stateB.profile.conflicts.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Scenario Weights & Metrics Card */}
              <Card className="border-border bg-card shadow-xs">
                <CardContent className="p-4 space-y-3">
                  <h4 className="text-xs font-bold text-foreground uppercase tracking-wider">
                    Allocation d&apos;actifs · {SCENARIO_TITLES[selectedScenario]}
                  </h4>

                  {/* Weights Table */}
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead>
                        <tr className="border-b border-border/60 text-muted-foreground text-[11px]">
                          <th className="py-1.5 font-medium">Actif</th>
                          <th className="py-1.5 font-medium text-right">Poids B</th>
                          <th className="py-1.5 font-medium text-right">Écart vs A</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/30">
                        {allTickers.map((ticker) => {
                          const wA = scA?.weights?.[ticker] || 0;
                          const wB = scB?.weights?.[ticker] || 0;
                          const delta = wB - wA;

                          if (wA === 0 && wB === 0) return null;

                          return (
                            <tr key={ticker} className="hover:bg-muted/20">
                              <td className="py-1.5 font-semibold text-foreground flex items-center gap-1.5">
                                <span>{ticker}</span>
                                {wB === 0 && (
                                  <Badge variant="outline" className="text-[9px] py-0 px-1 text-muted-foreground">
                                    0 %
                                  </Badge>
                                )}
                              </td>
                              <td className="py-1.5 text-right font-mono font-medium">
                                {(wB * 100).toFixed(1)} %
                              </td>
                              <td className="py-1.5 text-right font-mono text-[11px]">
                                {Math.abs(delta) > 1e-4 ? (
                                  <span
                                    className={
                                      delta > 0
                                        ? 'text-emerald-600 dark:text-emerald-400 font-semibold'
                                        : 'text-amber-600 dark:text-amber-400 font-semibold'
                                    }
                                  >
                                    {delta > 0 ? '+' : ''}
                                    {(delta * 100).toFixed(1)} %
                                  </span>
                                ) : (
                                  <span className="text-muted-foreground/60">=</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Metrics Section */}
                  <div className="pt-2 border-t border-border/50">
                    <span className="text-[11px] font-semibold text-foreground block mb-2">
                      Métriques quantitatives :
                    </span>
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      {Object.entries(SCENARIO_METRIC_LABELS).map(([mKey, mLabel]) => {
                        const eidB = scB?.metrics?.[mKey];
                        const evB = eidB && stateB.evidence ? stateB.evidence[eidB] : null;
                        const valB = evB ? evidenceNumber(evB.value) : null;

                        return (
                          <div key={mKey} className="p-2 rounded-md bg-muted/30 border border-border/40">
                            <span className="text-muted-foreground block text-[10px] truncate" title={mLabel}>
                              {mLabel}
                            </span>
                            <span className="font-mono font-semibold text-foreground block mt-0.5">
                              {valB != null
                                ? mKey.includes('hhi')
                                  ? valB.toFixed(3)
                                  : `${(valB * 100).toFixed(1)} %`
                                : 'n.d.'}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* 4-Question Explanation for Column B */}
              {stateB.explanation && (
                <Card className="border-border bg-card shadow-xs">
                  <CardContent className="p-4 space-y-3 text-xs">
                    <div className="flex items-center gap-1.5 font-bold text-foreground pb-2 border-b border-border/60">
                      <FileText className="w-4 h-4 text-blue-500" />
                      <span>Explication en 4 questions (Profil B)</span>
                    </div>

                    {/* Résumé */}
                    <div>
                      <span className="font-semibold text-foreground block text-[11px]">
                        1. Synthèse globale :
                      </span>
                      <p className="mt-1 text-muted-foreground leading-relaxed">
                        {stateB.explanation.resume}
                      </p>
                    </div>

                    {/* Quelles données */}
                    <div>
                      <span className="font-semibold text-foreground block text-[11px]">
                        2. Quelles données ont été prises en compte ?
                      </span>
                      <ul className="mt-1 space-y-1 text-muted-foreground">
                        {stateB.explanation.quelles_donnees?.slice(0, 2).map((item, i) => (
                          <li key={i} className="flex flex-wrap items-start gap-1">
                            <span className="text-blue-500">•</span>
                            <span>{item.claim}</span>
                            {item.evidence?.map((eid) => (
                              <button
                                key={eid}
                                type="button"
                                onClick={() => onSelectEvidence?.(eid)}
                                className="inline-flex items-center text-[10px] px-1 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 font-mono cursor-pointer"
                              >
                                {eid}
                              </button>
                            ))}
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Pourquoi ce choix */}
                    <div>
                      <span className="font-semibold text-foreground block text-[11px]">
                        3. Pourquoi ce choix de scénario ?
                      </span>
                      <p className="mt-1 text-muted-foreground">
                        Scénario le plus cohérent :{' '}
                        <strong className="text-foreground">
                          {stateB.explanation.scenario_le_plus_coherent}
                        </strong>
                      </p>
                    </div>

                    {/* Limites */}
                    <div>
                      <span className="font-semibold text-foreground block text-[11px]">
                        4. Limites & ce qui changerait la réponse :
                      </span>
                      <p className="mt-1 text-muted-foreground leading-relaxed">
                        {stateB.explanation.incertitude || stateB.explanation.avertissement}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
