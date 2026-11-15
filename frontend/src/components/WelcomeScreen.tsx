import React from 'react';
import { Logo } from './Logo';
import { ThemeToggle } from './ThemeToggle';
import { Button } from '@/components/ui/button';
import { ArrowRight } from 'lucide-react';

interface WelcomeScreenProps {
  onStart: () => void;
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({ onStart }) => {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-between px-4 py-6 transition-colors">
      {/* Top Bar with Theme Toggle */}
      <div className="w-full max-w-5xl flex justify-end">
        <ThemeToggle />
      </div>

      {/* Centered Hero */}
      <div className="text-center space-y-5 flex flex-col items-center my-auto">
        <Logo size="lg" />
        <div>
          <Button
            type="button"
            onClick={onStart}
            className="px-6 h-9 rounded-md text-xs sm:text-sm font-medium transition-all shadow-xs active:scale-98 flex items-center gap-2"
          >
            <span>Commencer</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* Discreet footer */}
      <div className="text-[11px] text-muted-foreground/60 select-none text-center">
        Moteur d'aide à la décision financière · PolyFinances 2026
      </div>
    </div>
  );
};
