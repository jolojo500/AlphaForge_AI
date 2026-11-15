import React from 'react';
import { Button } from '@/components/ui/button';
import { AppHeader } from './AppHeader';

interface LoadingScreenProps {
  onCancel: () => void;
  statusText?: string;
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({
  onCancel,
}) => {
  return (
    <div className="min-h-screen bg-background flex flex-col justify-between px-4 py-5 sm:py-8 font-sans transition-colors">
      {/* Top bar with centered Logo & ThemeToggle */}
      <AppHeader />

      {/* Main Centered Content */}
      <div className="w-full max-w-md mx-auto flex flex-col items-center justify-center my-auto space-y-5">
        <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        <h1 className="text-sm sm:text-base font-medium text-foreground text-center tracking-tight">
          Analyse en cours auprès des agents...
        </h1>

        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          className="h-9 px-6 rounded-lg text-xs font-medium cursor-pointer shadow-2xs"
        >
          Annuler
        </Button>
      </div>

      {/* Discrete bottom disclaimer */}
      <footer className="w-full max-w-4xl mx-auto pt-6 text-center text-[11px] text-muted-foreground border-t border-border/40 select-none">
        Simulation éducative · Aucun conseil réglementé · Les performances passées ne garantissent pas les résultats futurs
      </footer>
    </div>
  );
};
