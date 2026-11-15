import React from 'react';
import { PersonaMeta } from '../types';
import { User, Shield, Target, Clock, DollarSign, Play } from 'lucide-react';

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
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <div className="flex items-center gap-2 mb-4">
        <User className="w-5 h-5 text-blue-600" />
        <h2 className="text-lg font-semibold text-slate-800">1. Profil investisseur & demande</h2>
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
              className={`p-4 rounded-lg text-left transition-all border ${
                isSelected
                  ? 'border-blue-600 bg-blue-50/50 ring-2 ring-blue-600/20 shadow-sm'
                  : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-slate-900">{meta.label}</span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    isSelected ? 'bg-blue-600 text-white' : 'bg-slate-200 text-slate-700'
                  }`}
                >
                  {id}
                </span>
              </div>
              <p className="text-xs text-slate-500 line-clamp-2">
                {OBJECTIVE_LABELS[meta.objective] || meta.objective}
              </p>
            </button>
          );
        })}
      </div>

      {/* Selected Persona Hypothesis Summary */}
      {currentMeta && (
        <div className="bg-slate-50 rounded-lg p-4 border border-slate-100 mb-5 text-xs text-slate-600 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-400 shrink-0" />
            <div>
              <span className="text-slate-400 block">Horizon</span>
              <span className="font-medium text-slate-800">{currentMeta.horizon_years} ans</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-slate-400 shrink-0" />
            <div>
              <span className="text-slate-400 block">Tolérance risque</span>
              <span className="font-medium text-slate-800">
                {TOLERANCE_LABELS[currentMeta.risk_tolerance] || currentMeta.risk_tolerance}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-slate-400 shrink-0" />
            <div>
              <span className="text-slate-400 block">Contraintes</span>
              <span className="font-medium text-slate-800">
                {currentMeta.constraints.length > 0 ? currentMeta.constraints.join(', ') : 'Aucune'}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-slate-400 shrink-0" />
            <div>
              <span className="text-slate-400 block">Budget CAD</span>
              <span className="font-medium text-slate-800">
                {currentMeta.budget_cad ? `${currentMeta.budget_cad.toLocaleString('fr-CA')} $` : 'Non spécifié'}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Request input box */}
      <div className="space-y-2">
        <label htmlFor="request-text" className="block text-sm font-medium text-slate-700">
          Demande initiale (en langage naturel) :
        </label>
        <textarea
          id="request-text"
          rows={3}
          value={requestText}
          onChange={(e) => onChangeRequestText(e.target.value)}
          disabled={isRunning}
          placeholder="Entrez votre demande d'investissement..."
          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent bg-white disabled:bg-slate-100"
        />
        <div className="flex justify-end pt-1">
          <button
            type="button"
            onClick={onRun}
            disabled={isRunning}
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-medium px-5 py-2.5 rounded-lg text-sm shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {isRunning ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Analyse en cours...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-white" />
                <span>Lancer l&apos;analyse</span>
              </>
            )}
          </button>
        </div>
      </div>
    </section>
  );
};
