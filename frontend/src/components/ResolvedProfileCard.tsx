import React from 'react';
import { Profile, BackendRunPayload } from '../types';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Target,
  Clock,
  ShieldAlert,
  ShieldCheck,
  Filter,
  Sparkles,
  DollarSign,
  User,
  SlidersHorizontal,
} from 'lucide-react';
import { useLanguage } from '@/context/LanguageContext';

interface ResolvedProfileCardProps {
  profile: Profile | null;
  payloadData?: BackendRunPayload['profile_data'];
  persona?: string;
}

const OBJECTIVE_LABELS_FR: Record<string, string> = {
  growth: 'Croissance du capital',
  balanced: 'Équilibré & responsable',
  capital_preservation: 'Préservation du capital',
  income: 'Revenus réguliers',
};

const OBJECTIVE_LABELS_EN: Record<string, string> = {
  growth: 'Capital Growth',
  balanced: 'Balanced & Responsible',
  capital_preservation: 'Capital Preservation',
  income: 'Regular Income',
};

const TOLERANCE_LABELS_FR: Record<string, string> = {
  high: 'Élevée',
  moderate: 'Modérée',
  low_moderate: 'Faible à modérée',
  low: 'Faible',
};

const TOLERANCE_LABELS_EN: Record<string, string> = {
  high: 'High',
  moderate: 'Moderate',
  low_moderate: 'Low to Moderate',
  low: 'Low',
};

const CAPACITY_LABELS_FR: Record<string, string> = {
  high: 'Élevée',
  moderate: 'Modérée',
  low: 'Faible',
};

const CAPACITY_LABELS_EN: Record<string, string> = {
  high: 'High',
  moderate: 'Moderate',
  low: 'Low',
};

const CONSTRAINT_LABELS_FR: Record<string, string> = {
  no_crypto: 'Exclusion crypto',
  esg_only: 'Filtre ESG strict',
  no_controversies: 'Sans controverses',
};

const CONSTRAINT_LABELS_EN: Record<string, string> = {
  no_crypto: 'Crypto Exclusion',
  esg_only: 'Strict ESG Filter',
  no_controversies: 'No Controversies',
};

const PREFERENCE_LABELS_FR: Record<string, string> = {
  likes_tech: 'Technologies & IA',
  likes_crypto: 'Cryptoactifs',
  wants_diversification: 'Diversification',
  wants_balance: 'Équilibre',
};

const PREFERENCE_LABELS_EN: Record<string, string> = {
  likes_tech: 'Tech & AI',
  likes_crypto: 'Cryptoassets',
  wants_diversification: 'Diversification',
  wants_balance: 'Balance',
};

const ACCOUNT_TYPE_LABELS_FR: Record<string, string> = {
  tfsa: "CELI (Libre d'impôt)",
  rrsp: "REER (Épargne-retraite)",
  fhsa: "CELIAPP (Première propriété)",
  non_registered: "Non enregistré (Imposable)",
  mixed: "Portefeuille mixte",
};

const ACCOUNT_TYPE_LABELS_EN: Record<string, string> = {
  tfsa: 'TFSA (Tax-Free)',
  rrsp: 'RRSP (Retirement)',
  fhsa: 'FHSA (First Home)',
  non_registered: 'Non-Registered (Taxable)',
  mixed: 'Mixed Portfolio',
};

const PERSONA_NAMES_FR: Record<string, string> = {
  amira: 'Amira, 26 ans',
  mateo: 'Mateo, 41 ans',
  robert: 'Robert, 59 ans',
};

const PERSONA_NAMES_EN: Record<string, string> = {
  amira: 'Amira, 26 yo',
  mateo: 'Mateo, 41 yo',
  robert: 'Robert, 59 yo',
};

export const ResolvedProfileCard: React.FC<ResolvedProfileCardProps> = ({
  profile,
  payloadData,
  persona,
}) => {
  const { language } = useLanguage();
  const isEn = language === 'en';

  if (!profile && !payloadData && !persona) return null;

  const objectiveLabels = isEn ? OBJECTIVE_LABELS_EN : OBJECTIVE_LABELS_FR;
  const toleranceLabels = isEn ? TOLERANCE_LABELS_EN : TOLERANCE_LABELS_FR;
  const capacityLabels = isEn ? CAPACITY_LABELS_EN : CAPACITY_LABELS_FR;
  const constraintLabels = isEn ? CONSTRAINT_LABELS_EN : CONSTRAINT_LABELS_FR;
  const preferenceLabels = isEn ? PREFERENCE_LABELS_EN : PREFERENCE_LABELS_FR;
  const accountTypeLabels = isEn ? ACCOUNT_TYPE_LABELS_EN : ACCOUNT_TYPE_LABELS_FR;
  const personaNames = isEn ? PERSONA_NAMES_EN : PERSONA_NAMES_FR;

  const rawObjective = profile?.objective || payloadData?.objective || 'balanced';
  const objective = objectiveLabels[rawObjective] || rawObjective;

  const horizonYears = profile?.horizon_years ?? payloadData?.horizon_years ?? 5;

  const rawTolerance = profile?.risk_tolerance || payloadData?.risk_tolerance || 'moderate';
  const tolerance = toleranceLabels[rawTolerance] || rawTolerance;

  const rawCapacity = profile?.risk_capacity || payloadData?.risk_capacity || 'moderate';
  const capacity = capacityLabels[rawCapacity] || rawCapacity;

  const rawAccountType = profile?.account_type || payloadData?.account_type || 'non_registered';
  const accountTypeDisplay = accountTypeLabels[rawAccountType] || rawAccountType;

  const constraints = profile?.constraints || payloadData?.constraints || [];
  const preferences = profile?.preferences || payloadData?.preferences || [];

  const budget = profile?.budget_cad ?? payloadData?.budget_cad;
  const requestedIdea = profile?.requested_idea;

  const personaKey = persona || (profile?.persona as string) || '';
  const personaDisplay =
    personaNames[personaKey] ||
    (personaKey.startsWith('custom_')
      ? (isEn ? 'Custom Profile' : 'Profil personnalisé')
      : personaKey || (isEn ? 'Investor Profile' : 'Profil investisseur'));

  const isResolved = Boolean(profile);

  return (
    <Card className="shadow-xs border-border bg-card">
      <CardContent className="p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 pb-3 mb-3 border-b border-border/70">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
              <SlidersHorizontal className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground">
                  {isEn
                    ? `Investor Profile Hypotheses (${isResolved ? 'Resolved' : 'Submitted'})`
                    : `Hypothèses du profil ${isResolved ? 'résolu' : 'transmis'}`}
                </h3>
                <Badge
                  variant={isResolved ? 'secondary' : 'outline'}
                  className="text-[10px] py-0 px-2 font-normal"
                >
                  {isResolved
                    ? (isEn ? 'Verified by Agent 1' : 'Vérifié par Agent 1')
                    : (isEn ? 'In Progress' : 'En cours')}
                </Badge>
                {profile?.kyc_completeness && (
                  <Badge
                    variant="outline"
                    className={`text-[10px] py-0 px-2 font-normal ${
                      profile.kyc_completeness.is_complete
                        ? 'border-emerald-500/40 text-emerald-700 dark:text-emerald-300 bg-emerald-500/10'
                        : 'border-amber-500/40 text-amber-700 dark:text-amber-300 bg-amber-500/10'
                    }`}
                  >
                    KYC {Math.round(profile.kyc_completeness.score * 100)} %
                    {(() => {
                      const hypCount = Object.values(profile.kyc_completeness?.fields || {}).filter(
                        (f) => f.source === 'assumption'
                      ).length;
                      return hypCount > 0 ? ` (${hypCount} hyp.)` : '';
                    })()}
                  </Badge>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                {isEn
                  ? 'Investor inputs powering analysis, universe screening, and scenario calibration.'
                  : "Paramètres investisseur alimentant l'analyse, les filtres et le calibrage des scénarios."}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[11px] font-normal border-primary/30 text-primary">
              {accountTypeDisplay}
            </Badge>
            <div className="flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="text-xs font-medium text-foreground">{personaDisplay}</span>
            </div>
          </div>
        </div>

        {/* 4-column Key Parameters Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
          {/* Objectif */}
          <div className="bg-muted/30 rounded-lg p-2.5 border border-border/50">
            <div className="flex items-center gap-1.5 text-muted-foreground mb-1">
              <Target className="w-3.5 h-3.5 text-primary shrink-0" />
              <span className="text-[11px] font-medium">{isEn ? 'Objective' : 'Objectif'}</span>
            </div>
            <span className="font-semibold text-foreground block truncate" title={objective}>
              {objective}
            </span>
          </div>

          {/* Horizon */}
          <div className="bg-muted/30 rounded-lg p-2.5 border border-border/50">
            <div className="flex items-center gap-1.5 text-muted-foreground mb-1">
              <Clock className="w-3.5 h-3.5 text-blue-500 shrink-0" />
              <span className="text-[11px] font-medium">{isEn ? 'Horizon' : 'Horizon'}</span>
            </div>
            <span className="font-semibold text-foreground block">
              {horizonYears} {isEn ? (horizonYears > 1 ? 'years' : 'year') : (horizonYears > 1 ? 'ans' : 'an')}
            </span>
          </div>

          {/* Tolérance au risque */}
          <div className="bg-muted/30 rounded-lg p-2.5 border border-border/50">
            <div className="flex items-center gap-1.5 text-muted-foreground mb-1">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-500 shrink-0" />
              <span className="text-[11px] font-medium">{isEn ? 'Tolerance' : 'Tolérance'}</span>
            </div>
            <span className="font-semibold text-foreground block">{tolerance}</span>
          </div>

          {/* Capacité financière */}
          <div className="bg-muted/30 rounded-lg p-2.5 border border-border/50">
            <div className="flex items-center gap-1.5 text-muted-foreground mb-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
              <span className="text-[11px] font-medium">{isEn ? 'Capacity' : 'Capacité'}</span>
            </div>
            <span className="font-semibold text-foreground block">{capacity}</span>
          </div>
        </div>

        {/* Constraints, Preferences & Idea Details */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-2 border-t border-border/40 text-xs">
          {/* Contraintes */}
          <div className="flex items-start gap-2">
            <div className="flex items-center gap-1 text-muted-foreground mt-0.5 shrink-0">
              <Filter className="w-3 h-3" />
              <span className="text-[11px] font-medium">{isEn ? 'Constraints:' : 'Contraintes :'}</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {constraints.length > 0 ? (
                constraints.map((c) => (
                  <Badge
                    key={c}
                    variant="outline"
                    className="text-[10px] py-0 px-1.5 bg-muted/40 font-normal"
                  >
                    {constraintLabels[c] || c}
                  </Badge>
                ))
              ) : (
                <span className="text-muted-foreground text-[11px]">
                  {isEn ? 'No strict constraint' : 'Aucune contrainte stricte'}
                </span>
              )}
            </div>
          </div>

          {/* Préférences */}
          <div className="flex items-start gap-2">
            <div className="flex items-center gap-1 text-muted-foreground mt-0.5 shrink-0">
              <Sparkles className="w-3 h-3 text-amber-500" />
              <span className="text-[11px] font-medium">{isEn ? 'Preferences:' : 'Préférences :'}</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {preferences.length > 0 ? (
                preferences.map((p) => (
                  <Badge
                    key={p}
                    variant="secondary"
                    className="text-[10px] py-0 px-1.5 font-normal"
                  >
                    {preferenceLabels[p] || p}
                  </Badge>
                ))
              ) : (
                <span className="text-muted-foreground text-[11px]">
                  {isEn ? 'Neutral' : 'Neutre'}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Optional Budget & Evaluated Idea bar */}
        {(budget != null || requestedIdea || profile?.has_emergency_fund !== undefined || profile?.debt_level) && (
          <div className="flex flex-wrap items-center gap-3 mt-2.5 pt-2 border-t border-border/30 text-[11px] text-muted-foreground">
            {budget != null && (
              <div className="flex items-center gap-1">
                <DollarSign className="w-3 h-3 text-emerald-600" />
                <span>
                  {isEn ? 'Simulated Budget: ' : 'Budget simulé : '}
                  <strong className="text-foreground font-medium">
                    {budget.toLocaleString(isEn ? 'en-CA' : 'fr-CA')} $ CAD
                  </strong>
                </span>
              </div>
            )}
            {requestedIdea && (
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                <span>
                  {isEn ? 'Requested Idea: ' : 'Idée demandée : '}
                  <strong className="text-foreground font-medium">
                    {requestedIdea.ticker} ({Math.round(requestedIdea.weight * 100)} %)
                  </strong>
                </span>
              </div>
            )}
            {profile?.has_emergency_fund !== undefined && (
              <div className="flex items-center gap-1">
                <span className={`w-1.5 h-1.5 rounded-full ${profile.has_emergency_fund ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                <span>
                  Fonds d&apos;urgence :{' '}
                  <strong className="text-foreground font-medium">
                    {profile.has_emergency_fund ? 'Constitué' : 'Non constitué'}
                  </strong>
                </span>
              </div>
            )}
            {profile?.debt_level && (
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                <span>
                  Dettes :{' '}
                  <strong className="text-foreground font-medium">
                    {profile.debt_level}
                  </strong>
                </span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};
