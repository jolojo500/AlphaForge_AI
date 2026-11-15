import React from 'react';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/context/LanguageContext';
import { TraceEntry } from '../types';
import { AppHeader } from './AppHeader';
import { NodeTrace } from './NodeTrace';

interface LoadingScreenProps {
  onCancel: () => void;
  trace?: TraceEntry[];
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ onCancel, trace = [] }) => {
  const { language } = useLanguage();
  const isEn = language === 'en';
  return (
    <div className="min-h-screen bg-background flex flex-col justify-between px-4 py-5 sm:py-8 font-sans transition-colors">
      <AppHeader />

      <div className="w-full max-w-3xl mx-auto flex flex-col items-center justify-center my-auto space-y-5 py-8">
        <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        <h1 className="text-sm sm:text-base font-medium text-foreground text-center tracking-tight">
          {isEn ? 'The agents are working on your request...' : 'Analyse en cours auprès des agents...'}
        </h1>

        {/* Live agent trace: each node appears as it finishes */}
        <div className="w-full text-left">
          <NodeTrace trace={trace} isRunning />
        </div>

        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          className="h-9 px-6 rounded-lg text-xs font-medium cursor-pointer shadow-2xs"
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
