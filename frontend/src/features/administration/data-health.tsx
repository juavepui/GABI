import type { ReactNode } from 'react';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { ErrorState } from '@/shared/ui/resource-state';
import type { Row, useHealthJob } from './data-health-job';

export function Table({
  label,
  columns,
  rows,
}: {
  label: string;
  columns: [string, string][];
  rows: Row[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs" aria-label={label}>
        <thead>
          <tr className="border-b">
            {columns.map(([, title]) => (
              <th key={title} className="py-1.5 pr-3 font-medium">
                {title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b last:border-0">
              {columns.map(([key]) => (
                <td key={key} className="py-1.5 pr-3 align-top">
                  {row[key] == null || row[key] === '' ? '—' : String(row[key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function HealthStatus({
  state,
  failure,
}: {
  state: ReturnType<typeof useHealthJob>;
  failure: string;
}) {
  const { start, job, result } = state;
  return (
    <>
      {start.isError && <ErrorState error={start.error} retry={() => start.reset()} />}
      {result.isError && <ErrorState error={result.error} retry={() => void result.refetch()} />}
      {job.data && ['queued', 'running'].includes(job.data.status) && (
        <p role="status" className="text-xs text-muted-foreground">
          {job.data.phase} · {job.data.progress} %
        </p>
      )}
      {job.data && ['failed', 'cancelled'].includes(job.data.status) && (
        <p className="text-xs text-destructive">{failure}</p>
      )}
    </>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3 rounded-xl border bg-card p-5 text-sm" aria-label={title}>
      <h2 className="font-medium">{title}</h2>
      {children}
    </section>
  );
}

export function DateField({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  min?: string;
  max?: string;
}) {
  return (
    <label className="grid gap-1 text-xs font-medium">
      {label}
      <Input
        type="date"
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

export function RunButton({
  running,
  onClick,
  children,
}: {
  running: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Button variant="outline" disabled={running} onClick={onClick}>
      {children}
    </Button>
  );
}
