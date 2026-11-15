import { GraphState } from '../types';

/**
 * Retourne la synthèse textuelle vérifiée produite par l'Agent 4 (Explainer)
 * et certifiée par l'Agent 5 (Verifier).
 * 
 * Règle stricte d'explicabilité et de conformité :
 * Aucun calcul, prévision ou plafond n'est inventé ou recalculé côté navigateur.
 * Seule l'explication vérifiée par le pipeline multi-agents est restituée à l'utilisateur.
 */
export function getVerifiedSummary(state: GraphState | null): string {
  if (!state) {
    return 'Simulation en cours...';
  }
  return state.explanation?.resume || 'Synthèse vérifiée disponible dans les détails ci-dessous.';
}
