import type { JobResponse } from '@/shared/api/generated/types.gen';
import { dateLabel } from '@/shared/lib/format';
import { Button } from '@/shared/ui/button';
import { ProgressBar } from '@/shared/ui/progress-bar';

/** Downloads that bring the data up to date (the same kinds Inicio counts as an update). */
const UPDATES = new Set(['refresh', 'data_update', 'symbols']);

/**
 * «Actualizar todo»: the one action most visits need, with when it last happened and its progress.
 * The jobs come from the page's own list; nothing here decides freshness.
 */
export function UpdateAll({
  jobs,
  pending,
  onStart,
}: {
  jobs: JobResponse[] | undefined;
  pending: boolean;
  onStart: () => void;
}) {
  const running = jobs?.find(
    (job) => job.kind === 'refresh' && ['queued', 'running'].includes(job.status),
  );
  const last = jobs
    ?.filter((job) => UPDATES.has(job.kind) && job.status === 'succeeded' && job.finished_at)
    .sort((a, b) => (b.finished_at ?? '').localeCompare(a.finished_at ?? ''))[0];
  return (
    <section aria-label="Actualizar todo" className="space-y-3">
      <p className="text-sm">
        Pone al día todo lo que usa GABI: qué empresas forman hoy el S&amp;P 500, sus precios, sus
        cuentas y sus informes oficiales, el propio índice y los datos de la economía. Solo descarga
        lo que esté desactualizado.
      </p>
      <p className="text-xs text-muted-foreground">
        {last?.finished_at
          ? 'Última actualización: ' + dateLabel(last.finished_at.slice(0, 10)) + '. '
          : 'Todavía no has actualizado los datos desde aquí. '}
        Si las tareas automáticas están instaladas, GABI lo hace solo cada día. La primera vez tarda
        bastante; puedes cerrar el navegador mientras tanto.
      </p>
      <Button onClick={onStart} pending={pending || running != null} disabled={running != null}>
        Actualizar todo
      </Button>
      {running && (
        <div className="space-y-1">
          <ProgressBar value={running.progress} phase={running.phase} status={running.status} />
          <p className="text-xs text-muted-foreground">
            Actualizando. El detalle está en «Tareas en marcha y terminadas», más abajo.
          </p>
        </div>
      )}
    </section>
  );
}
