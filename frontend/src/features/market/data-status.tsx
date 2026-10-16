import { Link } from 'react-router-dom';
import type { DataResponse } from '@/shared/api/generated/types.gen';
import { dateLabel } from '@/shared/lib/format';

const warnings: Record<string, string> = {
  incomplete_coverage: 'Cobertura parcial: faltan datos en parte del universo.',
  prices_stale: 'Hay precios fuera del plazo de frescura.',
  fundamentals_stale: 'Hay fundamentales de Yahoo fuera del plazo de frescura.',
  sec_stale: 'Hay fundamentales SEC fuera del plazo de frescura.',
  universe_stale: 'La composición del universo necesita actualizarse.',
};

/** Presents backend classifications and counts; never infers financial freshness in JS. */
export function DataStatus({ data }: { data: DataResponse }) {
  return (
    <section aria-label="Estado de los datos" className="rounded-xl border bg-card p-4 text-sm">
      <p className="font-semibold" role="status">
        {
          {
            ready: 'Datos cacheados disponibles',
            stale: 'Datos obsoletos',
            empty: 'Sin datos locales suficientes',
          }[data.status]
        }
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Último precio del universo: {dateLabel(data.latest_price_date)}. Fuentes: caché local de
        Yahoo y SEC. La disponibilidad no acredita calidad financiera ni datos históricos
        point-in-time.
      </p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        {[
          ['Con precios', data.prices_available],
          ['Con fundamentales', data.fundamentals_available],
          ['Con datos SEC', data.sec_available],
          ['Con puntuación', data.scored_count],
        ].map(([label, count]) => (
          <div key={label}>
            <dt className="text-muted-foreground">{label}</dt>
            <dd>
              {count} / {data.universe_count}
            </dd>
          </div>
        ))}
      </dl>
      {data.warnings.length > 0 && (
        <details className="mt-3 text-xs" open={data.status !== 'ready'}>
          <summary className="cursor-pointer">Avisos de datos ({data.warnings.length})</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {data.warnings.map((code) => (
              <li key={code}>{warnings[code] ?? code}</li>
            ))}
          </ul>
        </details>
      )}
      {data.prices_current === false && (
        <p className="mt-2 text-xs">
          Falta el último cierre en parte del universo. Sesión de referencia:{' '}
          {dateLabel(data.last_session)}.
        </p>
      )}
      <Link
        className="mt-3 inline-block text-xs font-medium text-primary underline"
        to="/administracion"
      >
        Actualizar datos desde Administración
      </Link>
      <p className="mt-1 text-xs text-muted-foreground">
        Consultar o reintentar una lectura no descarga datos.
      </p>
    </section>
  );
}
