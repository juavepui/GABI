import { Link } from 'react-router-dom';
import { TriangleAlert } from 'lucide-react';
import type { DataResponse } from '@/shared/api/generated/types.gen';
import { dateLabel } from '@/shared/lib/format';

const warnings: Record<string, string> = {
  incomplete_coverage:
    'A algunas empresas les faltan datos, así que su puntuación es menos completa.',
  prices_stale: 'Hay precios con más de una semana: actualiza los datos para ver los de hoy.',
  fundamentals_stale:
    'Hay datos de las cuentas (Yahoo) con más de una semana: actualízalos cuando puedas.',
  sec_stale: 'Hay informes oficiales (SEC) sin revisar desde hace más de dos semanas.',
  universe_stale: 'La lista de empresas del S&P 500 puede haber cambiado: conviene actualizarla.',
};

const TITLE: Record<DataResponse['status'], string> = {
  ready: 'Datos guardados en tu equipo',
  stale: 'Datos antiguos: conviene actualizarlos',
  empty: 'Todavía no hay datos suficientes',
};

/** Each warning in words, plus a missing last close; the backend decides both. */
function problems(data: DataResponse): string[] {
  return [
    ...data.warnings.map((code) => warnings[code] ?? code),
    ...(data.prices_current === false
      ? [
          `A algunas empresas les falta el precio del último día de bolsa (${dateLabel(data.last_session)}).`,
        ]
      : []),
  ];
}

/** Where the data comes from and how many companies have each kind. */
function Details({ data }: { data: DataResponse }) {
  return (
    <>
      <p className="text-xs text-muted-foreground">
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
    </>
  );
}

const UPDATE_NOTE = 'Abrir o recargar esta página no descarga nada; solo lo hace ese botón.';

/**
 * Presents backend classifications and counts; never infers financial freshness in JS.
 * `compact` (data needing attention, in view above the list): what is wrong and what to do on a
 * few lines, with sources and counts folded behind «Ver detalle».
 */
export function DataStatus({ data, compact = false }: { data: DataResponse; compact?: boolean }) {
  const issues = problems(data);
  if (compact)
    return (
      <section
        aria-label="Estado de los datos"
        className="rounded-xl border border-warning-border bg-warning-soft p-4 text-sm text-warning-ink"
      >
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="flex min-w-0 items-start gap-2">
            <TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
            <p role="status">
              <span className="font-semibold">{TITLE[data.status]}</span>
              {data.latest_price_date && (
                <> · precios hasta el {dateLabel(data.latest_price_date)}</>
              )}
            </p>
          </div>
          <Link
            className="shrink-0 text-xs font-medium underline"
            to="/administracion"
            title={UPDATE_NOTE}
          >
            Actualizar los datos
          </Link>
        </div>
        {issues.length > 0 && (
          <ul className="mt-1.5 list-disc space-y-0.5 pl-11 text-xs">
            {issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        )}
        <details className="mt-2 pl-6 text-xs">
          <summary className="cursor-pointer">Ver detalle: fuentes y empresas con datos</summary>
          <div className="mt-2 rounded-lg bg-card p-3 text-foreground">
            <Details data={data} />
            <p className="mt-3 text-xs text-muted-foreground">{UPDATE_NOTE}</p>
          </div>
        </details>
      </section>
    );
  return (
    <section aria-label="Estado de los datos" className="rounded-xl border bg-card p-4 text-sm">
      <p className="font-semibold" role="status">
        {TITLE[data.status]}
      </p>
      <div className="mt-1">
        <Details data={data} />
      </div>
      {data.warnings.length > 0 && (
        <details className="mt-3 text-xs" open={data.status !== 'ready'}>
          <summary className="cursor-pointer">
            Avisos sobre los datos ({data.warnings.length})
          </summary>
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
      <p className="mt-1 text-xs text-muted-foreground">{UPDATE_NOTE}</p>
    </section>
  );
}
