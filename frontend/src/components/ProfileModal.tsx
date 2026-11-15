import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AuthUser, UserProfileData } from '../types';
import { apiFetch, fetchUserProfile } from '../api';
import { useLanguage } from '@/context/LanguageContext';
import {
  User,
  ShieldCheck,
  AlertCircle,
  Loader2,
  Download,
  Settings,
  History,
} from 'lucide-react';

interface ProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: AuthUser | null;
  onProfileUpdated?: () => void;
  /** Opens the questionnaire: the one place where the saved profile is edited (#170). */
  onEditQuestionnaire?: () => void;
}

const formatDate = (iso: string | undefined): string => {
  if (!iso) return '';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString('fr-CA');
};

/**
 * Read-only view of the one versioned server profile: every questionnaire field with its
 * French label (from the server's label map), the version history and the dossier download.
 */
export const ProfileModal: React.FC<ProfileModalProps> = ({
  isOpen,
  onClose,
  currentUser,
  onEditQuestionnaire,
}) => {
  const { t } = useLanguage();
  const [profileData, setProfileData] = useState<UserProfileData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !currentUser) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchUserProfile()
      .then((data) => {
        if (!cancelled) setProfileData(data);
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

  const handleDownloadDossier = async () => {
    setIsDownloading(true);
    setError(null);
    try {
      const res = await apiFetch('/users/me/dossier');
      if (!res.ok) {
        if (res.status === 404) {
          throw new Error(t('profile.dossier_not_found', 'Aucun dossier trouvé pour ce compte.'));
        }
        throw new Error(t('profile.dossier_error', 'Erreur lors du téléchargement du dossier.'));
      }
      const text = await res.text();
      const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `dossier_${currentUser?.username || 'user'}.md`;
      document.body.appendChild(link);
      link.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(link);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : t('profile.dossier_error', 'Erreur lors du téléchargement du dossier.')
      );
    } finally {
      setIsDownloading(false);
    }
  };

  const summary = profileData?.profile_summary || [];
  const history = [...(profileData?.profile_history || [])].reverse().slice(0, 5);
  const version = profileData?.profile_version;
  const labelByKey: Record<string, string> = {};
  summary.forEach((row) => {
    labelByKey[row.key] = row.label;
  });

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
                {t('profile.modal_title', 'Mon profil d’investisseur')}
              </DialogTitle>
              {version ? (
                <Badge variant="secondary" className="text-xs font-mono">
                  v{version}
                </Badge>
              ) : null}
            </div>
            {currentUser?.is_advisor && (
              <Badge variant="outline" className="flex items-center gap-1 border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10">
                <ShieldCheck className="h-3.5 w-3.5" />
                Réviseur (démonstration)
              </Badge>
            )}
          </div>
          <DialogDescription className="text-sm text-muted-foreground">
            {t(
              'profile.modal_desc',
              'Profil enregistré côté serveur : c’est exactement ce qui est envoyé avec chaque analyse. Chaque enregistrement crée une nouvelle version et ajoute l’écart daté au dossier.'
            )}
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="py-12 flex flex-col items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <p className="text-sm">Chargement du profil...</p>
          </div>
        ) : (
          <div className="space-y-5 pt-3">
            {error && (
              <div className="flex items-center gap-2 p-3 text-sm rounded-lg bg-destructive/10 text-destructive border border-destructive/20">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Identité */}
            <div className="p-3.5 rounded-lg bg-muted/40 border border-border/50 flex items-center justify-between">
              <div>
                <p className="text-xs uppercase font-semibold text-muted-foreground tracking-wider">Compte utilisateur</p>
                <p className="text-base font-semibold text-foreground">{currentUser?.username}</p>
                {currentUser?.email && <p className="text-xs text-muted-foreground">{currentUser.email}</p>}
                {profileData?.updated_at && (
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {t('profile.last_saved', 'Dernier enregistrement')} : {formatDate(profileData.updated_at)}
                  </p>
                )}
              </div>
              <Badge variant="secondary" className="capitalize text-xs">
                {currentUser?.is_advisor ? 'Conseiller' : 'Client investisseur'}
              </Badge>
            </div>

            {/* Every saved field, French labels from the server map */}
            {summary.length === 0 ? (
              <div className="p-4 rounded-lg border border-dashed border-border text-sm text-muted-foreground text-center">
                {t('profile.none_saved', 'Aucun profil enregistré : remplissez le questionnaire pour en créer un.')}
              </div>
            ) : (
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-xs">
                {summary
                  .filter((row) => row.key !== 'profile_version')
                  .map((row) => (
                    <div key={row.key} className="p-2.5 rounded-lg bg-muted/30 border border-border/50 min-w-0">
                      <dt className="text-[11px] text-muted-foreground">{row.label}</dt>
                      <dd className="font-medium text-foreground break-words">{row.value}</dd>
                    </div>
                  ))}
              </dl>
            )}

            {/* Version history: dated diffs */}
            {history.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase text-muted-foreground tracking-wider flex items-center gap-1.5">
                  <History className="h-3.5 w-3.5 text-primary" />
                  {t('profile.history', 'Historique des versions')}
                </p>
                <ul className="space-y-1.5 text-xs">
                  {history.map((h) => {
                    const changed = Object.keys(h.changes || {});
                    return (
                      <li key={h.version} className="p-2.5 rounded-lg border border-border/50 bg-muted/20">
                        <span className="font-mono font-semibold">v{h.version}</span>
                        <span className="text-muted-foreground"> · {formatDate(h.updated_at)}</span>
                        <p className="text-muted-foreground mt-0.5">
                          {changed.length === 0
                            ? t('profile.first_version', 'Première version enregistrée')
                            : `${t('profile.changed_fields', 'Champs modifiés')} : ${changed
                                .map((k) => labelByKey[k] || k)
                                .join(', ')}`}
                        </p>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-3 border-t border-border">
              <Button
                type="button"
                variant="outline"
                onClick={handleDownloadDossier}
                disabled={isDownloading}
                className="flex items-center justify-center gap-2"
              >
                {isDownloading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>{t('profile.downloading_dossier', 'Téléchargement...')}</span>
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4 text-primary" />
                    <span>{t('profile.download_dossier', 'Télécharger mon dossier')}</span>
                  </>
                )}
              </Button>

              <div className="flex items-center justify-end gap-3">
                <Button type="button" variant="outline" onClick={onClose}>
                  Fermer
                </Button>
                {onEditQuestionnaire && (
                  <Button
                    type="button"
                    onClick={() => {
                      onClose();
                      onEditQuestionnaire();
                    }}
                    className="flex items-center gap-2"
                  >
                    <Settings className="h-4 w-4" />
                    {t('profile.edit_questionnaire', 'Modifier via le questionnaire')}
                  </Button>
                )}
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};
