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

interface ResolvedProfileCardProps {
  profile: Profile | null;
  payloadData?: BackendRunPayload['profile_data'];
  persona?: string;
}

const OBJECTIVE_LABELS: Record<string, string> = {
  growth: 'Croissance du capital',
  balanced: 'Équilibré & responsable',
  capital_preservation: 'Préservation du capital',
  income: 'Revenus réguliers',
};

const TOLERANCE_LABELS: Record<string, string> = {
  high: 'Élevée',
  moderate: 'Modérée',
  low_moderate: 'Faible à modérée',
  low: 'Faible',
};

const CAPACITY_LABELS: Record<string, string> = {
  high: 'Élevée',
  moderate: 'Modérée',
  low: 'Faible',
};

const CONSTRAINT_LABELS: Record<string, string> = {
  no_crypto: 'Exclusion crypto',
  esg_only: 'Filtre ESG strict',
  no_controversies: 'Sans controverses',
};

const PREFERENCE_LABELS: Record<string, string> = {
  likes_tech: 'Technologies & IA',
  likes_crypto: 'Cryptoactifs',
  wants_diversification: 'Diversification',
  wants_balance: 'Équilibre',
};

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  tfsa: "CELI (Libre d'impôt)",
  rrsp: "REER (Épargne-retraite)",
  fhsa: "CELIAPP (Première propriété)",
  non_registered: "Non enregistré (Imposable)",
  mixed: "Portefeuille mixte",
};

const PERSONA_NAMES: Record<string, string> = {
  amira: 'Amira, 26 ans',
  mateo: 'Mateo, 41 ans',
  robert: 'Robert, 59 ans',
};

export const ResolvedProfileCard: React.FC<ResolvedProfileCardProps> = ({
  profile,
  payloadData,
  persona,
}) => {
  // If neither profile nor payloadData is available, do not render
  if (!profile && !payloadData && !persona) return null;

  const rawObjective = profile?.objective || payloadData?.objective || 'balanced';
  const objective = OBJECTIVE_LABELS[rawObjective] || rawObjective;

  const horizonYears = profile?.horizon_years ?? payloadData?.horizon_years ?? 5;

  const rawTolerance = profile?.risk_tolerance || payloadData?.risk_tolerance || 'moderate';
  const tolerance = TOLERANCE_LABELS[rawTolerance] || rawTolerance;

  const rawCapacity = profile?.risk_capacity || payloadData?.risk_capacity || 'moderate';
  const capacity = CAPACITY_LABELS[rawCapacity] || rawCapacity;

  const rawAccountType = profile?.account_type || payloadData?.account_type || 'non_registered';
  const accountTypeDisplay = ACCOUNT_TYPE_LABELS[rawAccountType] || rawAccountType;

  const constraints = profile?.constraints || payloadData?.constraints || [];
  const preferences = profile?.preferences || payloadData?.preferences || [];

  const budget = profile?.budget_cad ?? payloadData?.budget_cad;
  const requestedIdea = profile?.requested_idea;

  const personaKey = persona || (profile?.persona as string) || '';
  const personaDisplay =
    PERSONA_NAMES[personaKey] ||
    (personaKey.startsWith('custom_') ? 'Profil personnalisé' : personaKey || 'Profil investisseur');

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
                  Hypothèses du profil {isResolved ? 'résolu' : 'transmis'}
                </h3>
                <Badge
                  variant={isResolved ? 'secondary' : 'outline'}
                  className="text-[10px] py-0 px-2 font-normal"
                >
                  {isResolved ? 'Vérifié par Agent 1' : 'En cours'}
                </Badge>
              </div>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Paramètres investisseur alimentant l&apos;analyse, les filtres et le calibrage des scénarios.
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
              <span className="text-[11px] font-medium">Objectif</span>
            </div>
            <span className="font-semibold text-foreground block truncate" title={objective}>
              {objective}
            </span>
          </div>

          {/* Horizon */}
          <div className="bg-muted/30 rounded-lg p-2.5 border border-border/50">
            <div className="flex items-center gap-1.5 text-muted-foreground mb-1">
              <Clock className="w-3.5 h-3.5 text-blue-500 shrink-0" />
              <span className="text-[11px] font-medium">Horizon</span>
            </div>
            <span className="font-semibold text-foreground block">
              {horizonYears} {horizonYears > 1 ? 'ans' : 'an'}
            </span>
          </div>

          {/* Tolérance au risque */}
          <div className="bg-muted/30 rounded-lg p-2.5 border border-border/50">
            <div className="flex items-center gap-1.5 text-muted-foreground mb-1">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-500 shrink-0" />
              <span className="text-[11px] font-medium">Tolérance</span>
            </div>
            <span className="font-semibold text-foreground block">{tolerance}</span>
          </div>

          {/* Capacité financière */}
          <div className="bg-muted/30 rounded-lg p-2.5 border border-border/50">
            <div className="flex items-center gap-1.5 text-muted-foreground mb-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
              <span className="text-[11px] font-medium">Capacité</span>
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
              <span className="text-[11px] font-medium">Contraintes :</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {constraints.length > 0 ? (
                constraints.map((c) => (
                  <Badge
                    key={c}
                    variant="outline"
                    className="text-[10px] py-0 px-1.5 bg-muted/40 font-normal"
                  >
                    {CONSTRAINT_LABELS[c] || c}
                  </Badge>
                ))
              ) : (
                <span className="text-muted-foreground text-[11px]">Aucune contrainte stricte</span>
              )}
            </div>
          </div>

          {/* Préférences */}
          <div className="flex items-start gap-2">
            <div className="flex items-center gap-1 text-muted-foreground mt-0.5 shrink-0">
              <Sparkles className="w-3 h-3 text-amber-500" />
              <span className="text-[11px] font-medium">Préférences :</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {preferences.length > 0 ? (
                preferences.map((p) => (
                  <Badge
                    key={p}
                    variant="secondary"
                    className="text-[10px] py-0 px-1.5 font-normal"
                  >
                    {PREFERENCE_LABELS[p] || p}
                  </Badge>
                ))
              ) : (
                <span className="text-muted-foreground text-[11px]">Neutre</span>
              )}
            </div>
          </div>
        </div>

        {/* Optional Budget & Evaluated Idea bar */}
        {(budget != null || requestedIdea) && (
          <div className="flex flex-wrap items-center gap-3 mt-2.5 pt-2 border-t border-border/30 text-[11px] text-muted-foreground">
            {budget != null && (
              <div className="flex items-center gap-1">
                <DollarSign className="w-3 h-3 text-emerald-600" />
                <span>
                  Budget simulé :{' '}
                  <strong className="text-foreground font-medium">
                    {budget.toLocaleString('fr-CA')} $ CAD
                  </strong>
                </span>
              </div>
            )}
            {requestedIdea && (
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                <span>
                  Idée demandée :{' '}
                  <strong className="text-foreground font-medium">
                    {requestedIdea.ticker} ({Math.round(requestedIdea.weight * 100)} %)
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
