import React from 'react';
import { Logo } from './Logo';
import { ThemeToggle } from './ThemeToggle';
import { LanguageToggle } from './LanguageToggle';
import { UserOnboardingProfile, AuthUser } from '../types';
import { DEMO_PERSONAS } from '../lib/demoProfiles';
import { useLanguage } from '@/context/LanguageContext';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  User,
  History,
  LogIn,
  LogOut,
  ShieldCheck,
} from 'lucide-react';

export interface AppHeaderProps {
  userProfile?: UserOnboardingProfile | null;
  customProfile?: UserOnboardingProfile | null;
  activePersonaId?: 'custom' | 'robert' | 'amira' | 'mateo';
  onEditProfile?: () => void;
  onOpenHistory?: () => void;
  currentUser?: AuthUser | null;
  onOpenAuth?: () => void;
  onLogout?: () => void;
  rightActions?: React.ReactNode;
}

export const AppHeader: React.FC<AppHeaderProps> = ({
  userProfile,
  activePersonaId = 'custom',
  onOpenHistory,
  currentUser,
  onOpenAuth,
  onLogout,
  rightActions,
}) => {
  const { language } = useLanguage();
  const isEn = language === 'en';

  const isDemo = activePersonaId !== 'custom' && activePersonaId in DEMO_PERSONAS;
  const demoMeta = isDemo ? DEMO_PERSONAS[activePersonaId as 'robert' | 'amira' | 'mateo'] : null;

  return (
    <header className="w-full max-w-5xl mx-auto grid grid-cols-[1fr_auto_1fr] items-center px-4 py-3.5 mb-2 select-none gap-2">
      {/* Left Column: Non-clickable Profile indicator & History Button */}
      <div className="flex items-center gap-1.5 sm:gap-2 justify-start min-w-0">
        {userProfile && (
          <div
            className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-input bg-muted/30 text-foreground text-xs font-medium select-none shrink-0"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            <span className="truncate max-w-[100px] sm:max-w-[150px]">
              {demoMeta ? (
                <>
                  <span className="font-semibold">{demoMeta.name}</span>
                  <span className="text-muted-foreground ml-1 hidden sm:inline">· {demoMeta.badge}</span>
                </>
              ) : (
                <>
                  <span className="font-semibold">{isEn ? 'My profile' : 'Mon profil'}</span>
                  <span className="text-muted-foreground ml-1 hidden sm:inline">
                    · {userProfile.simulatedCapitalFormatted}
                  </span>
                </>
              )}
            </span>
          </div>
        )}

        {userProfile && onOpenHistory && (
          <Button
            variant="outline"
            size="icon"
            onClick={onOpenHistory}
            className="h-8 w-8 rounded-md cursor-pointer shrink-0"
            title={isEn ? 'Simulation history' : 'Historique des simulations'}
            aria-label="Historique des simulations"
          >
            <History className="w-3.5 h-3.5" />
          </Button>
        )}
      </div>

      {/* Center Column: Perfectly Centered Logo Always */}
      <div className="flex items-center justify-center shrink-0 px-2">
        <Logo size="md" />
      </div>

      {/* Right Column: Contextual Actions & User Auth & Toggles */}
      <div className="flex items-center gap-1.5 sm:gap-2 justify-end min-w-0">
        {rightActions}

        {currentUser ? (
          <div className="flex items-center gap-1.5">
            <div
              className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-input bg-muted/40 text-foreground text-xs font-medium select-none"
            >
              {currentUser.is_advisor ? (
                <ShieldCheck className="w-3.5 h-3.5 text-amber-500 shrink-0" />
              ) : (
                <User className="w-3.5 h-3.5 text-primary shrink-0" />
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
                variant="ghost"
                size="sm"
                onClick={onLogout}
                title={isEn ? 'Log out and return to home' : "Déconnexion et retour à l'accueil"}
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
              variant="outline"
              size="sm"
              onClick={onOpenAuth}
              className="h-8 gap-1.5 text-xs font-medium cursor-pointer"
            >
              <LogIn className="w-3.5 h-3.5 text-primary" />
              <span className="hidden sm:inline">{isEn ? 'Log in' : 'Connexion'}</span>
            </Button>
          )
        )}

        <LanguageToggle />
        <ThemeToggle />
      </div>
    </header>
  );
};
