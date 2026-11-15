import React, { useState, useRef } from 'react';
import { Button } from '@/components/ui/button';
import {
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react';
import {
  GraphState,
  UserOnboardingProfile,
  WhatIfDiff,
  AuthUser,
} from '../types';
import { getSuitabilityPdfUrl } from '../api';
import { useLanguage } from '@/context/LanguageContext';
import { ScenarioCards } from './ScenarioCards';
import { ExplanationSection } from './ExplanationSection';
import { ExclusionsCard } from './ExclusionsCard';
import { EvidenceTable } from './EvidenceTable';
import { NodeTrace } from './NodeTrace';
import { ConflictsAlert } from './ConflictsAlert';
import { WhatIfControls } from './WhatIfControls';
import { WhatIfDiffView } from './WhatIfDiffView';
import { AdvisorReviewPanel } from './AdvisorReviewPanel';
import { SimulationBanner } from './SimulationBanner';
import { AppHeader } from './AppHeader';

interface ResponseScreenProps {
  runState: GraphState;
  userProfile: UserOnboardingProfile | null;
  customProfile?: UserOnboardingProfile | null;
  activePersonaId?: 'custom' | 'robert' | 'amira' | 'mateo';
  onSelectPersona?: (personaId: 'custom' | 'robert' | 'amira' | 'mateo') => void;
  requestText: string;
  onAskAnother: () => void;
  onEditProfile: () => void;
  onResetProfile?: () => void;
  onSelectEvidence: (evidenceId: string) => void;
  whatIfDiff: WhatIfDiff | null;
  onCloseWhatIfDiff: () => void;
  onRunWhatIf: (field: string, value: unknown) => void;
  isWhatIfRunning: boolean;
  onOpenHistory?: () => void;
  currentUser?: AuthUser | null;
  onOpenAuth?: () => void;
  onOpenProfile?: () => void;
  onLogout?: () => void;
  onReviewed?: (updated: Partial<GraphState>) => void;
}

export const ResponseScreen: React.FC<ResponseScreenProps> = ({
  runState,
  userProfile,
  customProfile,
  activePersonaId = 'custom',
  onSelectPersona,
  requestText,
  onAskAnother,
  onEditProfile,
  onResetProfile,
  onSelectEvidence,
  whatIfDiff,
  onCloseWhatIfDiff,
  onRunWhatIf,
  isWhatIfRunning,
  onOpenHistory,
  currentUser,
  onOpenAuth,
  onOpenProfile,
  onLogout,
  onReviewed,
}) => {
  const [showDetails, setShowDetails] = useState(false);
  const detailsRef = useRef<HTMLDivElement>(null);
  const { language } = useLanguage();
  const isEn = language === 'en';

  // Strip out contextual metadata from the question heading
  const cleanQuestion = (requestText || runState.request_text || '')
    .split('\n\n[Contexte investisseur]')[0]
    .split('[Contexte investisseur]')[0]
    .trim();

  const effectiveRunId = runState.run_id || null;

  const handleToggleDetails = () => {
    const nextState = !showDetails;
    setShowDetails(nextState);
    if (nextState) {
      setTimeout(() => {
        detailsRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col justify-between font-sans transition-colors">
      <div>
        {/* Simulation Banner with Sign-off info and PDF generation */}
        <SimulationBanner
          isReviewed={runState.reviewed}
          reviewerId={runState.reviewer_id}
          reviewedAt={runState.reviewed_at}
          onDownloadPdf={
            effectiveRunId
              ? () => window.open(getSuitabilityPdfUrl(effectiveRunId), '_blank')
              : undefined
          }
        />

        {/* Clean, Non-overlapping Header */}
        <AppHeader
          userProfile={userProfile}
          customProfile={customProfile}
          activePersonaId={activePersonaId}
          onSelectPersona={onSelectPersona}
          onEditProfile={onEditProfile}
          onOpenHistory={onOpenHistory}
          currentUser={currentUser}
          onOpenAuth={onOpenAuth}
          onOpenProfile={onOpenProfile}
          onLogout={onLogout}
          rightActions={
            onResetProfile ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={onResetProfile}
                className="h-8 gap-1 text-xs text-muted-foreground hover:text-destructive cursor-pointer"
                title={isEn ? 'Reset profile and return to home' : "Réinitialiser et retourner à l'accueil"}
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{isEn ? 'Reset' : 'Réinitialiser'}</span>
              </Button>
            ) : undefined
          }
        />

        {/* Main Content Area */}
        <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">
          {/* Question Title */}
          <div className="text-center space-y-1">
            <h1 className="text-sm sm:text-base font-medium text-foreground tracking-tight leading-snug">
              « {cleanQuestion} »
            </h1>
          </div>

          {/* Direct Answer Card */}
          {runState.explanation && (
            <div className="p-5 sm:p-6 bg-card border border-border rounded-2xl shadow-sm space-y-4 text-left">
              {/* Profile Context Badges */}
              {runState.profile && (
                <div className="flex flex-wrap items-center gap-2 pb-3 border-b border-border/50 text-xs">
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-primary/10 text-primary">
                    {isEn ? 'Profile-based assessment' : 'Évaluation selon le profil'}
                  </span>
                  {runState.profile.horizon_years && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-muted text-foreground font-medium text-[11px]">
                      {isEn ? `Horizon: ${runState.profile.horizon_years} yrs` : `Horizon : ${runState.profile.horizon_years} ans`}
                    </span>
                  )}
                  {runState.profile.risk_tolerance && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-muted text-foreground font-medium text-[11px]">
                      {isEn
                        ? `Tolerance: ${runState.profile.risk_tolerance}`
                        : `Risque : ${
                            runState.profile.risk_tolerance === 'high'
                              ? 'Élevé'
                              : runState.profile.risk_tolerance === 'low_moderate'
                              ? 'Faible à modéré'
                              : runState.profile.risk_tolerance === 'low'
                              ? 'Faible'
                              : 'Modéré'
                          }`}
                    </span>
                  )}
                  {runState.profile.risk_capacity && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-muted text-foreground font-medium text-[11px]">
                      {isEn
                        ? `Capacity: ${runState.profile.risk_capacity}`
                        : `Capacité : ${
                            runState.profile.risk_capacity === 'high'
                              ? 'Élevée'
                              : runState.profile.risk_capacity === 'low'
                              ? 'Faible'
                              : 'Modérée'
                          }`}
                    </span>
                  )}
                  {runState.profile.objective && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-muted text-foreground font-medium text-[11px]">
                      {isEn
                        ? `Objective: ${runState.profile.objective}`
                        : `Objectif : ${
                            runState.profile.objective === 'capital_preservation'
                              ? 'Préservation du capital'
                              : runState.profile.objective === 'growth'
                              ? 'Croissance'
                              : 'Équilibré'
                          }`}
                    </span>
                  )}
                </div>
              )}

              <div className="space-y-3.5 text-xs sm:text-sm leading-relaxed text-foreground font-normal">
                {runState.explanation.resume.split('\n\n').map((paragraph, idx) => (
                  <p key={idx} className="leading-relaxed">
                    {paragraph}
                  </p>
                ))}
              </div>

              {runState.explanation.avertissement &&
                !runState.explanation.avertissement.toLowerCase().includes('simulation éducative') &&
                !runState.explanation.avertissement.toLowerCase().includes('aucun conseil') && (
                  <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg flex items-start gap-2 text-xs text-amber-900 dark:text-amber-200">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                    <p className="leading-relaxed">{runState.explanation.avertissement}</p>
                  </div>
                )}
            </div>
          )}

          {/* Action Buttons: Poser une autre question & Voir plus de détails */}
          <div className="space-y-2.5 pt-2 max-w-xl mx-auto">
            <Button
              type="button"
              onClick={onAskAnother}
              className="w-full h-10 text-xs sm:text-sm font-medium cursor-pointer"
            >
              {isEn ? 'Ask another question' : 'Poser une autre question'}
            </Button>

            <Button
              type="button"
              variant="outline"
              onClick={handleToggleDetails}
              className="w-full h-10 text-xs sm:text-sm font-normal cursor-pointer flex items-center justify-center gap-1.5"
            >
              <span>
                {showDetails
                  ? isEn
                    ? 'Hide audit details & evidence'
                    : 'Masquer les détails d’audit et preuves'
                  : isEn
                  ? 'Show audit details & evidence'
                  : 'Voir les détails d’audit et preuves'}
              </span>
              {showDetails ? (
                <ChevronUp className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              )}
            </Button>
          </div>
        </main>

        {/* Detailed Jury-Graded Technical Analysis Section (Revealed on click) */}
        {showDetails && (
          <div
            ref={detailsRef}
            className="w-full max-w-5xl mx-auto px-4 sm:px-6 pt-8 pb-16 space-y-6 border-t border-border/70 mt-8 animate-in fade-in-50 duration-300"
          >
            <div className="flex items-center justify-between pb-2 border-b border-border/60">
              <div>
                <h2 className="text-base sm:text-lg font-semibold text-foreground">
                  {isEn ? 'In-depth Multi-Agent Analysis' : 'Détails approfondis de l’analyse multi-agents'}
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {isEn
                    ? 'Factual data, mathematical scenarios, and deterministic evidence registry.'
                    : 'Données factuelles, scénarios mathématiques et preuves vérifiables.'}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleToggleDetails}
                className="gap-1.5 text-xs cursor-pointer h-8"
              >
                <ChevronUp className="w-3.5 h-3.5" />
                <span>{isEn ? 'Collapse' : 'Replier'}</span>
              </Button>
            </div>

            {/* Conflicts Alert if any detected */}
            {runState.profile?.conflicts && runState.profile.conflicts.length > 0 && (
              <ConflictsAlert conflicts={runState.profile.conflicts} />
            )}

            {/* Verified Scenario Comparison (Directly Visible inside technical details) */}
            {runState.scenarios && runState.scenarios.length > 0 && (
              <div className="space-y-2">
                <ScenarioCards
                  scenarios={runState.scenarios}
                  evidence={runState.evidence}
                  mostConsistentName={runState.explanation?.scenario_le_plus_coherent}
                />
              </div>
            )}

            {/* 4-Question BNCD Explanation with Clickable Evidence Badges (PRD 5.4) */}
            {runState.explanation && (
              <ExplanationSection
                explanation={runState.explanation}
                verification={runState.verification}
                evidence={runState.evidence}
                onSelectEvidence={onSelectEvidence}
              />
            )}

            {/* Exclusions and Ethical Constraints if any (PRD 5.6) */}
            {runState.exclusions && (
              <ExclusionsCard
                exclusions={runState.exclusions}
                evidence={runState.evidence}
                onSelectEvidence={onSelectEvidence}
              />
            )}

            {/* Interactive What-If Sensitivity Simulation (PRD 5.5) */}
            <div className="space-y-4">
              <WhatIfDiffView diff={whatIfDiff} onClose={onCloseWhatIfDiff} />
              <WhatIfControls
                currentProfile={runState.profile}
                asOfDate={runState.as_of_date}
                eligibleTickers={runState.eligible_universe}
                onRunWhatIf={onRunWhatIf}
                isRunning={isWhatIfRunning}
              />
            </div>

            {/* Advisor Review & Suitability Sign-off (PRD B-14, #121, #146) */}
            {effectiveRunId && onReviewed && (
              <AdvisorReviewPanel
                runId={effectiveRunId}
                graphState={runState}
                currentUser={currentUser || null}
                onReviewed={onReviewed}
              />
            )}

            {/* Complete Verifiable Evidence Registry (PRD 5.2) */}
            {runState.evidence && (
              <EvidenceTable
                evidence={runState.evidence}
                onSelectEvidence={onSelectEvidence}
              />
            )}

            {/* 9-Agent Execution Trace with Cost and Latency (PRD 5.1, #138) */}
            {runState.trace && (
              <NodeTrace
                trace={runState.trace}
                isRunning={isWhatIfRunning}
                cost={runState.cost}
              />
            )}
          </div>
        )}
      </div>

      {/* Bottom Uniform Disclaimer Footer */}
      <footer className="w-full max-w-4xl mx-auto py-6 text-center text-[11px] text-muted-foreground border-t border-border/40 select-none">
        {isEn
          ? 'Educational simulation · No regulated advice · Past performance does not guarantee future results'
          : 'Simulation éducative · Aucun conseil réglementé · Les performances passées ne garantissent pas les résultats futurs'}
      </footer>
    </div>
  );
};
