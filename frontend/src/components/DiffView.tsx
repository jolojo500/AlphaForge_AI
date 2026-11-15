import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { METRIC_LABEL, SCENARIO_LABEL, fmtMetric, fmtPct } from '@/lib/format'
import { cn } from '@/lib/utils'
import { SCENARIO_METRICS, SCENARIO_NAMES, type Diff } from '@/types'

const PROFILE_LABEL: Record<string, string> = {
  horizon_years: 'Horizon (ans)',
  budget_cad: 'Budget (CAD)',
  risk_tolerance: 'Tolérance',
  excluded_tickers: 'Actifs exclus',
  as_of_date: 'Date d’analyse',
}

const show = (v: unknown) => (Array.isArray(v) ? v.join(', ') || '—' : v === null || v === undefined ? '—' : String(v))

export function DiffView({ diff, changeLabel }: { diff: Diff; changeLabel: string }) {
  const profileRows = Object.entries(diff.profile)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Avant / après
          <Badge variant="secondary">{changeLabel}</Badge>
          {diff.most_coherent.changed ? (
            <Badge>
              Scénario le plus cohérent : {diff.most_coherent.old ? SCENARIO_LABEL[diff.most_coherent.old] : '—'} →{' '}
              {diff.most_coherent.new ? SCENARIO_LABEL[diff.most_coherent.new] : '—'}
            </Badge>
          ) : (
            <Badge variant="outline">Le scénario le plus cohérent ne change pas</Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {profileRows.length > 0 && (
          <ul className="text-sm">
            {profileRows.map(([k, v]) => (
              <li key={k}>
                {PROFILE_LABEL[k] ?? k} : <span className="text-muted-foreground">{show(v.old)}</span> →{' '}
                <strong>{show(v.new)}</strong>
              </li>
            ))}
          </ul>
        )}
        {(diff.eligible_universe.added.length > 0 || diff.eligible_universe.removed.length > 0) && (
          <p className="text-sm">
            Univers admissible : {diff.eligible_universe.removed.length > 0 && <>retiré {diff.eligible_universe.removed.join(', ')} </>}
            {diff.eligible_universe.added.length > 0 && <>ajouté {diff.eligible_universe.added.join(', ')}</>}
          </p>
        )}
        <div className="grid gap-4 lg:grid-cols-3">
          {SCENARIO_NAMES.map((name) => {
            const sc = diff.scenarios[name]
            if (!sc) return null
            const moved = Object.entries(sc.weights).sort((a, b) => Math.abs(b[1].delta) - Math.abs(a[1].delta)).slice(0, 4)
            return (
              <div key={name} className="space-y-2">
                <h3 className="font-medium">{SCENARIO_LABEL[name]}</h3>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Indicateur</TableHead>
                      <TableHead className="text-right">Avant</TableHead>
                      <TableHead className="text-right">Après</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {SCENARIO_METRICS.map((m) => {
                      const d = sc.metrics[m]
                      const changed = d && d.delta !== null && Math.abs(d.delta) > 1e-9
                      return (
                        <TableRow key={m}>
                          <TableCell>{METRIC_LABEL[m]}</TableCell>
                          <TableCell className="text-right tabular-nums">{fmtMetric(m, d?.old ?? null)}</TableCell>
                          <TableCell className={cn('text-right tabular-nums', changed && 'font-semibold text-primary')}>
                            {fmtMetric(m, d?.new ?? null)}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
                {moved.length > 0 ? (
                  <ul className="text-xs text-muted-foreground">
                    {moved.map(([t, w]) => (
                      <li key={t}>
                        <span className="font-mono">{t}</span> {fmtPct(w.old)} → {fmtPct(w.new)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-muted-foreground">Poids inchangés.</p>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
