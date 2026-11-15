import React from 'react';
import { AlertCircle, Info } from 'lucide-react';
import { useLanguage } from '@/context/LanguageContext';

interface ConflictsAlertProps {
  conflicts: string[];
}

export const ConflictsAlert: React.FC<ConflictsAlertProps> = ({ conflicts }) => {
  const { t, language } = useLanguage();
  const isEn = language === 'en';
  if (!conflicts || conflicts.length === 0) return null;

  const realConflicts = conflicts.filter(
    (c) => !c.toLowerCase().startsWith('hypothèse') && !c.toLowerCase().startsWith('assumption')
  );
  const assumptions = conflicts.filter(
    (c) => c.toLowerCase().startsWith('hypothèse') || c.toLowerCase().startsWith('assumption')
  );

  return (
    <div className="space-y-3 mb-6">
      {/* Real Conflicts / Inconsistencies */}
      {realConflicts.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 text-amber-950 dark:text-amber-200 shadow-xs">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-semibold mb-1 text-amber-950 dark:text-amber-100">
                {t('conflicts.title', 'Conflit ou incohérence détecté dans la demande')}
              </h3>
              <ul className="text-xs space-y-1 list-disc list-inside text-amber-900 dark:text-amber-200">
                {realConflicts.map((c, idx) => (
                  <li key={idx}>{c}</li>
                ))}
              </ul>
              <p className="text-[11px] text-amber-800 dark:text-amber-300/80 mt-2">
                {t(
                  'conflicts.sub',
                  "L'analyse s'est poursuivie en comparant votre idée brute à un scénario plafonné selon vos contraintes."
                )}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Reading Assumptions */}
      {assumptions.length > 0 && (
        <div className="bg-sky-500/10 border border-sky-500/20 rounded-xl p-3 text-sky-950 dark:text-sky-200 shadow-xs">
          <div className="flex items-start gap-2.5">
            <Info className="w-4 h-4 text-sky-600 dark:text-sky-400 shrink-0 mt-0.5" />
            <div className="text-xs space-y-0.5">
              <span className="font-semibold block text-[11px] uppercase tracking-wider text-sky-800 dark:text-sky-300">
                {isEn ? 'Reading Assumption' : 'Hypothèse de lecture'}
              </span>
              {assumptions.map((a, idx) => (
                <p key={idx} className="leading-relaxed text-foreground/90">{a}</p>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
