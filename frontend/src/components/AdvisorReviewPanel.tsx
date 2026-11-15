import React, { useState } from 'react';
import { GraphState, AuthUser, Scenario } from '../types';
import { reviewRun, getSuitabilityPdfUrl } from '../api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import {
  ShieldCheck,
  CheckCircle2,
  FileDown,
  AlertTriangle,
  Loader2,
  Check,
  Sliders,
  FileText,
} from 'lucide-react';

interface AdvisorReviewPanelProps {
  runId: string;
  graphState: GraphState;
  currentUser: AuthUser | null;
  onReviewed: (updatedState: Partial<GraphState>) => void;
}

export const AdvisorReviewPanel: React.FC<AdvisorReviewPanelProps> = ({
  runId,
  graphState,
  currentUser,
  onReviewed,
}) => {
  const isAdvisor = currentUser?.is_advisor === true;
  const isAlreadyReviewed = graphState.reviewed === true;

  const scenarios: Scenario[] = graphState.scenarios || [];
  const mostConsistentName = graphState.explanation?.scenario_le_plus_coherent || 'capped';

  const [chosenScenario, setChosenScenario] = useState<string>(
    graphState.chosen_scenario || mostConsistentName
  );
  const [rationale, setRationale] = useState<string>(
    graphState.advisor_rationale || ''
  );
  const [showEditAssumptions, setShowEditAssumptions] = useState<boolean>(false);
  const [editedHorizon, setEditedHorizon] = useState<number>(
    graphState.profile?.horizon_years || 10
  );
  const [editedRisk, setEditedRisk] = useState<string>(
    graphState.profile?.risk_tolerance || 'moderate'
  );

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  if (!isAdvisor) {
    return null;
  }

  const handleSignOff = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rationale.trim() || rationale.trim().length < 10) {
      setError('Veuillez fournir une justification professionnelle détaillée (au moins 10 caractères).');
      return;
    }
    setIsSubmitting(true);
    setError(null);

    const editedAssumptions = showEditAssumptions
      ? { horizon_years: editedHorizon, risk_tolerance: editedRisk }
      : null;

    try {
      const res = await reviewRun(runId, chosenScenario, rationale.trim(), editedAssumptions);
      onReviewed({
        reviewed: true,
        reviewer_id: res.reviewer_id,
        reviewed_at: res.reviewed_at,
        chosen_scenario: res.chosen_scenario,
        advisor_rationale: rationale.trim(),
        edited_assumptions: editedAssumptions,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Échec de la validation du conseiller.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDownloadPdf = () => {
    const url = getSuitabilityPdfUrl(runId);
    window.open(url, '_blank');
  };

  return (
    <Card className="border-amber-500/40 bg-amber-500/5 dark:bg-amber-950/10 shadow-md my-6 overflow-hidden">
      <CardContent className="p-6 space-y-6">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-border/80">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-amber-500/20 text-amber-600 dark:text-amber-400">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-foreground">
                  Module Conseiller · Revue de la convenance (PRD B-14)
                </h2>
                <Badge variant="outline" className="border-amber-500/50 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]">
                  Rôle conseiller
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Validez la recommandation, consignez votre justification et générez le dossier de convenance immuable.
              </p>
            </div>
          </div>

          {isAlreadyReviewed && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleDownloadPdf}
              className="gap-1.5 text-xs border-emerald-500/40 text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20"
            >
              <FileDown className="h-3.5 w-3.5" />
              <span>Télécharger le dossier (PDF)</span>
            </Button>
          )}
        </div>

        {/* State 1: Already reviewed */}
        {isAlreadyReviewed ? (
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-950 dark:text-emerald-200">
              <div className="flex items-start gap-3">
                <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" />
                <div className="space-y-1 text-xs">
                  <div className="font-semibold text-sm">
                    Recommandation validée et signée électroniquement
                  </div>
                  <p className="text-muted-foreground">
                    Revu par <span className="font-semibold text-foreground">{graphState.reviewer_id}</span> le{' '}
                    {graphState.reviewed_at ? new Date(graphState.reviewed_at).toLocaleString('fr-CA') : 'Date récente'}.
                  </p>
                  <p className="pt-1">
                    <span className="font-medium text-foreground">Scénario recommandé :</span>{' '}
                    <Badge variant="secondary" className="ml-1 uppercase font-mono text-[11px]">
                      {graphState.chosen_scenario}
                    </Badge>
                  </p>
                </div>
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-card border border-border/60 text-xs space-y-1">
              <span className="font-semibold text-foreground uppercase tracking-wider text-[10px] text-muted-foreground">
                Justification consignée par le conseiller
              </span>
              <p className="text-foreground leading-relaxed whitespace-pre-wrap">
                {graphState.advisor_rationale}
              </p>
            </div>
          </div>
        ) : (
          /* State 2: Advisor review in progress */
          <form onSubmit={handleSignOff} className="space-y-5">
            {error && (
              <div className="flex items-center gap-2 p-3 text-xs rounded-lg bg-destructive/10 text-destructive border border-destructive/20">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Audit quick summary */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-3 rounded-lg bg-card border border-border/50 text-xs">
                <span className="text-[10px] uppercase font-semibold text-muted-foreground block">
                  Vérificateur Agent 4
                </span>
                <span className={`font-semibold flex items-center gap-1 mt-0.5 ${graphState.verification?.passed ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-500'}`}>
                  {graphState.verification?.passed ? <Check className="h-3.5 w-3.5" /> : null}
                  {graphState.verification?.passed ? 'Vérifié conforme' : 'Non vérifié'}
                </span>
              </div>

              <div className="p-3 rounded-lg bg-card border border-border/50 text-xs">
                <span className="text-[10px] uppercase font-semibold text-muted-foreground block">
                  Objections Red Team
                </span>
                <span className="font-semibold text-foreground mt-0.5 block">
                  {graphState.objections?.length || 0} objection(s) analysée(s)
                </span>
              </div>

              <div className="p-3 rounded-lg bg-card border border-border/50 text-xs">
                <span className="text-[10px] uppercase font-semibold text-muted-foreground block">
                  Plus cohérent (Modèle)
                </span>
                <span className="font-semibold text-foreground mt-0.5 block uppercase font-mono">
                  {mostConsistentName}
                </span>
              </div>
            </div>

            {/* Step 1: Scenario Selection */}
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase text-muted-foreground tracking-wider">
                1. Sélectionner le scénario à recommander au client
              </Label>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {scenarios.map((sc) => {
                  const isSelected = chosenScenario === sc.name;
                  return (
                    <button
                      key={sc.name}
                      type="button"
                      onClick={() => setChosenScenario(sc.name)}
                      className={`p-3 rounded-xl border text-left transition-all relative ${
                        isSelected
                          ? 'border-primary bg-primary/10 shadow-xs'
                          : 'border-border/70 bg-card hover:border-border'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-xs text-foreground uppercase font-mono">
                          {sc.name}
                        </span>
                        {isSelected && <Check className="h-4 w-4 text-primary" />}
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        {Object.keys(sc.weights || {}).length} actifs · Poids principal :{' '}
                        {Object.entries(sc.weights || {}).sort((a, b) => b[1] - a[1])[0]
                          ? `${(Object.entries(sc.weights)[0][1] * 100).toFixed(0)} %`
                          : '—'}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Step 2: Optional Assumptions Adjustment */}
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => setShowEditAssumptions(!showEditAssumptions)}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground font-medium"
              >
                <Sliders className="h-3.5 w-3.5" />
                <span>{showEditAssumptions ? 'Masquer l’ajustement des hypothèses' : 'Ajuster les hypothèses KYC (optionnel)'}</span>
              </button>

              {showEditAssumptions && (
                <div className="p-3.5 rounded-lg bg-card border border-border/70 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div className="space-y-1">
                    <Label htmlFor="adv-horizon" className="text-[11px]">Horizon temporel (années)</Label>
                    <Input
                      id="adv-horizon"
                      type="number"
                      min={1}
                      max={40}
                      value={editedHorizon}
                      onChange={(e) => setEditedHorizon(Number(e.target.value))}
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="adv-risk" className="text-[11px]">Tolérance au risque validée</Label>
                    <select
                      id="adv-risk"
                      value={editedRisk}
                      onChange={(e) => setEditedRisk(e.target.value)}
                      className="w-full h-8 rounded-md border border-input bg-background px-2 py-1 text-xs"
                    >
                      <option value="low">Faible</option>
                      <option value="low_moderate">Faible à modéré</option>
                      <option value="moderate">Modéré</option>
                      <option value="high">Élevé</option>
                    </select>
                  </div>
                </div>
              )}
            </div>

            {/* Step 3: Advisor Rationale */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="adv-rationale" className="text-xs font-semibold uppercase text-muted-foreground tracking-wider flex items-center gap-1.5">
                  <FileText className="h-3.5 w-3.5 text-amber-500" />
                  2. Justification professionnelle du conseiller (obligatoire)
                </Label>
                <span className="text-[11px] text-muted-foreground">Min. 10 caractères</span>
              </div>
              <Textarea
                id="adv-rationale"
                rows={3}
                placeholder="Rédigez ici la justification de convenance réglementaire expliquant pourquoi le scénario retenu est approprié au regard des objectifs, de la tolérance et de la capacité de risque du client..."
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                required
                className="text-xs leading-relaxed bg-card"
              />
            </div>

            {/* Submit Sign-off button */}
            <div className="flex items-center justify-between pt-2">
              <div className="text-[11px] text-muted-foreground">
                Signataire : <span className="font-semibold text-foreground">{currentUser?.username}</span> (Conseiller agréé)
              </div>
              <Button
                type="submit"
                disabled={isSubmitting || rationale.trim().length < 10}
                className="gap-2 bg-amber-600 hover:bg-amber-700 text-white font-medium text-xs px-5 shadow-sm"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Signature & génération du dossier...
                  </>
                ) : (
                  <>
                    <ShieldCheck className="h-4 w-4" />
                    Signer et valider la recommandation
                  </>
                )}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
};
