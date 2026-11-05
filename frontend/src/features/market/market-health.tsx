import { useQuery } from '@tanstack/react-query';
import { getMarketHealth } from '@/shared/api/client';
import type { MarketCheck, MarketHealthResponse } from '@/shared/api/generated/types.gen';
import { dateLabel, formatNumber } from '@/shared/lib/format';
import { HowToRead } from '@/shared/ui/how-to-read';
import { Term } from '@/shared/ui/term';

const STATE_TONE: Record<NonNullable<MarketHealthResponse['state']>, string> = {
  favorable: 'bg-success-soft text-success-ink',
  pressure: 'bg-warning-soft text-warning-ink',
  correction: 'bg-danger-soft text-danger-ink',
};

const RESULT: Record<NonNullable<MarketCheck['result']> | 'none', { label: string; dot: string }> =
  {
    pass: { label: 'Pasa', dot: 'bg-success' },
    caution: { label: 'Precaución', dot: 'bg-warning' },
    fail: { label: 'Falla', dot: 'bg-danger' },
    none: { label: 'Sin dato', dot: 'bg-muted-foreground/40' },
  };

const TERM: Record<MarketCheck['key'], string> = {
  trend: 'sma200',
  breadth: 'market_breadth',
  distribution: 'distribution_day',
  volatility: 'vix',
};

function days(health: MarketHealthResponse): string {
  const count = health.days_in_state ?? 0;
  const text = count === 1 ? '1 sesión' : `${count} sesiones`;
  return health.days_at_least ? `al menos ${text}` : text;
}

/** «Cómo está el mercado» (#308): the backend's traffic light; context, never a buy or sell signal. */
export function MarketHealthCard() {
  const query = useQuery({
    queryKey: ['market', 'health'],
    queryFn: ({ signal }) => getMarketHealth(signal),
    staleTime: 300_000,
  });
  const health = query.data;
  if (query.isError) return null;
  return (
    <section aria-label="Cómo está el mercado" className="rounded-xl border bg-card p-5">
      <h2 className="text-lg font-semibold">
        Cómo está el mercado <Term k="market_health" name="Semáforo del mercado" />
      </h2>
      {!health ? (
        <p className="mt-2 text-sm text-muted-foreground" role="status">
          Leyendo los precios guardados…
        </p>
      ) : health.status === 'no_data' ? (
        <p className="mt-2 text-sm text-muted-foreground">
          Sin datos suficientes: hacen falta al menos 201 días de bolsa de precios del índice (
          {health.benchmark}) guardados en tu equipo. Actualiza los datos en Administración.
        </p>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            {health.state && (
              <span
                className={
                  'rounded-full px-3 py-1 text-base font-semibold ' + STATE_TONE[health.state]
                }
              >
                {health.state_label}
              </span>
            )}
            <span className="text-sm tabular-nums">
              {formatNumber(health.score, { digits: 0 })} de 100
            </span>
            <span className="text-xs text-muted-foreground">
              {days(health)} en este estado · cierre del {dateLabel(health.as_of)}
            </span>
          </div>
          <ul className="mt-4 grid gap-3 sm:grid-cols-2">
            {(health.checks ?? []).map((check) => {
              const result = RESULT[check.result ?? 'none'];
              return (
                <li key={check.key} className="min-w-0 rounded-lg border p-3 text-sm">
                  <p className="flex items-center gap-2 font-medium">
                    <span aria-hidden="true" className={'size-2.5 rounded-full ' + result.dot} />
                    {check.title} <Term k={TERM[check.key]} />
                    <span className="ml-auto text-xs font-normal text-muted-foreground">
                      {result.label}
                    </span>
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">{check.text}</p>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-xs font-medium">
            Describe el mercado de hoy; no predice lo que hará ni cambia la puntuación de las
            empresas.
          </p>
          <HowToRead className="mt-2">
            Cuatro comprobaciones con umbrales fijos: si el índice está por encima de sus medias de
            50 y 200 sesiones; si al menos el 60 % de las empresas está por encima de su media de
            200 sesiones (por debajo del 40 % falla); cuántas jornadas de ventas fuertes ha habido
            en las últimas 25 sesiones (pasa con 3 o menos, falla con 6 o más); y el VIX (pasa por
            debajo de 20, falla desde 30). Cada una suma 2 puntos si pasa y 1 si pide precaución; la
            nota es el porcentaje de los puntos posibles. «Favorable» desde 75, «Con presión» desde
            40, «En corrección» por debajo. Para un inversor a largo plazo, un mercado con presión
            es normal y no es motivo, por sí solo, para vender: estas reglas no están probadas para
            acertar el momento.
          </HowToRead>
        </>
      )}
    </section>
  );
}
