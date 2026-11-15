import React, { useState } from 'react';
import { HelpCircle, Send } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useLanguage } from '@/context/LanguageContext';

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
  const { t } = useLanguage();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!answer.trim() || isSubmitting) return;
    onAnswer(answer.trim());
  };

  return (
    <Card className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 sm:p-5 mb-5 shadow-xs">
      <CardContent className="p-0">
        <div className="flex items-start gap-2.5">
          <HelpCircle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-amber-950 dark:text-amber-100 mb-1">
              {t('clarification.title', "Précision requise pour poursuivre l'analyse")}
            </h2>
            <p className="text-xs sm:text-sm text-foreground mb-3 bg-background/80 p-2.5 rounded-lg border border-amber-500/20 leading-relaxed">
              {question}
            </p>

            <form onSubmit={handleSubmit} className="space-y-2.5">
              <label htmlFor="clarification-input" className="block text-[11px] font-medium text-amber-900/80 dark:text-amber-200/80">
                {t('clarification.label', 'Votre réponse :')}
              </label>
              <Input
                id="clarification-input"
                type="text"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                disabled={isSubmitting}
                placeholder={t('clarification.placeholder', 'Précisez votre choix ou votre objectif...')}
                className="w-full text-xs sm:text-sm"
              />
              <div className="flex justify-end pt-0.5">
                <Button
                  type="submit"
                  size="sm"
                  disabled={!answer.trim() || isSubmitting}
                  className="gap-1.5 h-8 text-xs font-medium"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>{isSubmitting ? t('clarification.sending', 'Envoi...') : t('clarification.btn_send', 'Répondre et continuer')}</span>
                </Button>
              </div>
            </form>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
