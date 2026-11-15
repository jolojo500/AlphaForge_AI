import React from 'react';
import { ArrowUpRight, Check } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface Step5Props {
  additionalNotes: string;
  setAdditionalNotes: (val: string) => void;
  fictionalCapitalAcknowledged: boolean;
  setFictionalCapitalAcknowledged: (val: boolean) => void;
  onSave: () => void;
  onPrev: () => void;
}

export const Step5AdditionalInfo: React.FC<Step5Props> = ({
  additionalNotes,
  setAdditionalNotes,
  fictionalCapitalAcknowledged,
  setFictionalCapitalAcknowledged,
  onSave,
  onPrev,
}) => {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm sm:text-base font-semibold text-foreground tracking-tight">
          05 / Portefeuille existant & contexte
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Titres déjà détenus, contraintes fiscales ou contexte spécifique (facultatif).
        </p>
      </div>

      {/* Textarea */}
      <div>
        <label htmlFor="notes-input" className="block text-xs font-medium text-foreground mb-1.5">
          Positions actuelles ou contexte particulier (facultatif)
        </label>
        <Textarea
          id="notes-input"
          rows={3}
          value={additionalNotes}
          onChange={(e) => setAdditionalNotes(e.target.value)}
          placeholder="Exemple : Je détiens déjà des actions Banque Nationale (NA), du S&P 500 (XSP) et Nvidia (NVDA). Je souhaite diversifier sans surpondérer la tech."
          className="resize-none text-xs sm:text-sm font-normal"
        />
        <p className="text-[11px] text-muted-foreground mt-1">
          Permet au moteur d’évaluer la concentration globale et d’éviter les doublons involontaires.
        </p>
      </div>

      {/* Fictional acknowledgment box */}
      <div
        onClick={() => setFictionalCapitalAcknowledged(!fictionalCapitalAcknowledged)}
        className={cn(
          "p-3 rounded-lg flex items-start gap-2.5 cursor-pointer select-none transition-colors border",
          fictionalCapitalAcknowledged
            ? "bg-sky-50/50 dark:bg-sky-950/30 border-sky-500/70 dark:border-sky-500/80 shadow-2xs"
            : "bg-muted/30 border-border/60 hover:bg-muted/50"
        )}
      >
        <div
          className={cn(
            "w-3.5 h-3.5 rounded flex items-center justify-center shrink-0 mt-0.5 transition-colors",
            fictionalCapitalAcknowledged
              ? "bg-foreground text-background"
              : "border border-muted-foreground/40 bg-background"
          )}
        >
          {fictionalCapitalAcknowledged && <Check className="w-2.5 h-2.5 stroke-[3]" />}
        </div>
        <p className="text-xs text-foreground leading-snug">
          J’utilise un profil et un capital simulés. Je comprends qu’aucune transaction réelle ne sera exécutée et qu’il ne s’agit pas d’un conseil financier personnalisé. <span className="text-destructive">*</span>
        </p>
      </div>

      {/* Save button & Back link */}
      <div className="space-y-2 pt-1">
        <Button
          type="button"
          onClick={onSave}
          disabled={!fictionalCapitalAcknowledged}
          className="w-full h-9 rounded-md text-xs sm:text-sm font-medium flex items-center justify-center gap-1.5 shadow-xs cursor-pointer"
        >
          <span>Enregistrer mon profil et continuer</span>
          <ArrowUpRight className="w-3.5 h-3.5" />
        </Button>

        <div className="flex justify-center">
          <button
            type="button"
            onClick={onPrev}
            className="text-xs text-muted-foreground hover:text-foreground py-0.5 font-normal transition-colors cursor-pointer"
          >
            ← Modifier les étapes précédentes
          </button>
        </div>

        <p className="text-center text-[11px] text-muted-foreground/80 pt-0.5">
          Les performances passées ne garantissent pas les résultats futurs.
        </p>
      </div>
    </div>
  );
};
