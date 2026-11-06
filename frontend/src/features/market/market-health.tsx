import { useQuery } from '@tanstack/react-query';
import { getMarketHealth } from '@/shared/api/client';
import type { MarketCheck, MarketHealthResponse } from '@/shared/api/generated/types.gen';
import { dateLabel, formatNumber } from '@/shared/lib/format';
import { Activity } from 'lucide-react';
import { HowToRead } from '@/shared/ui/how-to-read';
import { StatusTag } from '@/shared/ui/status';
import type { Tone } from '@/shared/ui/tone';
import { SummaryCard } from '@/shared/ui/summary-card';
import { Term } from '@/shared/ui/term';
import { VerdictBanner } from '@/shared/ui/verdict-banner';

const STATE_TONE: Record<NonNullable<MarketHealthResponse['state']>, Tone> = {
  favorable: 'good',
  pressure: 'caution',
  correction: 'bad',
};

const RESULT: Record<NonNullable<MarketCheck['result']> | 'none', { label: string; tone: Tone }> = {
  pass: { label: 'Pasa', tone: 'good' },
  caution: { label: 'Precaución', tone: 'caution' },
  fail: { label: 'Falla', tone: 'bad' },
  none: { label: 'Sin dato', tone: 'neutral' },
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
    <SummaryCard
      title="Cómo está el mercado"
      icon={Activity}
      titleExtra={<Term k="market_health" name="Semáforo del mercado" />}
    >
      {!health ? (
        <p className="text-sm text-muted-foreground" role="status">
          Leyendo los precios guardados…
        </p>
      ) : health.status === 'no_data' ? (
        <p className="text-sm text-muted-foreground">
          Sin datos suficientes: hacen falta al menos 201 días de bolsa de precios del índice (
          {health.benchmark}) guardados en tu equipo. Actualiza los datos en Administración.
        </p>
      ) : (
        <>
          <VerdictBanner
            tone={health.state ? STATE_TONE[health.state] : 'neutral'}
            verdict={health.state_label ?? 'Sin estado'}
            explanation={
              <span className="text-muted-foreground">
                {days(health)} en este estado · cierre del {dateLabel(health.as_of)}
              </span>
            }
            value={formatNumber(health.score, { digits: 0 }) + ' de 100'}
            valueLabel="Nota del semáforo"
          />
          <ul className="mt-4 grid gap-3 sm:grid-cols-2">
            {(health.checks ?? []).map((check) => {
              const result = RESULT[check.result ?? 'none'];
              return (
                <li key={check.key} className="min-w-0 rounded-lg border p-3 text-sm">
                  <p className="flex flex-wrap items-center gap-2 font-medium">
                    {check.title} <Term k={TERM[check.key]} />
                    <StatusTag tone={result.tone} label={result.label} className="ml-auto" />
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
    </SummaryCard>
  );
}
