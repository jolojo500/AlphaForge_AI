import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { AuthUser, UserProfileData } from '../types';
import { fetchUserProfile, updateUserProfile } from '../api';
import {
  User,
  ShieldCheck,
  Save,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Briefcase,
  Layers,
} from 'lucide-react';

interface ProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: AuthUser | null;
  onProfileUpdated?: () => void;
}

export const ProfileModal: React.FC<ProfileModalProps> = ({
  isOpen,
  onClose,
  currentUser,
  onProfileUpdated,
}) => {
  const [profileData, setProfileData] = useState<UserProfileData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form states
  const [objective, setObjective] = useState('growth');
  const [horizonYears, setHorizonYears] = useState(10);
  const [riskTolerance, setRiskTolerance] = useState('moderate');
  const [riskCapacity, setRiskCapacity] = useState('moderate');
  const [budgetCad, setBudgetCad] = useState<number | ''>(100000);
  const [accountType, setAccountType] = useState('CELI');
  const [currentHoldingsText, setCurrentHoldingsText] = useState('');
  const [notes, setNotes] = useState('');

  useEffect(() => {
    if (!isOpen || !currentUser) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setSuccessMessage(null);

    fetchUserProfile()
      .then((data) => {
        if (cancelled) return;
        setProfileData(data);
        const p = data.profile || {};
        if (p.objective) setObjective(String(p.objective));
        if (p.horizon_years) setHorizonYears(Number(p.horizon_years));
        if (p.risk_tolerance) setRiskTolerance(String(p.risk_tolerance));
        if (p.risk_capacity) setRiskCapacity(String(p.risk_capacity));
        if (p.budget_cad !== undefined && p.budget_cad !== null) {
          setBudgetCad(Number(p.budget_cad));
        }
        if (data.account_type) setAccountType(data.account_type);
        if (data.current_holdings) {
          setCurrentHoldingsText(JSON.stringify(data.current_holdings, null, 2));
        } else {
          setCurrentHoldingsText('');
        }
        if (p.notes) setNotes(String(p.notes));
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Erreur de chargement du profil.');
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, currentUser]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError(null);
    setSuccessMessage(null);

    let parsedHoldings = null;
    if (currentHoldingsText.trim()) {
      try {
        parsedHoldings = JSON.parse(currentHoldingsText.trim());
      } catch {
        setError('Format JSON invalide pour les avoirs actuels (ex: {"XIU": 0.4, "XBB": 0.6}).');
        setIsSaving(false);
        return;
      }
    }

    const updatedProfile = {
      ...(profileData?.profile || {}),
      objective,
      horizon_years: horizonYears,
      risk_tolerance: riskTolerance,
      risk_capacity: riskCapacity,
      budget_cad: budgetCad === '' ? null : Number(budgetCad),
      notes,
    };

    try {
      const res = await updateUserProfile({
        profile: updatedProfile,
        account_type: accountType || null,
        current_holdings: parsedHoldings,
      });
      setProfileData(res);
      setSuccessMessage('Profil d’investisseur enregistré et synchronisé avec le serveur DynamoDB.');
      if (onProfileUpdated) onProfileUpdated();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Échec de l’enregistrement du profil.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto p-6 bg-card border border-border rounded-xl shadow-2xl">
        <DialogHeader className="space-y-1">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg bg-primary/10 text-primary">
                <User className="h-5 w-5" />
              </div>
              <DialogTitle className="text-xl font-bold tracking-tight">
                Mon profil d’investisseur
              </DialogTitle>
            </div>
            {currentUser?.is_advisor && (
              <Badge variant="outline" className="flex items-center gap-1 border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10">
                <ShieldCheck className="h-3.5 w-3.5" />
                Conseiller agréé
              </Badge>
            )}
          </div>
          <DialogDescription className="text-sm text-muted-foreground">
            Profil KYC et paramètres de simulation stockés côté serveur dans Amazon DynamoDB.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="py-12 flex flex-col items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <p className="text-sm">Chargement du profil...</p>
          </div>
        ) : (
          <form onSubmit={handleSave} className="space-y-5 pt-3">
            {error && (
              <div className="flex items-center gap-2 p-3 text-sm rounded-lg bg-destructive/10 text-destructive border border-destructive/20">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {successMessage && (
              <div className="flex items-center gap-2 p-3 text-sm rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span>{successMessage}</span>
              </div>
            )}

            {/* Identité */}
            <div className="p-3.5 rounded-lg bg-muted/40 border border-border/50 flex items-center justify-between">
              <div>
                <p className="text-xs uppercase font-semibold text-muted-foreground tracking-wider">Compte utilisateur</p>
                <p className="text-base font-semibold text-foreground">{currentUser?.username}</p>
                {currentUser?.email && <p className="text-xs text-muted-foreground">{currentUser.email}</p>}
              </div>
              <Badge variant="secondary" className="capitalize text-xs">
                {currentUser?.is_advisor ? 'Conseiller' : 'Client investisseur'}
              </Badge>
            </div>

            {/* Paramètres financiers */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="accountType" className="text-xs font-semibold uppercase text-muted-foreground">
                  Type de compte fiscal (#118)
                </Label>
                <select
                  id="accountType"
                  value={accountType}
                  onChange={(e) => setAccountType(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="CELI">CELI (Compte d’épargne libre d’impôt)</option>
                  <option value="REER">REER (Régime enregistré d’épargne-retraite)</option>
                  <option value="Non enregistré">Compte non enregistré (Imposable)</option>
                  <option value="CELIAPP">CELIAPP (Première propriété)</option>
                  <option value="CRI">CRI (Compte de retraite immobilisé)</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="objective" className="text-xs font-semibold uppercase text-muted-foreground">
                  Objectif principal
                </Label>
                <select
                  id="objective"
                  value={objective}
                  onChange={(e) => setObjective(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="growth">Croissance du capital</option>
                  <option value="balanced">Équilibré (Croissance & protection)</option>
                  <option value="capital_preservation">Préservation du capital</option>
                  <option value="income">Génération de revenus</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="horizonYears" className="text-xs font-semibold uppercase text-muted-foreground">
                  Horizon d’investissement (années)
                </Label>
                <Input
                  id="horizonYears"
                  type="number"
                  min={1}
                  max={40}
                  value={horizonYears}
                  onChange={(e) => setHorizonYears(Number(e.target.value))}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="budgetCad" className="text-xs font-semibold uppercase text-muted-foreground">
                  Capital simulé (CAD)
                </Label>
                <Input
                  id="budgetCad"
                  type="number"
                  placeholder="ex: 100000"
                  value={budgetCad}
                  onChange={(e) => setBudgetCad(e.target.value === '' ? '' : Number(e.target.value))}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="riskTolerance" className="text-xs font-semibold uppercase text-muted-foreground">
                  Tolérance au risque (psychologique)
                </Label>
                <select
                  id="riskTolerance"
                  value={riskTolerance}
                  onChange={(e) => setRiskTolerance(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="low">Faible</option>
                  <option value="low_moderate">Faible à modéré</option>
                  <option value="moderate">Modéré</option>
                  <option value="high">Élevé</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="riskCapacity" className="text-xs font-semibold uppercase text-muted-foreground">
                  Capacité de risque (financière)
                </Label>
                <select
                  id="riskCapacity"
                  value={riskCapacity}
                  onChange={(e) => setRiskCapacity(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="low">Faible</option>
                  <option value="moderate">Modéré</option>
                  <option value="high">Élevée</option>
                </select>
              </div>
            </div>

            {/* Avoirs actuels */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="currentHoldings" className="text-xs font-semibold uppercase text-muted-foreground flex items-center gap-1.5">
                  <Briefcase className="h-3.5 w-3.5 text-primary" />
                  Avoirs actuels (#120, format JSON optionnel)
                </Label>
                <span className="text-[11px] text-muted-foreground">ex: {"{\"XIU\": 0.3, \"XBB\": 0.7}"}</span>
              </div>
              <Input
                id="currentHoldings"
                placeholder='ex: {"XIU": 0.4, "XBB": 0.6}'
                value={currentHoldingsText}
                onChange={(e) => setCurrentHoldingsText(e.target.value)}
              />
            </div>

            {/* Remarques */}
            <div className="space-y-1.5">
              <Label htmlFor="notes" className="text-xs font-semibold uppercase text-muted-foreground flex items-center gap-1.5">
                <Layers className="h-3.5 w-3.5 text-primary" />
                Remarques et contraintes particulières
              </Label>
              <Textarea
                id="notes"
                rows={2}
                placeholder="ex: Préférence techno, exclusion des énergies fossiles..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
              <Button type="button" variant="outline" onClick={onClose} disabled={isSaving}>
                Fermer
              </Button>
              <Button type="submit" disabled={isSaving} className="flex items-center gap-2">
                {isSaving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Enregistrement...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" />
                    Enregistrer les modifications
                  </>
                )}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
};
