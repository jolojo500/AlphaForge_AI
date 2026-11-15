import React from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { InfoTooltip } from '@/components/ui/info-tooltip';

interface CheckboxCardProps {
  label: string;
  checked: boolean;
  onToggle: () => void;
  className?: string;
  sublabel?: string;
  infoTooltip?: React.ReactNode;
}

export const CheckboxCard: React.FC<CheckboxCardProps> = ({
  label,
  checked,
  onToggle,
  className = '',
  sublabel,
  infoTooltip,
}) => {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "w-full text-left flex items-start sm:items-center gap-2.5 px-3 py-2.5 rounded-lg border transition-all duration-150 select-none active:scale-[0.99] cursor-pointer",
        checked
          ? "bg-sky-50/50 dark:bg-sky-950/30 border-sky-500/70 dark:border-sky-500/80 shadow-2xs"
          : "bg-card hover:bg-muted/40 border-border hover:border-border/80",
        className
      )}
    >
      <div
        className={cn(
          "w-3.5 h-3.5 rounded flex items-center justify-center shrink-0 mt-0.5 sm:mt-0 transition-colors",
          checked
            ? "bg-foreground text-background"
            : "border border-muted-foreground/40 bg-background"
        )}
      >
        {checked && <Check className="w-2.5 h-2.5 stroke-[3]" />}
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
