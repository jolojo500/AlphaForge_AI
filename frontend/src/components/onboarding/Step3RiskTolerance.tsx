import React from 'react';
import { RadioCard } from './RadioCard';
import { SegmentedControl } from './SegmentedControl';
import { ShieldCheck } from 'lucide-react';

interface Step3Props {
  riskTolerance: 'Faible' | 'Faible à modéré' | 'Modéré' | 'Élevé' | '';
  setRiskTolerance: (val: 'Faible' | 'Faible à modéré' | 'Modéré' | 'Élevé') => void;
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

  const lossOptions = [
    {
      id: '5',
      label: hasCap ? `Jusqu'à 5 % (${(cap * 0.05).toLocaleString('fr-CA')} $)` : `Jusqu'à 5 %`,
    },
    {
      id: '15',
      label: hasCap ? `Jusqu'à 15 % (${(cap * 0.15).toLocaleString('fr-CA')} $)` : `Jusqu'à 15 %`,
    },
    {
      id: '25',
      label: hasCap ? `Jusqu'à 25 % (${(cap * 0.25).toLocaleString('fr-CA')} $)` : `Jusqu'à 25 %`,
    },
    {
      id: '35+',
      label: hasCap ? `35 % ou plus (${(cap * 0.35).toLocaleString('fr-CA')} $ +)` : `35 % ou plus`,
    },
  ];

  const concentrationOptions = [
    'Diversification stricte · Max 25 % par secteur',
    'Diversification modérée · Max 40 % par secteur',
    'Concentration sectorielle assumée · Sans plafond strict',
  ];

  const emergencyOptions = [
    "Non, réserve d'urgence séparée",
    'Oui, une partie doit rester liquide',
    'Indéterminé',
  ];

  const essentialOptions = [
    'Non, dépenses couvertes par ailleurs',
    'Oui, sensible aux pertes durables',
    'Indéterminé',
  ];

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
            {riskTolerance || 'Sélection requise'}
          </span>
        </div>
        <SegmentedControl<'Faible' | 'Faible à modéré' | 'Modéré' | 'Élevé'>
          options={['Faible', 'Faible à modéré', 'Modéré', 'Élevé']}
          value={riskTolerance}
          onChange={setRiskTolerance}
        />
        <p className="text-[11px] text-muted-foreground mt-1.5">
          {riskTolerance === 'Faible' && 'Profil prudent : priorité absolue à la stabilité et à la sécurité du capital.'}
          {riskTolerance === 'Faible à modéré' && 'Profil modéré-prudent : fluctuations limitées pour contrer l’inflation.'}
          {riskTolerance === 'Modéré' && 'Profil équilibré : recherche de rendement avec volatilité contrôlée.'}
          {riskTolerance === 'Élevé' && 'Profil offensif : prêt à assumer de fortes fluctuations pour maximiser les gains.'}
          {!riskTolerance && 'Sélectionnez votre orientation globale face aux marchés.'}
        </p>
      </div>

      {/* Max loss tolerance */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Perte temporaire tolérée sur 12 mois sans vendre <span className="text-destructive">*</span>
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {lossOptions.map((opt) => (
            <RadioCard
              key={opt.id}
              label={opt.label}
              selected={maxLossTolerance === opt.id || maxLossTolerance === opt.label}
              onClick={() => setMaxLossTolerance(opt.id)}
            />
          ))}
        </div>
      </div>

      {/* Sector concentration */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Plafond de concentration sectorielle <span className="text-destructive">*</span>
        </label>
        <div className="space-y-1.5">
          {concentrationOptions.map((opt) => (
            <RadioCard
              key={opt}
              label={opt}
              selected={sectorConcentrationLimit === opt}
              onClick={() => setSectorConcentrationLimit(opt)}
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
            {emergencyOptions.map((opt) => (
              <RadioCard
                key={opt}
                label={opt}
                selected={capitalNeedNext12Months === opt}
                onClick={() => setCapitalNeedNext12Months(opt)}
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
            {essentialOptions.map((opt) => (
              <RadioCard
                key={opt}
                label={opt}
                selected={essentialExpensesImpact === opt}
                onClick={() => setEssentialExpensesImpact(opt)}
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
            {[
              'Aucune dette ou dettes remboursées',
              'Prêt hypothécaire uniquement',
              'Dettes à taux élevé (cartes de crédit, marge)',
            ].map((opt) => (
              <RadioCard
                key={opt}
                label={opt}
                selected={debtLevel === opt || Boolean(debtLevel && opt.startsWith(debtLevel.slice(0, 10)))}
                onClick={() => setDebtLevel && setDebtLevel(opt)}
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
            {[
              'Revenus stables (salarié permanent)',
              'Revenus variables ou travailleur autonome',
              'Retraité (revenu fixe de rente)',
            ].map((opt) => (
              <RadioCard
                key={opt}
                label={opt}
                selected={incomeStability === opt || Boolean(incomeStability && opt.startsWith(incomeStability.slice(0, 10)))}
                onClick={() => setIncomeStability && setIncomeStability(opt)}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
