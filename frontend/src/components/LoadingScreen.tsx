import React from 'react';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/context/LanguageContext';
import { AppHeader } from './AppHeader';

interface LoadingScreenProps {
  onCancel: () => void;
  trace?: unknown;
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ onCancel }) => {
  const { language } = useLanguage();
  const isEn = language === 'en';
  return (
    <div className="min-h-screen bg-background flex flex-col justify-between px-4 py-5 sm:py-8 font-sans transition-colors">
      <AppHeader />

      <div className="w-full max-w-md mx-auto flex flex-col items-center justify-center my-auto space-y-6 py-12 text-center">
        <div className="w-9 h-9 rounded-full border-2 border-primary border-t-transparent animate-spin" />

        <div className="space-y-1.5">
          <h1 className="text-sm sm:text-base font-medium text-foreground tracking-tight">
            {isEn ? 'Analysis in progress...' : 'Analyse en cours...'}
          </h1>
          <p className="text-xs text-muted-foreground">
            {isEn
              ? 'Evaluating risk parameters and running portfolio simulations.'
              : 'Évaluation des contraintes et simulation des scénarios de risque.'}
          </p>
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
