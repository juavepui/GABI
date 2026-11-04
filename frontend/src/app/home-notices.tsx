import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getNotices } from '@/shared/api/client';
import type { PeriodicNotice } from '@/shared/api/generated/types.gen';
import { dateText } from '@/shared/lib/format';

const COMMAND = 'python -m gabi_cli periodic --run';
const SCHEDULE_SCRIPT = 'scripts\\programar_tareas.ps1';

/** Whether the daily follow-up ran recently (#290); the backend decides the status. */
function PeriodicFollowUp({ notice }: { notice: PeriodicNotice }) {
  const lost =
    'Cada noche anota qué empresas elige GABI, para comprobar más adelante, con datos nuevos, si acierta. Un día sin anotar no se puede recuperar después.';
  if (notice.status === 'never')
    return (
      <p role="alert" className="rounded-lg border border-amber-500/40 p-3">
        <strong>El seguimiento diario de GABI no se ha ejecutado nunca en este equipo.</strong>{' '}
        {lost} Para activarlo, ejecuta una vez en PowerShell <code>{SCHEDULE_SCRIPT}</code>: se
        lanza solo de martes a sábado a las 23:30, con el ordenador encendido.
      </p>
    );
  if (notice.status === 'late')
    return (
      <p role="alert" className="rounded-lg border border-amber-500/40 p-3">
        <strong>
          El seguimiento diario de GABI lleva {notice.business_days} días laborables sin ejecutarse
        </strong>{' '}
        (último registro correcto: {dateText(notice.last_working_at)}). {lost} Comprueba que el
        ordenador estaba encendido a las 23:30 y que las tareas siguen programadas; si no, vuelve a
        ejecutar <code>{SCHEDULE_SCRIPT}</code>.
      </p>
    );
  if (notice.last_status === 'ERROR')
    return (
      <p role="status" className="rounded-lg border p-3">
        La última ejecución del seguimiento diario terminó con error; el registro anterior sí se
        guardó. Revisa el detalle en{' '}
        <Link className="underline" to="/administracion">
          Administración
        </Link>
        .
      </p>
    );
  return null;
}

/** Notices shown on the landing page: legal notice, daily follow-up, blind rebalances due soon and the #44 state. */
export function HomeNotices() {
  const notices = useQuery({
    queryKey: ['notices'],
    queryFn: ({ signal }) => getNotices(signal),
    staleTime: 300_000,
  });
  const data = notices.data;
  return (
    <div className="mb-6 space-y-2 text-sm" aria-label="Avisos" role="region">
      <p className="rounded-lg border border-amber-500/40 bg-amber-50/60 p-3 dark:bg-amber-950/20">
        Herramienta para uso personal y para aprender.{' '}
        <strong>No es asesoramiento financiero</strong> ni te dice qué comprar. Los datos vienen de
        fuentes gratuitas (Yahoo Finance, la SEC y la Reserva Federal) y pueden llegar con retraso o
        tener errores. Compruébalos siempre antes de invertir.
      </p>
      {data?.periodic && <PeriodicFollowUp notice={data.periodic} />}
      {data?.smallmid?.analyzed && (
        <p className="rounded-lg border p-3">
          El estudio de GABI fuera del S&amp;P 500 (#44), cuyas reglas se fijaron antes de ver los
          datos, ya está analizado: <code>docs/smallmid-test/resultado.json</code>.
        </p>
      )}
      {data?.smallmid && !data.smallmid.analyzed && data.smallmid.data_frozen && (
        <p role="alert" className="rounded-lg border border-amber-500/40 p-3">
          Los datos del estudio fuera del S&amp;P 500 (#44) ya están cerrados y falta analizarlos.
          Lo hacen solas las tareas automáticas si están instaladas; si no, ejecuta{' '}
          <code>{COMMAND}</code>.
        </p>
      )}
      {data?.blind_rebalances.map((row) => (
        <p key={row.id} role="alert" className="rounded-lg border border-primary/40 p-3">
          Rebalanceo de la prueba ciega #{row.id} ({row.name}){' '}
          {row.overdue ? 'vencido' : `en ${row.days} ${row.days === 1 ? 'día' : 'días'}`}, el{' '}
          {row.due}: toca reajustar esa cartera de prueba de GABI. Tras el cierre del mercado,
          ejecuta <code>{COMMAND}</code> o apúntalo en{' '}
          <Link className="underline" to="/investigacion/validaciones">
            Investigación → Validaciones ciegas
          </Link>
          .
        </p>
      ))}
      {data && !data.blind_available && (
        <p className="text-xs text-muted-foreground">
          No se pudo comprobar el calendario de las pruebas ciegas.
        </p>
      )}
    </div>
  );
}
