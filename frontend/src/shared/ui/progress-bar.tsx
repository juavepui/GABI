/** Progress of a local job: percentage, phase text and an animated bar while it runs. */
export function ProgressBar({
  value,
  phase,
  status,
}: {
  value: number;
  phase: string;
  status: string;
}) {
  const running = status === 'running' || status === 'queued';
  const percent = Math.min(Math.max(Math.round(value), 0), 100);
  const label = status === 'queued' ? 'En cola' : phase;
  return (
    <div className="space-y-1.5" role="status" aria-live="polite">
      <div className="flex items-baseline justify-between gap-3 text-xs">
        <span className="font-medium text-foreground">{label}</span>
        <span className="tabular-nums text-muted-foreground">{percent} %</span>
      </div>
      <div
        className="h-2.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div
          className={
            'h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 transition-[width] duration-700 ' +
            (running ? 'animate-pulse' : '')
          }
          style={{ width: `${Math.max(percent, running ? 3 : 0)}%` }}
        />
      </div>
    </div>
  );
}
