import React from 'react';
import { ExternalLink, ListTree } from 'lucide-react';
import { Evidence } from '../types';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ConfidenceBadge } from './ConfidenceBadge';
import { evidenceLabel } from '@/lib/evidenceText';
import { dateKindLabel, methodLabel } from '@/lib/labels';
import { fmtPct, type Lang } from '@/lib/format';

interface EvidencePopoverProps {
  id: string;
  evidence?: Evidence;
  lang: Lang;
  /** Opens the full evidence registry at this row. */
  onOpenRegistry?: (id: string) => void;
  /** The element the reader clicks: the cited number, a chip, a metric value. */
  children: React.ReactElement;
  align?: 'start' | 'center' | 'end';
}

function renderValue(ev: Evidence, lang: Lang): React.ReactNode {
  let val: unknown = ev.value;
  if (typeof val === 'object' && val !== null && 'value' in (val as Record<string, unknown>)) {
    val = (val as { value: unknown }).value;
  }
  if (typeof val === 'number') {
    const asPct = Math.abs(val) <= 1.0 ? fmtPct(val, lang, 2) : null;
    return (
      <span className="font-mono text-sm font-semibold text-foreground">
        {val.toLocaleString(lang === 'en' ? 'en-CA' : 'fr-CA', { maximumFractionDigits: 4 })}
        {asPct ? <span className="text-muted-foreground font-normal"> ({asPct})</span> : null}
      </span>
    );
  }
  if (typeof val === 'object' && val !== null) {
    return (
      <pre className="text-[11px] bg-muted text-foreground p-2 rounded-md overflow-x-auto font-mono border border-border max-h-32">
        {JSON.stringify(val, null, 1)}
      </pre>
    );
  }
  return <span className="font-mono text-sm text-foreground break-words">{String(val)}</span>;
}

/**
 * The detail of one evidence item, opened beside the number that cites it. The full registry
 * stays one click away so the reader can come back to where they were.
 */
export const EvidencePopover: React.FC<EvidencePopoverProps> = ({
  id,
  evidence,
  lang,
  onOpenRegistry,
  children,
  align = 'start',
}) => {
  const en = lang === 'en';
  const label = evidenceLabel(evidence, lang, id);
  return (
    <Popover>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent align={align} className="w-[22rem] text-left space-y-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-foreground leading-snug">{label}</p>
            <p className="text-[10px] font-mono text-muted-foreground mt-0.5">{id}</p>
          </div>
          {evidence && <ConfidenceBadge confidence={evidence.confidence} />}
        </div>

        {evidence ? (
          <>
            <div className="p-2.5 bg-muted/40 rounded-lg border border-border/60">
              <span className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-0.5">
                {en ? 'Value' : 'Valeur'}
              </span>
              {renderValue(evidence, lang)}
            </div>

            <dl className="text-[11px] space-y-1">
              <div className="flex gap-1.5">
                <dt className="text-muted-foreground shrink-0">{en ? 'Source' : 'Source'}&nbsp;:</dt>
                <dd className="text-foreground break-all">{evidence.source}</dd>
              </div>
              <div className="flex gap-1.5">
                <dt className="text-muted-foreground shrink-0">{en ? 'Date' : 'Date'}&nbsp;:</dt>
                <dd className="text-foreground">
                  {evidence.date}
                  <span className="text-muted-foreground"> ({dateKindLabel(evidence.date_kind, lang)})</span>
                </dd>
              </div>
              <div className="flex gap-1.5">
                <dt className="text-muted-foreground shrink-0">{en ? 'Method' : 'Méthode'}&nbsp;:</dt>
                <dd className="text-foreground leading-snug">{methodLabel(evidence.method, lang)}</dd>
              </div>
            </dl>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 border-t border-border/60">
              {onOpenRegistry && (
                <button
                  type="button"
                  onClick={() => onOpenRegistry(id)}
                  className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline cursor-pointer"
                >
                  <ListTree className="w-3 h-3" />
                  {en ? 'See it in the evidence registry' : 'Voir dans le registre des preuves'}
                </button>
              )}
              {evidence.url && (
                <a
                  href={evidence.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
                >
                  <ExternalLink className="w-3 h-3" />
                  {en ? 'Open the source' : 'Ouvrir la source'}
                </a>
              )}
            </div>
          </>
        ) : (
          <p className="text-[11px] text-muted-foreground">
            {en ? 'This evidence item is not in the current run.' : "Cette preuve n'est pas dans l'analyse courante."}
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
};
