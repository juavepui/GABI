import type { HeatmapCompany } from '@/shared/api/generated/types.gen';

/**
 * Diverging score scale of the map (#311): blue for high, neutral gray in the middle, orange for low.
 * Not green/red, which many colour-blind readers confuse. Adjacent pairs checked with the dataviz
 * validator (CVD ΔE ≥ 16, normal-vision ΔE ≥ 17 on the light surface); every tile also carries its number.
 */
export const BAND: Record<HeatmapCompany['band'], { fill: string; ink: string; label: string }> = {
  very_high: { fill: '#1c5cab', ink: '#ffffff', label: 'muy alta' },
  high: { fill: '#6da7ec', ink: '#0b0b0b', label: 'alta' },
  medium: { fill: '#d6d5cf', ink: '#0b0b0b', label: 'media' },
  low: { fill: '#e57a49', ink: '#0b0b0b', label: 'baja' },
  very_low: { fill: '#a8380f', ink: '#ffffff', label: 'muy baja' },
  none: { fill: '#f4f3ef', ink: '#52514e', label: 'sin puntuación' },
};
