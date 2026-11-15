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
  /** Position in the detailed section, so the numbering stays continuous. */
  sectionNumber?: number;
}

export const ExclusionsCard: React.FC<ExclusionsCardProps> = ({
  exclusions,
  evidence,
  onSelectEvidence,
  sectionNumber,
}) => {
  const { language } = useLanguage();
  const isEn = language === 'en';
  const prefix = sectionNumber ? `${sectionNumber}. ` : '';

  return (
    <Card className="bg-card border-border shadow-sm mb-6">
      <CardContent className="p-5 sm:p-6">
        <div className="flex items-center gap-2 mb-3.5">
          <Ban className="w-4 h-4 text-destructive" />
          <h2 className="text-sm sm:text-base font-semibold text-foreground">
            {prefix}
            {isEn ? 'Assets set aside for your profile' : 'Actifs écartés pour votre profil'}
          </h2>
        </div>

        {exclusions.length === 0 ? (
          <div className="flex items-center gap-2 p-3 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 rounded-lg border border-emerald-500/20 text-xs">
            <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
            <span>
              {isEn
                ? 'No asset set aside: all 31 analysed assets comply with your stated constraints.'
                : 'Aucun actif écarté\u00a0: les 31 actifs analysés respectent les contraintes que vous avez déclarées.'}
            </span>
          </div>
        ) : (
          <div className="rounded-lg border border-border/80 overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/50">
                <TableRow className="border-border/80">
                  <TableHead className="font-semibold text-foreground text-xs">{isEn ? 'Asset' : 'Actif'}</TableHead>
                  <TableHead className="font-semibold text-foreground text-xs">{isEn ? 'Reason' : 'Raison'}</TableHead>
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
                          evidence={evidence[item.evidence_id]}
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
