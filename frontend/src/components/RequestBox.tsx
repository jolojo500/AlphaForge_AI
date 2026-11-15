import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { Persona } from '@/types'

interface Props {
  persona: Persona | null
  value: string
  busy: boolean
  onChange: (text: string) => void
  onSubmit: () => void
}

export function RequestBox({ persona, value, busy, onChange, onSubmit }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Votre demande</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Label htmlFor="request">Décrivez ce que vous souhaitez évaluer ou construire</Label>
        <Textarea
          id="request"
          value={value}
          maxLength={2000}
          rows={3}
          disabled={busy}
          placeholder={persona ? 'Écrivez votre demande, ou utilisez l’exemple.' : 'Choisissez d’abord un persona.'}
          onChange={(e) => onChange(e.target.value)}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={onSubmit} disabled={!persona || busy}>
            {busy ? 'Analyse en cours…' : 'Lancer l’analyse'}
          </Button>
          {persona && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => onChange(persona.example_request)}
            >
              Utiliser l’exemple
            </Button>
          )}
        </div>
        {persona && (
          <p className="text-sm text-muted-foreground">Exemple : « {persona.example_request} »</p>
        )}
      </CardContent>
    </Card>
  )
}
