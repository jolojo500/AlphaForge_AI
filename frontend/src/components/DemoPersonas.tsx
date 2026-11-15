import React, { useEffect, useState } from 'react';
import { fetchPersonas } from '../api';
import { Button } from '@/components/ui/button';
import { UserRound } from 'lucide-react';

interface PersonaInfo {
  label?: string;
  example_request?: string;
}

interface DemoPersonasProps {
  /** Launches a run with a built-in persona and its canonical request (no questionnaire). */
  onPick: (personaId: string, requestText: string) => void;
  disabled?: boolean;
}

const ORDER = ['robert', 'amira', 'mateo'];

export const DemoPersonas: React.FC<DemoPersonasProps> = ({ onPick, disabled }) => {
  const [personas, setPersonas] = useState<Record<string, PersonaInfo>>({});

  useEffect(() => {
    fetchPersonas()
      .then((p) => setPersonas(p as Record<string, PersonaInfo>))
      .catch(() => setPersonas({}));
  }, []);

  const ids = ORDER.filter((id) => personas[id]);
  if (ids.length === 0) return null;

  return (
    <div className="w-full max-w-xl mx-auto text-center space-y-2">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
        Profils de démonstration
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        {ids.map((id) => (
          <Button
            key={id}
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            title={personas[id].example_request}
            onClick={() => onPick(id, personas[id].example_request ?? '')}
            className="h-8 text-xs gap-1.5"
          >
            <UserRound className="w-3.5 h-3.5" />
            <span>{personas[id].label ?? id}</span>
          </Button>
        ))}
      </div>
    </div>
  );
};
