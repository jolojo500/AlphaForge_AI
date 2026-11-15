import React, { useState, useMemo } from 'react';
import { Evidence } from '../types';
import { ConfidenceBadge } from './ConfidenceBadge';
import { Database, Search, ExternalLink } from 'lucide-react';

interface EvidenceTableProps {
  evidence: Record<string, Evidence>;
  onSelectEvidence: (eid: string) => void;
}

type PrefixFilter = 'ALL' | 'ES' | 'EQ' | 'EM' | 'EN' | 'EP';

const PREFIX_LABELS: Record<PrefixFilter, string> = {
  ALL: 'Toutes les preuves',
  ES: 'Filtrage (ES)',
  EQ: 'Quantitatif (EQ)',
  EM: 'Macroéconomie (EM)',
  EN: 'Actualités (EN)',
  EP: 'Portefeuille (EP)',
};

export const EvidenceTable: React.FC<EvidenceTableProps> = ({
  evidence,
  onSelectEvidence,
}) => {
  const [filterPrefix, setFilterPrefix] = useState<PrefixFilter>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  const evidenceList = useMemo(() => Object.values(evidence), [evidence]);

  const filteredEvidence = useMemo(() => {
    return evidenceList.filter((item) => {
      // Prefix match
      if (filterPrefix !== 'ALL' && !item.id.startsWith(filterPrefix)) {
        return false;
      }
      // Search query match
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const idMatch = item.id.toLowerCase().includes(q);
        const sourceMatch = item.source.toLowerCase().includes(q);
        const methodMatch = item.method.toLowerCase().includes(q);
        const valueMatch = JSON.stringify(item.value).toLowerCase().includes(q);
        return idMatch || sourceMatch || methodMatch || valueMatch;
      }
      return true;
    });
  }, [evidenceList, filterPrefix, searchQuery]);

  if (evidenceList.length === 0) return null;

  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2">
          <Database className="w-5 h-5 text-blue-600" />
          <h2 className="text-lg font-semibold text-slate-800">
            5. Registre complet des preuves ({evidenceList.length})
          </h2>
        </div>

        {/* Search input */}
        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Filtrer par actif, source..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-600"
          />
        </div>
      </div>

      {/* Prefix filter tabs */}
      <div className="flex flex-wrap gap-1.5 mb-4 border-b border-slate-100 pb-3">
        {(Object.keys(PREFIX_LABELS) as PrefixFilter[]).map((p) => {
          const count =
            p === 'ALL'
              ? evidenceList.length
              : evidenceList.filter((e) => e.id.startsWith(p)).length;
          const isActive = filterPrefix === p;
          return (
            <button
              key={p}
              type="button"
              onClick={() => setFilterPrefix(p)}
              className={`text-xs px-3 py-1 rounded-full font-medium transition-colors cursor-pointer ${
                isActive
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {PREFIX_LABELS[p]} ({count})
            </button>
          );
        })}
      </div>

      {/* Table */}
      <div className="overflow-x-auto max-h-96 overflow-y-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 text-slate-600 uppercase border-b border-slate-200 sticky top-0 z-10">
            <tr>
              <th className="py-2 px-3 font-semibold">ID</th>
              <th className="py-2 px-3 font-semibold">Valeur</th>
              <th className="py-2 px-3 font-semibold">Source</th>
              <th className="py-2 px-3 font-semibold">Date</th>
              <th className="py-2 px-3 font-semibold">Méthode</th>
              <th className="py-2 px-3 font-semibold">Statut</th>
              <th className="py-2 px-3 font-semibold">Lien</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredEvidence.map((ev) => {
              let displayVal = String(ev.value);
              if (typeof ev.value === 'object' && ev.value !== null) {
                if ('value' in ev.value) {
                  const subVal = (ev.value as { value: unknown }).value;
                  displayVal = String(subVal);
                } else {
                  displayVal = JSON.stringify(ev.value);
                }
              }

              return (
                <tr
                  key={ev.id}
                  onClick={() => onSelectEvidence(ev.id)}
                  className="hover:bg-slate-50 cursor-pointer transition-colors"
                >
                  <td className="py-2 px-3 font-mono font-bold text-blue-600">{ev.id}</td>
                  <td className="py-2 px-3 font-mono text-slate-900 max-w-[150px] truncate" title={displayVal}>
                    {displayVal}
                  </td>
                  <td className="py-2 px-3 text-slate-600 max-w-[120px] truncate" title={ev.source}>
                    {ev.source}
                  </td>
                  <td className="py-2 px-3 text-slate-500 whitespace-nowrap">
                    {ev.date}
                    <span className="text-[10px] text-slate-400 block">({ev.date_kind})</span>
                  </td>
                  <td className="py-2 px-3 text-slate-600 max-w-[220px] truncate" title={ev.method}>
                    {ev.method}
                  </td>
                  <td className="py-2 px-3">
                    <ConfidenceBadge confidence={ev.confidence} />
                  </td>
                  <td className="py-2 px-3">
                    {ev.url ? (
                      <a
                        href={ev.url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="text-blue-600 hover:text-blue-800"
                        title="Ouvrir le lien externe"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
};
