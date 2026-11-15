import { EvidenceChip } from '@/components/EvidenceChip'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { SCENARIO_LABEL } from '@/lib/format'
import type { Claim, Evidence, GraphState } from '@/types'

interface Props {
  state: GraphState
  selectedEvidence: string | null
  onSelectEvidence: (id: string) => void
}

const SECTIONS: { key: 'quelles_donnees' | 'pourquoi_ce_choix' | 'limites' | 'ce_qui_changerait_la_reponse'; title: string }[] = [
  { key: 'quelles_donnees', title: 'Quelles données ont été utilisées ?' },
  { key: 'pourquoi_ce_choix', title: 'Pourquoi cette comparaison ?' },
  { key: 'limites', title: 'Quelles sont les limites ?' },
  { key: 'ce_qui_changerait_la_reponse', title: 'Qu’est-ce qui changerait la réponse ?' },
]

function Claims({ claims, evidence, selected, onSelect }: {
  claims: Claim[]
  evidence: Record<string, Evidence>
  selected: string | null
  onSelect: (id: string) => void
}) {
  return (
    <ul className="space-y-3">
      {claims.map((c, i) => (
        <li key={i} className="text-sm">
          <p>{c.claim}</p>
          {c.evidence.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1" aria-label="Preuves citées">
              {c.evidence.map((id) => (
                <EvidenceChip key={id} id={id} evidence={evidence} active={selected === id} onSelect={onSelect} />
              ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}

export function ExplanationView({ state, selectedEvidence, onSelectEvidence }: Props) {
  const ex = state.explanation
  const v = state.verification
  if (!ex) return null
  return (
    <section aria-label="Explication" className="space-y-4">
      {v && !v.passed && (
        <Alert variant="destructive">
          <AlertTitle>La vérification automatique a échoué</AlertTitle>
          <AlertDescription>
            <p>Cette explication n’a pas passé les contrôles (preuves, nombres, formulations). Ne vous y fiez pas.</p>
            <ul className="mt-2 list-disc pl-4">
              {v.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            Explication
            {v?.passed && <Badge variant="secondary">Vérifiée : preuves, nombres, formulations</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <p className="text-sm">{ex.resume}</p>
          <p className="text-sm">
            Scénario le plus cohérent avec le profil déclaré :{' '}
            <strong>{SCENARIO_LABEL[ex.scenario_le_plus_coherent]}</strong>
          </p>
          {SECTIONS.map(({ key, title }) => (
            <div key={key} className="space-y-2">
              <h3 className="font-medium">{title}</h3>
              <Claims claims={ex[key]} evidence={state.evidence} selected={selectedEvidence} onSelect={onSelectEvidence} />
            </div>
          ))}
          <div className="space-y-1">
            <h3 className="font-medium">Incertitude</h3>
            <p className="text-sm text-muted-foreground">{ex.incertitude}</p>
          </div>
          {state.objections.length > 0 && (
            <div className="space-y-2">
              <h3 className="font-medium">Relecture critique</h3>
              <ul className="space-y-2 text-sm">
                {state.objections.map((o, i) => (
                  <li key={i}>
                    <Badge variant={o.severity === 'blocking' ? 'destructive' : 'outline'}>
                      {o.severity === 'blocking' ? 'Bloquante' : 'Point d’attention'}
                    </Badge>{' '}
                    <span className="text-muted-foreground">{SCENARIO_LABEL[o.scenario]} : </span>
                    {o.objection}
                    <span className="ml-2 inline-flex gap-1">
                      {o.evidence.map((id) => (
                        <EvidenceChip key={id} id={id} evidence={state.evidence} active={selectedEvidence === id} onSelect={onSelectEvidence} />
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
