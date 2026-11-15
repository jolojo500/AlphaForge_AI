import React from 'react';
import { Logo } from './Logo';
import { ThemeToggle } from './ThemeToggle';
import { LanguageToggle } from './LanguageToggle';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  ArrowRight,
  History,
  LogIn,
  LogOut,
  User as UserIcon,
  ShieldCheck,
  UserRound,
} from 'lucide-react';
import { AuthUser } from '../types';
import { useLanguage } from '@/context/LanguageContext';
import { DEMO_PERSONAS, DEMO_ORDER } from '../lib/demoProfiles';

interface WelcomeScreenProps {
  onStart: () => void;
  onSelectDemo: (personaId: 'robert' | 'amira' | 'mateo') => void;
  onOpenHistory?: () => void;
  currentUser?: AuthUser | null;
  onOpenAuth?: () => void;
  onLogout?: () => void;
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({
  onStart,
  onSelectDemo,
  onOpenHistory,
  currentUser,
  onOpenAuth,
  onLogout,
}) => {
  const { language } = useLanguage();
  const isEn = language === 'en';

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-between px-4 py-5 sm:py-8 font-sans transition-colors">
      {/* Top Bar with History, Auth, Language Toggle and Theme Toggle */}
      <header className="w-full max-w-4xl mx-auto flex justify-between items-center select-none">
        <div>
          {onOpenHistory && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onOpenHistory}
              className="text-xs text-muted-foreground hover:text-foreground gap-1.5 h-8 cursor-pointer"
            >
              <History className="w-3.5 h-3.5 text-primary" />
              <span>{isEn ? 'Past simulations' : 'Historique'}</span>
            </Button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {currentUser ? (
            <div className="flex items-center gap-1.5">
              <div
                className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-input bg-muted/40 text-foreground text-xs font-medium select-none"
              >
                {currentUser.is_advisor ? (
                  <ShieldCheck className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                ) : (
                  <UserIcon className="w-3.5 h-3.5 text-primary shrink-0" />
                )}
                <span className="max-w-[120px] truncate">{currentUser.username}</span>
                {currentUser.is_advisor && (
                  <Badge variant="outline" className="border-amber-500/40 text-amber-600 dark:text-amber-400 text-[10px] px-1 py-0 h-4">
                    {isEn ? 'Advisor' : 'Conseiller'}
                  </Badge>
                )}
              </div>
              {onLogout && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={onLogout}
                  title={isEn ? 'Log out' : 'Déconnexion'}
                  className="h-8 gap-1.5 px-2 text-xs text-muted-foreground hover:text-destructive cursor-pointer"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">{isEn ? 'Log out' : 'Déconnexion'}</span>
                </Button>
              )}
            </div>
          ) : (
            onOpenAuth && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onOpenAuth}
                className="gap-1.5 text-xs font-medium cursor-pointer h-8"
              >
                <LogIn className="w-3.5 h-3.5 text-primary" />
                <span>{isEn ? 'Log in' : 'Connexion'}</span>
              </Button>
            )
          )}
          <LanguageToggle />
          <ThemeToggle />
        </div>
      </header>

      {/* Centered Hero - Logo prominently centered above Start Button */}
      <div className="text-center space-y-6 flex flex-col items-center my-auto w-full max-w-xl mx-auto py-8">
        <div className="flex justify-center items-center py-2">
          <Logo size="xl" className="h-8 sm:h-10" />
        </div>

        {/* Primary Action Button */}
        <div className="w-full max-w-sm">
          {currentUser ? (
            <Button
              type="button"
              onClick={onStart}
              className="w-full h-11 text-xs sm:text-sm font-medium cursor-pointer flex items-center justify-center gap-2"
            >
              <span>{isEn ? 'Start investor questionnaire' : 'Commencer le questionnaire'}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          ) : (
            <Button
              type="button"
              onClick={onOpenAuth}
              className="w-full h-11 text-xs sm:text-sm font-medium cursor-pointer flex items-center justify-center gap-2"
            >
              <LogIn className="w-4 h-4 text-primary" />
              <span>{isEn ? 'Log in to start questionnaire' : 'Se connecter pour commencer le questionnaire'}</span>
            </Button>
          )}
        </div>

        {/* 3 Demo Personas (Sober, Minimalist, Pre-fills Query Screen without auto-launch) */}
        <div className="w-full pt-4 space-y-2.5">
          <p className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium select-none">
            {isEn ? 'Or explore with a demo profile' : 'Ou tester avec un profil de démonstration'}
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 w-full">
            {DEMO_ORDER.map((id) => {
              const persona = DEMO_PERSONAS[id];
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => onSelectDemo(id)}
                  className="p-3 bg-card hover:bg-muted/60 border border-border rounded-xl text-left transition-all group flex flex-col justify-between cursor-pointer active:scale-98"
                >
                  <div className="flex items-center justify-between w-full mb-1">
                    <span className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors flex items-center gap-1.5">
                      <UserRound className="w-3.5 h-3.5 text-muted-foreground" />
                      <span>{persona.name}</span>
                    </span>
                    <span className="text-[10px] text-muted-foreground font-mono">
                      {persona.age} ans
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug line-clamp-2">
                    {persona.badge}
                  </p>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Discrete uniform footer disclaimer */}
      <footer className="w-full max-w-4xl mx-auto pt-6 text-center text-[11px] text-muted-foreground border-t border-border/40 select-none">
        {isEn
          ? 'Educational simulation · No personalized advice · Past performance does not guarantee future results'
          : 'Simulation éducative · Aucun conseil réglementé · Les performances passées ne garantissent pas les résultats futurs'}
      </footer>
    </div>
  );
};
