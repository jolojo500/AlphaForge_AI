import React from 'react';
import { RadioCard } from './RadioCard';
import { CheckboxCard } from './CheckboxCard';
import { SegmentedControl } from './SegmentedControl';

interface Step1Props {
  ageRange: string;
  setAgeRange: (val: string) => void;
  familySituation: string;
  setFamilySituation: (val: string) => void;
  investmentExperience: 'Débutant' | 'Intermédiaire' | 'Avancé' | '';
  setInvestmentExperience: (val: 'Débutant' | 'Intermédiaire' | 'Avancé') => void;
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
  const ageOptions = ['18–29 ans', '30–44 ans', '45–59 ans', '60 ans et plus'];

  const familyOptions = [
    'Célibataire',
    'En couple (sans enfant)',
    'Famille avec personnes à charge',
    'Retraité / Enfants indépendants',
  ];

  const assetOptions = [
    'Actions cotées en bourse',
    'FNB & Fonds indiciels',
    'Obligations & Titres à revenu fixe',
    'Technologies & Forte croissance',
    'Cryptoactifs & Actifs numériques',
  ];

  const selectedAssets = Array.isArray(businessModelsUnderstanding)
    ? businessModelsUnderstanding
    : businessModelsUnderstanding
    ? businessModelsUnderstanding.split(', ').filter(Boolean)
    : [];

  const toggleAsset = (asset: string) => {
    let updated: string[];
    if (selectedAssets.includes(asset)) {
      updated = selectedAssets.filter((a) => a !== asset);
    } else {
      updated = [...selectedAssets, asset];
    }
    setBusinessModelsUnderstanding(updated);
  };

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
          {ageOptions.map((opt) => (
            <RadioCard
              key={opt}
              label={opt}
              selected={ageRange === opt}
              onClick={() => setAgeRange(opt)}
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
          {familyOptions.map((opt) => (
            <RadioCard
              key={opt}
              label={opt}
              selected={familySituation === opt}
              onClick={() => setFamilySituation(opt)}
            />
          ))}
        </div>
      </div>

      {/* Investment experience */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Niveau d’expérience en investissement <span className="text-destructive">*</span>
        </label>
        <SegmentedControl<'Débutant' | 'Intermédiaire' | 'Avancé'>
          options={['Débutant', 'Intermédiaire', 'Avancé']}
          value={investmentExperience}
          onChange={setInvestmentExperience}
        />
        <p className="text-[11px] text-muted-foreground mt-1.5">
          {investmentExperience === 'Débutant' && 'Priorité à la simplicité et aux explications des concepts de base.'}
          {investmentExperience === 'Intermédiaire' && 'Compréhension courante des actions, des FNB et des cycles de marché.'}
          {investmentExperience === 'Avancé' && 'Suivi actif des marchés et maîtrise des métriques quantitatives.'}
          {!investmentExperience && 'Sélectionnez votre niveau de familiarité avec les marchés.'}
        </p>
      </div>

      {/* Assets familiarity */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Actifs que vous êtes à l’aise d’analyser <span className="text-destructive">*</span>
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {assetOptions.map((opt) => (
            <CheckboxCard
              key={opt}
              label={opt}
              checked={selectedAssets.includes(opt)}
              onToggle={() => toggleAsset(opt)}
            />
          ))}
        </div>
      </div>
    </div>
  );
};
