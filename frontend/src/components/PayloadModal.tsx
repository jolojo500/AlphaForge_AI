import React, { useState } from 'react';
import { BackendRunPayload, UserOnboardingProfile } from '../types';
import { labelOf } from '../lib/questionnaireCodes';
import { CheckCircle2, Copy, Check, Eye, Code2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface PayloadModalProps {
  payload: BackendRunPayload;
  profile: UserOnboardingProfile;
  isOpen: boolean;
  onClose: () => void;
  onRunAnalysis: () => void;
}

export const PayloadModal: React.FC<PayloadModalProps> = ({
  payload,
  profile,
  isOpen,
  onClose,
  onRunAnalysis,
}) => {
  const [copied, setCopied] = useState(false);
  const [showRawJson, setShowRawJson] = useState(false);

  const jsonString = JSON.stringify(payload, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(jsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
              <CheckCircle2 className="w-4 h-4" />
            </div>
            <div>
              <DialogTitle className="text-sm sm:text-base font-semibold">
                Données prêtes pour le backend
              </DialogTitle>
              <DialogDescription className="text-xs">
                Profil utilisateur et question prêts à être transmis à l'IA
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-3.5 pt-1">
          {/* Status announcement */}
          <div className="p-3 bg-primary/10 border border-primary/20 rounded-lg text-xs text-foreground leading-relaxed">
            <span className="font-semibold text-primary">Connexion backend active :</span> Les données de votre profil (sauvegardées localement) sont transmises au backend FastAPI / LangGraph pour orchestrer les 9 agents et générer des scénarios avec preuves déterministes.
          </div>

          {/* Question asked */}
          <div>
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
              Question de l'investisseur
            </label>
            <div className="p-2.5 bg-muted/40 rounded-lg text-xs sm:text-sm text-foreground border border-border/60">
              « {payload.request_text} »
            </div>
          </div>

          {/* Profile summary */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block">
                Paramètres du profil utilisateur (localStorage)
              </label>
              <Badge variant="outline" className="text-[10px]">
                Profil actif
              </Badge>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
              <div className="p-2.5 bg-muted/40 rounded-lg border border-border/60">
                <span className="text-muted-foreground block text-[11px]">Objectif</span>
                <span className="font-semibold text-foreground mt-0.5 block truncate">
                  {labelOf('primaryObjective', profile.primaryObjective)}
                </span>
              </div>
              <div className="p-2.5 bg-muted/40 rounded-lg border border-border/60">
                <span className="text-muted-foreground block text-[11px]">Horizon de retrait</span>
                <span className="font-semibold text-foreground mt-0.5 block truncate">
                  {profile.firstWithdrawalHorizon}
                </span>
              </div>
              <div className="p-2.5 bg-muted/40 rounded-lg border border-border/60">
                <span className="text-muted-foreground block text-[11px]">Tolérance au risque</span>
                <span className="font-semibold text-foreground mt-0.5 block truncate">
                  {labelOf('riskTolerance', profile.riskTolerance)}
                </span>
              </div>
              <div className="p-2.5 bg-muted/40 rounded-lg border border-border/60">
                <span className="text-muted-foreground block text-[11px]">Capital simulé</span>
                <span className="font-semibold text-foreground mt-0.5 block truncate">
                  {profile.simulatedCapitalFormatted}
                </span>
              </div>
              <div className="p-2.5 bg-muted/40 rounded-lg border border-border/60">
                <span className="text-muted-foreground block text-[11px]">Cryptoactifs</span>
                <span className="font-semibold text-foreground mt-0.5 block truncate">
                  {labelOf('cryptoPreference', profile.cryptoPreference)}
                </span>
              </div>
              <div className="p-2.5 bg-muted/40 rounded-lg border border-border/60">
                <span className="text-muted-foreground block text-[11px]">Expérience</span>
                <span className="font-semibold text-foreground mt-0.5 block truncate">
                  {labelOf('investmentExperience', profile.investmentExperience)}
                </span>
              </div>
            </div>
          </div>

          {/* Raw JSON toggle */}
          <div>
            <button
              type="button"
              onClick={() => setShowRawJson(!showRawJson)}
              className="text-xs font-medium text-muted-foreground hover:text-foreground flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <Code2 className="w-3.5 h-3.5" />
              <span>{showRawJson ? 'Masquer le JSON payload' : 'Afficher le payload JSON complet pour le backend'}</span>
            </button>

            {showRawJson && (
              <div className="mt-2 relative">
                <pre className="p-3.5 bg-muted text-foreground text-xs rounded-xl overflow-x-auto max-h-56 font-mono leading-relaxed border border-border">
                  {jsonString}
                </pre>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleCopy}
                  className="absolute top-2.5 right-2.5 h-7 px-2.5 text-xs flex items-center gap-1"
                >
                  {copied ? (
                    <>
                      <Check className="w-3 h-3 text-emerald-500" />
                      <span>Copié !</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      <span>Copier</span>
                    </>
                  )}
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Footer actions */}
        <div className="pt-3.5 flex flex-col sm:flex-row items-center justify-between gap-2.5 border-t border-border/60 mt-2">
          <Button
            type="button"
            onClick={onRunAnalysis}
            className="w-full sm:w-auto h-9 rounded-md text-xs sm:text-sm font-medium flex items-center justify-center gap-1.5 shadow-xs"
          >
            <Eye className="w-3.5 h-3.5" />
            <span>Lancer l'analyse en direct</span>
          </Button>

          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            className="w-full sm:w-auto h-9 rounded-md text-xs sm:text-sm"
          >
            Modifier ma question
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
