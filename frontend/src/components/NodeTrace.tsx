import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { NODE_LABEL, NODE_ORDER } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { TraceEntry } from '@/types'

interface Props {
  trace: TraceEntry[]
  running: boolean
  /** Nodes that never ran in this run (for example the profile in a what-if). */
  skipped?: string[]
}

const time = (iso: string) => new Date(iso).toLocaleTimeString('fr-CA')

export function NodeTrace({ trace, running, skipped = [] }: Props) {
  const done = new Map<string, TraceEntry[]>()
  for (const t of trace) done.set(t.node, [...(done.get(t.node) ?? []), t])
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Trace de l’analyse
          {running && <Badge variant="secondary">en direct</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="space-y-2">
          {NODE_ORDER.map((node) => {
            const entries = done.get(node) ?? []
            const last = entries.at(-1)
            const state = last ? 'done' : skipped.includes(node) ? 'skipped' : 'pending'
            return (
              <li key={node} className="flex items-start gap-3 text-sm" data-state={state}>
                <span
                  aria-hidden
                  className={cn(
                    'mt-1.5 size-2.5 shrink-0 rounded-full',
                    state === 'done' && 'bg-primary',
                    state === 'pending' && (running ? 'animate-pulse bg-muted-foreground/60' : 'bg-muted-foreground/30'),
                    state === 'skipped' && 'bg-muted-foreground/20',
                  )}
                />
                <div className="min-w-0">
                  <p className="font-medium">
                    {NODE_LABEL[node]}
                    {entries.length > 1 && (
                      <span className="ml-2 text-xs text-muted-foreground">×{entries.length}</span>
                    )}
                    {last && <span className="ml-2 text-xs text-muted-foreground">{time(last.ended_at)}</span>}
                  </p>
                  <p className="text-muted-foreground">
                    {last ? last.summary : state === 'skipped' ? 'Non exécuté dans cette variante.' : 'En attente'}
                  </p>
                </div>
              </li>
            )
          })}
        </ol>
      </CardContent>
    </Card>
  )
}
