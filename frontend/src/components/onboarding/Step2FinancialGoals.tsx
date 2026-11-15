import React from 'react';
import { RadioCard } from './RadioCard';
import { Calendar } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import {
  ACCOUNT_OPTIONS,
  NET_WORTH_OPTIONS,
  OBJECTIVE_OPTIONS,
  WITHDRAWAL_OPTIONS,
  codeOf,
} from '@/lib/questionnaireCodes';

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
  netWorthShare?: string;
  setNetWorthShare?: (val: string) => void;
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
  netWorthShare = '',
  setNetWorthShare,
}) => {
  const objectiveCode = codeOf('primaryObjective', primaryObjective);
  const withdrawalCode = codeOf('withdrawalMethod', withdrawalMethod);
  const accountCode = codeOf('accountType', accountType);
  const netWorthCode = codeOf('netWorthShare', netWorthShare);

  // Parse current horizon number from string (defaults to 5 years)
  const currentHorizonNum = (() => {
    if (!firstWithdrawalHorizon) return 5;
    const m = firstWithdrawalHorizon.match(/\d+/);
    return m ? parseInt(m[0], 10) : 5;
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
    { val: 25, label: '25 ans' },
    { val: 30, label: '30 ans' },
  ];

  const capitalPresets = [10000, 25000, 50000, 100000, 250000];

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
          {OBJECTIVE_OPTIONS.map((opt) => (
            <RadioCard
              key={opt.code}
              label={opt.label}
              selected={objectiveCode === opt.code}
              onClick={() => setPrimaryObjective(opt.code)}
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
            {firstWithdrawalHorizon ? `${currentHorizonNum} an${currentHorizonNum > 1 ? 's' : ''}` : 'À choisir'}
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
              const isSelected = Boolean(firstWithdrawalHorizon) && currentHorizonNum === mark.val;

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
          {WITHDRAWAL_OPTIONS.map((opt) => (
            <RadioCard
              key={opt.code}
              label={opt.label}
              selected={withdrawalCode === opt.code}
              onClick={() => setWithdrawalMethod(opt.code)}
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
              value={simulatedCapital > 0 ? formatCurrency(simulatedCapital) : ''}
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

        {/* Share of net worth (KYC suitability #117) */}
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">
            Part du patrimoine global représentée par ce montant <span className="text-destructive">*</span>
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {NET_WORTH_OPTIONS.map((opt) => (
              <RadioCard
                key={opt.code}
                label={opt.label}
                selected={netWorthCode === opt.code}
                onClick={() => setNetWorthShare && setNetWorthShare(opt.code)}
              />
            ))}
          </div>
        </div>

        {/* Account type with (i) tooltips */}
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">
            Type de compte fiscal <span className="text-destructive">*</span>
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {ACCOUNT_OPTIONS.map((opt) => (
              <RadioCard
                key={opt.code}
                label={opt.label}
                selected={accountCode === opt.code}
                onClick={() => setAccountType(opt.code)}
                infoTooltip={opt.info}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
