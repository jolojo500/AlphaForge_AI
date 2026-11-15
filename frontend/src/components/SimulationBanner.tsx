import React from 'react';
import { ShieldAlert, ShieldCheck, FileDown } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface SimulationBannerProps {
  isReviewed?: boolean;
  reviewerId?: string | null;
  reviewedAt?: string | null;
  onDownloadPdf?: () => void;
}

export const SimulationBanner: React.FC<SimulationBannerProps> = ({
  isReviewed,
  reviewerId,
  reviewedAt,
  onDownloadPdf,
}) => {
  if (isReviewed) {
    return (
      <div className="bg-emerald-500/15 border-b border-emerald-500/30 text-emerald-950 dark:text-emerald-200 px-4 py-2 text-xs font-normal sticky top-0 z-50 backdrop-blur-md transition-colors">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
            <span className="leading-tight text-[11px] sm:text-xs">
              <strong className="font-semibold text-emerald-700 dark:text-emerald-300">REVU PAR UN CONSEILLER AGRÉÉ :</strong>{' '}
              Cette analyse a fait l&apos;objet d&apos;une détermination de convenance par{' '}
              <span className="font-mono font-medium">{reviewerId || 'le conseiller'}</span>
              {reviewedAt ? ` le ${new Date(reviewedAt).toLocaleDateString('fr-CA')}` : ''}. Dossier KYC et recommandation signée conformes.
            </span>
          </div>
          {onDownloadPdf && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onDownloadPdf}
              className="h-7 text-[11px] gap-1.5 border-emerald-500/40 text-emerald-800 dark:text-emerald-200 hover:bg-emerald-500/20"
            >
              <FileDown className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              <span>Dossier de convenance (PDF)</span>
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-amber-500/10 border-b border-amber-500/20 text-amber-900 dark:text-amber-300 px-4 py-1.5 text-xs font-normal flex items-center justify-between sticky top-0 z-50 backdrop-blur-md transition-colors">
      <div className="max-w-7xl mx-auto flex items-center gap-2 w-full">
        <ShieldAlert className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
        <span className="leading-tight text-[11px] sm:text-xs">
          <strong className="font-medium">SIMULATION ÉDUCATIVE UNIQUEMENT :</strong> Cet outil fournit un second avis d&apos;analyse de scénarios. Aucun conseil d&apos;investissement personnalisé, aucune recommandation d&apos;achat/vente, aucune prévision de rendement.
        </span>
      </div>
    </div>
  );
};
