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
import { AuthUser } from '../types';
import { login, register } from '../api';
import { LogIn, UserPlus, AlertCircle, Loader2 } from 'lucide-react';
import { useLanguage } from '@/context/LanguageContext';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (user: AuthUser) => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const { language } = useLanguage();
  const isEn = language === 'en';

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetForm = () => {
    setUsername('');
    setEmail('');
    setPassword('');
    setError(null);
  };

  const handleToggleMode = () => {
    setMode((prev) => (prev === 'login' ? 'register' : 'login'));
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError(
        isEn
          ? 'Please enter your username and password.'
          : 'Veuillez saisir votre nom d’utilisateur et mot de passe.'
      );
      return;
    }
    if (mode === 'register' && password.length < 6) {
      setError(
        isEn
          ? 'Password must be at least 6 characters.'
          : 'Le mot de passe doit comporter au moins 6 caractères.'
      );
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      if (mode === 'login') {
        const res = await login(username.trim(), password);
        onSuccess(res.user);
      } else {
        const res = await register(username.trim(), password, email.trim() || undefined);
        onSuccess(res.user);
      }
      resetForm();
      onClose();
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : isEn
          ? 'Authentication failed.'
          : 'Échec de connexion.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) {
          resetForm();
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-md p-6 bg-card border border-border rounded-xl shadow-2xl">
        <DialogHeader className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              {mode === 'login' ? <LogIn className="h-5 w-5" /> : <UserPlus className="h-5 w-5" />}
            </div>
            <DialogTitle className="text-lg sm:text-xl font-bold tracking-tight">
              {mode === 'login'
                ? isEn
                  ? 'Secure Login'
                  : 'Connexion sécurisée'
                : isEn
                ? 'Create an Account'
                : 'Créer un compte'}
            </DialogTitle>
          </div>
          <DialogDescription className="text-xs text-muted-foreground">
            {mode === 'login'
              ? isEn
                ? 'Access your saved profiles and analysis history.'
                : 'Accédez à vos profils enregistrés et à l’historique de vos analyses.'
              : isEn
              ? 'Register to save your profiles and financial simulations.'
              : 'Inscrivez-vous pour conserver vos profils et simulations financières.'}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="flex items-center gap-2 p-3 text-xs rounded-lg bg-destructive/10 text-destructive border border-destructive/20">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5 pt-1">
          <div className="space-y-1">
            <Label htmlFor="auth-username" className="text-xs font-semibold uppercase text-muted-foreground">
              {isEn ? 'Username' : 'Nom d’utilisateur'}
            </Label>
            <Input
              id="auth-username"
              type="text"
              autoComplete="username"
              placeholder={isEn ? 'e.g. amira or robert' : 'ex: amira ou robert'}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
              className="text-xs sm:text-sm h-9"
              required
            />
          </div>

          {mode === 'register' && (
            <div className="space-y-1">
              <Label htmlFor="auth-email" className="text-xs font-semibold uppercase text-muted-foreground">
                {isEn ? 'Email (optional)' : 'Courriel (facultatif)'}
              </Label>
              <Input
                id="auth-email"
                type="email"
                autoComplete="email"
                placeholder={isEn ? 'e.g. user@example.com' : 'ex: utilisateur@example.com'}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading}
                className="text-xs sm:text-sm h-9"
              />
            </div>
          )}

          <div className="space-y-1">
            <Label htmlFor="auth-password" className="text-xs font-semibold uppercase text-muted-foreground">
              {isEn ? 'Password' : 'Mot de passe'}
            </Label>
            <Input
              id="auth-password"
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              className="text-xs sm:text-sm h-9"
              required
            />
          </div>

          <Button
            type="submit"
            className="w-full h-9 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 flex items-center justify-center gap-2 cursor-pointer shadow-xs transition-colors"
            disabled={isLoading}
          >
            {isLoading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>{isEn ? 'Processing...' : 'Traitement en cours...'}</span>
              </>
            ) : mode === 'login' ? (
              <>
                <LogIn className="h-3.5 w-3.5" />
                <span>{isEn ? 'Log In' : 'Se connecter'}</span>
              </>
            ) : (
              <>
                <UserPlus className="h-3.5 w-3.5" />
                <span>{isEn ? 'Create Account' : 'Créer mon compte'}</span>
              </>
            )}
          </Button>

          <div className="pt-2 text-center">
            <button
              type="button"
              onClick={handleToggleMode}
              disabled={isLoading}
              className="text-xs text-muted-foreground hover:text-foreground font-normal transition-colors cursor-pointer"
            >
              {mode === 'login'
                ? isEn
                  ? "Don't have an account? Sign up"
                  : "Pas encore de compte ? S'inscrire"
                : isEn
                ? 'Already have an account? Log in'
                : 'Déjà un compte ? Se connecter'}
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};
