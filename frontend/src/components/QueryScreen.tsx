import React, { useState, useEffect } from 'react';
import { UserOnboardingProfile, BackendRunPayload, AuthUser } from '../types';
import { prepareBackendPayload } from '../api';
import { PayloadModal } from './PayloadModal';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/context/LanguageContext';
import { DEMO_PERSONAS } from '../lib/demoProfiles';
import { AppHeader } from './AppHeader';
import { ArrowUpRight, RotateCcw } from 'lucide-react';

interface QueryScreenProps {
  profile: UserOnboardingProfile;
  customProfile: UserOnboardingProfile | null;
  activePersonaId: 'custom' | 'robert' | 'amira' | 'mateo';
  onSelectPersona: (personaId: 'custom' | 'robert' | 'amira' | 'mateo') => void;
  onEditProfile: () => void;
  onResetProfile: () => void;
  onRunQuery: (payload: BackendRunPayload) => void;
  onOpenHistory?: () => void;
  currentUser?: AuthUser | null;
  onOpenAuth?: () => void;
  onOpenProfile?: () => void;
  onLogout?: () => void;
  initialQuery?: string;
}

export const QueryScreen: React.FC<QueryScreenProps> = ({
  profile,
  customProfile,
  activePersonaId,
  onSelectPersona,
  onEditProfile,
  onResetProfile,
  onRunQuery,
  onOpenHistory,
  currentUser,
  onOpenAuth,
  onOpenProfile,
  onLogout,
  initialQuery = '',
}) => {
  const [query, setQuery] = useState<string>(initialQuery);
  const [preparedPayload, setPreparedPayload] = useState<BackendRunPayload | null>(null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const { language } = useLanguage();
  const isEn = language === 'en';

  // Synchronize initialQuery when persona changes
  useEffect(() => {
    if (initialQuery) {
      setQuery(initialQuery);
    }
  }, [initialQuery]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    const personaToken = activePersonaId === 'custom' ? 'custom_user' : activePersonaId;
    const payload = prepareBackendPayload(profile, query.trim(), language);
    payload.persona = personaToken;
    onRunQuery(payload);
  };

  const handleInspect = () => {
    if (!query.trim()) return;
    const personaToken = activePersonaId === 'custom' ? 'custom_user' : activePersonaId;
    const payload = prepareBackendPayload(profile, query.trim(), language);
    payload.persona = personaToken;
    setPreparedPayload(payload);
    setIsModalOpen(true);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col justify-between px-4 py-5 sm:py-8 font-sans transition-colors">
      {/* Clean, Non-overlapping Header */}
      <AppHeader
        userProfile={profile}
        customProfile={customProfile}
        activePersonaId={activePersonaId}
        onSelectPersona={(val) => {
          onSelectPersona(val);
          const demo = val !== 'custom' ? DEMO_PERSONAS[val] : null;
          if (demo) {
            setQuery(demo.canonicalQuestion);
          }
        }}
        onEditProfile={onEditProfile}
        onOpenHistory={onOpenHistory}
        currentUser={currentUser}
        onOpenAuth={onOpenAuth}
        onOpenProfile={onOpenProfile}
        onLogout={onLogout}
        rightActions={
          onResetProfile && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onResetProfile}
              className="h-8 gap-1 text-xs text-muted-foreground hover:text-destructive cursor-pointer"
              title={isEn ? 'Reset profile and return to home' : "Réinitialiser et retourner à l'accueil"}
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{isEn ? 'Reset' : 'Réinitialiser'}</span>
            </Button>
          )
        }
      />

      {/* Main Centered Content */}
      <div className="w-full max-w-xl mx-auto flex flex-col items-center justify-center my-auto py-8 space-y-5">
        <h1 className="text-sm sm:text-base font-medium text-foreground text-center tracking-tight leading-snug">
          {isEn
            ? 'What decision would you like to explore today?'
            : "Quelle décision souhaitez-vous éclairer aujourd'hui ?"}
        </h1>

        <form onSubmit={handleSubmit} className="w-full space-y-4 flex flex-col items-center">
          <div className="w-full">
            <Textarea
              required
              rows={4}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={
                isEn
                  ? "Ex: I'm interested in NVIDIA (NVDA), but I'm planning a withdrawal in 4 years. Is this consistent with my profile?"
                  : "Ex: Je m'intéresse à NVIDIA (NVDA), mais je prévois un retrait d'ici 4 ans. Est-ce cohérent avec mon profil ?"
              }
              className="w-full min-h-[110px] text-xs sm:text-sm leading-relaxed p-3.5 bg-card border-border rounded-lg resize-none shadow-xs"
            />
          </div>

          <div className="flex flex-row items-center justify-center gap-3 w-full">
            <Button
              type="submit"
              disabled={!query.trim()}
              className="h-9 px-6 text-xs font-medium cursor-pointer"
            >
              {isEn ? 'Submit' : 'Envoyer'}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={handleInspect}
              disabled={!query.trim()}
              className="h-9 px-4 text-xs font-normal text-muted-foreground hover:text-foreground cursor-pointer"
            >
              <span>{isEn ? 'Inspect payload' : 'Inspecter le payload'}</span>
              <ArrowUpRight className="w-3 h-3 ml-1" />
            </Button>
          </div>
        </form>
      </div>

      {/* Bottom Uniform Disclaimer Footer */}
      <footer className="w-full max-w-4xl mx-auto pt-6 text-center text-[11px] text-muted-foreground border-t border-border/40 select-none">
        {isEn
          ? 'Educational simulation · No regulated advice · Past performance does not guarantee future results'
          : 'Simulation éducative · Aucun conseil réglementé · Les performances passées ne garantissent pas les résultats futurs'}
      </footer>

      {preparedPayload && (
        <PayloadModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          payload={preparedPayload}
          profile={profile}
          onRunAnalysis={() => {
            setIsModalOpen(false);
            onRunQuery(preparedPayload);
          }}
        />
      )}
    </div>
  );
};
