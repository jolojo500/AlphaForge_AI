import React from 'react';
import { RadioCard } from './RadioCard';
import { Calendar } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';

interface Step2Props {
  primaryObjective: string;
  setPrimaryObjective: (val: string) => void;
  firstWithdrawalHorizon: string;
  setFirstWithdrawalHorizon: (val: string) => void;
  withdrawalMethod: string;
  setWithdrawalMethod: (val: string) => void;
  simulatedCapital: number;
  setSimulatedCapital: (val: number) => void;
  accountType: string;
  setAccountType: (val: string) => void;
}

export const Step2FinancialGoals: React.FC<Step2Props> = ({
  primaryObjective,
  setPrimaryObjective,
  firstWithdrawalHorizon,
  setFirstWithdrawalHorizon,
  withdrawalMethod,
  setWithdrawalMethod,
  simulatedCapital,
  setSimulatedCapital,
  accountType,
  setAccountType,
}) => {
  const objectiveOptions = [
    'Croissance du capital',
    'Croissance équilibrée & stabilité',
    'Préservation du capital',
    'Génération de revenus réguliers',
    'Financement d’un projet spécifique',
  ];

  // Parse current horizon number from string (null if not set yet)
  const currentHorizonNum = (() => {
    if (!firstWithdrawalHorizon) return null;
    const m = firstWithdrawalHorizon.match(/\d+/);
    return m ? parseInt(m[0], 10) : null;
  })();

  const formatHorizonText = (val: number): string => {
    const years = Math.min(Math.max(1, Math.round(val)), 30);
    if (years >= 20) {
      return `${years} ans · Long terme (Retraite)`;
    } else if (years >= 15) {
      return `${years} ans · Long terme`;
    } else if (years >= 8) {
      return `${years} ans · Moyen-long terme`;
    } else if (years >= 4) {
      return `${years} ans · Moyen terme`;
    } else if (years >= 2) {
      return `${years} ans · Court terme`;
    } else {
      return '1 an · Court terme';
    }
  };

  const handleSetYears = (years: number) => {
    const clamped = Math.min(Math.max(1, years), 30);
    setFirstWithdrawalHorizon(formatHorizonText(clamped));
  };

  const horizonMarks = [
    { val: 1, label: '1 an' },
    { val: 5, label: '5 ans' },
    { val: 10, label: '10 ans' },
    { val: 15, label: '15 ans' },
    { val: 20, label: '20 ans' },
    { val: 30, label: '30 ans' },
  ];

  const methodOptions = [
    'Réinvestissement total (Aucun retrait)',
    'Retraits progressifs périodiques',
    'Décaissement unique à terme',
  ];

  const capitalPresets = [10000, 25000, 50000, 100000, 250000];

  const accountTypeOptions = [
    {
      id: "CELI — Compte d'épargne libre d'impôt",
      label: "CELI · Libre d'impôt",
      info: "Compte d'épargne libre d'impôt. Tous les gains, dividendes et retraits sont 100 % non imposables au Canada. Plafond cumulatif annuel sans pénalité de retrait.",
    },
    {
      id: "REER — Régime d'épargne-retraite",
      label: "REER · Épargne-retraite",
      info: "Régime enregistré d'épargne-retraite. Les cotisations sont déductibles de votre revenu imposable. La croissance est à l'abri de l'impôt jusqu'au retrait à la retraite.",
    },
    {
      id: "CELIAPP — Première propriété",
      label: "CELIAPP · Achat première propriété",
      info: "Compte combinant les atouts du REER et du CELI : cotisations déductibles d'impôt et retraits non taxés pour l'achat d'une première habitation (max 40 000 $).",
    },
    {
      id: "Compte non enregistré (Imposable)",
      label: "Non enregistré · Comptant / Marge",
      info: "Compte imposable ordinaire sans plafond de dépôt. 50 % des gains en capital sont imposables, crédits d'impôt sur dividendes canadiens admissibles.",
    },
    {
      id: "CRI / FERR — Décaissement de retraite",
      label: "CRI / FERR · Revenu de retraite",
      info: "Compte de retraite immobilisé (CRI) ou Fonds Enregistré de Revenu de Retraite (FERR) soumis à des retraits annuels obligatoires calculés selon l'âge.",
    },
  ];

  const formatCurrency = (val: number) => {
    if (!val) return '';
    return `${val.toLocaleString('fr-CA')} $ CAD`;
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm sm:text-base font-semibold text-foreground tracking-tight">
          02 / Objectifs & paramètres financiers
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Précisez la finalité, l’horizon et le cadre fiscal de ce portefeuille simulé.
        </p>
      </div>

      {/* Primary objective */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Objectif principal d’investissement <span className="text-destructive">*</span>
        </label>
        <div className="space-y-1.5">
          {objectiveOptions.map((opt) => (
            <RadioCard
              key={opt}
              label={opt}
              selected={primaryObjective === opt}
              onClick={() => setPrimaryObjective(opt)}
            />
          ))}
        </div>
      </div>

      {/* Horizon - Épuré */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-medium text-foreground flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5 text-primary" />
            <span>Horizon avant retrait majeur <span className="text-destructive">*</span></span>
          </label>
          <span className="text-xs font-semibold text-primary">
            {currentHorizonNum !== null ? (
              `${currentHorizonNum} an${currentHorizonNum > 1 ? 's' : ''}`
            ) : (
              <span className="text-muted-foreground font-normal italic">À définir</span>
            )}
          </span>
        </div>

        <div className="space-y-1.5 px-1.5">
          <div
            onPointerDown={() => {
              if (!firstWithdrawalHorizon) {
                handleSetYears(currentHorizonNum ?? 5);
              }
            }}
            className="py-1"
          >
            <Slider
              value={[currentHorizonNum ?? 5]}
              onValueChange={(vals) => handleSetYears(vals[0])}
              min={1}
              max={30}
              step={1}
              className="cursor-pointer"
            />
          </div>

          {/* Repères précisément alignés sur la position exacte du curseur */}
          <div className="relative w-full h-6 select-none mt-0.5">
            {horizonMarks.map((mark) => {
              const ratio = (mark.val - 1) / 29;
              const isSelected = currentHorizonNum === mark.val;

              return (
                <button
                  key={mark.val}
                  type="button"
                  onClick={() => handleSetYears(mark.val)}
                  style={{
                    left: `calc(10px + (100% - 20px) * ${ratio})`,
                    transform: 'translateX(-50%)',
                  }}
                  className={`absolute top-0 flex flex-col items-center hover:text-foreground transition-colors cursor-pointer py-0.5 whitespace-nowrap ${
                    isSelected ? 'text-primary font-semibold' : 'text-muted-foreground'
                  }`}
                >
                  <span
                    className={`w-0.5 h-1 rounded-full mb-1 transition-colors ${
                      isSelected ? 'bg-primary' : 'bg-border'
                    }`}
                  />
                  <span className="text-[11px] leading-none">
                    {mark.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Withdrawal method */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Mode de décaissement prévu <span className="text-destructive">*</span>
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {methodOptions.map((opt) => (
            <RadioCard
              key={opt}
              label={opt}
              selected={withdrawalMethod === opt}
              onClick={() => setWithdrawalMethod(opt)}
            />
          ))}
        </div>
      </div>

      {/* Capital & Account Type */}
      <div className="grid grid-cols-1 gap-4 pt-1">
        {/* Capital */}
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">
            Capital fictif à allouer <span className="text-destructive">*</span>
          </label>
          <div className="flex flex-col sm:flex-row gap-2">
            <Input
              type="text"
              required
              value={formatCurrency(simulatedCapital)}
              placeholder="ex : 50 000 $ CAD"
              onChange={(e) => {
                const num = parseInt(e.target.value.replace(/\D/g, ''), 10);
                setSimulatedCapital(isNaN(num) ? 0 : num);
              }}
              className="w-full sm:w-1/2 text-xs sm:text-sm font-medium h-9"
            />
            <div className="flex-1 grid grid-cols-5 gap-1.5">
              {capitalPresets.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => setSimulatedCapital(preset)}
                  className={`py-1.5 text-[11px] rounded-md text-center transition-all cursor-pointer ${
                    simulatedCapital === preset
                      ? 'bg-foreground text-background shadow-xs font-medium'
                      : 'bg-muted hover:bg-muted/80 text-foreground border border-border/60'
                  }`}
                >
                  {preset >= 1000 ? `${preset / 1000} k$` : `${preset} $`}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Account type with (i) tooltips */}
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">
            Type de compte fiscal <span className="text-destructive">*</span>
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {accountTypeOptions.map((opt) => (
              <RadioCard
                key={opt.id}
                label={opt.label}
                selected={accountType === opt.id || accountType.startsWith(opt.label.split(' · ')[0])}
                onClick={() => setAccountType(opt.id)}
                infoTooltip={opt.info}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
