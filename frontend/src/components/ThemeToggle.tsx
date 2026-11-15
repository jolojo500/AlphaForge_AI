import React from "react"
import { Moon, Sun } from "lucide-react"
import { useTheme } from "@/lib/theme"

interface ThemeToggleProps {
  className?: string;
  showLabel?: boolean;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ className = "", showLabel = false }) => {
  const { theme, toggleTheme } = useTheme()

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`inline-flex items-center gap-2 p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/70 transition-all active:scale-95 border border-transparent hover:border-border/60 ${className}`}
      title={theme === "dark" ? "Passer en mode clair" : "Passer en mode sombre"}
      aria-label="Basculer le thème"
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
          {theme === "dark" ? "Mode clair" : "Mode sombre"}
        </span>
      )}
    </button>
  )
}
