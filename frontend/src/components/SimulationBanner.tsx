import { Alert, AlertDescription } from '@/components/ui/alert'

export const DISCLAIMER = 'Simulation éducative. Aucun conseil personnalisé.'

export function SimulationBanner() {
  return (
    <Alert className="border-primary/40 bg-primary/10">
      <AlertDescription className="text-foreground">
        <strong>Simulation éducative.</strong> Les scénarios sont fictifs, fondés sur des données
        historiques, sans prévision de rendement ni conseil personnalisé. Aucune transaction réelle.
      </AlertDescription>
    </Alert>
  )
}
