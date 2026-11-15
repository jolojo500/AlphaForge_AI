import React from 'react';
import { Logo } from './Logo';
import { ThemeToggle } from './ThemeToggle';
import { LanguageToggle } from './LanguageToggle';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ArrowRight, Columns2, RotateCcw, LogIn, LogOut, User as UserIcon, ShieldCheck } from 'lucide-react';
import { DemoPersonas } from './DemoPersonas';
import { AuthUser } from '../types';
import { useLanguage } from '@/context/LanguageContext';

interface WelcomeScreenProps {
  onStart: () => void;
  onDemo: (personaId: string, requestText: string) => void;
  onCompare?: () => void;
  onReplay?: () => void;
  currentUser?: AuthUser | null;
  onOpenAuth?: () => void;
  onOpenProfile?: () => void;
  onLogout?: () => void;
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({
  onStart,
  onDemo,
  onCompare,
  onReplay,
  currentUser,
  onOpenAuth,
  onOpenProfile,
  onLogout,
}) => {
  const { language } = useLanguage();
  const isEn = language === 'en';

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-between px-4 py-6 transition-colors">
      {/* Top Bar with Theme Toggle, Language Toggle, Auth, and Compare Button */}
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
            <span>{isEn ? 'Compare two profiles' : 'Comparer deux profils'}</span>
          </Button>
        ) : (
          <div />
        )}
        <div className="flex items-center gap-2">
          {currentUser ? (
            <div className="flex items-center gap-1.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onOpenProfile}
                className="gap-1.5 text-xs font-medium cursor-pointer h-8"
              >
                {currentUser.is_advisor ? (
                  <ShieldCheck className="w-3.5 h-3.5 text-amber-500" />
                ) : (
                  <UserIcon className="w-3.5 h-3.5 text-primary" />
                )}
                <span>{currentUser.username}</span>
                {currentUser.is_advisor && (
                  <Badge variant="outline" className="border-amber-500/40 text-amber-600 dark:text-amber-400 text-[10px] px-1 py-0 h-4">
                    {isEn ? 'Advisor' : 'Conseiller'}
                  </Badge>
                )}
              </Button>
              {onLogout && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={onLogout}
                  title={isEn ? 'Log out' : 'Déconnexion'}
                  className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  <LogOut className="w-3.5 h-3.5" />
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
            <span>{isEn ? 'Start investor questionnaire' : 'Commencer le questionnaire'}</span>
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
              <span>{isEn ? 'Compare two profiles' : 'Comparer deux profils'}</span>
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
              <span>{isEn ? 'Replay an analysis' : 'Rejouer une analyse'}</span>
            </Button>
          )}
        </div>
        <DemoPersonas onPick={onDemo} />
      </div>

      {/* Discreet footer */}
      <div className="text-[11px] text-muted-foreground/60 select-none text-center">
        {isEn
          ? 'Educational simulation · No personalized advice · PolyFinances 2026'
          : 'Simulation éducative · Aucun conseil personnalisé · PolyFinances 2026'}
      </div>
    </div>
  );
};
