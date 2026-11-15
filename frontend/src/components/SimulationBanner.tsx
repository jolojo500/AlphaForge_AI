import React from 'react';
import { ShieldAlert } from 'lucide-react';

export const SimulationBanner: React.FC = () => {
  return (
    <div className="bg-amber-500/10 border-b border-amber-500/20 text-amber-900 px-4 py-2 text-xs md:text-sm font-medium flex items-center justify-between sticky top-0 z-50 backdrop-blur-sm bg-white/90">
      <div className="max-w-7xl mx-auto flex items-center gap-2 w-full">
        <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0" />
        <span>
          <strong>SIMULATION ÉDUCATIVE UNIQUEMENT :</strong> Cet outil fournit un second avis d&apos;analyse de scénarios. Aucun conseil d&apos;investissement personnalisé, aucune recommandation d&apos;achat/vente, aucune prévision de rendement.
        </span>
      </div>
    </div>
  );
};
