import React from 'react';
import { Logo } from './Logo';
import { ThemeToggle } from './ThemeToggle';
import { Button } from '@/components/ui/button';
import { ArrowRight, Columns2, RotateCcw } from 'lucide-react';
import { DemoPersonas } from './DemoPersonas';

interface WelcomeScreenProps {
  onStart: () => void;
  onDemo: (personaId: string, requestText: string) => void;
  onCompare?: () => void;
  onReplay?: () => void;
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({
  onStart,
  onDemo,
  onCompare,
  onReplay,
}) => {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-between px-4 py-6 transition-colors">
      {/* Top Bar with Theme Toggle and Compare Button */}
      <div className="w-full max-w-5xl flex justify-between items-center">
        {onCompare ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onCompare}
            className="text-xs text-muted-foreground hover:text-foreground gap-1.5"
          >
            <Columns2 className="w-3.5 h-3.5" />
            <span>Comparer deux profils</span>
          </Button>
        ) : (
          <div />
        )}
        <ThemeToggle />
      </div>

      {/* Centered Hero */}
      <div className="text-center space-y-5 flex flex-col items-center my-auto">
        <Logo size="lg" />
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button
            type="button"
            onClick={onStart}
            className="px-6 h-9 rounded-md text-xs sm:text-sm font-medium transition-all shadow-xs active:scale-98 flex items-center gap-2"
          >
            <span>Commencer le questionnaire</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Button>
          {onCompare && (
            <Button
              type="button"
              variant="outline"
              onClick={onCompare}
              className="px-4 h-9 rounded-md text-xs sm:text-sm font-medium transition-all gap-1.5"
            >
              <Columns2 className="w-3.5 h-3.5" />
              <span>Comparer deux profils</span>
            </Button>
          )}
          {onReplay && (
            <Button
              type="button"
              variant="outline"
              onClick={onReplay}
              className="px-4 h-9 rounded-md text-xs sm:text-sm font-medium transition-all flex items-center gap-2 border-border/80 cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5 text-muted-foreground" />
              <span>Rejouer une analyse</span>
            </Button>
          )}
        </div>
        <DemoPersonas onPick={onDemo} />
      </div>

      {/* Discreet footer */}
      <div className="text-[11px] text-muted-foreground/60 select-none text-center">
        Simulation éducative · Aucun conseil personnalisé · PolyFinances 2026
      </div>
    </div>
  );
};
