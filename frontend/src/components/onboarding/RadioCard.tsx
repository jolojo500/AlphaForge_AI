import React from 'react';
import { cn } from '@/lib/utils';
import { InfoTooltip } from '@/components/ui/info-tooltip';

interface RadioCardProps {
  label: string;
  selected: boolean;
  onClick: () => void;
  className?: string;
  sublabel?: string;
  infoTooltip?: React.ReactNode;
}

export const RadioCard: React.FC<RadioCardProps> = ({
  label,
  selected,
  onClick,
  className = '',
  sublabel,
  infoTooltip,
}) => {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full text-left flex items-start sm:items-center gap-2.5 px-3 py-2.5 rounded-lg border transition-all duration-150 select-none active:scale-[0.99] cursor-pointer",
        selected
          ? "bg-sky-50/50 dark:bg-sky-950/30 border-sky-500/70 dark:border-sky-500/80 shadow-2xs"
          : "bg-card hover:bg-muted/40 border-border hover:border-border/80",
        className
      )}
    >
      <div
        className={cn(
          "w-3.5 h-3.5 rounded-full flex items-center justify-center shrink-0 mt-0.5 sm:mt-0 transition-colors",
          selected
            ? "border-2 border-foreground"
            : "border border-muted-foreground/40"
        )}
      >
        {selected && (
          <div className="w-1.5 h-1.5 rounded-full bg-foreground" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-normal leading-snug text-foreground">
            {label}
          </span>
          {infoTooltip && (
            <span onClick={(e) => e.stopPropagation()}>
              <InfoTooltip content={infoTooltip} />
            </span>
          )}
        </div>
        {sublabel && (
          <span className="block text-[11px] mt-0.5 text-muted-foreground leading-normal">
            {sublabel}
          </span>
        )}
      </div>
    </button>
  );
};
