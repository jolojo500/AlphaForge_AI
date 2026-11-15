import React, { useState } from 'react';
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
import { AuthUser } from '../types';
import { login } from '../api';
import { LogIn, UserCheck, AlertCircle, Loader2 } from 'lucide-react';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (user: AuthUser) => void;
}

const DEMO_PRESETS = [
  { username: 'amira', label: 'Amira · Croissance 15 ans' },
  { username: 'mateo', label: 'Mateo · Équilibré ESG' },
  { username: 'robert', label: 'Robert · Idée TSLA 25%' },
];

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Veuillez saisir votre nom d’utilisateur et mot de passe.');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const res = await login(username.trim(), password);
      onSuccess(res.user);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Échec de connexion.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectPreset = (presetUser: string) => {
    setUsername(presetUser);
    setPassword('AlphaForge2026!');
    setError(null);
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md p-6 bg-card border border-border rounded-xl shadow-2xl">
        <DialogHeader className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <LogIn className="h-5 w-5" />
            </div>
            <DialogTitle className="text-xl font-bold tracking-tight">
              Connexion sécurisée
            </DialogTitle>
          </div>
          <DialogDescription className="text-sm text-muted-foreground">
            Accédez à vos profils d’investisseur personnalisés et à l’historique privé de vos analyses.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="flex items-center gap-2 p-3 text-sm rounded-lg bg-destructive/10 text-destructive border border-destructive/20">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <Label htmlFor="auth-username" className="text-xs font-semibold uppercase text-muted-foreground">
              Nom d’utilisateur ou courriel
            </Label>
            <Input
              id="auth-username"
              type="text"
              autoComplete="username"
              placeholder="ex: amira ou amira@alphaforge.demo"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="auth-password" className="text-xs font-semibold uppercase text-muted-foreground">
              Mot de passe
            </Label>
            <Input
              id="auth-password"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              required
            />
          </div>

          <Button type="submit" className="w-full flex items-center justify-center gap-2" disabled={isLoading}>
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Connexion en cours...
              </>
            ) : (
              <>
                <LogIn className="h-4 w-4" />
                Se connecter
              </>
            )}
          </Button>
        </form>

        <div className="pt-4 border-t border-border/60">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Comptes de démonstration (clients fictifs)
            </span>
          </div>
          <div className="grid grid-cols-1 gap-1.5">
            {DEMO_PRESETS.map((p) => (
              <button
                key={p.username}
                type="button"
                onClick={() => handleSelectPreset(p.username)}
                className="flex items-center justify-between px-3 py-2 text-xs rounded-lg border border-border/50 hover:border-primary/40 hover:bg-muted/50 transition-colors text-left"
              >
                <div className="flex items-center gap-2">
                  <UserCheck className="h-3.5 w-3.5 text-primary" />
                  <span className="font-medium text-foreground">{p.label}</span>
                </div>
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4">
                  Compte de démonstration
                </Badge>
              </button>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground mt-2 text-center">
            Mot de passe de démonstration : <code className="font-mono text-xs">AlphaForge2026!</code>
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
};
