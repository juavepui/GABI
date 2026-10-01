import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getNotices } from '@/shared/api/client';

const COMMAND = 'python -m gabi.periodic_tasks --run';

/** The old Streamlit portada notices, shown on the landing page. */
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
        Herramienta de uso personal y educativo. <strong>No es asesoramiento financiero.</strong>{' '}
        Los datos vienen de fuentes gratuitas (Yahoo Finance, SEC EDGAR, FRED) y pueden tener
        retraso o errores. Verifica siempre antes de invertir.
      </p>
      {data?.smallmid?.analyzed && (
        <p className="rounded-lg border p-3">
          El análisis preregistrado de GABI fuera del S&amp;P 500 (#44) ya está hecho:{' '}
          <code>docs/smallmid-test/resultado.json</code>.
        </p>
      )}
      {data?.smallmid && !data.smallmid.analyzed && data.smallmid.data_frozen && (
        <p role="alert" className="rounded-lg border border-amber-500/40 p-3">
          Los datos del #44 ya están congelados y falta su análisis: ejecuta <code>{COMMAND}</code>{' '}
          (lo hace solo si las tareas programadas están instaladas).
        </p>
      )}
      {data?.blind_rebalances.map((row) => (
        <p key={row.id} role="alert" className="rounded-lg border border-primary/40 p-3">
          Rebalanceo de la prueba ciega #{row.id} ({row.name}){' '}
          {row.overdue ? 'vencido' : `en ${row.days} ${row.days === 1 ? 'día' : 'días'}`}, el{' '}
          {row.due}. Ejecuta <code>{COMMAND}</code> después del cierre del mercado, o regístralo en{' '}
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
