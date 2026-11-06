import type { ReactNode } from 'react';
import { TONE_STYLE, type Tone } from './tone';

/**
 * The answer to «¿es bueno, malo o normal?» before any detail (#320, CLAUDE.md §2): a large verdict in
 * words, coloured and with its icon, one line that explains it, and the number small at the side. The tone
 * and the words come from the backend's own classification; this component never sets a threshold.
 */
export function VerdictBanner({
  tone,
  verdict,
  explanation,
  value,
  valueLabel,
  className = '',
}: {
  tone: Tone;
  verdict: string;
  explanation?: ReactNode;
  value?: ReactNode;
  valueLabel?: string;
  className?: string;
}) {
  const style = TONE_STYLE[tone];
  const Icon = style.icon;
  return (
    <div
      data-tone={tone}
      className={
        'flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-l-4 bg-card p-4 ' +
        style.bar +
        ' ' +
        className
      }
    >
      <div className="min-w-0 flex-1 basis-60">
        <p className={'flex items-center gap-2 text-xl font-semibold ' + style.ink}>
          <Icon size={22} aria-hidden="true" className="shrink-0" />
          {verdict}
        </p>
        {explanation != null && <div className="mt-1 text-sm">{explanation}</div>}
      </div>
      {value != null && (
        <div className="shrink-0 text-right">
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
          {valueLabel && <p className="text-xs text-muted-foreground">{valueLabel}</p>}
        </div>
      )}
    </div>
  );
}
