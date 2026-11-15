import { evidenceText } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Evidence } from '@/types'

interface Props {
  id: string
  evidence: Record<string, Evidence>
  active?: boolean
  onSelect: (id: string) => void
}

/** A clickable evidence id. Unknown ids are shown as such, never hidden. */
export function EvidenceChip({ id, evidence, active, onSelect }: Props) {
  const ev = evidence[id]
  return (
    <button
      type="button"
      title={ev ? `${evidenceText(ev)} · ${ev.source} · ${ev.date}` : 'Preuve introuvable'}
      onClick={() => onSelect(id)}
      className={cn(
        'inline-flex h-5 items-center rounded-full border px-2 font-mono text-xs transition-colors',
        ev ? 'border-primary/40 bg-primary/10 text-primary hover:bg-primary/20' : 'border-destructive/50 text-destructive',
        ev?.confidence === 'fictional' && 'border-dashed',
        active && 'bg-primary text-primary-foreground',
      )}
    >
      {id}
    </button>
  )
}
