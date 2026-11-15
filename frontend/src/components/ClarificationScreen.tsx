import React, { useState } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { AppHeader } from './AppHeader';

interface ClarificationScreenProps {
  question: string;
  onAnswer: (text: string) => void;
  isSubmitting: boolean;
}

export const ClarificationScreen: React.FC<ClarificationScreenProps> = ({
  question,
  onAnswer,
  isSubmitting,
}) => {
  const [answer, setAnswer] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!answer.trim() || isSubmitting) return;
    onAnswer(answer.trim());
  };

  return (
    <div className="min-h-screen bg-background flex flex-col justify-between px-4 py-5 sm:py-8 font-sans transition-colors">
      {/* Top bar with centered Logo & ThemeToggle */}
      <AppHeader />

      {/* Main Centered Content */}
      <div className="w-full max-w-xl mx-auto flex flex-col items-center justify-center my-auto space-y-5">
        <div className="text-center space-y-1.5 mb-1">
          <span className="text-xs sm:text-sm text-muted-foreground font-normal block">
            J’ai besoin d’une précision...
          </span>
          <h1 className="text-sm sm:text-base font-medium text-foreground tracking-tight leading-snug">
            {question}
          </h1>
        </div>

        <form onSubmit={handleSubmit} className="w-full space-y-4 flex flex-col items-center">
          <div className="w-full">
            <Textarea
              required
              rows={4}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              disabled={isSubmitting}
              placeholder="Précisez votre demande ici..."
              className="w-full min-h-[110px] text-xs sm:text-sm leading-relaxed p-4 bg-card border-border rounded-xl resize-none shadow-2xs focus-visible:ring-1 focus-visible:ring-foreground"
            />
          </div>

          <Button
            type="submit"
            disabled={!answer.trim() || isSubmitting}
            className="h-10 px-6 rounded-lg text-xs sm:text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-xs active:scale-98 flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            <span>{isSubmitting ? 'Transmission...' : 'Envoyer ma précision'}</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Button>
        </form>
      </div>

      {/* Discrete bottom disclaimer */}
      <footer className="w-full max-w-4xl mx-auto pt-6 text-center text-[11px] text-muted-foreground border-t border-border/40 select-none">
        Simulation éducative · Aucun conseil réglementé · Les performances passées ne garantissent pas les résultats futurs
      </footer>
    </div>
  );
};
