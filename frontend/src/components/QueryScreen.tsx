import React, { useState } from 'react';
import { Logo } from './Logo';
import { ThemeToggle } from './ThemeToggle';
import { UserOnboardingProfile, BackendRunPayload } from '../types';
import { ArrowUpRight, Settings, RotateCcw } from 'lucide-react';
import { prepareBackendPayload } from '../api';
import { DemoPersonas } from './DemoPersonas';
import { PayloadModal } from './PayloadModal';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface QueryScreenProps {
  profile: UserOnboardingProfile;
  onEditProfile: () => void;
  onResetProfile: () => void;
  onRunQuery: (payload: BackendRunPayload) => void;
}

export const QueryScreen: React.FC<QueryScreenProps> = ({
  profile,
  onEditProfile,
  onResetProfile,
  onRunQuery,
}) => {
  const [query, setQuery] = useState<string>('');
  const [preparedPayload, setPreparedPayload] = useState<BackendRunPayload | null>(null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    const payload = prepareBackendPayload(profile, query.trim());
    onRunQuery(payload);
  };

  const handleInspect = () => {
    if (!query.trim()) return;
    const payload = prepareBackendPayload(profile, query.trim());
    setPreparedPayload(payload);
    setIsModalOpen(true);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col justify-between px-4 py-5 sm:py-8 font-sans transition-colors">
      {/* Top bar with active profile and ThemeToggle */}
      <div className="w-full max-w-4xl mx-auto flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="gap-1.5 py-1 px-2.5 font-normal border-border/80 bg-card">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="font-medium text-foreground">
              {profile.simulatedCapitalFormatted} · {profile.riskTolerance}
            </span>
          </Badge>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={onEditProfile}
            className="h-8 gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <Settings className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Modifier le profil</span>
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={onResetProfile}
            className="h-8 gap-1 text-xs text-muted-foreground hover:text-destructive"
            title="Effacer le profil de localStorage et recommencer l'onboarding"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Réinitialiser</span>
          </Button>

          <div className="h-4 w-px bg-border/60 mx-1" />

          <ThemeToggle />
        </div>
      </div>

      {/* Main Centered Content */}
      <div className="w-full max-w-xl mx-auto flex flex-col items-center justify-center my-auto space-y-5">
        <Logo size="lg" />

        <h1 className="text-sm sm:text-base font-medium text-foreground text-center tracking-tight">
          Quelle décision souhaitez-vous éclairer aujourd'hui ?
        </h1>

        <form onSubmit={handleSubmit} className="w-full space-y-4 flex flex-col items-center">
          <div className="w-full">
            <Textarea
              required
              rows={4}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Je m'intéresse à NVIDIA (NVDA), mais je prends ma retraite dans 4 ans. Est-ce cohérent avec mon objectif de préservation du capital ?"
              className="w-full min-h-[110px] text-xs sm:text-sm leading-relaxed p-3.5 bg-card border-border rounded-lg resize-none shadow-xs"
            />
          </div>

          <Button
            type="submit"
            disabled={!query.trim()}
            className="w-full h-10 rounded-md text-xs sm:text-sm font-medium transition-all shadow-xs active:scale-98 flex items-center justify-center gap-1.5 cursor-pointer"
          >
            <span>Envoyer</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Button>

          <div className="w-full flex items-center justify-between pt-1">
            <button
              type="button"
              disabled={!query.trim()}
              onClick={handleInspect}
              className="text-[11px] text-muted-foreground hover:text-foreground transition-colors cursor-pointer disabled:opacity-40"
            >
              Inspecter le payload JSON
            </button>
            <p className="text-[11px] text-muted-foreground/70 select-none">
              Simulation éducative · Aucun conseil
            </p>
          </div>
        </form>
        <div className="pt-6">
          <DemoPersonas onPick={(persona, request_text) => onRunQuery({ persona, request_text })} />
        </div>
      </div>

      {/* Empty bottom spacer for perfect centering */}
      <div className="h-6" />

      {/* Modal showing prepared backend payload */}
      {preparedPayload && (
        <PayloadModal
          payload={preparedPayload}
          profile={profile}
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          onRunAnalysis={() => {
            setIsModalOpen(false);
            onRunQuery(preparedPayload);
          }}
        />
      )}
    </div>
  );
};
