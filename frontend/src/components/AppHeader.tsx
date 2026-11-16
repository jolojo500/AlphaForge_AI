import React, { useState, useRef, useEffect } from 'react';
import { Logo } from './Logo';
import { ThemeToggle } from './ThemeToggle';
import { LanguageToggle } from './LanguageToggle';
import { UserOnboardingProfile, AuthUser } from '../types';
import { useLanguage } from '@/context/LanguageContext';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  User,
  UserCog,
  UserRound,
  ChevronDown,
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
  /** Opens the read-only ProfileModal (versioned profile, history, dossier download, #170/#192). */
  onOpenProfile?: () => void;
  onOpenHistory?: () => void;
  currentUser?: AuthUser | null;
  onOpenAuth?: () => void;
  onLogout?: () => void;
  rightActions?: React.ReactNode;
}

export const AppHeader: React.FC<AppHeaderProps> = ({
  onEditProfile,
  onOpenProfile,
  onOpenHistory,
  currentUser,
  onOpenAuth,
  onLogout,
  rightActions,
}) => {
  const { language } = useLanguage();
  const isEn = language === 'en';

  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false);
      }
    };
    if (isMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isMenuOpen]);

  return (
    <header className="w-full max-w-5xl mx-auto grid grid-cols-[1fr_auto_1fr] items-center px-4 py-3.5 mb-2 select-none gap-2">
      {/* Left Column: Simulation History Button only (Left profile badge removed) */}
      <div className="flex items-center gap-1.5 sm:gap-2 justify-start min-w-0">
        {onOpenHistory && (
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

      {/* Right Column: Contextual Actions & User Dropdown Menu & Toggles */}
      <div className="flex items-center gap-1.5 sm:gap-2 justify-end min-w-0">
        {rightActions}

        {currentUser ? (
          <div ref={menuRef} className="relative">
            <button
              type="button"
              onClick={() => setIsMenuOpen((prev) => !prev)}
              aria-expanded={isMenuOpen}
              aria-haspopup="true"
              className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-input bg-muted/40 hover:bg-muted text-foreground text-xs font-medium cursor-pointer transition-colors shadow-xs"
              title={isEn ? 'User menu' : 'Menu utilisateur'}
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
              <ChevronDown className={`w-3 h-3 text-muted-foreground transition-transform duration-150 ${isMenuOpen ? 'rotate-180' : ''}`} />
            </button>

            {isMenuOpen && (
              <div
                role="menu"
                className="absolute right-0 top-full mt-1.5 w-52 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-lg z-50 animate-in fade-in-0 zoom-in-95 duration-100"
              >
                <div className="px-2.5 py-1.5 text-xs border-b border-border/60 mb-1">
                  <p className="font-semibold text-foreground truncate">{currentUser.username}</p>
                  {currentUser.email && (
                    <p className="text-[11px] text-muted-foreground truncate">{currentUser.email}</p>
                  )}
                </div>

                {onOpenProfile && (
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setIsMenuOpen(false);
                      onOpenProfile();
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs rounded-md text-foreground hover:bg-muted hover:text-foreground text-left cursor-pointer transition-colors"
                  >
                    <UserRound className="w-3.5 h-3.5 text-primary shrink-0" />
                    <span>{isEn ? 'My profile' : 'Mon profil'}</span>
                  </button>
                )}

                {onEditProfile && (
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setIsMenuOpen(false);
                      onEditProfile();
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs rounded-md text-foreground hover:bg-muted hover:text-foreground text-left cursor-pointer transition-colors"
                  >
                    <UserCog className="w-3.5 h-3.5 text-primary shrink-0" />
                    <span>{isEn ? 'Edit profile' : 'Modifier le profil'}</span>
                  </button>
                )}

                {onLogout && (
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setIsMenuOpen(false);
                      onLogout();
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs rounded-md text-destructive hover:bg-destructive/10 text-left cursor-pointer transition-colors mt-0.5"
                  >
                    <LogOut className="w-3.5 h-3.5 shrink-0" />
                    <span>{isEn ? 'Log out' : 'Se déconnecter'}</span>
                  </button>
                )}
              </div>
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
