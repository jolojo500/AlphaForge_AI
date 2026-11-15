import React from 'react';
import { PersonaMeta } from '../types';
import { User, Shield, Target, Clock, DollarSign, Play } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';

interface PersonaPickerProps {
  personas: Record<string, PersonaMeta>;
  selectedPersona: string;
  onSelectPersona: (personaId: string) => void;
  requestText: string;
  onChangeRequestText: (text: string) => void;
  onRun: () => void;
  isRunning: boolean;
}

const TOLERANCE_LABELS: Record<string, string> = {
  low: 'Faible',
  low_moderate: 'Faible à modérée',
  moderate: 'Modérée',
  high: 'Élevée',
};

const OBJECTIVE_LABELS: Record<string, string> = {
  growth: 'Croissance du capital',
  balanced: 'Équilibré & responsable',
  capital_preservation: 'Préservation du capital',
};

export const PersonaPicker: React.FC<PersonaPickerProps> = ({
  personas,
  selectedPersona,
  onSelectPersona,
  requestText,
  onChangeRequestText,
  onRun,
  isRunning,
}) => {
  const currentMeta = personas[selectedPersona];

  return (
    <Card className="mb-6 shadow-sm border-border bg-card">
      <CardContent className="p-6">
        <div className="flex items-center gap-2 mb-4">
          <User className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-foreground">1. Profil investisseur & demande</h2>
        </div>

        {/* Persona Selection Tabs */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
          {Object.entries(personas).map(([id, meta]) => {
            const isSelected = id === selectedPersona;
            return (
              <button
                key={id}
                type="button"
                onClick={() => onSelectPersona(id)}
                disabled={isRunning}
                className={`p-4 rounded-xl text-left transition-all border ${
                  isSelected
                    ? 'border-primary bg-primary/5 ring-1 ring-primary/20 shadow-sm'
                    : 'border-border hover:border-border/80 bg-muted/30'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-foreground">{meta.label}</span>
                  <Badge variant={isSelected ? "default" : "secondary"} className="text-xs">
                    {id}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {OBJECTIVE_LABELS[meta.objective] || meta.objective}
                </p>
              </button>
            );
          })}
        </div>

        {/* Selected Persona Hypothesis Summary */}
        {currentMeta && (
          <div className="bg-muted/40 rounded-xl p-4 border border-border/70 mb-5 text-xs text-muted-foreground grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-muted-foreground/70 shrink-0" />
              <div>
                <span className="text-muted-foreground/80 block">Horizon</span>
                <span className="font-medium text-foreground">{currentMeta.horizon_years} ans</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-muted-foreground/70 shrink-0" />
              <div>
                <span className="text-muted-foreground/80 block">Tolérance risque</span>
                <span className="font-medium text-foreground">
                  {TOLERANCE_LABELS[currentMeta.risk_tolerance] || currentMeta.risk_tolerance}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Target className="w-4 h-4 text-muted-foreground/70 shrink-0" />
              <div>
                <span className="text-muted-foreground/80 block">Contraintes</span>
                <span className="font-medium text-foreground">
                  {currentMeta.constraints.length > 0 ? currentMeta.constraints.join(', ') : 'Aucune'}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-muted-foreground/70 shrink-0" />
              <div>
                <span className="text-muted-foreground/80 block">Budget CAD</span>
                <span className="font-medium text-foreground">
                  {currentMeta.budget_cad ? `${currentMeta.budget_cad.toLocaleString('fr-CA')} $` : 'Non spécifié'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Request input box */}
        <div className="space-y-2">
          <label htmlFor="request-text" className="block text-sm font-medium text-foreground">
            Demande initiale (en langage naturel) :
          </label>
          <Textarea
            id="request-text"
            rows={3}
            value={requestText}
            onChange={(e) => onChangeRequestText(e.target.value)}
            disabled={isRunning}
            placeholder="Entrez votre demande d'investissement..."
            className="w-full text-sm bg-card"
          />
          <div className="flex justify-end pt-1">
            <Button
              type="button"
              onClick={onRun}
              disabled={isRunning}
              className="gap-2"
            >
              {isRunning ? (
                <>
                  <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                  <span>Analyse en cours...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  <span>Lancer l&apos;analyse</span>
                </>
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
