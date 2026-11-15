import React from 'react';
import { Exclusion, Evidence } from '../types';
import { EvidenceChip } from './EvidenceChip';
import { Ban, CheckCircle } from 'lucide-react';

interface ExclusionsCardProps {
  exclusions: Exclusion[];
  evidence: Record<string, Evidence>;
  onSelectEvidence: (eid: string) => void;
}

export const ExclusionsCard: React.FC<ExclusionsCardProps> = ({
  exclusions,
  evidence,
  onSelectEvidence,
}) => {
  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <div className="flex items-center gap-2 mb-4">
        <Ban className="w-5 h-5 text-red-600" />
        <h2 className="text-lg font-semibold text-slate-800">
          Actifs exclus de l&apos;univers d&apos;investissement
        </h2>
      </div>

      {exclusions.length === 0 ? (
        <div className="flex items-center gap-2 p-3 bg-emerald-50 text-emerald-800 rounded-lg border border-emerald-200 text-xs">
          <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>
            Aucun actif exclu : l&apos;ensemble de l&apos;univers (31 actifs éligibles) respecte les contraintes déclarées.
          </span>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-600 uppercase border-b border-slate-200">
              <tr>
                <th className="py-2.5 px-3 font-semibold">Actif</th>
                <th className="py-2.5 px-3 font-semibold">Motif d&apos;exclusion</th>
                <th className="py-2.5 px-3 font-semibold">Preuve</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {exclusions.map((ex, idx) => (
                <tr key={`${ex.ticker}-${idx}`} className="hover:bg-slate-50/70 transition-colors">
                  <td className="py-2.5 px-3 font-mono font-bold text-red-600">{ex.ticker}</td>
                  <td className="py-2.5 px-3 text-slate-700">{ex.reason}</td>
                  <td className="py-2.5 px-3">
                    <EvidenceChip
                      id={ex.evidence_id}
                      onClick={onSelectEvidence}
                      confidence={evidence[ex.evidence_id]?.confidence}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
