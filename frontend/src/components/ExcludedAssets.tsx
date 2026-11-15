import { EvidenceChip } from '@/components/EvidenceChip'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Evidence, Exclusion } from '@/types'

interface Props {
  exclusions: Exclusion[]
  evidence: Record<string, Evidence>
  selected: string | null
  onSelect: (id: string) => void
}

export function ExcludedAssets({ exclusions, evidence, selected, onSelect }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Actifs exclus ({exclusions.length})</CardTitle>
      </CardHeader>
      <CardContent>
        {exclusions.length === 0 ? (
          <p className="text-sm text-muted-foreground">Aucun actif exclu : tout l’univers est admissible.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {exclusions.map((e) => (
              <li key={e.ticker} className="flex flex-wrap items-center gap-2">
                <span className="font-mono font-medium">{e.ticker}</span>
                <span className="text-muted-foreground">{e.reason}</span>
                <EvidenceChip id={e.evidence_id} evidence={evidence} active={selected === e.evidence_id} onSelect={onSelect} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
