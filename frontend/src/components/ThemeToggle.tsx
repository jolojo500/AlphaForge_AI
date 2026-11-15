import React from "react"
import { Moon, Sun } from "lucide-react"
import { useTheme } from "@/lib/theme"
import { useLanguage } from "@/context/LanguageContext"

interface ThemeToggleProps {
  className?: string;
  showLabel?: boolean;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ className = "", showLabel = false }) => {
  const { theme, toggleTheme } = useTheme()
  const { language } = useLanguage()
  const label =
    language === "en"
      ? theme === "dark" ? "Switch to light mode" : "Switch to dark mode"
      : theme === "dark" ? "Passer en mode clair" : "Passer en mode sombre"

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`inline-flex items-center justify-center h-8 w-8 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer border border-transparent ${className}`}
      title={label}
      aria-label={label}
    >
      <div className="relative w-4 h-4 flex items-center justify-center">
        {theme === "dark" ? (
          <Sun className="w-4 h-4 text-amber-400 rotate-0 scale-100 transition-all duration-300" />
        ) : (
          <Moon className="w-4 h-4 text-foreground rotate-0 scale-100 transition-all duration-300" />
        )}
      </div>
      {showLabel && (
        <span className="text-xs font-medium">
          {language === "en"
            ? theme === "dark" ? "Light mode" : "Dark mode"
            : theme === "dark" ? "Mode clair" : "Mode sombre"}
        </span>
      )}
    </button>
  )
}
