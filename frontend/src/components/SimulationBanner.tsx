import React from 'react';
import { ShieldAlert } from 'lucide-react';

export const SimulationBanner: React.FC = () => {
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
