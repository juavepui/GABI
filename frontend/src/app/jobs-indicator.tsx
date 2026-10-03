import { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, CircleX, ListChecks, LoaderCircle, X } from 'lucide-react';
import { cancelJob, getJobs } from '@/shared/api/client';
import type { JobResponse } from '@/shared/api/generated/types.gen';
import { ACTIVE_JOB_STATES, JOB_STATES, jobName } from '@/shared/lib/jobs';
import { Button } from '@/shared/ui/button';
import { ProgressBar } from '@/shared/ui/progress-bar';
import { jobLaunches } from './job-launches';

type Toast = { id: string; name: string; status: string };

const isActive = (job: JobResponse) => ACTIVE_JOB_STATES.includes(job.status);

function useJobsWatch() {
  const queryClient = useQueryClient();
  const seen = useRef(new Map<string, string>());
  const [toasts, setToasts] = useState<Toast[]>([]);
  const jobs = useQuery({
    queryKey: ['jobs', 'indicator'],
    queryFn: async ({ signal }) => {
      const data = await getJobs(signal);
      const finished: Toast[] = [];
      for (const job of data.jobs) {
        const before = seen.current.get(job.id);
        // Only jobs this tab saw queued or running: no toasts for history found on the first load.
        // Not on the page that launched it either: that page already shows the result in place.
        const launchedHere = jobLaunches.get(job.id) === window.location.pathname;
        if (before && ACTIVE_JOB_STATES.includes(before) && !isActive(job) && !launchedHere) {
          finished.push({ id: job.id, name: jobName(job.kind), status: job.status });
        }
        seen.current.set(job.id, job.status);
      }
      if (finished.length) {
        setToasts((current) => [...current, ...finished].slice(-2));
        void queryClient.invalidateQueries({ queryKey: ['home'] });
      }
      return data;
    },
    // Frequent while something runs, sparse otherwise: the same GET Administración already uses.
    refetchInterval: (query) => (query.state.data?.jobs.some(isActive) ? 2000 : 15000),
  });
  return {
    jobs: jobs.data?.jobs ?? [],
    toasts,
    dismiss: (id: string) => setToasts((current) => current.filter((toast) => toast.id !== id)),
  };
}

function Toasts({ toasts, dismiss }: { toasts: Toast[]; dismiss: (id: string) => void }) {
  useEffect(() => {
    if (!toasts.length) return;
    const timer = window.setTimeout(() => dismiss(toasts[0].id), 6000);
    return () => window.clearTimeout(timer);
  }, [toasts, dismiss]);
  if (!toasts.length) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Avisos de trabajos"
      className="fixed bottom-4 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2"
    >
      {toasts.map((toast) => {
        const ok = toast.status === 'succeeded';
        return (
          <div
            key={toast.id}
            className={
              'flex items-start gap-3 rounded-xl border bg-card p-3 text-sm shadow-lg ' +
              (ok ? 'border-emerald-300' : 'border-rose-300')
            }
          >
            {ok ? (
              <CheckCircle2
                size={18}
                className="mt-0.5 shrink-0 text-emerald-600"
                aria-hidden="true"
              />
            ) : (
              <CircleX size={18} className="mt-0.5 shrink-0 text-rose-600" aria-hidden="true" />
            )}
            <div className="min-w-0 flex-1">
              <p className="font-medium">{toast.name}</p>
              <p className="text-xs text-muted-foreground">
                {JOB_STATES[toast.status] ?? toast.status} ·{' '}
                <Link className="underline" to="/administracion" onClick={() => dismiss(toast.id)}>
                  Ver en Administración
                </Link>
              </p>
            </div>
            <button
              type="button"
              aria-label="Cerrar aviso"
              className="rounded p-0.5 text-muted-foreground hover:bg-muted"
              onClick={() => dismiss(toast.id)}
            >
              <X size={15} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

/** Header button with the queued/running jobs, their progress and the latest finished ones. */
export function JobsIndicator() {
  const { jobs, toasts, dismiss } = useJobsWatch();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const box = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: cancelJob,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  });
  const active = jobs.filter(isActive);
  const recent = jobs.filter((job) => !isActive(job)).slice(0, 5);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (
        event instanceof KeyboardEvent
          ? event.key === 'Escape'
          : !box.current?.contains(event.target as Node)
      )
        setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);
  const label = active.length
    ? `Trabajos: ${active.length} en curso`
    : 'Trabajos: ninguno en curso';
  return (
    <>
      <div className="relative" ref={box}>
        <button
          type="button"
          aria-label={label}
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen(!open)}
          className={
            'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium transition-colors ' +
            (active.length
              ? 'border-emerald-300 bg-emerald-50 text-emerald-900 hover:bg-emerald-100'
              : 'bg-background hover:bg-muted')
          }
        >
          {active.length ? (
            <LoaderCircle size={14} className="animate-spin" aria-hidden="true" />
          ) : (
            <ListChecks size={14} aria-hidden="true" />
          )}
          <span className="hidden sm:inline">Trabajos</span>
          {active.length > 0 && (
            <span className="rounded-full bg-emerald-600 px-1.5 text-white tabular-nums">
              {active.length}
            </span>
          )}
        </button>
        {open && (
          <div
            id={panelId}
            role="region"
            aria-label="Trabajos locales"
            className="absolute right-0 z-40 mt-2 w-96 max-w-[calc(100vw-2rem)] rounded-xl border bg-card p-4 text-sm shadow-xl"
          >
            <p className="font-semibold">En curso</p>
            {active.length === 0 && (
              <p className="mt-1 text-xs text-muted-foreground">Ningún trabajo en marcha.</p>
            )}
            <ul className="mt-2 space-y-3">
              {active.map((job) => (
                <li key={job.id} aria-label={jobName(job.kind)} className="space-y-1.5">
                  <p className="text-xs font-medium">{jobName(job.kind)}</p>
                  <ProgressBar value={job.progress} phase={job.phase} status={job.status} />
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={job.cancel_requested || cancel.isPending}
                    onClick={() => cancel.mutate(job.id)}
                  >
                    {job.cancel_requested ? 'Cancelación solicitada' : 'Solicitar cancelación'}
                  </Button>
                </li>
              ))}
            </ul>
            {recent.length > 0 && (
              <>
                <p className="mt-4 font-semibold">Recientes</p>
                <ul className="mt-1 divide-y">
                  {recent.map((job) => (
                    <li key={job.id} className="flex justify-between gap-3 py-1.5 text-xs">
                      <span className="truncate">{jobName(job.kind)}</span>
                      <span
                        className={
                          job.status === 'succeeded'
                            ? 'shrink-0 text-emerald-700'
                            : 'shrink-0 text-rose-700'
                        }
                      >
                        {JOB_STATES[job.status] ?? job.status}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <Link
              to="/administracion"
              className="mt-4 inline-block text-xs font-medium text-primary underline"
              onClick={() => setOpen(false)}
            >
              Ver todos en Administración
            </Link>
          </div>
        )}
      </div>
      <Toasts toasts={toasts} dismiss={dismiss} />
    </>
  );
}
