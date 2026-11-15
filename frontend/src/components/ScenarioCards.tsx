import { EvidenceChip } from '@/components/EvidenceChip'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { SCENARIO_HELP, SCENARIO_LABEL, METRIC_LABEL, evidenceNumber, fmtMetric, fmtPct } from '@/lib/format'
import { cn } from '@/lib/utils'
import { SCENARIO_METRICS, type Evidence, type Scenario, type ScenarioName } from '@/types'

interface Props {
  scenarios: Scenario[]
  evidence: Record<string, Evidence>
  mostCoherent: ScenarioName | null
  selectedEvidence: string | null
  onSelectEvidence: (id: string) => void
}

const TOP_POSITIONS = 8

function WeightBars({ weights }: { weights: Record<string, number> }) {
  const rows = Object.entries(weights)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, TOP_POSITIONS)
  const max = Math.max(...rows.map(([, w]) => w), 0.0001)
  const rest = Object.keys(weights).length - rows.length
  return (
    <div className="space-y-1" role="img" aria-label="Répartition des positions principales">
      {rows.map(([ticker, w]) => (
        <div key={ticker} className="grid grid-cols-[5.5rem_1fr_3rem] items-center gap-2 text-xs">
          <span className="truncate font-mono">{ticker}</span>
          <div className="h-2 rounded-full bg-muted">
            <div className="h-2 rounded-full bg-primary" style={{ width: `${(w / max) * 100}%` }} />
          </div>
          <span className="text-right tabular-nums">{fmtPct(w, 1)}</span>
        </div>
      ))}
      {rest > 0 && <p className="text-xs text-muted-foreground">+ {rest} autres positions</p>}
    </div>
  )
}

export function ScenarioCards({ scenarios, evidence, mostCoherent, selectedEvidence, onSelectEvidence }: Props) {
  return (
    <section aria-label="Scénarios" className="grid gap-4 lg:grid-cols-3">
      {scenarios.map((sc) => {
        const best = sc.name === mostCoherent
        const fictional = Object.values(sc.metrics).some((id) => evidence[id]?.confidence === 'fictional')
        return (
          <Card key={sc.name} className={cn(best && 'border-primary ring-1 ring-primary')}>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">
                {SCENARIO_LABEL[sc.name]}
                {best && <Badge>Le plus cohérent avec votre profil</Badge>}
                {fictional && <Badge variant="outline">Données fictives</Badge>}
              </CardTitle>
              <CardDescription>{SCENARIO_HELP[sc.name]}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <WeightBars weights={sc.weights} />
              <dl className="space-y-1 text-sm">
                {SCENARIO_METRICS.map((m) => {
                  const id = sc.metrics[m]
                  return (
                    <div key={m} className="flex items-center justify-between gap-2">
                      <dt className="text-muted-foreground">{METRIC_LABEL[m]}</dt>
                      <dd className="flex items-center gap-2">
                        <span className="tabular-nums">{fmtMetric(m, evidenceNumber(evidence[id]))}</span>
                        {id && (
                          <EvidenceChip id={id} evidence={evidence} active={selectedEvidence === id} onSelect={onSelectEvidence} />
                        )}
                      </dd>
                    </div>
                  )
                })}
              </dl>
              {sc.notes.length > 0 && (
                <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                  {sc.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        )
      })}
    </section>
  )
}
