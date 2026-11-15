import React from 'react';
import { Globe } from 'lucide-react';
import { useLanguage } from '@/context/LanguageContext';

interface LanguageToggleProps {
  className?: string;
  showFullLabel?: boolean;
}

export const LanguageToggle: React.FC<LanguageToggleProps> = ({
  className = '',
  showFullLabel = false,
}) => {
  const { language, toggleLanguage } = useLanguage();

  return (
    <button
      type="button"
      onClick={toggleLanguage}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/70 transition-all active:scale-95 border border-transparent hover:border-border/60 cursor-pointer ${className}`}
      title={language === 'fr' ? 'Switch to English' : 'Passer en français'}
      aria-label="Toggle language"
    >
      <Globe className="w-3.5 h-3.5 text-primary" />
      <span className="tracking-wider text-xs">
        {language === 'fr' ? (
          <span>
            <strong className="text-foreground font-bold">FR</strong>
            <span className="text-muted-foreground/60 mx-0.5">|</span>
            <span className="text-muted-foreground/80">EN</span>
          </span>
        ) : (
          <span>
            <span className="text-muted-foreground/80">FR</span>
            <span className="text-muted-foreground/60 mx-0.5">|</span>
            <strong className="text-foreground font-bold">EN</strong>
          </span>
        )}
      </span>
      {showFullLabel && (
        <span className="text-[11px] text-muted-foreground ml-1">
          {language === 'fr' ? 'Français' : 'English'}
        </span>
      )}
    </button>
  );
};
