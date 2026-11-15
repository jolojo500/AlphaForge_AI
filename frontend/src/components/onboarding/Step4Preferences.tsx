import React from 'react';
import { CheckboxCard } from './CheckboxCard';
import { RadioCard } from './RadioCard';
import { InfoTooltip } from '@/components/ui/info-tooltip';
import { AlertTriangle } from 'lucide-react';
import {
  CRYPTO_OPTIONS,
  CURRENCY_OPTIONS,
  ESG_OPTIONS,
  EXCLUSION_OPTIONS,
  SECTOR_OPTIONS,
  codeOf,
  codesOf,
  questionnaireWarnings,
} from '@/lib/questionnaireCodes';

interface Step4Props {
  interestedSectors: string[];
  setInterestedSectors: (val: string[]) => void;
  cryptoPreference: string;
  setCryptoPreference: (val: string) => void;
  esgImportance: string;
  setEsgImportance: (val: string) => void;
  excludedCategories?: string[];
  setExcludedCategories?: (val: string[]) => void;
  currencyPreference?: string;
  setCurrencyPreference?: (val: string) => void;
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
  currencyPreference,
  setCurrencyPreference,
}) => {
  const sectors = codesOf('interestedSectors', interestedSectors);
  const exclusions = codesOf('excludedCategories', excludedCategories);
  const cryptoCode = codeOf('cryptoPreference', cryptoPreference);
  const esgCode = codeOf('esgImportance', esgImportance);
  const currencyCode = codeOf('currencyPreference', currencyPreference);

  const toggleSector = (code: string) => {
    setInterestedSectors(sectors.includes(code) ? sectors.filter((s) => s !== code) : [...sectors, code]);
  };

  const toggleExclusion = (code: string) => {
    if (!setExcludedCategories) return;
    setExcludedCategories(
      exclusions.includes(code) ? exclusions.filter((e) => e !== code) : [...exclusions, code]
    );
  };

  const warnings = questionnaireWarnings({
    cryptoPreference,
    excludedCategories,
    interestedSectors,
    esgImportance,
  });

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
          {SECTOR_OPTIONS.map((opt) => (
            <CheckboxCard
              key={opt.code}
              label={opt.label}
              checked={sectors.includes(opt.code)}
              onToggle={() => toggleSector(opt.code)}
            />
          ))}
        </div>
      </div>

      {/* Crypto */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Place accordée aux cryptoactifs <span className="text-destructive">*</span>
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {CRYPTO_OPTIONS.map((opt) => (
            <RadioCard
              key={opt.code}
              label={opt.label}
              selected={cryptoCode === opt.code}
              onClick={() => setCryptoPreference(opt.code)}
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
          <InfoTooltip content="ESG : Critères évaluant l'impact environnemental, social et la gouvernance d'une entreprise. « Secondaire » favorise la part détenue par le FNB ESGV sans exclure de titres." />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {ESG_OPTIONS.map((opt) => (
            <RadioCard
              key={opt.code}
              label={opt.label}
              selected={esgCode === opt.code}
              onClick={() => setEsgImportance(opt.code)}
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
            {EXCLUSION_OPTIONS.map((opt) => (
              <CheckboxCard
                key={opt.code}
                label={opt.label}
                checked={exclusions.includes(opt.code)}
                onToggle={() => toggleExclusion(opt.code)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Devise d'ancrage */}
      {setCurrencyPreference && (
        <div>
          <label className="block text-xs font-medium text-foreground mb-1.5">
            Devise & marché d’ancrage <span className="text-destructive">*</span>
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {CURRENCY_OPTIONS.map((opt) => (
              <RadioCard
                key={opt.code}
                label={opt.label}
                selected={currencyCode === opt.code}
                onClick={() => setCurrencyPreference(opt.code)}
              />
            ))}
          </div>
        </div>
      )}

      {warnings.length > 0 && (
        <div
          role="alert"
          className="p-3 rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300 text-xs space-y-1"
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
  );
};
