import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  CAPACITY_LABEL,
  CONSTRAINT_LABEL,
  PREFERENCE_LABEL,
  TOLERANCE_LABEL,
  fmtMoney,
  humanize,
} from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Persona, PersonaId } from '@/types'

interface Props {
  personas: Persona[]
  selected: PersonaId | null
  disabled: boolean
  onSelect: (id: PersonaId) => void
}

export function PersonaPicker({ personas, selected, disabled, onSelect }: Props) {
  return (
    <section aria-label="Choix du persona" className="grid gap-4 md:grid-cols-3">
      {personas.map((p) => (
        <button
          key={p.id}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(p.id)}
          aria-pressed={selected === p.id}
          className="text-left disabled:opacity-60"
        >
          <Card
            className={cn(
              'h-full transition-colors hover:border-primary/60',
              selected === p.id && 'border-primary ring-1 ring-primary',
            )}
          >
            <CardHeader>
              <CardTitle>{p.label}</CardTitle>
              <CardDescription>Hypothèses du profil</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                Horizon : <strong>{p.horizon_years} ans</strong>
              </p>
              <p>
                Tolérance : <strong>{TOLERANCE_LABEL[p.risk_tolerance]}</strong> · Capacité :{' '}
                <strong>{CAPACITY_LABEL[p.risk_capacity]}</strong>
              </p>
              {p.budget_cad !== null && <p>Budget : {fmtMoney(p.budget_cad)}</p>}
              <div className="flex flex-wrap gap-1 pt-1">
                {p.constraints.map((c) => (
                  <Badge key={c} variant="destructive">
                    {humanize(c, CONSTRAINT_LABEL)}
                  </Badge>
                ))}
                {p.preferences.map((c) => (
                  <Badge key={c} variant="secondary">
                    {humanize(c, PREFERENCE_LABEL)}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        </button>
      ))}
    </section>
  )
}
