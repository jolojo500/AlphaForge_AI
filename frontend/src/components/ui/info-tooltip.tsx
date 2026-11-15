import React, { useState } from 'react';
import { Info } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  TooltipArrow,
} from '@/components/ui/tooltip';

interface InfoTooltipProps {
  content: React.ReactNode;
  className?: string;
}

export const InfoTooltip: React.FC<InfoTooltipProps> = ({ content, className = '' }) => {
  const [open, setOpen] = useState(false);

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip open={open} onOpenChange={setOpen}>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setOpen((prev) => !prev);
            }}
            onPointerDown={(e) => {
              e.stopPropagation();
            }}
            className={`inline-flex items-center justify-center w-3.5 h-3.5 rounded-full text-muted-foreground/70 hover:text-foreground hover:bg-muted/80 transition-colors cursor-pointer shrink-0 ${className}`}
            aria-label="Plus d'informations"
          >
            <Info className="w-3 h-3 stroke-[2.2]" />
          </button>
        </TooltipTrigger>
        <TooltipContent
          side="top"
          align="center"
          className="max-w-[280px] p-2.5 text-xs font-normal leading-relaxed bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 border border-zinc-200 dark:border-zinc-800 shadow-xl rounded-md select-text"
        >
          {content}
          <TooltipArrow className="fill-white dark:fill-zinc-900" />
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
