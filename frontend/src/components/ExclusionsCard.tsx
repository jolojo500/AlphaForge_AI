import React from 'react';
import { Exclusion, Evidence } from '../types';
import { EvidenceChip } from './EvidenceChip';
import { Ban, CheckCircle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from '@/components/ui/table';

interface ExclusionsCardProps {
  exclusions: Exclusion[];
  evidence: Record<string, Evidence>;
  onSelectEvidence: (eid: string) => void;
}

export const ExclusionsCard: React.FC<ExclusionsCardProps> = ({
  exclusions,
  evidence,
  onSelectEvidence,
}) => {
  return (
    <Card className="bg-card border-border shadow-sm mb-6">
      <CardContent className="p-5 sm:p-6">
        <div className="flex items-center gap-2 mb-3.5">
          <Ban className="w-4 h-4 text-destructive" />
          <h2 className="text-sm sm:text-base font-semibold text-foreground">
            Actifs exclus de l&apos;univers d&apos;investissement
          </h2>
        </div>

        {exclusions.length === 0 ? (
          <div className="flex items-center gap-2 p-3 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 rounded-lg border border-emerald-500/20 text-xs">
            <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
            <span>
              Aucun actif exclu : l&apos;ensemble de l&apos;univers (31 actifs éligibles) respecte les contraintes déclarées.
            </span>
          </div>
        ) : (
          <div className="rounded-lg border border-border/80 overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/50">
                <TableRow className="border-border/80">
                  <TableHead className="font-semibold text-foreground text-xs">Actif</TableHead>
                  <TableHead className="font-semibold text-foreground text-xs">Motif d&apos;exclusion</TableHead>
                  <TableHead className="font-semibold text-foreground text-xs">Preuve</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {exclusions.map((ex, idx) => (
                  <TableRow key={`${ex.ticker}-${idx}`} className="border-border/60 hover:bg-muted/40">
                    <TableCell className="font-mono font-bold text-red-500">{ex.ticker}</TableCell>
                    <TableCell className="text-foreground text-xs">{ex.reason}</TableCell>
                    <TableCell>
                      <EvidenceChip
                        id={ex.evidence_id}
                        onClick={onSelectEvidence}
                        confidence={evidence[ex.evidence_id]?.confidence}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
