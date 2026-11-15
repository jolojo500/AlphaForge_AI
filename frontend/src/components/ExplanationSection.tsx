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
  // If verification failed explicitly, show the failure panel instead of explanation
  if (verification && verification.passed === false) {
    return (
      <section className="bg-red-50/90 border-2 border-red-400 rounded-xl p-6 mb-6 shadow-sm">
        <div className="flex items-start gap-3">
          <ShieldAlert className="w-6 h-6 text-red-600 shrink-0 mt-0.5" />
          <div>
            <h2 className="text-base font-bold text-red-950 mb-1">
              Échec du vérificateur formel déterministe
            </h2>
            <p className="text-xs text-red-900 mb-3">
              L&apos;explication générée par le modèle a été rejetée car elle ne satisfait pas aux critères stricts d&apos;intégrité numérique ou de conformité (non-conseil).
            </p>
            <div className="bg-white/80 rounded-lg p-3 border border-red-200">
              <span className="text-xs font-semibold text-red-950 block mb-1">
                Erreurs identifiées ({verification.errors.length}) :
              </span>
              <ul className="text-xs text-red-900 space-y-1 list-disc list-inside">
                {verification.errors.map((err, idx) => (
                  <li key={idx} className="font-mono">{err}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>
    );
  }

  if (!explanation) return null;

  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      {/* Verification passed badge & Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 mb-5 border-b border-slate-100 gap-2">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-blue-600" />
          <h2 className="text-lg font-semibold text-slate-800">
            4. Explicabilité de la décision (Les 4 questions BNCD)
          </h2>
        </div>

        {verification?.passed && (
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-800 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200 w-fit">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            Vérification formelle réussie (chiffres & conformité validés)
          </span>
        )}
      </div>

      {/* Résumé */}
      {explanation.resume && (
        <div className="bg-blue-50/50 border border-blue-100 rounded-lg p-4 mb-6 text-sm text-slate-800 leading-relaxed">
          <span className="text-xs font-bold uppercase tracking-wider text-blue-900 block mb-1">
            Synthèse de l&apos;analyse :
          </span>
          <p>{explanation.resume}</p>
        </div>
      )}

      {/* The 4 Questions Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Question 1: Quelles données ? */}
        <div className="bg-slate-50/60 rounded-xl p-4 border border-slate-100">
          <div className="flex items-center gap-2 mb-2 text-slate-900 font-semibold text-sm">
            <HelpCircle className="w-4 h-4 text-blue-600" />
            <h3>1. Quelles données avons-nous utilisées ?</h3>
          </div>
          <p className="text-xs text-slate-500 mb-3">
            Séries de prix historiques ajustées, macroéconomie et actualités datées.
          </p>
          <ul className="space-y-2 text-xs text-slate-700">
            {explanation.quelles_donnees?.map((item, idx) => (
              <li key={idx} className="bg-white p-2.5 rounded-lg border border-slate-100 shadow-2xs">
                <p className="mb-1">{item.claim}</p>
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
        <div className="bg-slate-50/60 rounded-xl p-4 border border-slate-100">
          <div className="flex items-center gap-2 mb-2 text-slate-900 font-semibold text-sm">
            <TrendingUp className="w-4 h-4 text-emerald-600" />
            <h3>2. Pourquoi ce choix ?</h3>
          </div>
          <p className="text-xs text-slate-500 mb-3">
            Cohérence avec les objectifs, la tolérance et la capacité déclarées.
          </p>
          <ul className="space-y-2 text-xs text-slate-700">
            {explanation.pourquoi_ce_choix?.map((item, idx) => (
              <li key={idx} className="bg-white p-2.5 rounded-lg border border-slate-100 shadow-2xs">
                <p className="mb-1">{item.claim}</p>
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
        <div className="bg-slate-50/60 rounded-xl p-4 border border-slate-100">
          <div className="flex items-center gap-2 mb-2 text-slate-900 font-semibold text-sm">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <h3>3. Quelles sont les limites ?</h3>
          </div>
          <p className="text-xs text-slate-500 mb-3">
            Biais de survie, modèles rétrospectifs et hypothèses de distribution.
          </p>
          <ul className="space-y-2 text-xs text-slate-700">
            {explanation.limites?.map((item, idx) => (
              <li key={idx} className="bg-white p-2.5 rounded-lg border border-slate-100 shadow-2xs">
                <p className="mb-1">{item.claim}</p>
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
        <div className="bg-slate-50/60 rounded-xl p-4 border border-slate-100">
          <div className="flex items-center gap-2 mb-2 text-slate-900 font-semibold text-sm">
            <RefreshCw className="w-4 h-4 text-indigo-600" />
            <h3>4. Qu&apos;est-ce qui changerait la réponse ?</h3>
          </div>
          <p className="text-xs text-slate-500 mb-3">
            Sensibilité de l&apos;allocation aux variations d&apos;horizon ou de contraintes.
          </p>
          <ul className="space-y-2 text-xs text-slate-700">
            {explanation.ce_qui_changerait_la_reponse?.map((item, idx) => (
              <li key={idx} className="bg-white p-2.5 rounded-lg border border-slate-100 shadow-2xs">
                <p className="mb-1">{item.claim}</p>
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
        <div className="mt-5 p-3 rounded-lg bg-slate-50 border border-slate-100 flex items-start gap-2 text-xs text-slate-600">
          <Info className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-slate-800">Incertitude déclarée :</span>{' '}
            {explanation.incertitude}
          </div>
        </div>
      )}
    </section>
  );
};
