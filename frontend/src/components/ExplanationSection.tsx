import React from 'react';
import { Explanation, Verification, Evidence } from '../types';
import { EvidenceChip } from './EvidenceChip';
import {
  FileText,
  ShieldCheck,
  ShieldAlert,
  HelpCircle,
  TrendingUp,
  AlertTriangle,
  RefreshCw,
  Info,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useLanguage } from '@/context/LanguageContext';

interface ExplanationSectionProps {
  explanation: Explanation | null;
  verification: Verification | null;
  evidence: Record<string, Evidence>;
  onSelectEvidence: (eid: string) => void;
}

export const ExplanationSection: React.FC<ExplanationSectionProps> = ({
  explanation,
  verification,
  evidence,
  onSelectEvidence,
}) => {
  const { language, t } = useLanguage();
  const isEn = language === 'en';

  // If verification failed explicitly, show the failure panel instead of explanation
  if (verification && verification.passed === false) {
    return (
      <Card className="bg-red-500/10 border-2 border-red-500/40 rounded-2xl p-6 mb-6 shadow-sm">
        <div className="flex items-start gap-3">
          <ShieldAlert className="w-6 h-6 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <div>
            <h2 className="text-base font-bold text-red-950 dark:text-red-200 mb-1">
              {t('explain.verification_failed', 'Échec du vérificateur formel déterministe')}
            </h2>
            <p className="text-xs text-red-900 dark:text-red-300 mb-3">
              {t(
                'explain.verification_failed_desc',
                "L'explication générée par le modèle a été rejetée car elle ne satisfait pas aux critères stricts d'intégrité numérique ou de conformité (non-conseil)."
              )}
            </p>
            <div className="bg-background/80 rounded-xl p-3 border border-red-500/30">
              <span className="text-xs font-semibold text-red-950 dark:text-red-200 block mb-1">
                {isEn ? `Identified Errors (${verification.errors.length}):` : `Erreurs identifiées (${verification.errors.length}) :`}
              </span>
              <ul className="text-xs text-red-900 dark:text-red-300 space-y-1 list-disc list-inside">
                {verification.errors.map((err, idx) => (
                  <li key={idx} className="font-mono">{err}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </Card>
    );
  }

  if (!explanation) return null;

  return (
    <Card className="bg-card border-border shadow-sm mb-6">
      <CardContent className="p-5 sm:p-6">
        {/* Verification passed badge & Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3.5 mb-4 border-b border-border/60 gap-2">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary" />
            <h2 className="text-sm sm:text-base font-semibold text-foreground">
              {t('explain.title', 'Explicabilité & Gouvernance (Les 4 piliers BNCD)')}
            </h2>
          </div>

          {verification?.passed && (
            <Badge variant="outline" className="gap-1 border-emerald-500/40 text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 text-[11px] py-0.5">
              <ShieldCheck className="w-3 h-3 text-emerald-500" />
              {t('explain.verification_passed', 'Vérification formelle réussie')}
            </Badge>
          )}
        </div>

        {/* Résumé */}
        {explanation.resume && (
          <div className="bg-sky-500/10 border border-sky-500/20 rounded-lg p-3 mb-5 text-xs text-foreground leading-relaxed">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-sky-800 dark:text-sky-300 block mb-0.5">
              {t('explain.summary', "Synthèse de l'analyse :")}
            </span>
            <p>{explanation.resume}</p>
          </div>
        )}

        {/* The 4 Questions Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Question 1: Quelles données ? */}
          <div className="bg-muted/40 rounded-xl p-4 border border-border/60">
            <div className="flex items-center gap-2 mb-2 text-foreground font-semibold text-sm">
              <HelpCircle className="w-4 h-4 text-blue-500" />
              <h3>{t('explain.what_data', '1. Quelles données avons-nous utilisées ?')}</h3>
            </div>
            <p className="text-xs text-muted-foreground mb-3">
              {t('explain.what_data_sub', 'Séries de prix historiques ajustées, macroéconomie et actualités datées.')}
            </p>
            <ul className="space-y-2 text-xs text-foreground">
              {explanation.quelles_donnees?.map((item, idx) => (
                <li key={idx} className="bg-card p-3 rounded-lg border border-border/70 shadow-2xs">
                  <p className="mb-1 text-foreground leading-snug">{item.claim}</p>
                  <div className="flex flex-wrap items-center mt-1">
                    {item.evidence?.map((eid) => (
                      <EvidenceChip
                        key={eid}
                        id={eid}
                        onClick={onSelectEvidence}
                        confidence={evidence[eid]?.confidence}
                      />
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* Question 2: Pourquoi ce choix ? */}
          <div className="bg-muted/40 rounded-xl p-4 border border-border/60">
            <div className="flex items-center gap-2 mb-2 text-foreground font-semibold text-sm">
              <TrendingUp className="w-4 h-4 text-emerald-500" />
              <h3>{t('explain.why_choice', '2. Pourquoi ce choix ?')}</h3>
            </div>
            <p className="text-xs text-muted-foreground mb-3">
              {t('explain.why_choice_sub', 'Cohérence avec les objectifs, la tolérance et la capacité déclarées.')}
            </p>
            <ul className="space-y-2 text-xs text-foreground">
              {explanation.pourquoi_ce_choix?.map((item, idx) => (
                <li key={idx} className="bg-card p-3 rounded-lg border border-border/70 shadow-2xs">
                  <p className="mb-1 text-foreground leading-snug">{item.claim}</p>
                  <div className="flex flex-wrap items-center mt-1">
                    {item.evidence?.map((eid) => (
                      <EvidenceChip
                        key={eid}
                        id={eid}
                        onClick={onSelectEvidence}
                        confidence={evidence[eid]?.confidence}
                      />
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* Question 3: Quelles sont les limites ? */}
          <div className="bg-muted/40 rounded-xl p-4 border border-border/60">
            <div className="flex items-center gap-2 mb-2 text-foreground font-semibold text-sm">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              <h3>{t('explain.limits', '3. Quelles sont les limites ?')}</h3>
            </div>
            <p className="text-xs text-muted-foreground mb-3">
              {t('explain.limits_sub', 'Biais de survie, modèles rétrospectifs et hypothèses de distribution.')}
            </p>
            <ul className="space-y-2 text-xs text-foreground">
              {explanation.limites?.map((item, idx) => (
                <li key={idx} className="bg-card p-3 rounded-lg border border-border/70 shadow-2xs">
                  <p className="mb-1 text-foreground leading-snug">{item.claim}</p>
                  <div className="flex flex-wrap items-center mt-1">
                    {item.evidence?.map((eid) => (
                      <EvidenceChip
                        key={eid}
                        id={eid}
                        onClick={onSelectEvidence}
                        confidence={evidence[eid]?.confidence}
                      />
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* Question 4: Qu'est-ce qui changerait la réponse ? */}
          <div className="bg-muted/40 rounded-xl p-4 border border-border/60">
            <div className="flex items-center gap-2 mb-2 text-foreground font-semibold text-sm">
              <RefreshCw className="w-4 h-4 text-indigo-500" />
              <h3>{t('explain.what_change', "4. Qu'est-ce qui changerait la réponse ?")}</h3>
            </div>
            <p className="text-xs text-muted-foreground mb-3">
              {t('explain.what_change_sub', "Sensibilité de l'allocation aux variations d'horizon ou de contraintes.")}
            </p>
            <ul className="space-y-2 text-xs text-foreground">
              {explanation.ce_qui_changerait_la_reponse?.map((item, idx) => (
                <li key={idx} className="bg-card p-3 rounded-lg border border-border/70 shadow-2xs">
                  <p className="mb-1 text-foreground leading-snug">{item.claim}</p>
                  <div className="flex flex-wrap items-center mt-1">
                    {item.evidence?.map((eid) => (
                      <EvidenceChip
                        key={eid}
                        id={eid}
                        onClick={onSelectEvidence}
                        confidence={evidence[eid]?.confidence}
                      />
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Uncertainty & Disclaimer footer */}
        {explanation.incertitude && (
          <div className="mt-5 p-3 rounded-xl bg-muted/40 border border-border/60 flex items-start gap-2 text-xs text-muted-foreground">
            <Info className="w-4 h-4 text-muted-foreground/80 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-foreground">
                {t('explain.uncertainty', 'Note sur l’incertitude :')}
              </span>{' '}
              {explanation.incertitude}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
