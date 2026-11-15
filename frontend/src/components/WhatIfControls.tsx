import React, { useState } from 'react';
import { Profile } from '../types';
import { Sliders, Sparkles, Ban, Calendar, Shield, Clock, DollarSign } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

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
  const [activeTab, setActiveTab] = useState<'tolerance' | 'account_type' | 'exclude' | 'horizon' | 'budget' | 'date'>('tolerance');

  const [tolerance, setTolerance] = useState<string>(currentProfile?.risk_tolerance || 'moderate');
  const [accountType, setAccountType] = useState<string>(currentProfile?.account_type || 'non_registered');
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
    } else if (activeTab === 'account_type') {
      onRunWhatIf('account_type', accountType);
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
    <Card className="bg-card border-border shadow-xs p-5 sm:p-6 mb-6">
      <CardContent className="p-0">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-primary" />
            <h2 className="text-sm sm:text-base font-semibold text-foreground">
              Module What-If : Simulation d&apos;hypothèses alternatives
            </h2>
          </div>
          <span className="text-xs text-muted-foreground hidden sm:inline">
            Rejoue l&apos;analyse dès le filtrage en conservant le profil
          </span>
        </div>

        {/* Tabs */}
        <div className="flex flex-wrap gap-1.5 mb-4 border-b border-border/60 pb-3">
          <button
            type="button"
            onClick={() => setActiveTab('tolerance')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
              activeTab === 'tolerance'
                ? 'bg-primary text-primary-foreground shadow-2xs'
                : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground'
            }`}
          >
            <Shield className="w-3.5 h-3.5" />
            <span>Tolérance au risque</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('account_type')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
              activeTab === 'account_type'
                ? 'bg-primary text-primary-foreground shadow-2xs'
                : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Régime fiscal / Compte</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('exclude')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
              activeTab === 'exclude'
                ? 'bg-primary text-primary-foreground shadow-2xs'
                : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground'
            }`}
          >
            <Ban className="w-3.5 h-3.5" />
            <span>Exclure un actif</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('horizon')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
              activeTab === 'horizon'
                ? 'bg-primary text-primary-foreground shadow-2xs'
                : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground'
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>Horizon temporel</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('budget')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
              activeTab === 'budget'
                ? 'bg-primary text-primary-foreground shadow-2xs'
                : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground'
            }`}
          >
            <DollarSign className="w-3.5 h-3.5" />
            <span>Budget simulé</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('date')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
              activeTab === 'date'
                ? 'bg-primary text-primary-foreground shadow-2xs'
                : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground'
            }`}
          >
            <Calendar className="w-3.5 h-3.5" />
            <span>Date d&apos;analyse (as-of)</span>
          </button>
        </div>

        {/* Tab controls */}
        <div className="bg-muted/30 p-4 rounded-lg border border-border/70 mb-4">
          {activeTab === 'tolerance' && (
            <div>
              <label className="block text-xs font-medium text-foreground mb-2">
                Modifier la tolérance au risque (actuelle :{' '}
                <span className="font-semibold text-primary">{({ low: 'faible', low_moderate: 'faible à modérée', moderate: 'modérée', high: 'élevée' } as Record<string, string>)[currentProfile?.risk_tolerance || ''] || '—'}</span>)
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[
                  { val: 'low', label: 'Faible (cap 5%)' },
                  { val: 'low_moderate', label: 'Faible à modérée (cap 5%)' },
                  { val: 'moderate', label: 'Modérée (cap 7%)' },
                  { val: 'high', label: 'Élevée (cap 10%)' },
                ].map(({ val, label }) => (
                  <button
                    key={val}
                    type="button"
                    onClick={() => setTolerance(val)}
                    className={`p-2.5 rounded-md text-xs font-medium border text-center transition-all cursor-pointer ${
                      tolerance === val
                        ? 'border-primary bg-primary/10 text-primary font-semibold shadow-2xs'
                        : 'border-border bg-card text-muted-foreground hover:bg-muted/50 hover:text-foreground'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">
                Exemple : Passer de « modérée » à « élevée » déverrouille le plafond de risque sur le scénario plafonné.
              </p>
            </div>
          )}

          {activeTab === 'account_type' && (
            <div>
              <label className="block text-xs font-medium text-foreground mb-2">
                Changer le type de compte fiscal (actuel :{' '}
                <span className="font-semibold text-primary">{({ tfsa: 'CELI', rrsp: 'REER', fhsa: 'CELIAPP', resp: 'REEE', non_registered: 'non enregistré' } as Record<string, string>)[currentProfile?.account_type || 'non_registered'] || currentProfile?.account_type}</span>)
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                {[
                  { val: 'tfsa', label: "CELI (Libre d'impôt)" },
                  { val: 'rrsp', label: 'REER (Épargne-retraite)' },
                  { val: 'fhsa', label: 'CELIAPP (1re propriété)' },
                  { val: 'non_registered', label: 'Non enregistré' },
                  { val: 'mixed', label: 'Mixte (Asset location)' },
                ].map(({ val, label }) => (
                  <button
                    key={val}
                    type="button"
                    onClick={() => setAccountType(val)}
                    className={`p-2.5 rounded-md text-xs font-medium border text-center transition-all cursor-pointer ${
                      accountType === val
                        ? 'border-primary bg-primary/10 text-primary font-semibold shadow-2xs'
                        : 'border-border bg-card text-muted-foreground hover:bg-muted/50 hover:text-foreground'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">
                Simule l&apos;impact fiscal : retenue américaine de 15 % récupérable en REER mais non en CELI, crédit d&apos;impôt sur dividendes et imposition à 100 % des intérêts en non enregistré.
              </p>
            </div>
          )}

          {activeTab === 'exclude' && (
            <div>
              <label htmlFor="exclude-ticker-select" className="block text-xs font-medium text-foreground mb-1">
                Choisir un actif à exclure :
              </label>
              <div className="flex gap-2">
                <select
                  id="exclude-ticker-select"
                  value={tickerToExclude}
                  onChange={(e) => setTickerToExclude(e.target.value)}
                  className="px-3 py-1.5 bg-card border border-border rounded-md text-xs font-mono font-medium text-foreground"
                >
                  {eligibleTickers.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <Input
                  type="text"
                  value={tickerToExclude}
                  onChange={(e) => setTickerToExclude(e.target.value.toUpperCase())}
                  placeholder="Autre ticker..."
                  className="w-32 text-xs font-mono"
                />
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">
                L&apos;actif sera filtré dès l&apos;étape de screening et retiré de l&apos;ensemble des scénarios construits.
              </p>
            </div>
          )}

          {activeTab === 'horizon' && (
            <div>
              <label htmlFor="horizon-input" className="block text-xs font-medium text-foreground mb-1">
                Horizon de placement (en années) : <span className="font-bold text-primary">{horizon} ans</span>
              </label>
              <input
                id="horizon-input"
                type="range"
                min="1"
                max="30"
                value={horizon}
                onChange={(e) => setHorizon(parseInt(e.target.value, 10))}
                className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
              />
            </div>
          )}

          {activeTab === 'budget' && (
            <div>
              <label htmlFor="budget-input" className="block text-xs font-medium text-foreground mb-1">
                Budget total à allouer (CAD) :
              </label>
              <Input
                id="budget-input"
                type="number"
                step="1000"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                className="w-48 text-xs font-medium"
              />
            </div>
          )}

          {activeTab === 'date' && (
            <div>
              <label htmlFor="date-input" className="block text-xs font-medium text-foreground mb-1">
                Date d&apos;analyse (as-of date, historique max 2026-11-12) :
              </label>
              <Input
                id="date-input"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                max="2026-11-12"
                className="w-48 text-xs font-medium"
              />
            </div>
          )}
        </div>

        {/* Action button */}
        <div className="flex justify-end">
          <Button
            type="button"
            onClick={handleApply}
            disabled={isRunning}
            className="gap-2 h-9 text-xs font-medium shadow-xs cursor-pointer"
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
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};
