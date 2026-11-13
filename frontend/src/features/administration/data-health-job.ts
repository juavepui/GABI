import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getJobResult, getJobs } from '@/shared/api/client';
import type { DataHealthRequest } from '@/shared/api/generated/types.gen';
import { useJob } from '@/shared/api/use-job';
import { formatPercent } from '@/shared/lib/format';

export type Cell = string | number | boolean | null | undefined;
export type Row = Record<string, Cell>;

export const pct = (value: number | null | undefined) => formatPercent(value, { digits: 0 });

export function age(hours: number | null | undefined) {
  if (hours == null) return '—';
  return hours < 48 ? `${Math.round(hours)} h` : `${Math.round(hours / 24)} días`;
}

/** Runs one data_health scope as an explicit job and, optionally, restores its latest result. */
export function useHealthJob<T>(prefix: string, restoreScope?: string) {
  const state = useJob(prefix);
  const { jobId, setJobId, job } = state;
  const recent = useQuery({
    queryKey: ['jobs'],
    queryFn: ({ signal }) => getJobs(signal),
    enabled: restoreScope != null && jobId == null,
  });
  useEffect(() => {
    if (jobId != null || !restoreScope) return;
    const last = recent.data?.jobs.find(
      (item) =>
        item.kind === 'data_health' &&
        item.status === 'succeeded' &&
        (item.parameters.health as { scope?: string } | undefined)?.scope === restoreScope,
    );
    if (last) setJobId(last.id);
  }, [jobId, recent.data, restoreScope, setJobId]);
  const result = useQuery({
    queryKey: ['job', jobId, 'result'],
    queryFn: ({ signal }) => getJobResult(jobId!, signal) as Promise<T>,
    enabled: job.data?.status === 'succeeded',
  });
  const running = state.start.isPending || ['queued', 'running'].includes(job.data?.status ?? '');
  const run = (health: DataHealthRequest) => state.start.mutate({ kind: 'data_health', health });
  return { ...state, result, running, run };
}

export function useToday() {
  // Local YYYY-MM-DD, as the server's date.today().
  const [today] = useState(() => new Date().toLocaleDateString('sv-SE'));
  return today;
}
