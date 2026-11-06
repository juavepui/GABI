import type { LucideIcon } from 'lucide-react';
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';

/** The four states a reading can be in (#320). The backend decides which one; React only shows it. */
export type Tone = 'good' | 'caution' | 'bad' | 'neutral';

export const TONE_STYLE: Record<Tone, { icon: LucideIcon; box: string; ink: string; bar: string }> =
  {
    good: {
      icon: CheckCircle2,
      box: 'border-success-border bg-success-soft text-success-ink',
      ink: 'text-success-ink',
      bar: 'border-l-success',
    },
    caution: {
      icon: AlertTriangle,
      box: 'border-warning-border bg-warning-soft text-warning-ink',
      ink: 'text-warning-ink',
      bar: 'border-l-warning',
    },
    bad: {
      icon: XCircle,
      box: 'border-danger-border bg-danger-soft text-danger-ink',
      ink: 'text-danger-ink',
      bar: 'border-l-danger',
    },
    neutral: {
      icon: Info,
      box: 'border-border bg-muted/40 text-foreground',
      ink: 'text-foreground',
      bar: 'border-l-muted-foreground/50',
    },
  };
