import { useEffect, useRef } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { CONFIDENCE_LABEL, evidenceText } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Evidence } from '@/types'

interface Props {
  evidence: Record<string, Evidence>
  selected: string | null
}

const order = (id: string) => [id.slice(0, 2), Number(id.slice(2))] as const

export function EvidenceTable({ evidence, selected }: Props) {
  const rows = Object.values(evidence).sort((a, b) => {
    const [pa, na] = order(a.id)
    const [pb, nb] = order(b.id)
    return pa.localeCompare(pb) || na - nb
  })
  const selectedRef = useRef<HTMLTableRowElement | null>(null)
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [selected])
  return (
    <Card id="evidence">
      <CardHeader>
        <CardTitle>Preuves ({rows.length})</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="max-h-96 overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Id</TableHead>
                <TableHead>Valeur</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Méthode</TableHead>
                <TableHead>Nature</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((ev) => (
                <TableRow
                  key={ev.id}
                  ref={ev.id === selected ? selectedRef : undefined}
                  className={cn(ev.id === selected && 'bg-primary/15')}
                >
                  <TableCell className="font-mono">{ev.id}</TableCell>
                  <TableCell className="max-w-64 whitespace-normal">{evidenceText(ev)}</TableCell>
                  <TableCell className="whitespace-normal">
                    {ev.url ? (
                      <a className="text-primary underline" href={ev.url} target="_blank" rel="noreferrer noopener">
                        {ev.source}
                      </a>
                    ) : (
                      ev.source
                    )}
                  </TableCell>
                  <TableCell>
                    {ev.date}
                    <span className="block text-xs text-muted-foreground">
                      {ev.date_kind === 'publication' ? 'publication' : 'observation'}
                    </span>
                  </TableCell>
                  <TableCell className="max-w-64 whitespace-normal text-xs text-muted-foreground">{ev.method}</TableCell>
                  <TableCell>
                    <Badge variant={ev.confidence === 'fact' ? 'secondary' : 'outline'}>
                      {CONFIDENCE_LABEL[ev.confidence]}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
