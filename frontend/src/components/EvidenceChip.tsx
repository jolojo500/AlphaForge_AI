import React from 'react';

interface EvidenceChipProps {
  id: string;
  onClick: (id: string) => void;
  confidence?: 'fact' | 'assumption' | 'fictional';
}

export const EvidenceChip: React.FC<EvidenceChipProps> = ({ id, onClick, confidence }) => {
  // Prefix coloring
  // ES: screening, EQ: quant, EM: macro, EN: news, EP: portfolio
  let bgClass = 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100';
  if (confidence === 'assumption') {
    bgClass = 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100';
  } else if (confidence === 'fictional') {
    bgClass = 'bg-purple-50 text-purple-800 border-purple-200 hover:bg-purple-100';
  } else if (id.startsWith('EQ')) {
    bgClass = 'bg-cyan-50 text-cyan-800 border-cyan-200 hover:bg-cyan-100';
  } else if (id.startsWith('EM')) {
    bgClass = 'bg-indigo-50 text-indigo-800 border-indigo-200 hover:bg-indigo-100';
  } else if (id.startsWith('EN')) {
    bgClass = 'bg-emerald-50 text-emerald-800 border-emerald-200 hover:bg-emerald-100';
  } else if (id.startsWith('EP')) {
    bgClass = 'bg-violet-50 text-violet-800 border-violet-200 hover:bg-violet-100';
  }

  return (
    <button
      type="button"
      onClick={() => onClick(id)}
      title={`Consulter la preuve ${id}`}
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono font-medium border transition-colors cursor-pointer mr-1.5 mb-1 ${bgClass}`}
    >
      [{id}]
    </button>
  );
};
