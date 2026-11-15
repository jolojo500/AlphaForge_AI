import React, { useState } from 'react';
import { AppHeader } from '../AppHeader';
import { UserOnboardingProfile } from '../../types';
import { Step1Identity } from './Step1Identity';
import { Step2FinancialGoals } from './Step2FinancialGoals';
import { Step3RiskTolerance } from './Step3RiskTolerance';
import { Step4Preferences } from './Step4Preferences';
import { Step5AdditionalInfo } from './Step5AdditionalInfo';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Card, CardContent } from '@/components/ui/card';

interface OnboardingFlowProps {
  initialProfile?: UserOnboardingProfile | null;
  onComplete: (profile: UserOnboardingProfile) => void;
  onCancel?: () => void;
}

export const OnboardingFlow: React.FC<OnboardingFlowProps> = ({
  initialProfile,
  onComplete,
  onCancel,
}) => {
  const [currentStep, setCurrentStep] = useState<number>(1);

  // Form State (Empty defaults for new users)
  const [ageRange, setAgeRange] = useState<string>(
    initialProfile?.ageRange || ''
  );
  const [familySituation, setFamilySituation] = useState<string>(
    initialProfile?.familySituation || ''
  );
  const [investmentExperience, setInvestmentExperience] = useState<
    'Débutant' | 'Intermédiaire' | 'Avancé' | ''
  >(initialProfile?.investmentExperience || '');
  const [businessModelsUnderstanding, setBusinessModelsUnderstanding] = useState<
    string | string[]
  >(initialProfile?.businessModelsUnderstanding || []);

  const [primaryObjective, setPrimaryObjective] = useState<string>(
    initialProfile?.primaryObjective || ''
  );
  const [firstWithdrawalHorizon, setFirstWithdrawalHorizon] = useState<string>(
    initialProfile?.firstWithdrawalHorizon || '5 ans · Moyen terme'
  );
  const [withdrawalMethod, setWithdrawalMethod] = useState<string>(
    initialProfile?.withdrawalMethod || ''
  );
  const [simulatedCapital, setSimulatedCapital] = useState<number>(
    initialProfile?.simulatedCapital || 0
  );
  const [accountType, setAccountType] = useState<string>(
    initialProfile?.accountType || ''
  );
  const [netWorthShare, setNetWorthShare] = useState<string>(
    initialProfile?.netWorthShare || ''
  );

  const [riskTolerance, setRiskTolerance] = useState<
    'Faible' | 'Faible à modéré' | 'Modéré' | 'Élevé' | ''
  >(initialProfile?.riskTolerance || '');
  const [maxLossTolerance, setMaxLossTolerance] = useState<string>(
    initialProfile?.maxLossTolerance || ''
  );
  const [sectorConcentrationLimit, setSectorConcentrationLimit] = useState<string>(
    initialProfile?.sectorConcentrationLimit || ''
  );
  const [capitalNeedNext12Months, setCapitalNeedNext12Months] = useState<string>(
    initialProfile?.capitalNeedNext12Months || ''
  );
  const [essentialExpensesImpact, setEssentialExpensesImpact] = useState<string>(
    initialProfile?.essentialExpensesImpact || ''
  );
  const [debtLevel, setDebtLevel] = useState<string>(
    initialProfile?.debtLevel || ''
  );
  const [incomeStability, setIncomeStability] = useState<string>(
    initialProfile?.incomeStability || ''
  );

  const [interestedSectors, setInterestedSectors] = useState<string[]>(
    initialProfile?.interestedSectors || []
  );
  const [cryptoPreference, setCryptoPreference] = useState<string>(
    initialProfile?.cryptoPreference || ''
  );
  const [esgImportance, setEsgImportance] = useState<string>(
    initialProfile?.esgImportance || ''
  );
  const [excludedCategories, setExcludedCategories] = useState<string[]>(
    initialProfile?.excludedCategories || []
  );
  const [currencyPreference, setCurrencyPreference] = useState<string>(
    initialProfile?.currencyPreference || ''
  );

  const [additionalNotes, setAdditionalNotes] = useState<string>(
    initialProfile?.additionalNotes || ''
  );
  const [currentHoldingsCsv, setCurrentHoldingsCsv] = useState<string>(
    initialProfile?.currentHoldingsCsv || ''
  );
  const [currentHoldings, setCurrentHoldings] = useState<Record<string, number>>(
    initialProfile?.currentHoldings || {}
  );
  const [fictionalCapitalAcknowledged, setFictionalCapitalAcknowledged] = useState<boolean>(
    initialProfile?.fictionalCapitalAcknowledged ?? false
  );

  const handleSave = () => {
    const profile: UserOnboardingProfile = {
      ageRange: ageRange || 'Non spécifié',
      familySituation: familySituation || 'Non spécifié',
      investmentExperience: (investmentExperience || 'Intermédiaire') as 'Débutant' | 'Intermédiaire' | 'Avancé',
      businessModelsUnderstanding: Array.isArray(businessModelsUnderstanding)
        ? businessModelsUnderstanding.join(', ')
        : businessModelsUnderstanding || 'Non spécifié',
      primaryObjective: primaryObjective || 'Non spécifié',
      firstWithdrawalHorizon: firstWithdrawalHorizon || 'Non spécifié',
      withdrawalMethod: withdrawalMethod || 'Non spécifié',
      simulatedCapital: simulatedCapital || 0,
      simulatedCapitalFormatted: simulatedCapital > 0 ? `${simulatedCapital.toLocaleString('fr-CA')} $ CAD` : '0 $ CAD',
      accountType: accountType || 'Non spécifié',
      netWorthShare: netWorthShare || 'Moins de 25 %',
      riskTolerance: (riskTolerance || 'Modéré') as 'Faible' | 'Faible à modéré' | 'Modéré' | 'Élevé',
      maxLossTolerance: maxLossTolerance || 'Non spécifié',
      sectorConcentrationLimit: sectorConcentrationLimit || 'Non spécifié',
      capitalNeedNext12Months: capitalNeedNext12Months || 'Non spécifié',
      essentialExpensesImpact: essentialExpensesImpact || 'Non spécifié',
      debtLevel: debtLevel || 'Aucune dette',
      incomeStability: incomeStability || 'Revenus stables',
      interestedSectors,
      cryptoPreference: cryptoPreference || 'Non spécifié',
      esgImportance: esgImportance || 'Non spécifié',
      excludedCategories,
      currencyPreference: currencyPreference || 'Non spécifié',
      additionalNotes,
      currentHoldingsCsv,
      currentHoldings: Object.keys(currentHoldings).length > 0 ? currentHoldings : undefined,
      fictionalCapitalAcknowledged,
      completedAt: new Date().toISOString(),
    };

    try {
      localStorage.setItem('alphaforge_user_profile', JSON.stringify(profile));
    } catch (e) {
      console.warn('Could not write to localStorage:', e);
    }

    onComplete(profile);
  };

  // Step validation (all questions are required)
  const isStep1Complete = Boolean(
    ageRange &&
      familySituation &&
      investmentExperience &&
      (Array.isArray(businessModelsUnderstanding)
        ? businessModelsUnderstanding.length > 0
        : Boolean(businessModelsUnderstanding))
  );
  const isStep2Complete = Boolean(
    primaryObjective && firstWithdrawalHorizon && withdrawalMethod && simulatedCapital > 0 && accountType && netWorthShare
  );
  const isStep3Complete = Boolean(
    riskTolerance && maxLossTolerance && sectorConcentrationLimit && capitalNeedNext12Months && essentialExpensesImpact && debtLevel && incomeStability
  );
  const isStep4Complete = Boolean(
    interestedSectors.length > 0 && cryptoPreference && esgImportance && currencyPreference
  );

  const isCurrentStepValid = (() => {
    switch (currentStep) {
      case 1:
        return isStep1Complete;
      case 2:
        return isStep2Complete;
      case 3:
        return isStep3Complete;
      case 4:
        return isStep4Complete;
      default:
        return true;
    }
  })();

  const progressPercent = (currentStep / 5) * 100;

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-between px-4 py-5 sm:py-8 font-sans transition-colors">
      {/* Unified Top Header with Centered Logo & Right Theme/Cancel */}
      <AppHeader
        rightActions={
          onCancel ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={onCancel}
              className="h-8 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
            >
              Annuler
            </Button>
          ) : undefined
        }
      />

      <div className="w-full max-w-2xl mx-auto my-auto py-4">
        {/* Sleek Step Progress Indicator */}
        <div className="w-full mb-5 space-y-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground px-0.5">
            <span>Questionnaire investisseur</span>
            <span className="font-mono text-[11px]">Étape {currentStep} / 5</span>
          </div>
          <Progress value={progressPercent} className="h-1" />
        </div>

        {/* Main card using shadcn Card */}
        <Card className="w-full bg-card border-border/80 rounded-xl shadow-xs transition-all duration-200">
          <CardContent className="p-5 sm:p-7">
          {currentStep === 1 && (
            <Step1Identity
              ageRange={ageRange}
              setAgeRange={setAgeRange}
              familySituation={familySituation}
              setFamilySituation={setFamilySituation}
              investmentExperience={investmentExperience}
              setInvestmentExperience={setInvestmentExperience}
              businessModelsUnderstanding={businessModelsUnderstanding}
              setBusinessModelsUnderstanding={setBusinessModelsUnderstanding}
            />
          )}

          {currentStep === 2 && (
            <Step2FinancialGoals
              primaryObjective={primaryObjective}
              setPrimaryObjective={setPrimaryObjective}
              firstWithdrawalHorizon={firstWithdrawalHorizon}
              setFirstWithdrawalHorizon={setFirstWithdrawalHorizon}
              withdrawalMethod={withdrawalMethod}
              setWithdrawalMethod={setWithdrawalMethod}
              simulatedCapital={simulatedCapital}
              setSimulatedCapital={setSimulatedCapital}
              accountType={accountType}
              setAccountType={setAccountType}
              netWorthShare={netWorthShare}
              setNetWorthShare={setNetWorthShare}
            />
          )}

          {currentStep === 3 && (
            <Step3RiskTolerance
              riskTolerance={riskTolerance}
              setRiskTolerance={setRiskTolerance}
              maxLossTolerance={maxLossTolerance}
              setMaxLossTolerance={setMaxLossTolerance}
              sectorConcentrationLimit={sectorConcentrationLimit}
              setSectorConcentrationLimit={setSectorConcentrationLimit}
              capitalNeedNext12Months={capitalNeedNext12Months}
              setCapitalNeedNext12Months={setCapitalNeedNext12Months}
              essentialExpensesImpact={essentialExpensesImpact}
              setEssentialExpensesImpact={setEssentialExpensesImpact}
              debtLevel={debtLevel}
              setDebtLevel={setDebtLevel}
              incomeStability={incomeStability}
              setIncomeStability={setIncomeStability}
              simulatedCapital={simulatedCapital}
            />
          )}

          {currentStep === 4 && (
            <Step4Preferences
              interestedSectors={interestedSectors}
              setInterestedSectors={setInterestedSectors}
              cryptoPreference={cryptoPreference}
              setCryptoPreference={setCryptoPreference}
              esgImportance={esgImportance}
              setEsgImportance={setEsgImportance}
              excludedCategories={excludedCategories}
              setExcludedCategories={setExcludedCategories}
              currencyPreference={currencyPreference}
              setCurrencyPreference={setCurrencyPreference}
            />
          )}

          {currentStep === 5 && (
            <Step5AdditionalInfo
              additionalNotes={additionalNotes}
              setAdditionalNotes={setAdditionalNotes}
              currentHoldingsCsv={currentHoldingsCsv}
              setCurrentHoldingsCsv={setCurrentHoldingsCsv}
              setCurrentHoldings={setCurrentHoldings}
              fictionalCapitalAcknowledged={fictionalCapitalAcknowledged}
              setFictionalCapitalAcknowledged={setFictionalCapitalAcknowledged}
              onSave={handleSave}
              onPrev={() => setCurrentStep(4)}
            />
          )}
        </CardContent>
      </Card>

      {/* Outside Buttons for Steps 1-4 */}
      {currentStep < 5 && (
        <div className="mt-5 flex flex-col items-center gap-2">
          <div className="flex items-center justify-center gap-2.5">
            {currentStep > 1 && (
              <Button
                type="button"
                variant="outline"
                onClick={() => setCurrentStep((s) => s - 1)}
                className="px-5 h-10 text-xs sm:text-sm font-medium cursor-pointer"
              >
                ← Retour
              </Button>
            )}
            <Button
              type="button"
              disabled={!isCurrentStepValid}
              onClick={() => {
                if (isCurrentStepValid) setCurrentStep((s) => s + 1);
              }}
              className="px-6 h-10 text-xs sm:text-sm font-medium cursor-pointer"
            >
              Continuer →
            </Button>
          </div>
          {!isCurrentStepValid && (
            <p className="text-[11px] text-muted-foreground/75 text-center">
              Veuillez répondre à toutes les questions obligatoires (*) pour continuer
            </p>
          )}
        </div>
      )}
      </div>

      {/* Discrete uniform footer disclaimer */}
      <footer className="w-full max-w-4xl mx-auto pt-6 text-center text-[11px] text-muted-foreground border-t border-border/40 select-none">
        Simulation éducative · Aucun conseil réglementé · Les performances passées ne garantissent pas les résultats futurs
      </footer>
    </div>
  );
};
