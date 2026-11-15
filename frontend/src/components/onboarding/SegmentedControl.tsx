import { cn } from '@/lib/utils';

interface SegmentedControlProps<T extends string> {
  options: T[];
  value: T | '';
  onChange: (val: T) => void;
  className?: string;
  /** Label shown for each option code; the code itself when absent. */
  labels?: Partial<Record<T, string>>;
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  className = '',
  labels,
}: SegmentedControlProps<T>) {
  return (
    <div className={cn("bg-muted p-1 rounded-lg flex items-center gap-1 border border-border/60", className)}>
      {options.map((opt) => {
        const isSelected = opt === value;
        return (
          <button
            key={opt}
            type="button"
            onClick={() => onChange(opt)}
            className={cn(
              "flex-1 py-1.5 text-center text-xs rounded-md transition-all duration-150 select-none",
              isSelected
                ? "bg-card text-foreground font-medium shadow-xs border border-border/70 cursor-default"
                : "text-muted-foreground hover:text-foreground font-normal cursor-pointer hover:bg-background/40"
            )}
          >
            {labels?.[opt] ?? opt}
          </button>
        );
      })}
    </div>
  );
}
