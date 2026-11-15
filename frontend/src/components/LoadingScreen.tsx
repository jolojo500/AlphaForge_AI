import React from 'react';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/context/LanguageContext';
import { TraceEntry } from '../types';
import { AppHeader } from './AppHeader';
import { nodeLabel } from '@/lib/labels';
import { TOTAL_STEPS, remainingLabel, runProgress } from '@/lib/progress';
import { type Lang } from '@/lib/format';

interface LoadingScreenProps {
  onCancel: () => void;
  trace?: TraceEntry[];
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ onCancel, trace = [] }) => {
  const { language } = useLanguage();
  const lang: Lang = language === 'en' ? 'en' : 'fr';
  const isEn = lang === 'en';
  const { step, remainingS, currentNode } = runProgress(trace);
  const allDone = trace.length >= TOTAL_STEPS || currentNode === null;

  const stepLine = allDone
    ? isEn
      ? `Step ${TOTAL_STEPS} / ${TOTAL_STEPS} · preparing the answer`
      : `Étape ${TOTAL_STEPS} / ${TOTAL_STEPS} · préparation de la réponse`
    : isEn
    ? `Step ${step} / ${TOTAL_STEPS} · ${remainingLabel(remainingS, lang)}`
    : `Étape ${step} / ${TOTAL_STEPS} · ${remainingLabel(remainingS, lang)}`;

  return (
    <div className="min-h-screen bg-background flex flex-col justify-between px-4 py-5 sm:py-8 font-sans transition-colors">
      <AppHeader />

      <div className="w-full max-w-md mx-auto flex flex-col items-center justify-center my-auto space-y-6 py-12 text-center">
        <div className="w-9 h-9 rounded-full border-2 border-primary border-t-transparent animate-spin" aria-hidden="true" />

        <div className="space-y-1.5">
          <h1 className="text-sm sm:text-base font-medium text-foreground tracking-tight">
            {isEn ? 'Analysis in progress...' : 'Analyse en cours...'}
          </h1>
          <p className="text-xs text-muted-foreground">
            {isEn
              ? 'Checking your limits and simulating the risk scenarios.'
              : 'Vérification de vos limites et simulation des scénarios de risque.'}
          </p>
          {/* Live progress: step counter with the time estimate, then the step in progress */}
          <div className="pt-1 space-y-0.5" aria-live="polite">
            <p className="text-xs font-medium text-foreground tabular-nums">{stepLine}</p>
            <p className="text-[11px] text-muted-foreground/80 h-4">
              {currentNode ? nodeLabel(currentNode, lang) : ''}
            </p>
          </div>
          <div
            className="w-full h-1 rounded-full bg-muted overflow-hidden mt-2"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={TOTAL_STEPS}
            aria-valuenow={Math.min(TOTAL_STEPS, trace.length)}
            aria-label={isEn ? 'Analysis progress' : "Progression de l'analyse"}
          >
            <div
              className="h-full bg-primary transition-all duration-500"
              style={{ width: `${Math.min(100, (Math.min(TOTAL_STEPS, trace.length) / TOTAL_STEPS) * 100)}%` }}
            />
          </div>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onCancel}
          className="h-8 px-5 text-xs font-normal cursor-pointer"
        >
          {isEn ? 'Cancel' : 'Annuler'}
        </Button>
      </div>

      <footer className="w-full max-w-4xl mx-auto pt-6 text-center text-[11px] text-muted-foreground border-t border-border/40 select-none">
        {isEn
          ? 'Educational simulation · No regulated advice · Past performance does not guarantee future results'
          : 'Simulation éducative · Aucun conseil réglementé · Les performances passées ne garantissent pas les résultats futurs'}
      </footer>
    </div>
  );
};
