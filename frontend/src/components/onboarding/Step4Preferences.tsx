import React from 'react';
import { CheckboxCard } from './CheckboxCard';
import { RadioCard } from './RadioCard';
import { InfoTooltip } from '@/components/ui/info-tooltip';

interface Step4Props {
  interestedSectors: string[];
  setInterestedSectors: (val: string[]) => void;
  cryptoPreference: string;
  setCryptoPreference: (val: string) => void;
  esgImportance: string;
  setEsgImportance: (val: string) => void;
  excludedCategories?: string[];
  setExcludedCategories?: (val: string[]) => void;
}

export const Step4Preferences: React.FC<Step4Props> = ({
  interestedSectors,
  setInterestedSectors,
  cryptoPreference,
  setCryptoPreference,
  esgImportance,
  setEsgImportance,
  excludedCategories = [],
  setExcludedCategories,
}) => {
  const sectorOptions = [
    'Technologies & IA',
    'Banques & Finance',
    'Dividendes & Services publics',
    'Santé & Consommation',
    'Obligations & Revenu fixe',
    'Or & Valeurs refuges',
    'Énergie & Ressources',
  ];

  const cryptoOptions = [
    'Exclusion totale (0 % crypto)',
    'Exposition modérée (1 à 5 %)',
    'Actifs majeurs (Bitcoin, Ether)',
  ];

  const esgOptions = [
    'Prioritaire · Filtres stricts',
    'Secondaire · Favoriser les mieux notés',
    'Neutre · Performance financière pure',
  ];

  const exclusionChoices = [
    'Énergies fossiles & controverses climatiques',
    'Cryptoactifs & devises virtuelles',
    'Aucune exclusion particulière',
  ];

  const toggleSector = (sector: string) => {
    if (interestedSectors.includes(sector)) {
      setInterestedSectors(interestedSectors.filter((s) => s !== sector));
    } else {
      setInterestedSectors([...interestedSectors, sector]);
    }
  };

  const toggleExclusion = (item: string) => {
    if (!setExcludedCategories) return;
    if (item === 'Aucune exclusion particulière') {
      setExcludedCategories(['Aucune exclusion particulière']);
      return;
    }
    const cleanList = excludedCategories.filter((e) => e !== 'Aucune exclusion particulière');
    if (cleanList.includes(item)) {
      setExcludedCategories(cleanList.filter((e) => e !== item));
    } else {
      setExcludedCategories([...cleanList, item]);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm sm:text-base font-semibold text-foreground tracking-tight">
          04 / Préférences, convictions & exclusions
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Définissez vos préférences sectorielles, géographiques et vos critères d’exclusion.
        </p>
      </div>

      {/* Sectors */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Secteurs et thématiques d’intérêt <span className="text-destructive">*</span>
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {sectorOptions.map((opt) => (
            <CheckboxCard
              key={opt}
              label={opt}
              checked={interestedSectors.includes(opt)}
              onToggle={() => toggleSector(opt)}
            />
          ))}
        </div>
      </div>

      {/* Crypto */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Place accordée aux cryptoactifs <span className="text-destructive">*</span>
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {cryptoOptions.map((opt) => (
            <RadioCard
              key={opt}
              label={opt}
              selected={cryptoPreference === opt}
              onClick={() => setCryptoPreference(opt)}
            />
          ))}
        </div>
      </div>

      {/* ESG with one single (i) */}
      <div>
        <div className="flex items-center gap-1.5 mb-1.5">
          <label className="text-xs font-medium text-foreground">
            Critères environnementaux, sociaux et gouvernance (ESG) <span className="text-destructive">*</span>
          </label>
          <InfoTooltip content="ESG : Critères évaluant l'impact environnemental, social et la gouvernance d'une entreprise." />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {esgOptions.map((opt) => (
            <RadioCard
              key={opt}
              label={opt}
              selected={esgImportance === opt}
              onClick={() => setEsgImportance(opt)}
            />
          ))}
        </div>
      </div>

      {/* Specific Exclusions */}
      {setExcludedCategories && (
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">
            Exclusions éthiques ou sectorielles spécifiques (facultatif)
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {exclusionChoices.map((item) => (
              <CheckboxCard
                key={item}
                label={item}
                checked={excludedCategories.includes(item)}
                onToggle={() => toggleExclusion(item)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
