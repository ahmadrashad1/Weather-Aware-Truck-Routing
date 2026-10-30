import type { RiskCode } from '@/api/client'

/** How each risk level looks. The levels themselves are always decided by the backend. */
export const RISK_DISPLAY: Record<RiskCode, { label: string; color: string }> =
  {
    low: { label: 'Low', color: '#2f8f5b' },
    moderate: { label: 'Moderate', color: '#e3b505' },
    high: { label: 'High', color: '#e8770c' },
    severe: { label: 'Severe', color: '#c4122f' },
    no_travel: { label: 'No Travel', color: '#4a0d1a' },
    unknown: { label: 'No weather', color: '#9aa3a8' },
  }
