import React, { useState } from 'react';
import { HelpCircle, Send } from 'lucide-react';

interface ClarificationBoxProps {
  question: string;
  onAnswer: (text: string) => void;
  isSubmitting: boolean;
}

export const ClarificationBox: React.FC<ClarificationBoxProps> = ({
  question,
  onAnswer,
  isSubmitting,
}) => {
  const [answer, setAnswer] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!answer.trim() || isSubmitting) return;
    onAnswer(answer.trim());
  };

  return (
    <section className="bg-amber-50/70 border-2 border-amber-300 rounded-xl p-6 mb-6 shadow-sm">
      <div className="flex items-start gap-3">
        <HelpCircle className="w-6 h-6 text-amber-600 shrink-0 mt-0.5" />
        <div className="flex-1">
          <h2 className="text-base font-semibold text-amber-950 mb-1">
            Précision requise pour poursuivre l&apos;analyse
          </h2>
          <p className="text-sm text-amber-900 mb-4 bg-white/80 p-3 rounded-lg border border-amber-200">
            {question}
          </p>

          <form onSubmit={handleSubmit} className="space-y-3">
            <label htmlFor="clarification-input" className="block text-xs font-medium text-amber-900">
              Votre réponse :
            </label>
            <input
              id="clarification-input"
              type="text"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              disabled={isSubmitting}
              placeholder="Précisez votre choix ou votre objectif..."
              className="w-full px-3 py-2 border border-amber-300 rounded-lg text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={!answer.trim() || isSubmitting}
                className="inline-flex items-center gap-2 bg-amber-600 hover:bg-amber-700 text-white font-medium px-4 py-2 rounded-lg text-sm shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                {isSubmitting ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Envoi...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    <span>Répondre et continuer</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </section>
  );
};
