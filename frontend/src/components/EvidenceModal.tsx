import React from 'react';
import { Evidence } from '../types';
import { ConfidenceBadge } from './ConfidenceBadge';
import { X, ExternalLink, Calendar, Database, Cpu } from 'lucide-react';

interface EvidenceModalProps {
  evidence: Evidence | null;
  onClose: () => void;
}

export const EvidenceModal: React.FC<EvidenceModalProps> = ({ evidence, onClose }) => {
  if (!evidence) return null;

  const renderValue = (val: unknown) => {
    if (typeof val === 'object' && val !== null) {
      return (
        <pre className="text-xs bg-slate-900 text-slate-100 p-3 rounded-lg overflow-x-auto font-mono">
          {JSON.stringify(val, null, 2)}
        </pre>
      );
    }
    if (typeof val === 'number') {
      return (
        <span className="font-mono text-base font-bold text-slate-900">
          {val} {Math.abs(val) <= 1.0 ? `(${(val * 100).toFixed(2)} %)` : ''}
        </span>
      );
    }
    return <span className="font-mono text-sm text-slate-900">{String(val)}</span>;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs">
      <div
        className="bg-white rounded-xl shadow-xl max-w-lg w-full border border-slate-200 overflow-hidden transform transition-all"
        role="dialog"
        aria-modal="true"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50">
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-1 rounded bg-blue-100 text-blue-900 font-mono font-bold text-sm">
              {evidence.id}
            </span>
            <ConfidenceBadge confidence={evidence.confidence} />
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 rounded-lg p-1 transition-colors cursor-pointer"
            aria-label="Fermer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-4">
          <div>
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
              Valeur observée / calculée
            </h4>
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
              {renderValue(evidence.value)}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="flex items-start gap-2">
              <Database className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
              <div>
                <span className="text-slate-500 block">Source</span>
                <span className="font-medium text-slate-800 break-all">{evidence.source}</span>
              </div>
            </div>

            <div className="flex items-start gap-2">
              <Calendar className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
              <div>
                <span className="text-slate-500 block">Date ({evidence.date_kind})</span>
                <span className="font-medium text-slate-800">{evidence.date}</span>
              </div>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-1 text-xs text-slate-500 font-semibold uppercase tracking-wider mb-1">
              <Cpu className="w-3.5 h-3.5" />
              <span>Méthode de calcul & alignement</span>
            </div>
            <p className="text-xs text-slate-700 bg-slate-50 p-3 rounded-lg border border-slate-100 leading-relaxed">
              {evidence.method}
            </p>
          </div>

          {evidence.url && (
            <div>
              <a
                href={evidence.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 hover:underline font-medium"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Consulter la source externe</span>
              </a>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-slate-50 border-t border-slate-100 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-200 hover:bg-slate-300 text-slate-800 text-xs font-medium transition-colors cursor-pointer"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>
  );
};
