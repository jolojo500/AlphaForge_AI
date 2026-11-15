import React from 'react';

interface EvidenceChipProps {
  id: string;
  onClick: (id: string) => void;
  confidence?: 'fact' | 'assumption' | 'fictional';
}

export const EvidenceChip: React.FC<EvidenceChipProps> = ({ id, onClick, confidence }) => {
  let bgClass = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/30 hover:bg-blue-500/20';
  if (confidence === 'assumption') {
    bgClass = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30 hover:bg-amber-500/20';
  } else if (confidence === 'fictional') {
    bgClass = 'bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-500/30 hover:bg-purple-500/20';
  } else if (id.startsWith('EQ')) {
    bgClass = 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border-cyan-500/30 hover:bg-cyan-500/20';
  } else if (id.startsWith('EM')) {
    bgClass = 'bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-500/30 hover:bg-indigo-500/20';
  } else if (id.startsWith('EN')) {
    bgClass = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/20';
  } else if (id.startsWith('EP')) {
    bgClass = 'bg-violet-500/10 text-violet-700 dark:text-violet-300 border-violet-500/30 hover:bg-violet-500/20';
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
