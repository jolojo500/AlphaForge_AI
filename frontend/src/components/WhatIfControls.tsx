import React, { useState } from 'react';
import { Profile } from '../types';
import { Sliders, Sparkles, Ban, Calendar, Shield, Clock, DollarSign } from 'lucide-react';

interface WhatIfControlsProps {
  currentProfile: Profile | null;
  asOfDate: string;
  eligibleTickers: string[];
  onRunWhatIf: (field: string, value: unknown) => void;
  isRunning: boolean;
}

export const WhatIfControls: React.FC<WhatIfControlsProps> = ({
  currentProfile,
  asOfDate,
  eligibleTickers,
  onRunWhatIf,
  isRunning,
}) => {
  const [activeTab, setActiveTab] = useState<'tolerance' | 'horizon' | 'exclude' | 'budget' | 'date'>('tolerance');

  const [tolerance, setTolerance] = useState<string>(currentProfile?.risk_tolerance || 'high');
  const [horizon, setHorizon] = useState<number>(currentProfile?.horizon_years || 5);
  const [budget, setBudget] = useState<string>(currentProfile?.budget_cad ? String(currentProfile.budget_cad) : '100000');
  const [tickerToExclude, setTickerToExclude] = useState<string>(
    eligibleTickers.length > 0 ? eligibleTickers[0] : 'TSLA'
  );
  const [date, setDate] = useState<string>(asOfDate || '2026-11-12');

  const handleApply = () => {
    if (isRunning) return;
    if (activeTab === 'tolerance') {
      onRunWhatIf('risk_tolerance', tolerance);
    } else if (activeTab === 'horizon') {
      onRunWhatIf('horizon_years', horizon);
    } else if (activeTab === 'budget') {
      onRunWhatIf('budget_cad', parseFloat(budget) || null);
    } else if (activeTab === 'exclude') {
      onRunWhatIf('exclude_ticker', tickerToExclude.toUpperCase().trim());
    } else if (activeTab === 'date') {
      onRunWhatIf('as_of_date', date);
    }
  };

  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sliders className="w-5 h-5 text-indigo-600" />
          <h2 className="text-lg font-semibold text-slate-800">
            6. Module What-If : Simulation d&apos;hypothèses alternatives
          </h2>
        </div>
        <span className="text-xs text-slate-500">
          Rejoue l&apos;analyse dès le filtrage en sautant l&apos;Agent 1
        </span>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 mb-4 border-b border-slate-100 pb-3">
        <button
          type="button"
          onClick={() => setActiveTab('tolerance')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
            activeTab === 'tolerance'
              ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-2xs'
              : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <Shield className="w-3.5 h-3.5" />
          <span>Tolérance au risque</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('exclude')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
            activeTab === 'exclude'
              ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-2xs'
              : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <Ban className="w-3.5 h-3.5" />
          <span>Exclure un actif</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('horizon')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
            activeTab === 'horizon'
              ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-2xs'
              : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <Clock className="w-3.5 h-3.5" />
          <span>Horizon temporel</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('budget')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
            activeTab === 'budget'
              ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-2xs'
              : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <DollarSign className="w-3.5 h-3.5" />
          <span>Budget d&apos;investissement</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('date')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
            activeTab === 'date'
              ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-2xs'
              : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <Calendar className="w-3.5 h-3.5" />
          <span>Date d&apos;observation (as-of)</span>
        </button>
      </div>

      {/* Tab controls */}
      <div className="bg-slate-50 p-4 rounded-xl border border-slate-100 mb-4">
        {activeTab === 'tolerance' && (
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-2">
              Modifier la tolérance au risque (actuelle :{' '}
              <span className="font-semibold text-slate-900">{currentProfile?.risk_tolerance || '—'}</span>)
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {[
                { val: 'low', label: 'Faible (cap 3%)' },
                { val: 'low_moderate', label: 'Faible à modérée (cap 5%)' },
                { val: 'moderate', label: 'Modérée (cap 7%)' },
                { val: 'high', label: 'Élevée (cap 10%)' },
              ].map(({ val, label }) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setTolerance(val)}
                  className={`p-2 rounded-lg text-xs font-medium border text-center transition-all cursor-pointer ${
                    tolerance === val
                      ? 'border-indigo-600 bg-white ring-2 ring-indigo-600/20 text-indigo-900 shadow-2xs'
                      : 'border-slate-200 bg-slate-100 text-slate-700 hover:bg-white'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-slate-500 mt-2">
              Exemple démo : Passer de « faible à modérée » à « élevée » déverrouille le plafond de risque sur le scénario plafonné.
            </p>
          </div>
        )}

        {activeTab === 'exclude' && (
          <div>
            <label htmlFor="exclude-ticker-select" className="block text-xs font-medium text-slate-700 mb-1">
              Choisir un actif à exclure :
            </label>
            <div className="flex gap-2">
              <select
                id="exclude-ticker-select"
                value={tickerToExclude}
                onChange={(e) => setTickerToExclude(e.target.value)}
                className="px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-mono font-medium focus:ring-2 focus:ring-indigo-600"
              >
                {eligibleTickers.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={tickerToExclude}
                onChange={(e) => setTickerToExclude(e.target.value.toUpperCase())}
                placeholder="Autre ticker..."
                className="px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-mono w-32 focus:ring-2 focus:ring-indigo-600"
              />
            </div>
            <p className="text-[11px] text-slate-500 mt-2">
              L&apos;actif sera filtré dès l&apos;étape de screening et retiré de l&apos;ensemble des scénarios construits.
            </p>
          </div>
        )}

        {activeTab === 'horizon' && (
          <div>
            <label htmlFor="horizon-input" className="block text-xs font-medium text-slate-700 mb-1">
              Horizon de placement (en années) : <span className="font-bold text-slate-900">{horizon} ans</span>
            </label>
            <input
              id="horizon-input"
              type="range"
              min="1"
              max="30"
              value={horizon}
              onChange={(e) => setHorizon(parseInt(e.target.value, 10))}
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer"
            />
          </div>
        )}

        {activeTab === 'budget' && (
          <div>
            <label htmlFor="budget-input" className="block text-xs font-medium text-slate-700 mb-1">
              Budget total à allouer (CAD) :
            </label>
            <input
              id="budget-input"
              type="number"
              step="1000"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              className="px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium w-48 focus:ring-2 focus:ring-indigo-600"
            />
          </div>
        )}

        {activeTab === 'date' && (
          <div>
            <label htmlFor="date-input" className="block text-xs font-medium text-slate-700 mb-1">
              Date d&apos;analyse (as-of date, historique max 2026-11-12) :
            </label>
            <input
              id="date-input"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              max="2026-11-12"
              className="px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-medium w-48 focus:ring-2 focus:ring-indigo-600"
            />
          </div>
        )}
      </div>

      {/* Action button */}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleApply}
          disabled={isRunning}
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-4 py-2 rounded-lg text-xs shadow-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {isRunning ? (
            <>
              <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <span>Calcul du scénario What-If...</span>
            </>
          ) : (
            <>
              <Sparkles className="w-3.5 h-3.5" />
              <span>Simuler cette hypothèse alternative</span>
            </>
          )}
        </button>
      </div>
    </section>
  );
};
