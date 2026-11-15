import React, { useState, useEffect, useId } from 'react';
import { ArrowUpRight, Check, Plus, Trash2, AlertCircle } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface Step5Props {
  additionalNotes: string;
  setAdditionalNotes: (val: string) => void;
  currentHoldingsCsv: string;
  setCurrentHoldingsCsv: (val: string) => void;
  setCurrentHoldings: (val: Record<string, number>) => void;
  fictionalCapitalAcknowledged: boolean;
  setFictionalCapitalAcknowledged: (val: boolean) => void;
  onSave: () => void;
  onPrev: () => void;
}

interface PositionRow {
  id: string;
  ticker: string;
  weightPct: string;
}

const KNOWN_UNIVERSE = new Set([
  'RY.TO', 'TD.TO', 'MFC.TO', 'ENB.TO', 'CNQ.TO', 'CNR.TO', 'FTS.TO', 'ATD.TO',
  'SHOP.TO', 'CSU.TO', 'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA',
  'JPM', 'JNJ', 'PG', 'XOM', 'XIU.TO', 'SPY', 'QQQ', 'ESGV',
  'XBB.TO', 'ZST.TO', 'AGG', 'TLT', 'GLD', 'BTC-USD', 'ETH-USD',
]);

const PROXY_MAP: Record<string, string> = {
  CASH: 'ZST.TO',
  CAD: 'ZST.TO',
  USD: 'ZST.TO',
  'CASH.TO': 'ZST.TO',
  'PSA.TO': 'ZST.TO',
  'CSAV.TO': 'ZST.TO',
  'VCN.TO': 'XIU.TO',
  'XIC.TO': 'XIU.TO',
  'VCE.TO': 'XIU.TO',
  'ZAG.TO': 'XBB.TO',
  'VAB.TO': 'XBB.TO',
  VOO: 'SPY',
  IVV: 'SPY',
  VTI: 'SPY',
  XLK: 'QQQ',
  VGT: 'QQQ',
  BND: 'AGG',
};

export const Step5AdditionalInfo: React.FC<Step5Props> = ({
  additionalNotes,
  setAdditionalNotes,
  currentHoldingsCsv,
  setCurrentHoldingsCsv,
  setCurrentHoldings,
  fictionalCapitalAcknowledged,
  setFictionalCapitalAcknowledged,
  onSave,
  onPrev,
}) => {
  const baseId = useId();

  // Parse existing CSV into initial rows if any
  const [positions, setPositions] = useState<PositionRow[]>(() => {
    if (!currentHoldingsCsv) return [];
    const rows: PositionRow[] = [];
    const lines = currentHoldingsCsv.split('\n');
    lines.forEach((line, idx) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) return;
      const parts = trimmed.split(/[,;\t]+/);
      if (parts.length >= 2) {
        const ticker = parts[0].trim().toUpperCase().replace('$', '');
        const rawVal = parts[1].trim().replace('%', '').replace(',', '.');
        rows.push({
          id: `${baseId}-${idx}`,
          ticker,
          weightPct: rawVal,
        });
      }
    });
    return rows;
  });

  // Sync positions to parent state
  useEffect(() => {
    const holdings: Record<string, number> = {};
    const csvLines: string[] = [];

    positions.forEach((p) => {
      const cleanTicker = p.ticker.trim().toUpperCase().replace('$', '');
      const parsedWeight = parseFloat(p.weightPct.replace(',', '.'));
      if (cleanTicker && !isNaN(parsedWeight) && parsedWeight > 0) {
        holdings[cleanTicker] = parsedWeight / 100;
        csvLines.push(`${cleanTicker}, ${parsedWeight}%`);
      }
    });

    setCurrentHoldings(holdings);
    setCurrentHoldingsCsv(csvLines.join('\n'));
  }, [positions, setCurrentHoldings, setCurrentHoldingsCsv]);

  const handleAddPosition = () => {
    setPositions((prev) => [
      ...prev,
      { id: `${Date.now()}-${Math.random()}`, ticker: '', weightPct: '' },
    ]);
  };

  const handleUpdatePosition = (id: string, field: 'ticker' | 'weightPct', value: string) => {
    setPositions((prev) =>
      prev.map((row) => {
        if (row.id !== id) return row;
        return {
          ...row,
          [field]: field === 'ticker' ? value.toUpperCase().replace('$', '') : value,
        };
      })
    );
  };

  const handleRemovePosition = (id: string) => {
    setPositions((prev) => prev.filter((row) => row.id !== id));
  };

  const totalWeight = positions.reduce((acc, p) => {
    const val = parseFloat(p.weightPct.replace(',', '.'));
    return acc + (isNaN(val) ? 0 : val);
  }, 0);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm sm:text-base font-semibold text-foreground tracking-tight">
          05 / Portefeuille existant & contexte
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Titres déjà détenus, contraintes fiscales ou contexte spécifique (facultatif).
        </p>
      </div>

      {/* Interactive Line-Item Positions Builder */}
      <div className="border border-border rounded-xl p-3.5 bg-card space-y-3 shadow-2xs">
        <div className="flex items-center justify-between">
          <div>
            <label className="block text-xs font-semibold text-foreground">
              Positions du portefeuille actuel (facultatif)
            </label>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Ajoutez les titres que vous détenez déjà pour éviter la surconcentration involontaire.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleAddPosition}
            className="h-7 text-xs gap-1 cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Ajouter une position</span>
          </Button>
        </div>

        {positions.length === 0 ? (
          <div className="py-4 text-center border border-dashed border-border/70 rounded-lg bg-muted/20">
            <p className="text-xs text-muted-foreground">
              Aucune position actuelle renseignée.
            </p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleAddPosition}
              className="mt-1 h-7 text-xs text-primary hover:text-primary/90 cursor-pointer"
            >
              + Ajouter une première position
            </Button>
          </div>
        ) : (
          <div className="space-y-2 pt-1">
            {positions.map((pos, idx) => {
              const clean = pos.ticker.trim().toUpperCase();
              const inUniverse = clean && KNOWN_UNIVERSE.has(clean);
              const proxy = clean && PROXY_MAP[clean];

              return (
                <div
                  key={pos.id}
                  className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 p-2 bg-muted/30 border border-border/60 rounded-lg"
                >
                  <div className="flex-1 flex items-center gap-2">
                    <span className="text-[11px] font-mono text-muted-foreground w-4 text-center">
                      {idx + 1}
                    </span>
                    <Input
                      type="text"
                      value={pos.ticker}
                      onChange={(e) => handleUpdatePosition(pos.id, 'ticker', e.target.value)}
                      placeholder="Symbole (ex: XIU.TO, TSLA, AAPL)"
                      className="h-8 text-xs font-mono uppercase bg-background"
                    />
                  </div>

                  <div className="flex items-center gap-2 sm:w-48">
                    <div className="relative flex-1">
                      <Input
                        type="number"
                        min="0"
                        max="100"
                        step="1"
                        value={pos.weightPct}
                        onChange={(e) => handleUpdatePosition(pos.id, 'weightPct', e.target.value)}
                        placeholder="% part"
                        className="h-8 text-xs font-mono pr-7 bg-background"
                      />
                      <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground pointer-events-none">
                        %
                      </span>
                    </div>

                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => handleRemovePosition(pos.id)}
                      className="h-8 w-8 text-muted-foreground hover:text-destructive shrink-0 cursor-pointer"
                      title="Supprimer cette position"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>

                  {clean && (
                    <div className="sm:hidden flex items-center pl-6 text-[10px]">
                      {inUniverse ? (
                        <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                          ✓ Univers vérifié
                        </span>
                      ) : proxy ? (
                        <span className="text-amber-600 dark:text-amber-400 font-medium">
                          → Proxy {proxy}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">
                          Hors univers (non analysé)
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            <div className="flex items-center justify-between pt-1 px-1 text-xs">
              <span className="text-muted-foreground">
                Total des positions :{' '}
                <span className={cn('font-semibold', totalWeight > 100 ? 'text-destructive' : 'text-foreground')}>
                  {totalWeight} %
                </span>
              </span>

              {totalWeight > 100 && (
                <span className="text-[11px] text-destructive flex items-center gap-1 font-medium">
                  <AlertCircle className="w-3 h-3" />
                  Le total dépasse 100 %
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Free-text Context Textarea */}
      <div>
        <label htmlFor="notes-input" className="block text-xs font-medium text-foreground mb-1.5">
          Contexte particulier (facultatif)
        </label>
        <Textarea
          id="notes-input"
          rows={2}
          value={additionalNotes}
          onChange={(e) => setAdditionalNotes(e.target.value)}
          placeholder="Exemple : Projets de vie, contraintes fiscales, horizon spécifique ou remarques libres."
          className="resize-none text-xs sm:text-sm font-normal"
        />
        <p className="text-[11px] text-muted-foreground mt-1">
          Précisez tout élément utile pour adapter la simulation à votre situation.
        </p>
      </div>

      {/* Fictional acknowledgment box */}
      <div
        onClick={() => setFictionalCapitalAcknowledged(!fictionalCapitalAcknowledged)}
        className={cn(
          "p-3 rounded-lg flex items-start gap-2.5 cursor-pointer select-none transition-colors border",
          fictionalCapitalAcknowledged
            ? "bg-sky-50/50 dark:bg-sky-950/30 border-sky-500/70 dark:border-sky-500/80 shadow-2xs"
            : "bg-muted/30 border-border/60 hover:bg-muted/50"
        )}
      >
        <div
          className={cn(
            "w-3.5 h-3.5 rounded flex items-center justify-center shrink-0 mt-0.5 transition-colors",
            fictionalCapitalAcknowledged
              ? "bg-foreground text-background"
              : "border border-muted-foreground/40 bg-background"
          )}
        >
          {fictionalCapitalAcknowledged && <Check className="w-2.5 h-2.5 stroke-[3]" />}
        </div>
        <p className="text-xs text-foreground leading-snug">
          J’utilise un profil et un capital simulés. Je comprends qu’aucune transaction réelle ne sera exécutée et qu’il ne s’agit pas d’un conseil financier personnalisé. <span className="text-destructive">*</span>
        </p>
      </div>

      {/* Save button & Back link */}
      <div className="space-y-2 pt-1">
        <Button
          type="button"
          onClick={onSave}
          disabled={!fictionalCapitalAcknowledged}
          className="w-full h-10 text-xs sm:text-sm font-medium cursor-pointer flex items-center justify-center gap-1.5"
        >
          <span>Enregistrer mon profil et continuer</span>
          <ArrowUpRight className="w-3.5 h-3.5" />
        </Button>

        <div className="flex justify-center">
          <button
            type="button"
            onClick={onPrev}
            className="text-xs text-muted-foreground hover:text-foreground py-0.5 font-normal transition-colors cursor-pointer"
          >
            ← Modifier les étapes précédentes
          </button>
        </div>
      </div>
    </div>
  );
};
