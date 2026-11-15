import React from 'react';
import { AlertCircle } from 'lucide-react';

interface ConflictsAlertProps {
  conflicts: string[];
}

export const ConflictsAlert: React.FC<ConflictsAlertProps> = ({ conflicts }) => {
  if (!conflicts || conflicts.length === 0) return null;

  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 mb-6 text-amber-950 dark:text-amber-200 shadow-xs">
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <div>
          <h3 className="text-sm font-semibold mb-1 text-amber-950 dark:text-amber-100">
            Conflit ou incohérence détecté dans la demande
          </h3>
          <ul className="text-xs space-y-1 list-disc list-inside text-amber-900 dark:text-amber-200">
            {conflicts.map((c, idx) => (
              <li key={idx}>{c}</li>
            ))}
          </ul>
          <p className="text-[11px] text-amber-800 dark:text-amber-300/80 mt-2">
            L&apos;analyse s&apos;est poursuivie en comparant votre idée brute à un scénario plafonné selon vos contraintes.
          </p>
        </div>
      </div>
    </div>
  );
};
