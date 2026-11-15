import React, { useState, useEffect, useId } from 'react';
import { ArrowUpRight, Check, Plus, Trash2, AlertCircle, AlertTriangle } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { RadioCard } from './RadioCard';
import { SegmentedControl } from './SegmentedControl';
import { cn } from '@/lib/utils';
import { fetchUniverse } from '../../api';
import { UniverseAsset } from '../../types';
import { HOLDINGS_PRESENCE_OPTIONS, UNIVERSE_FALLBACK, questionnaireWarnings } from '@/lib/questionnaireCodes';

interface Step5Props {
  additionalNotes: string;
  setAdditionalNotes: (val: string) => void;
  currentHoldingsCsv: string;
  setCurrentHoldingsCsv: (val: string) => void;
  setCurrentHoldings: (val: Record<string, number>) => void;
  hasExistingHoldings: 'none' | 'some' | '';
  setHasExistingHoldings: (val: 'none' | 'some' | '') => void;
  holdingsUnit: 'pct' | 'cad';
  setHoldingsUnit: (val: 'pct' | 'cad') => void;
  setUnanalysedConfirmed: (val: string[]) => void;
  initialUnanalysedConfirmed?: string[];
  fictionalCapitalAcknowledged: boolean;
  setFictionalCapitalAcknowledged: (val: boolean) => void;
  onSave: () => void;
  onPrev: () => void;
}

interface PositionRow {
  id: string;
  ticker: string;
  value: string;
  confirmedUnanalysed: boolean;
}

/** Spoken names and short symbols the engine maps to a universe ticker (alphaforge/holdings.py). */
const TICKER_ALIASES: Record<string, string> = {
  BTC: 'BTC-USD',
  BITCOIN: 'BTC-USD',
  XBT: 'BTC-USD',
  ETH: 'ETH-USD',
  ETHER: 'ETH-USD',
  ETHEREUM: 'ETH-USD',
};

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
  IBIT: 'BTC-USD',
  FBTC: 'BTC-USD',
  'BTCC.TO': 'BTC-USD',
  'BTCC.B.TO': 'BTC-USD',
  'ETHH.TO': 'ETH-USD',
};

type TickerStatus = { kind: 'universe'; ticker: string } | { kind: 'proxy'; proxy: string } | { kind: 'unknown' };

/** Mirrors `normalise_ticker` on the server: exact, alias, "RY" -> "RY.TO", proxy, else unknown. */
function resolveTicker(raw: string, universe: UniverseAsset[]): TickerStatus {
  const key = raw.trim().toUpperCase().replace('$', '');
  if (!key) return { kind: 'unknown' };
  const tickers = universe.map((u) => u.ticker);
  if (tickers.includes(key)) return { kind: 'universe', ticker: key };
  if (TICKER_ALIASES[key] && tickers.includes(TICKER_ALIASES[key])) {
    return { kind: 'universe', ticker: TICKER_ALIASES[key] };
  }
  const byRoot = tickers.find((t) => t.split('.')[0] === key || t.split('-')[0] === key);
  if (byRoot) return { kind: 'universe', ticker: byRoot };
  if (PROXY_MAP[key]) return { kind: 'proxy', proxy: PROXY_MAP[key] };
  return { kind: 'unknown' };
}

const parseNum = (s: string): number => {
  const v = parseFloat(s.replace(/\s/g, '').replace(',', '.'));
  return isNaN(v) ? 0 : v;
};

const fmtCad = (v: number) => `${Math.round(v).toLocaleString('fr-CA')} $ CAD`;
const fmtPct = (v: number) => `${Math.round(v * 100) / 100} %`;

export const Step5AdditionalInfo: React.FC<Step5Props> = ({
  additionalNotes,
  setAdditionalNotes,
  currentHoldingsCsv,
  setCurrentHoldingsCsv,
  setCurrentHoldings,
  hasExistingHoldings,
  setHasExistingHoldings,
  holdingsUnit,
  setHoldingsUnit,
  setUnanalysedConfirmed,
  initialUnanalysedConfirmed = [],
  fictionalCapitalAcknowledged,
  setFictionalCapitalAcknowledged,
  onSave,
  onPrev,
}) => {
  const baseId = useId();
  const listId = `${baseId}-universe`;
  const [universe, setUniverse] = useState<UniverseAsset[]>(UNIVERSE_FALLBACK);

  useEffect(() => {
    let cancelled = false;
    fetchUniverse().then((rows) => {
      if (!cancelled) setUniverse(rows);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Parse existing CSV into initial rows if any ("XIU.TO, 40%" or "XIU.TO, 12000 $")
  const [positions, setPositions] = useState<PositionRow[]>(() => {
    if (!currentHoldingsCsv) return [];
    const rows: PositionRow[] = [];
    currentHoldingsCsv.split('\n').forEach((line, idx) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) return;
      const parts = trimmed.split(/[,;\t]+/);
      if (parts.length >= 2) {
        const ticker = parts[0].trim().toUpperCase().replace('$', '');
        const rawVal = parts[1].trim().replace('%', '').replace('$', '').trim().replace(',', '.');
        rows.push({
          id: `${baseId}-${idx}`,
          ticker,
          value: rawVal,
          confirmedUnanalysed: initialUnanalysedConfirmed.includes(ticker),
        });
      }
    });
    return rows;
  });

  const isCad = holdingsUnit === 'cad';

  // Sync positions to parent state
  useEffect(() => {
    const holdings: Record<string, number> = {};
    const csvLines: string[] = [];
    const confirmed: string[] = [];

    positions.forEach((p) => {
      const cleanTicker = p.ticker.trim().toUpperCase().replace('$', '');
      const v = parseNum(p.value);
      if (cleanTicker && v > 0) {
        holdings[cleanTicker] = isCad ? v : v / 100;
        csvLines.push(isCad ? `${cleanTicker}, ${v} $` : `${cleanTicker}, ${v}%`);
        if (p.confirmedUnanalysed) confirmed.push(cleanTicker);
      }
    });

    setCurrentHoldings(holdings);
    setCurrentHoldingsCsv(csvLines.join('\n'));
    setUnanalysedConfirmed(confirmed);
  }, [positions, isCad, setCurrentHoldings, setCurrentHoldingsCsv, setUnanalysedConfirmed]);

  const handleAddPosition = () => {
    if (hasExistingHoldings !== 'some') setHasExistingHoldings('some');
    setPositions((prev) => [
      ...prev,
      { id: `${Date.now()}-${Math.random()}`, ticker: '', value: '', confirmedUnanalysed: false },
    ]);
  };

  const handleUpdatePosition = (id: string, field: 'ticker' | 'value', value: string) => {
    setPositions((prev) =>
      prev.map((row) => {
        if (row.id !== id) return row;
        if (field === 'ticker') {
          return { ...row, ticker: value.toUpperCase().replace('$', ''), confirmedUnanalysed: false };
        }
        return { ...row, value };
      })
    );
  };

  const handleConfirmUnanalysed = (id: string, confirmed: boolean) => {
    setPositions((prev) => prev.map((row) => (row.id === id ? { ...row, confirmedUnanalysed: confirmed } : row)));
  };

  const handleRemovePosition = (id: string) => {
    setPositions((prev) => prev.filter((row) => row.id !== id));
  };

  const filledRows = positions.filter((p) => p.ticker.trim() && parseNum(p.value) > 0);
  const total = filledRows.reduce((acc, p) => acc + parseNum(p.value), 0);
  const overHundred = !isCad && total > 100 + 1e-9;
  const cashRemainder = !isCad ? Math.max(0, 100 - total) : 0;
  const unconfirmedUnknown = positions.filter(
    (p) => p.ticker.trim() && resolveTicker(p.ticker, universe).kind === 'unknown' && !p.confirmedUnanalysed
  );
  const warnings = questionnaireWarnings({ hasExistingHoldings, holdingsCount: filledRows.length });
  const holdingsContradiction = hasExistingHoldings === 'none' && filledRows.length > 0;

  const blockers: string[] = [];
  if (overHundred) blockers.push('Le total des positions dépasse 100 %.');
  if (unconfirmedUnknown.length > 0) {
    blockers.push(
      `Confirmez « non analysé » pour : ${unconfirmedUnknown.map((p) => p.ticker.trim()).join(', ')}.`
    );
  }
  if (holdingsContradiction) blockers.push('« Aucun avoir » est coché alors que des positions sont listées.');
  const canSave = fictionalCapitalAcknowledged && blockers.length === 0;

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

      {/* Existing holdings: explicit answer so "Aucun avoir" can be checked against the list */}
      <div>
        <label className="block text-xs font-medium text-foreground mb-1.5">
          Détenez-vous déjà des placements à prendre en compte ?
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {HOLDINGS_PRESENCE_OPTIONS.map((opt) => (
            <RadioCard
              key={opt.code}
              label={opt.label}
              selected={hasExistingHoldings === opt.code}
              onClick={() => setHasExistingHoldings(opt.code as 'none' | 'some')}
            />
          ))}
        </div>
      </div>

      {/* Interactive Line-Item Positions Builder */}
      <div className="border border-border rounded-xl p-3.5 bg-card space-y-3 shadow-2xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <label className="block text-xs font-semibold text-foreground">
              Positions du portefeuille actuel (facultatif)
            </label>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Symboles de l’univers de 31 actifs proposés à la saisie ; tout autre symbole doit être confirmé
              « non analysé ».
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <SegmentedControl<'pct' | 'cad'>
              options={['pct', 'cad']}
              labels={{ pct: '% du portefeuille', cad: 'Montants $ CAD' }}
              value={holdingsUnit}
              onChange={setHoldingsUnit}
              className="h-8 min-w-[220px]"
            />
          </div>
        </div>

        <datalist id={listId}>
          {universe.map((u) => (
            <option key={u.ticker} value={u.ticker}>
              {u.name} · {u.asset_class}
            </option>
          ))}
        </datalist>

        {positions.length === 0 ? (
          <div className="py-6 text-center border border-dashed border-border/70 rounded-lg bg-muted/20 flex flex-col items-center justify-center gap-2.5">
            <p className="text-xs text-muted-foreground">
              Aucune position actuelle renseignée.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddPosition}
              className="h-8 text-xs gap-1.5 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Ajouter une position</span>
            </Button>
          </div>
        ) : (
          <div className="space-y-2 pt-1">
            {positions.map((pos, idx) => {
              const clean = pos.ticker.trim().toUpperCase();
              const status = clean ? resolveTicker(clean, universe) : null;
              const rowChecked = `${baseId}-${pos.id}-confirm`;

              return (
                <div
                  key={pos.id}
                  className="flex flex-col gap-2 p-2 bg-muted/30 border border-border/60 rounded-lg"
                >
                  <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                    <div className="flex-1 flex items-center gap-2">
                      <span className="text-[11px] font-mono text-muted-foreground w-4 text-center">
                        {idx + 1}
                      </span>
                      <Input
                        type="text"
                        list={listId}
                        value={pos.ticker}
                        onChange={(e) => handleUpdatePosition(pos.id, 'ticker', e.target.value)}
                        placeholder="Symbole (ex: XIU.TO, TSLA, BTC-USD)"
                        aria-label={`Symbole de la position ${idx + 1}`}
                        autoComplete="off"
                        className="h-8 text-xs font-mono uppercase bg-background"
                      />
                    </div>

                    <div className="flex items-center gap-2 sm:w-52">
                      <div className="relative flex-1">
                        <Input
                          type="number"
                          min="0"
                          max={isCad ? undefined : 100}
                          step={isCad ? '100' : '1'}
                          value={pos.value}
                          onChange={(e) => handleUpdatePosition(pos.id, 'value', e.target.value)}
                          placeholder={isCad ? 'Montant' : 'Part'}
                          aria-label={isCad ? `Montant en dollars canadiens de la position ${idx + 1}` : `Part en pourcentage de la position ${idx + 1}`}
                          className="h-8 text-xs font-mono pr-12 bg-background"
                        />
                        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground pointer-events-none">
                          {isCad ? '$ CAD' : '%'}
                        </span>
                      </div>

                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => handleRemovePosition(pos.id)}
                        className="h-8 w-8 text-muted-foreground hover:text-destructive shrink-0 cursor-pointer"
                        title="Supprimer cette position"
                        aria-label="Supprimer cette position"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>

                  {status && (
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pl-6 text-[11px]">
                      {status.kind === 'universe' ? (
                        <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 font-medium">
                          <Check className="w-3 h-3" />
                          Univers vérifié{status.ticker !== clean ? ` · ${status.ticker}` : ''}
                        </span>
                      ) : status.kind === 'proxy' ? (
                        <span className="inline-flex items-center rounded-full px-2 py-0.5 bg-amber-500/10 text-amber-700 dark:text-amber-400 font-medium">
                          Analysé via le substitut {status.proxy}
                        </span>
                      ) : (
                        <>
                          <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 bg-destructive/10 text-destructive font-medium">
                            <AlertCircle className="w-3 h-3" />
                            Hors univers · non analysé
                          </span>
                          <label htmlFor={rowChecked} className="inline-flex items-center gap-1.5 cursor-pointer text-foreground">
                            <input
                              id={rowChecked}
                              type="checkbox"
                              checked={pos.confirmedUnanalysed}
                              onChange={(e) => handleConfirmUnanalysed(pos.id, e.target.checked)}
                              className="h-3.5 w-3.5 accent-foreground"
                            />
                            <span>Je confirme : {clean} sera conservé à sa part déclarée, sans analyse</span>
                          </label>
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            <div className="flex items-center justify-between pt-1">
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

            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 pt-1 px-1 text-xs border-t border-border/50">
              {isCad ? (
                <span className="text-muted-foreground">
                  Total déclaré :{' '}
                  <span className="font-semibold text-foreground">{fmtCad(total)}</span>
                  <span className="text-[11px]"> · chaque position sera convertie en part du total</span>
                </span>
              ) : (
                <span className="text-muted-foreground">
                  Total des positions :{' '}
                  <span className={cn('font-semibold', overHundred ? 'text-destructive' : 'text-foreground')}>
                    {fmtPct(total)}
                  </span>
                  {!overHundred && (
                    <span className="text-[11px]"> · reste en liquidités : {fmtPct(cashRemainder)}</span>
                  )}
                </span>
              )}

              {overHundred && (
                <span className="text-[11px] text-destructive flex items-center gap-1 font-medium">
                  <AlertCircle className="w-3 h-3" />
                  Le total dépasse 100 % : corrigez les parts avant d’enregistrer
                </span>
              )}
            </div>
          </div>
        )}

        {warnings.length > 0 && (
          <div
            role="alert"
            className="p-2.5 rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300 text-xs space-y-1"
          >
            {warnings.map((w) => (
              <p key={w} className="flex items-start gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>{w}</span>
              </p>
            ))}
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
          disabled={!canSave}
          className="w-full h-10 text-xs sm:text-sm font-medium cursor-pointer flex items-center justify-center gap-1.5"
        >
          <span>Enregistrer mon profil et continuer</span>
          <ArrowUpRight className="w-3.5 h-3.5" />
        </Button>
        {blockers.length > 0 && (
          <ul className="text-[11px] text-destructive text-center space-y-0.5">
            {blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        )}

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
