import React, { useState } from 'react';
import { Logo } from './Logo';
import { ThemeToggle } from './ThemeToggle';
import { LanguageToggle } from './LanguageToggle';
import { UserOnboardingProfile, AuthUser } from '../types';
import { DEMO_PERSONAS } from '../lib/demoProfiles';
import { useLanguage } from '@/context/LanguageContext';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  User,
  Users,
  Check,
  Settings,
  ShieldAlert,
  Clock,
  TrendingUp,
  Wallet,
  Building,
  Info,
  History,
  LogIn,
  LogOut,
  ShieldCheck,
} from 'lucide-react';

export interface AppHeaderProps {
  userProfile?: UserOnboardingProfile | null;
  customProfile?: UserOnboardingProfile | null;
  activePersonaId?: 'custom' | 'robert' | 'amira' | 'mateo';
  onSelectPersona?: (personaId: 'custom' | 'robert' | 'amira' | 'mateo') => void;
  onEditProfile?: () => void;
  onOpenHistory?: () => void;
  currentUser?: AuthUser | null;
  onOpenAuth?: () => void;
  onOpenProfile?: () => void;
  onLogout?: () => void;
  rightActions?: React.ReactNode;
}

export const AppHeader: React.FC<AppHeaderProps> = ({
  userProfile,
  customProfile,
  activePersonaId = 'custom',
  onSelectPersona,
  onEditProfile,
  onOpenHistory,
  currentUser,
  onOpenAuth,
  onOpenProfile,
  onLogout,
  rightActions,
}) => {
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [isSwitcherOpen, setIsSwitcherOpen] = useState(false);
  const { language } = useLanguage();
  const isEn = language === 'en';

  const isDemo = activePersonaId !== 'custom' && activePersonaId in DEMO_PERSONAS;
  const demoMeta = isDemo ? DEMO_PERSONAS[activePersonaId as 'robert' | 'amira' | 'mateo'] : null;

  return (
    <>
      <header className="w-full max-w-5xl mx-auto grid grid-cols-[1fr_auto_1fr] items-center px-4 py-3.5 mb-2 select-none gap-2">
        {/* Left Column: Profile Badge & Switcher & History Button */}
        <div className="flex items-center gap-1.5 sm:gap-2 justify-start min-w-0">
          {userProfile && (
            <button
              type="button"
              onClick={() => setIsDetailsOpen(true)}
              className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-input bg-background text-foreground hover:bg-accent text-xs font-medium transition-colors cursor-pointer group shrink min-w-0"
              title={isEn ? 'View profile details' : 'Afficher les détails de ce profil'}
              aria-label={isEn ? 'View profile details' : 'Afficher les détails de ce profil'}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shrink-0" aria-hidden="true" />
              <span className="truncate max-w-[140px] sm:max-w-[260px] md:max-w-none">
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
              <Info className="w-3 h-3 text-muted-foreground group-hover:text-foreground transition-colors ml-0.5" />
            </button>
          )}

          {onSelectPersona && (
            <Button
              variant="outline"
              size="icon"
              onClick={() => setIsSwitcherOpen(true)}
              className="h-8 w-8 rounded-md cursor-pointer shrink-0"
              title={isEn ? 'Switch investor profile' : "Changer de profil d'analyse (démo ou personnalisé)"}
              aria-label={isEn ? 'Switch investor profile' : "Changer de profil d'analyse"}
            >
              <Users className="w-3.5 h-3.5" />
            </Button>
          )}

          {userProfile && onOpenHistory && (
            <Button
              variant="outline"
              size="icon"
              onClick={onOpenHistory}
              className="h-8 w-8 rounded-md cursor-pointer shrink-0"
              title={isEn ? 'Simulation history' : 'Historique des simulations'}
              aria-label={isEn ? 'Simulation history' : 'Historique des simulations'}
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
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={onOpenProfile}
                className="h-8 gap-1.5 text-xs font-medium cursor-pointer"
                aria-label={isEn ? `Account of ${currentUser.username}` : `Compte de ${currentUser.username}`}
              >
                {currentUser.is_advisor ? (
                  <ShieldCheck className="w-3.5 h-3.5 text-amber-500" />
                ) : (
                  <User className="w-3.5 h-3.5 text-primary" />
                )}
                <span className="hidden md:inline max-w-[90px] truncate">{currentUser.username}</span>
                {currentUser.is_advisor && (
                  <Badge variant="outline" className="border-amber-500/40 text-amber-600 dark:text-amber-400 text-[10px] px-1 py-0 h-4">
                    {isEn ? 'Advisor' : 'Conseiller'}
                  </Badge>
                )}
              </Button>
              {onLogout && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onLogout}
                  title={isEn ? 'Log out' : 'Déconnexion'}
                  aria-label={isEn ? 'Log out' : 'Se déconnecter'}
                  className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  <LogOut className="w-3.5 h-3.5" />
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
                aria-label={isEn ? 'Log in' : 'Se connecter'}
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

      {/* Modal 1: Détails du profil d'investisseur */}
      {userProfile && (
        <Dialog open={isDetailsOpen} onOpenChange={setIsDetailsOpen}>
          <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-base font-semibold">
                <User className="w-4 h-4 text-muted-foreground" />
                <span>
                  {demoMeta
                    ? `${isEn ? 'Demo Profile' : 'Profil de test'} : ${demoMeta.name}`
                    : isEn
                    ? 'Investor Profile Details'
                    : "Détails de votre profil d'investisseur"}
                </span>
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                {isEn
                  ? 'Parameters and hypotheses used to simulate financial decisions.'
                  : 'Paramètres et hypothèses pris en compte pour simuler les décisions financières.'}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-3 pt-2 text-xs">
              <div className="grid grid-cols-2 gap-2 bg-muted/40 p-3 rounded-lg border border-border/60">
                <div>
                  <span className="text-muted-foreground block text-[11px]">
                    {isEn ? 'Simulated Capital' : 'Capital simulé'}
                  </span>
                  <span className="font-semibold text-foreground text-sm">
                    {userProfile.simulatedCapitalFormatted}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-[11px]">
                    {isEn ? 'Risk Tolerance' : 'Tolérance au risque'}
                  </span>
                  <span className="font-semibold text-foreground text-sm capitalize">
                    {userProfile.riskTolerance}
                  </span>
                </div>
              </div>

              <div className="space-y-2 border-t border-border/60 pt-3">
                <div className="flex items-start gap-2">
                  <Clock className="w-3.5 h-3.5 text-muted-foreground mt-0.5 shrink-0" />
                  <div>
                    <span className="text-muted-foreground block text-[11px]">
                      {isEn ? 'Withdrawal Horizon' : 'Horizon de retrait'}
                    </span>
                    <span className="font-medium text-foreground">{userProfile.firstWithdrawalHorizon}</span>
                  </div>
                </div>

                <div className="flex items-start gap-2">
                  <TrendingUp className="w-3.5 h-3.5 text-muted-foreground mt-0.5 shrink-0" />
                  <div>
                    <span className="text-muted-foreground block text-[11px]">
                      {isEn ? 'Investment Objective' : "Objectif d'investissement"}
                    </span>
                    <span className="font-medium text-foreground">{userProfile.primaryObjective}</span>
                  </div>
                </div>

                <div className="flex items-start gap-2">
                  <ShieldAlert className="w-3.5 h-3.5 text-muted-foreground mt-0.5 shrink-0" />
                  <div>
                    <span className="text-muted-foreground block text-[11px]">
                      {isEn ? '12-Month Loss Tolerance' : 'Perte tolérée sur 12 mois'}
                    </span>
                    <span className="font-medium text-foreground">
                      {userProfile.maxLossTolerance ? `${userProfile.maxLossTolerance} %` : 'Non renseigné'}
                    </span>
                  </div>
                </div>

                <div className="flex items-start gap-2">
                  <Building className="w-3.5 h-3.5 text-muted-foreground mt-0.5 shrink-0" />
                  <div>
                    <span className="text-muted-foreground block text-[11px]">
                      {isEn ? 'Account Type' : 'Type de compte'}
                    </span>
                    <span className="font-medium text-foreground">{userProfile.accountType || 'Non spécifié'}</span>
                  </div>
                </div>

                <div className="flex items-start gap-2">
                  <Wallet className="w-3.5 h-3.5 text-muted-foreground mt-0.5 shrink-0" />
                  <div>
                    <span className="text-muted-foreground block text-[11px]">
                      {isEn ? 'Crypto Preference' : 'Préférence crypto'}
                    </span>
                    <span className="font-medium text-foreground">{userProfile.cryptoPreference}</span>
                  </div>
                </div>

                {userProfile.excludedCategories && userProfile.excludedCategories.length > 0 && (
                  <div className="flex items-start gap-2">
                    <ShieldAlert className="w-3.5 h-3.5 text-amber-500 mt-0.5 shrink-0" />
                    <div>
                      <span className="text-muted-foreground block text-[11px]">
                        {isEn ? 'Specific Exclusions' : 'Exclusions spécifiques'}
                      </span>
                      <span className="font-medium text-foreground">
                        {userProfile.excludedCategories.join(', ')}
                      </span>
                    </div>
                  </div>
                )}

                {userProfile.additionalNotes && (
                  <div className="bg-muted/30 p-2.5 rounded border border-border/50 text-[11px] text-muted-foreground italic">
                    « {userProfile.additionalNotes} »
                  </div>
                )}
              </div>

              {onEditProfile && !isDemo && (
                <div className="pt-2 border-t border-border/60">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setIsDetailsOpen(false);
                      onEditProfile();
                    }}
                    className="w-full gap-1.5 text-xs h-8 cursor-pointer"
                  >
                    <Settings className="w-3.5 h-3.5" />
                    <span>{isEn ? 'Edit questionnaire responses' : 'Modifier les réponses du questionnaire'}</span>
                  </Button>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Modal 2: Sélectionner un profil d'analyse */}
      {onSelectPersona && (
        <Dialog open={isSwitcherOpen} onOpenChange={setIsSwitcherOpen}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-base font-semibold">
                <Users className="w-4 h-4 text-muted-foreground" />
                <span>{isEn ? 'Select an Investor Profile' : "Sélectionner un profil d'analyse"}</span>
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                {isEn
                  ? 'Switch between your custom profile and official Datathon test cases.'
                  : 'Basculez entre votre profil personnalisé et les cas de test officiels du Datathon.'}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-2 pt-2 text-xs">
              {/* Option 1: Profil Personnalisé */}
              {customProfile && (
                <button
                  type="button"
                  onClick={() => {
                    onSelectPersona('custom');
                    setIsSwitcherOpen(false);
                  }}
                  className={`w-full text-left p-3 rounded-lg border transition-all flex items-center justify-between cursor-pointer ${
                    activePersonaId === 'custom'
                      ? 'border-primary bg-primary/5 text-foreground ring-1 ring-primary'
                      : 'border-border/80 bg-card hover:bg-accent text-foreground'
                  }`}
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-1.5 font-semibold text-xs">
                      <span>{isEn ? 'My Custom Profile' : 'Mon profil personnalisé'}</span>
                      {activePersonaId === 'custom' && (
                        <Badge variant="secondary" className="text-[10px] py-0 px-1.5 h-4">
                          {isEn ? 'Active' : 'Actif'}
                        </Badge>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      {customProfile.simulatedCapitalFormatted} · {customProfile.riskTolerance} ·{' '}
                      {customProfile.firstWithdrawalHorizon}
                    </p>
                  </div>
                  {activePersonaId === 'custom' && <Check className="w-4 h-4 text-primary shrink-0" />}
                </button>
              )}

              {/* Démos du Datathon */}
              {(['robert', 'amira', 'mateo'] as const).map((personaId) => {
                const meta = DEMO_PERSONAS[personaId];
                const isActive = activePersonaId === personaId;
                return (
                  <button
                    key={personaId}
                    type="button"
                    onClick={() => {
                      onSelectPersona(personaId);
                      setIsSwitcherOpen(false);
                    }}
                    className={`w-full text-left p-3 rounded-lg border transition-all flex items-center justify-between cursor-pointer ${
                      isActive
                        ? 'border-primary bg-primary/5 text-foreground ring-1 ring-primary'
                        : 'border-border/80 bg-card hover:bg-accent text-foreground'
                    }`}
                  >
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-1.5 font-semibold text-xs">
                        <span>{meta.name}</span>
                        <Badge variant="outline" className="text-[10px] py-0 px-1.5 h-4 font-normal">
                          {meta.badge}
                        </Badge>
                        {isActive && (
                          <Badge variant="secondary" className="text-[10px] py-0 px-1.5 h-4">
                            {isEn ? 'Active' : 'Actif'}
                          </Badge>
                        )}
                      </div>
                      <p className="text-[11px] text-muted-foreground leading-snug">
                        {meta.summary}
                      </p>
                    </div>
                    {isActive && <Check className="w-4 h-4 text-primary shrink-0" />}
                  </button>
                );
              })}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
};
