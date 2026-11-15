import React, { useMemo } from 'react';
import { ArrowUpRight, Check, ListFilter } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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

function parseHoldingsCsv(csvText: string): Record<string, number> {
  const result: Record<string, number> = {};
  if (!csvText) return result;
  const lines = csvText.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#') || trimmed.startsWith('//')) continue;
    let parts: string[] = [];
    if (trimmed.includes(';')) parts = trimmed.split(';');
    else if (trimmed.includes('\t')) parts = trimmed.split('\t');
    else if (trimmed.includes(',')) parts = trimmed.split(',');
    else parts = trimmed.split(/\s+/);

    if (parts.length >= 2) {
      const ticker = parts[0].trim().toUpperCase().replace('$', '');
      if (['TICKER', 'SYMBOL', 'ACTIF', 'TITRE', 'NOM', 'ASSET'].includes(ticker)) continue;
      const rawVal = parts[1].trim().replace('$', '').replace(/\s/g, '').replace('%', '').replace(',', '.');
      const val = parseFloat(rawVal);
      if (!isNaN(val) && val > 0) {
        result[ticker] = val;
      }
    }
  }
  return result;
}

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
  const parsedHoldings = useMemo(() => {
    const parsed = parseHoldingsCsv(currentHoldingsCsv);
    setCurrentHoldings(parsed);
    return parsed;
  }, [currentHoldingsCsv, setCurrentHoldings]);

  const parsedEntries = Object.entries(parsedHoldings);

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

      {/* CSV paste box for current_holdings (#120) */}
      <div className="border border-border/80 rounded-lg p-3 bg-muted/20 space-y-2">
        <div className="flex items-center justify-between">
          <label htmlFor="csv-holdings-input" className="block text-xs font-semibold text-foreground">
            Portefeuille actuel (CSV facultatif)
          </label>
          {parsedEntries.length > 0 && (
            <Badge variant="secondary" className="text-[10px] py-0 px-1.5 font-mono">
              {parsedEntries.length} position(s) détectée(s)
            </Badge>
          )}
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Collez vos positions sous la forme <code>Symbole, Montant CAD</code> ou <code>Symbole, Poids %</code> (ex: <code>XIU.TO, 50000</code>).
          Les actifs hors univers sont associés à un proxy ou listés comme non analysés.
        </p>
        <Textarea
          id="csv-holdings-input"
          rows={3}
          value={currentHoldingsCsv}
          onChange={(e) => setCurrentHoldingsCsv(e.target.value)}
          placeholder={`Exemple :\nXIU.TO, 50000\nZST.TO, 50000\nou\nAAPL, 30%\nMSFT, 30%\nZST.TO, 40%`}
          className="font-mono text-xs resize-none"
        />

        {parsedEntries.length > 0 && (
          <div className="mt-2 pt-2 border-t border-border/50 space-y-1">
            <span className="text-[11px] font-medium text-foreground/80 flex items-center gap-1">
              <ListFilter className="w-3 h-3 text-primary" />
              Aperçu des positions analysées :
            </span>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {parsedEntries.map(([ticker, val]) => {
                const inUniverse = KNOWN_UNIVERSE.has(ticker);
                const proxy = PROXY_MAP[ticker];
                return (
                  <Badge
                    key={ticker}
                    variant="outline"
                    className={cn(
                      'text-[10px] font-mono py-0.5 px-2',
                      inUniverse
                        ? 'border-emerald-500/40 text-emerald-700 dark:text-emerald-300 bg-emerald-500/10'
                        : proxy
                        ? 'border-amber-500/40 text-amber-700 dark:text-amber-300 bg-amber-500/10'
                        : 'border-muted-foreground/30 text-muted-foreground bg-muted/40'
                    )}
                  >
                    {ticker} ({val.toLocaleString('fr-CA')})
                    {proxy && ` → proxy ${proxy}`}
                    {!inUniverse && !proxy && ' (non analysé)'}
                  </Badge>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Free-text Context Textarea */}
      <div>
        <label htmlFor="notes-input" className="block text-xs font-medium text-foreground mb-1.5">
          Positions actuelles ou contexte particulier (facultatif)
        </label>
        <Textarea
          id="notes-input"
          rows={2}
          value={additionalNotes}
          onChange={(e) => setAdditionalNotes(e.target.value)}
          placeholder="Exemple : Je détiens déjà des actions Banque Nationale et Nvidia. Je souhaite diversifier sans surpondérer la tech."
          className="resize-none text-xs sm:text-sm font-normal"
        />
        <p className="text-[11px] text-muted-foreground mt-1">
          Permet au moteur d’évaluer la concentration globale et d’éviter les doublons involontaires.
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
          className="w-full h-9 rounded-md text-xs sm:text-sm font-medium flex items-center justify-center gap-1.5 shadow-xs cursor-pointer"
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

        <p className="text-center text-[11px] text-muted-foreground/80 pt-0.5">
          Vos réponses permettent de personnaliser les contraintes d’allocation.
        </p>
      </div>
    </div>
  );
};
