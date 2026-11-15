import React from 'react';
import { RadioCard } from './RadioCard';
import { CheckboxCard } from './CheckboxCard';
import { SegmentedControl } from './SegmentedControl';
import {
  AGE_OPTIONS,
  ASSET_FAMILIARITY_OPTIONS,
  EXPERIENCE_OPTIONS,
  FAMILY_OPTIONS,
  codeOf,
  codesOf,
} from '@/lib/questionnaireCodes';

interface Step1Props {
  ageRange: string;
  setAgeRange: (val: string) => void;
  familySituation: string;
  setFamilySituation: (val: string) => void;
  investmentExperience: string;
  setInvestmentExperience: (val: string) => void;
  businessModelsUnderstanding: string | string[];
  setBusinessModelsUnderstanding: (val: string | string[]) => void;
}

export const Step1Identity: React.FC<Step1Props> = ({
  ageRange,
  setAgeRange,
  familySituation,
  setFamilySituation,
  investmentExperience,
  setInvestmentExperience,
  businessModelsUnderstanding,
  setBusinessModelsUnderstanding,
}) => {
  const ageCode = codeOf('ageRange', ageRange);
  const familyCode = codeOf('familySituation', familySituation);
  const experienceCode = codeOf('investmentExperience', investmentExperience) || '';
  const selectedAssets = codesOf('businessModelsUnderstanding', businessModelsUnderstanding);

  const toggleAsset = (code: string) => {
    const updated = selectedAssets.includes(code)
      ? selectedAssets.filter((a) => a !== code)
      : [...selectedAssets, code];
    setBusinessModelsUnderstanding(updated);
  };

  const experienceLabels: Record<string, string> = {};
  EXPERIENCE_OPTIONS.forEach((o) => {
    experienceLabels[o.code] = o.label;
  });

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm sm:text-base font-semibold text-foreground tracking-tight">
          01 / Identité & expérience
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Paramètres nécessaires pour calibrer le niveau des explications et le cadre de risque.
        </p>
      </div>

      {/* Age range */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Tranche d’âge <span className="text-destructive">*</span>
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {AGE_OPTIONS.map((opt) => (
            <RadioCard
              key={opt.code}
              label={opt.label}
              selected={ageCode === opt.code}
              onClick={() => setAgeRange(opt.code)}
            />
          ))}
        </div>
      </div>

      {/* Family situation */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Situation personnelle & familiale <span className="text-destructive">*</span>
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {FAMILY_OPTIONS.map((opt) => (
            <RadioCard
              key={opt.code}
              label={opt.label}
              selected={familyCode === opt.code}
              onClick={() => setFamilySituation(opt.code)}
            />
          ))}
        </div>
      </div>

      {/* Investment experience */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Niveau d’expérience en investissement <span className="text-destructive">*</span>
        </label>
        <SegmentedControl<string>
          options={EXPERIENCE_OPTIONS.map((o) => o.code)}
          labels={experienceLabels}
          value={experienceCode}
          onChange={setInvestmentExperience}
        />
        <p className="text-[11px] text-muted-foreground mt-1.5">
          {experienceCode === 'beginner' && 'Priorité à la simplicité et aux explications des concepts de base.'}
          {experienceCode === 'intermediate' && 'Compréhension courante des actions, des FNB et des cycles de marché.'}
          {experienceCode === 'advanced' && 'Suivi actif des marchés et maîtrise des métriques quantitatives.'}
          {!experienceCode && 'Sélectionnez votre niveau de familiarité avec les marchés.'}
        </p>
      </div>

      {/* Assets familiarity */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Actifs que vous êtes à l’aise d’analyser <span className="text-destructive">*</span>
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {ASSET_FAMILIARITY_OPTIONS.map((opt) => (
            <CheckboxCard
              key={opt.code}
              label={opt.label}
              checked={selectedAssets.includes(opt.code)}
              onToggle={() => toggleAsset(opt.code)}
            />
          ))}
        </div>
      </div>
    </div>
  );
};
