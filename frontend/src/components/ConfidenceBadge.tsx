import React from 'react';
import { Badge } from '@/components/ui/badge';

interface ConfidenceBadgeProps {
  confidence: 'fact' | 'assumption' | 'fictional';
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({ confidence }) => {
  switch (confidence) {
    case 'fact':
      return (
        <Badge variant="outline" className="text-[11px] font-semibold bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30">
          Fait vérifié
        </Badge>
      );
    case 'assumption':
      return (
        <Badge variant="outline" className="text-[11px] font-semibold bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30">
          Hypothèse
        </Badge>
      );
    case 'fictional':
      return (
        <Badge variant="outline" className="text-[11px] font-semibold bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-500/30">
          Fictif (simulation)
        </Badge>
      );
    default:
      return (
        <Badge variant="outline" className="text-[11px] font-semibold bg-muted text-muted-foreground border-border">
          {confidence}
        </Badge>
      );
  }
};
