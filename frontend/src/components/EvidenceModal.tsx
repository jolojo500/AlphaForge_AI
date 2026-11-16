import React from 'react';
import { Evidence } from '../types';
import { ConfidenceBadge } from './ConfidenceBadge';
import { ExternalLink, Calendar, Database, Cpu } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useLanguage } from '@/context/LanguageContext';
import { evidenceLabel } from '@/lib/evidenceText';
import { dateKindLabel, methodLabel } from '@/lib/labels';
import { fmtPct } from '@/lib/format';

interface EvidenceModalProps {
  evidence: Evidence | null;
  onClose: () => void;
}

export const EvidenceModal: React.FC<EvidenceModalProps> = ({ evidence, onClose }) => {
  const { language } = useLanguage();
  const isEn = language === 'en';
  if (!evidence) return null;

  const renderValue = (val: unknown) => {
    if (typeof val === 'object' && val !== null) {
      return (
        <pre className="text-xs bg-muted text-foreground p-3 rounded-lg overflow-x-auto max-w-full font-mono border border-border whitespace-pre">
          {JSON.stringify(val, null, 2)}
        </pre>
      );
    }
    if (typeof val === 'number') {
      return (
        <span className="font-mono text-base font-bold text-foreground">
          {val.toLocaleString(isEn ? 'en-CA' : 'fr-CA', { maximumFractionDigits: 4 })}
          {Math.abs(val) <= 1.0 ? ` (${fmtPct(val, language, 2)})` : ''}
        </span>
      );
    }
    return <span className="font-mono text-sm text-foreground break-words">{String(val)}</span>;
  };

  return (
    <Dialog open={Boolean(evidence)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg w-full min-w-0 overflow-hidden">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="font-mono font-bold text-xs bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30">
              {evidence.id}
            </Badge>
            <ConfidenceBadge confidence={evidence.confidence} />
          </div>
          <DialogTitle className="text-sm font-semibold pt-1">{evidenceLabel(evidence, language)}</DialogTitle>
        </DialogHeader>

        {/* Content Body */}
        <div className="space-y-4 pt-1 min-w-0 max-w-full">
          <div className="min-w-0 max-w-full">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
              {isEn ? 'Observed or computed value' : 'Valeur observée ou calculée'}
            </h4>
            <div className="p-3 bg-muted/40 rounded-xl border border-border/60 min-w-0 max-w-full overflow-hidden">
              {renderValue(evidence.value)}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs min-w-0">
            <div className="flex items-start gap-2 bg-muted/40 p-2.5 rounded-xl border border-border/60 min-w-0 overflow-hidden">
              <Database className="w-4 h-4 text-muted-foreground mt-0.5 shrink-0" aria-hidden="true" />
              <div className="min-w-0 overflow-hidden">
                <span className="text-muted-foreground block text-[11px]">Source</span>
                <span className="font-medium text-foreground break-all">{evidence.source}</span>
              </div>
            </div>

            <div className="flex items-start gap-2 bg-muted/40 p-2.5 rounded-xl border border-border/60 min-w-0 overflow-hidden">
              <Calendar className="w-4 h-4 text-muted-foreground mt-0.5 shrink-0" aria-hidden="true" />
              <div className="min-w-0">
                <span className="text-muted-foreground block text-[11px]">Date ({dateKindLabel(evidence.date_kind, language)})</span>
                <span className="font-medium text-foreground">{evidence.date}</span>
              </div>
            </div>
          </div>

          <div className="min-w-0">
            <div className="flex items-center gap-1 text-xs text-muted-foreground font-semibold uppercase tracking-wider mb-1">
              <Cpu className="w-3.5 h-3.5" aria-hidden="true" />
              <span>{isEn ? 'How it was computed' : 'Comment ce chiffre a été calculé'}</span>
            </div>
            <p className="text-xs text-foreground bg-muted/40 p-3 rounded-xl border border-border/60 leading-relaxed break-words">
              {methodLabel(evidence.method, language)}
            </p>
          </div>

          {evidence.url && (
            <div>
              <a
                href={evidence.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-blue-500 hover:text-blue-600 dark:text-blue-400 hover:underline font-medium"
              >
                <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                <span>{isEn ? 'Open the external source' : 'Ouvrir la source externe'}</span>
              </a>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="pt-3 border-t border-border/60 flex justify-end">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onClose}
            className="text-xs"
          >
            {isEn ? 'Close' : 'Fermer'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
