import { Link } from 'react-router-dom';
import type { DataResponse } from '@/shared/api/generated/types.gen';
import { dateLabel } from '@/shared/lib/format';

const warnings: Record<string, string> = {
  incomplete_coverage: 'A algunas empresas les faltan datos, así que su puntuación es menos completa.',
  prices_stale: 'Hay precios con más de una semana: actualiza los datos para ver los de hoy.',
  fundamentals_stale:
    'Hay datos de las cuentas (Yahoo) con más de una semana: actualízalos cuando puedas.',
  sec_stale: 'Hay informes oficiales (SEC) sin revisar desde hace más de dos semanas.',
  universe_stale: 'La lista de empresas del S&P 500 puede haber cambiado: conviene actualizarla.',
};

/** Presents backend classifications and counts; never infers financial freshness in JS. */
export function DataStatus({ data }: { data: DataResponse }) {
  return (
    <section aria-label="Estado de los datos" className="rounded-xl border bg-card p-4 text-sm">
      <p className="font-semibold" role="status">
        {
          {
            ready: 'Datos guardados en tu equipo',
            stale: 'Datos antiguos: conviene actualizarlos',
            empty: 'Todavía no hay datos suficientes',
          }[data.status]
        }
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Precios hasta el {dateLabel(data.latest_price_date)}, descargados de Yahoo Finance y de la
        SEC (el organismo que publica las cuentas oficiales de las empresas de EE. UU.). Que haya
        datos no significa que sean perfectos: revisa las cifras importantes antes de decidir.
      </p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        {[
          ['Con precio', data.prices_available],
          ['Con datos de sus cuentas', data.fundamentals_available],
          ['Con informes oficiales (SEC)', data.sec_available],
          ['Con puntuación', data.scored_count],
        ].map(([label, count]) => (
          <div key={label}>
            <dt className="text-muted-foreground">{label}</dt>
            <dd>
              {count} de {data.universe_count} empresas
            </dd>
          </div>
        ))}
      </dl>
      {data.warnings.length > 0 && (
        <details className="mt-3 text-xs" open={data.status !== 'ready'}>
          <summary className="cursor-pointer">Avisos sobre los datos ({data.warnings.length})</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {data.warnings.map((code) => (
              <li key={code}>{warnings[code] ?? code}</li>
            ))}
          </ul>
        </details>
      )}
      {data.prices_current === false && (
        <p className="mt-2 text-xs">
          A algunas empresas les falta el precio del último día de bolsa (
          {dateLabel(data.last_session)}).
        </p>
      )}
      <Link
        className="mt-3 inline-block text-xs font-medium text-primary underline"
        to="/administracion"
      >
        Actualizar los datos
      </Link>
      <p className="mt-1 text-xs text-muted-foreground">
        Abrir o recargar esta página no descarga nada; solo lo hace ese botón.
      </p>
    </section>
  );
}
