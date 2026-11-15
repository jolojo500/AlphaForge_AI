import React from 'react';
import { RadioCard } from './RadioCard';
import { SegmentedControl } from './SegmentedControl';
import { AlertTriangle, ShieldCheck } from 'lucide-react';
import {
  CAPITAL_NEED_OPTIONS,
  DEBT_OPTIONS,
  ESSENTIAL_EXPENSES_OPTIONS,
  INCOME_OPTIONS,
  MAX_LOSS_OPTIONS,
  SECTOR_CAP_OPTIONS,
  TOLERANCE_OPTIONS,
  codeOf,
  labelOf,
  questionnaireWarnings,
} from '@/lib/questionnaireCodes';

interface Step3Props {
  riskTolerance: string;
  setRiskTolerance: (val: string) => void;
  maxLossTolerance: string;
  setMaxLossTolerance: (val: string) => void;
  sectorConcentrationLimit: string;
  setSectorConcentrationLimit: (val: string) => void;
  capitalNeedNext12Months: string;
  setCapitalNeedNext12Months: (val: string) => void;
  essentialExpensesImpact: string;
  setEssentialExpensesImpact: (val: string) => void;
  simulatedCapital: number;
  debtLevel?: string;
  setDebtLevel?: (val: string) => void;
  incomeStability?: string;
  setIncomeStability?: (val: string) => void;
}

export const Step3RiskTolerance: React.FC<Step3Props> = ({
  riskTolerance,
  setRiskTolerance,
  maxLossTolerance,
  setMaxLossTolerance,
  sectorConcentrationLimit,
  setSectorConcentrationLimit,
  capitalNeedNext12Months,
  setCapitalNeedNext12Months,
  essentialExpensesImpact,
  setEssentialExpensesImpact,
  simulatedCapital,
  debtLevel = '',
  setDebtLevel,
  incomeStability = '',
  setIncomeStability,
}) => {
  const cap = simulatedCapital || 0;
  const hasCap = cap > 0;

  const toleranceCode = codeOf('riskTolerance', riskTolerance) || '';
  const lossCode = codeOf('maxLossTolerance', maxLossTolerance);
  const sectorCapCode = codeOf('sectorConcentrationLimit', sectorConcentrationLimit);
  const capitalNeedCode = codeOf('capitalNeedNext12Months', capitalNeedNext12Months);
  const expensesCode = codeOf('essentialExpensesImpact', essentialExpensesImpact);
  const debtCode = codeOf('debtLevel', debtLevel);
  const incomeCode = codeOf('incomeStability', incomeStability);

  const toleranceLabels: Record<string, string> = {};
  TOLERANCE_OPTIONS.forEach((o) => {
    toleranceLabels[o.code] = o.label;
  });

  const lossLabel = (code: string, label: string) => {
    if (!hasCap) return label;
    const pct = parseFloat(code) / 100;
    const amount = (cap * pct).toLocaleString('fr-CA');
    return code === '35' ? `${label} (${amount} $ +)` : `${label} (${amount} $)`;
  };

  const warnings = questionnaireWarnings({ riskTolerance, maxLossTolerance });

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm sm:text-base font-semibold text-foreground tracking-tight">
          03 / Tolérance au risque & capacité financière
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Distinguez votre tolérance psychologique de votre capacité financière réelle à absorber une perte.
        </p>
      </div>

      {/* Risk tolerance segmented control */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-medium text-foreground">
            Tolérance globale au risque <span className="text-destructive">*</span>
          </label>
          <span className="text-xs font-medium text-primary">
            {toleranceCode ? labelOf('riskTolerance', toleranceCode) : 'Sélection requise'}
          </span>
        </div>
        <SegmentedControl<string>
          options={TOLERANCE_OPTIONS.map((o) => o.code)}
          labels={toleranceLabels}
          value={toleranceCode}
          onChange={setRiskTolerance}
        />
        <p className="text-[11px] text-muted-foreground mt-1.5">
          {toleranceCode === 'low' && 'Profil prudent : priorité absolue à la stabilité et à la sécurité du capital.'}
          {toleranceCode === 'low_moderate' && 'Profil modéré-prudent : fluctuations limitées pour contrer l’inflation.'}
          {toleranceCode === 'moderate' && 'Profil équilibré : recherche de rendement avec volatilité contrôlée.'}
          {toleranceCode === 'high' && 'Profil offensif : prêt à assumer de fortes fluctuations pour maximiser les gains.'}
          {!toleranceCode && 'Sélectionnez votre orientation globale face aux marchés.'}
        </p>
      </div>

      {/* Max loss tolerance */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Perte temporaire tolérée sur 12 mois sans vendre <span className="text-destructive">*</span>
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {MAX_LOSS_OPTIONS.map((opt) => (
            <RadioCard
              key={opt.code}
              label={lossLabel(opt.code, opt.label)}
              selected={lossCode === opt.code}
              onClick={() => setMaxLossTolerance(opt.code)}
            />
          ))}
        </div>
        {warnings.length > 0 && (
          <div
            role="alert"
            className="mt-2 p-2.5 rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300 text-xs space-y-1"
          >
            {warnings.map((w) => (
              <p key={w} className="flex items-start gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>{w}</span>
              </p>
            ))}
          </div>
        )}
      </div>

      {/* Sector concentration */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Plafond de concentration sectorielle <span className="text-destructive">*</span>
        </label>
        <div className="space-y-1.5">
          {SECTOR_CAP_OPTIONS.map((opt) => (
            <RadioCard
              key={opt.code}
              label={opt.label}
              selected={sectorCapCode === opt.code}
              onClick={() => setSectorConcentrationLimit(opt.code)}
            />
          ))}
        </div>
      </div>

      {/* Financial capacity section */}
      <div className="pt-2 border-t border-border/50 space-y-3">
        <div className="flex items-center gap-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
          <span className="text-xs font-semibold text-foreground">Capacité financière réelle</span>
        </div>

        {/* Emergency reserve */}
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">
            Aurez-vous besoin de ce capital dans les 12 prochains mois ? <span className="text-destructive">*</span>
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {CAPITAL_NEED_OPTIONS.map((opt) => (
              <RadioCard
                key={opt.code}
                label={opt.label}
                selected={capitalNeedCode === opt.code}
                onClick={() => setCapitalNeedNext12Months(opt.code)}
              />
            ))}
          </div>
        </div>

        {/* Essential expenses */}
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">
            Une baisse prolongée impacterait-elle vos dépenses essentielles ? <span className="text-destructive">*</span>
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {ESSENTIAL_EXPENSES_OPTIONS.map((opt) => (
              <RadioCard
                key={opt.code}
                label={opt.label}
                selected={expensesCode === opt.code}
                onClick={() => setEssentialExpensesImpact(opt.code)}
              />
            ))}
          </div>
        </div>
        {/* Debt status (KYC hard gate #117) */}
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">
            Endettement & dettes à taux d'intérêt élevé <span className="text-destructive">*</span>
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {DEBT_OPTIONS.map((opt) => (
              <RadioCard
                key={opt.code}
                label={opt.label}
                selected={debtCode === opt.code}
                onClick={() => setDebtLevel && setDebtLevel(opt.code)}
              />
            ))}
          </div>
        </div>

        {/* Income stability (KYC suitability #117) */}
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">
            Stabilité de vos revenus <span className="text-destructive">*</span>
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {INCOME_OPTIONS.map((opt) => (
              <RadioCard
                key={opt.code}
                label={opt.label}
                selected={incomeCode === opt.code}
                onClick={() => setIncomeStability && setIncomeStability(opt.code)}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
