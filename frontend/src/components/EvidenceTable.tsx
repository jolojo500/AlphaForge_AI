import React, { useState, useMemo, useEffect } from 'react';
import { useLanguage } from '@/context/LanguageContext';
import { evidenceLabel } from '@/lib/evidenceText';
import { dateKindLabel, methodLabel } from '@/lib/labels';
import { Evidence } from '../types';
import { ConfidenceBadge } from './ConfidenceBadge';
import { Database, Search, ExternalLink } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from '@/components/ui/table';

interface EvidenceTableProps {
  evidence: Record<string, Evidence>;
  onSelectEvidence: (eid: string) => void;
  /** Evidence to reveal and highlight; `n` changes on every request so the same id can be asked twice. */
  focus?: { id: string; n: number } | null;
  /** Position in the detailed section, so the numbering stays continuous. */
  sectionNumber?: number;
}

type PrefixFilter = 'ALL' | 'ES' | 'EQ' | 'EM' | 'EN' | 'EP';

const PREFIX_LABELS: Record<PrefixFilter, [string, string]> = {
  ALL: ['Toutes les preuves', 'All evidence'],
  ES: ['Admissibilité (ES)', 'Eligibility (ES)'],
  EQ: ['Mesures de risque (EQ)', 'Risk measures (EQ)'],
  EM: ['Économie (EM)', 'Economy (EM)'],
  EN: ['Actualités (EN)', 'News (EN)'],
  EP: ['Portefeuille (EP)', 'Portfolio (EP)'],
};

export const EvidenceTable: React.FC<EvidenceTableProps> = ({
  evidence,
  onSelectEvidence,
  focus,
  sectionNumber,
}) => {
  const { language } = useLanguage();
  const isEn = language === 'en';
  const prefix = sectionNumber ? `${sectionNumber}. ` : '';
  const [filterPrefix, setFilterPrefix] = useState<PrefixFilter>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [flashId, setFlashId] = useState<string | null>(null);

  // A link in the answer points here: show every row, then scroll to the cited one.
  useEffect(() => {
    if (!focus) return;
    setFilterPrefix('ALL');
    setSearchQuery('');
    setFlashId(focus.id);
    const doScroll = () => {
      document.getElementById(`evidence-row-${focus.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };
    const t1 = window.setTimeout(doScroll, 100);
    const t2 = window.setTimeout(doScroll, 280);
    const clear = window.setTimeout(() => setFlashId(null), 3200);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      window.clearTimeout(clear);
    };
  }, [focus]);

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
    <Card className="bg-card border-border shadow-sm mb-6">
      <CardContent className="p-5 sm:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3.5">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-primary" />
            <h2 className="text-sm sm:text-base font-semibold text-foreground">
              {isEn
                ? `${prefix}Every figure and its source (${evidenceList.length})`
                : `${prefix}Chaque chiffre et sa source (${evidenceList.length})`}
            </h2>
          </div>

          {/* Search input */}
          <div className="relative w-full sm:w-60">
            <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-2.5" aria-hidden="true" />
            <Input
              type="text"
              placeholder={isEn ? 'Filter by asset, source...' : 'Filtrer par actif, source...'}
              aria-label={isEn ? 'Filter the evidence' : 'Filtrer les preuves'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 h-8 text-xs"
            />
          </div>
        </div>

        {/* Prefix filter tabs */}
        <div className="flex flex-wrap gap-1 mb-3.5 border-b border-border/60 pb-3">
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
                aria-pressed={isActive}
                className={`text-xs px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                  isActive
                    ? 'bg-foreground text-background shadow-xs font-medium'
                    : 'bg-muted text-muted-foreground hover:text-foreground hover:bg-muted/80'
                }`}
              >
                {PREFIX_LABELS[p][isEn ? 1 : 0]} ({count})
              </button>
            );
          })}
        </div>

        {/* Table */}
        <div className="rounded-lg border border-border/80 overflow-hidden max-h-96 overflow-y-auto">
          <Table>
            <TableHeader className="bg-muted/60 sticky top-0 z-10">
              <TableRow className="border-border/80">
                <TableHead className="font-semibold text-foreground text-xs py-2 px-3">{isEn ? 'Id' : 'Identifiant'}</TableHead>
                <TableHead className="font-semibold text-foreground text-xs py-2 px-3">{isEn ? 'Value' : 'Valeur'}</TableHead>
                <TableHead className="font-semibold text-foreground text-xs py-2 px-3">Source</TableHead>
                <TableHead className="font-semibold text-foreground text-xs py-2 px-3">Date</TableHead>
                <TableHead className="font-semibold text-foreground text-xs py-2 px-3">{isEn ? 'Method' : 'Méthode'}</TableHead>
                <TableHead className="font-semibold text-foreground text-xs py-2 px-3">{isEn ? 'Nature' : 'Nature'}</TableHead>
                <TableHead className="font-semibold text-foreground text-xs py-2 px-3">{isEn ? 'Link' : 'Lien'}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
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

                const method = methodLabel(ev.method, language);
                return (
                  <TableRow
                    key={ev.id}
                    id={`evidence-row-${ev.id}`}
                    onClick={() => onSelectEvidence(ev.id)}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onSelectEvidence(ev.id);
                      }
                    }}
                    className={`border-border/60 hover:bg-muted/40 cursor-pointer transition-colors ${
                      flashId === ev.id ? 'bg-amber-500/20 ring-2 ring-inset ring-amber-500/60' : ''
                    }`}
                  >
                    <TableCell className="py-2.5 px-3 font-mono font-bold text-blue-600 dark:text-blue-400">
                      {ev.id}
                      <span className="block font-sans font-normal text-[11px] text-foreground/80 leading-snug max-w-[220px] whitespace-normal">
                        {evidenceLabel(ev, language)}
                      </span>
                    </TableCell>
                    <TableCell className="py-2.5 px-3 font-mono text-foreground max-w-[150px] truncate" title={displayVal}>
                      {displayVal}
                    </TableCell>
                    <TableCell className="py-2.5 px-3 text-muted-foreground max-w-[120px] truncate" title={ev.source}>
                      {ev.source}
                    </TableCell>
                    <TableCell className="py-2.5 px-3 text-muted-foreground whitespace-nowrap text-xs">
                      {ev.date}
                      <span className="text-[10px] text-muted-foreground/70 block">({dateKindLabel(ev.date_kind, language)})</span>
                    </TableCell>
                    <TableCell className="py-2.5 px-3 text-muted-foreground max-w-[220px] truncate text-xs" title={method}>
                      {method}
                    </TableCell>
                    <TableCell className="py-2.5 px-3">
                      <ConfidenceBadge confidence={ev.confidence} />
                    </TableCell>
                    <TableCell className="py-2.5 px-3">
                      {ev.url ? (
                        <a
                          href={ev.url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-blue-500 hover:text-blue-700 dark:text-blue-400 inline-flex"
                          title={isEn ? `Open the source of ${ev.id}` : `Ouvrir la source de ${ev.id}`}
                          aria-label={isEn ? `Open the source of ${ev.id} in a new tab` : `Ouvrir la source de ${ev.id} dans un nouvel onglet`}
                        >
                          <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                        </a>
                      ) : (
                        <span className="text-muted-foreground/40">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
};
