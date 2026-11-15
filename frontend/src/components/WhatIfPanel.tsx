import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TOLERANCE_LABEL } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Profile, Tolerance, WhatIfField } from '@/types'

interface Props {
  profile: Profile
  asOf: string
  eligible: string[]
  busy: boolean
  error: string | null
  onApply: (field: WhatIfField, value: string | number) => void
}

const TOLERANCES: Tolerance[] = ['low', 'low_moderate', 'moderate', 'high']

export function WhatIfPanel({ profile, asOf, eligible, busy, error, onApply }: Props) {
  const [horizon, setHorizon] = useState(profile.horizon_years)
  const [budget, setBudget] = useState(String(profile.budget_cad ?? 100000))
  const [tolerance, setTolerance] = useState<Tolerance>(profile.risk_tolerance)
  const [ticker, setTicker] = useState('')
  const [date, setDate] = useState(asOf)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Et si… ?</CardTitle>
        <CardDescription>
          Changez UNE hypothèse. L’analyse est relancée en entier et comparée à la précédente.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Tabs defaultValue="horizon">
          <TabsList className="flex-wrap">
            <TabsTrigger value="horizon">Horizon</TabsTrigger>
            <TabsTrigger value="budget">Budget</TabsTrigger>
            <TabsTrigger value="tolerance">Tolérance</TabsTrigger>
            <TabsTrigger value="exclude">Exclure un actif</TabsTrigger>
            <TabsTrigger value="date">Date d’analyse</TabsTrigger>
          </TabsList>

          <TabsContent value="horizon" className="space-y-3 pt-3">
            <Label>Horizon de placement : {horizon} ans</Label>
            <Slider
              min={1}
              max={30}
              step={1}
              value={[horizon]}
              onValueChange={(v) => setHorizon(Array.isArray(v) ? v[0] : (v as number))}
              aria-label="Horizon en années"
            />
            <Button disabled={busy || horizon === profile.horizon_years} onClick={() => onApply('horizon_years', horizon)}>
              Relancer avec cet horizon
            </Button>
          </TabsContent>

          <TabsContent value="budget" className="space-y-3 pt-3">
            <Label htmlFor="wi-budget">Budget (CAD)</Label>
            <Input id="wi-budget" type="number" min={1} step={1000} value={budget} onChange={(e) => setBudget(e.target.value)} />
            <Button disabled={busy || !(Number(budget) > 0)} onClick={() => onApply('budget_cad', Number(budget))}>
              Relancer avec ce budget
            </Button>
          </TabsContent>

          <TabsContent value="tolerance" className="space-y-3 pt-3">
            <Label>Tolérance au risque</Label>
            <div className="flex flex-wrap gap-2">
              {TOLERANCES.map((t) => (
                <Button
                  key={t}
                  type="button"
                  variant={tolerance === t ? 'default' : 'outline'}
                  aria-pressed={tolerance === t}
                  onClick={() => setTolerance(t)}
                >
                  {TOLERANCE_LABEL[t]}
                </Button>
              ))}
            </div>
            <Button disabled={busy || tolerance === profile.risk_tolerance} onClick={() => onApply('risk_tolerance', tolerance)}>
              Relancer avec cette tolérance
            </Button>
          </TabsContent>

          <TabsContent value="exclude" className="space-y-3 pt-3">
            <Label htmlFor="wi-ticker">Actif à exclure</Label>
            <Input
              id="wi-ticker"
              list="wi-tickers"
              value={ticker}
              placeholder="Par exemple SPY"
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
            />
            <datalist id="wi-tickers">
              {eligible.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
            <Button disabled={busy || !eligible.includes(ticker)} onClick={() => onApply('exclude_ticker', ticker)}>
              Relancer sans cet actif
            </Button>
          </TabsContent>

          <TabsContent value="date" className="space-y-3 pt-3">
            <Label htmlFor="wi-date">Date d’analyse</Label>
            <Input id="wi-date" type="date" value={date} max="2026-11-12" min="2021-11-13" onChange={(e) => setDate(e.target.value)} />
            <Button disabled={busy || !date || date === asOf} onClick={() => onApply('as_of_date', date)}>
              Relancer à cette date
            </Button>
          </TabsContent>
        </Tabs>
        {busy && <p className="text-sm text-muted-foreground">Nouvelle analyse en cours…</p>}
        <p role="alert" className={cn('text-sm text-destructive', !error && 'hidden')}>
          {error}
        </p>
      </CardContent>
    </Card>
  )
}
