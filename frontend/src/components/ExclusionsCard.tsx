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
import { useLanguage } from '@/context/LanguageContext';

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
  const { language } = useLanguage();
  const isEn = language === 'en';

  return (
    <Card className="bg-card border-border shadow-sm mb-6">
      <CardContent className="p-5 sm:p-6">
        <div className="flex items-center gap-2 mb-3.5">
          <Ban className="w-4 h-4 text-destructive" />
          <h2 className="text-sm sm:text-base font-semibold text-foreground">
            {isEn ? 'Assets Excluded from Investment Universe' : "Actifs exclus de l'univers d'investissement"}
          </h2>
        </div>

        {exclusions.length === 0 ? (
          <div className="flex items-center gap-2 p-3 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 rounded-lg border border-emerald-500/20 text-xs">
            <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
            <span>
              {isEn
                ? 'No assets excluded: the entire universe (31 eligible assets) complies with declared constraints.'
                : "Aucun actif exclu : l'ensemble de l'univers (31 actifs éligibles) respecte les contraintes déclarées."}
            </span>
          </div>
        ) : (
          <div className="rounded-lg border border-border/80 overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/50">
                <TableRow className="border-border/80">
                  <TableHead className="font-semibold text-foreground text-xs">{isEn ? 'Asset' : 'Actif'}</TableHead>
                  <TableHead className="font-semibold text-foreground text-xs">{isEn ? 'Exclusion Reason' : "Motif d'exclusion"}</TableHead>
                  <TableHead className="font-semibold text-foreground text-xs">{isEn ? 'Evidence' : 'Preuve'}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {exclusions.map((item, idx) => (
                  <TableRow key={idx} className="border-border/60 hover:bg-muted/30">
                    <TableCell className="font-semibold text-xs text-foreground py-2.5">
                      {item.ticker}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground py-2.5 leading-snug">
                      {item.reason}
                    </TableCell>
                    <TableCell className="py-2.5">
                      {item.evidence_id && (
                        <EvidenceChip
                          id={item.evidence_id}
                          onClick={onSelectEvidence}
                          confidence={evidence[item.evidence_id]?.confidence}
                        />
                      )}
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
