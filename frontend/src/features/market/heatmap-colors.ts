import type { HeatmapCompany } from '@/shared/api/generated/types.gen';

/**
 * Diverging score scale of the map (#311): blue for high, neutral gray in the middle, orange for low.
 * Not green/red, which many colour-blind readers confuse. Each band is a theme variable (#321) with its
 * own light and dark value, both checked with the dataviz validator; every tile also carries its number.
 */
export const BAND: Record<HeatmapCompany['band'], { fill: string; ink: string; label: string }> = {
  very_high: { fill: 'var(--heat-very-high)', ink: 'var(--heat-very-high-ink)', label: 'muy alta' },
  high: { fill: 'var(--heat-high)', ink: 'var(--heat-high-ink)', label: 'alta' },
  medium: { fill: 'var(--heat-medium)', ink: 'var(--heat-medium-ink)', label: 'media' },
  low: { fill: 'var(--heat-low)', ink: 'var(--heat-low-ink)', label: 'baja' },
  very_low: { fill: 'var(--heat-very-low)', ink: 'var(--heat-very-low-ink)', label: 'muy baja' },
  none: { fill: 'var(--heat-none)', ink: 'var(--heat-none-ink)', label: 'sin puntuación' },
};
