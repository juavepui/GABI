import { Landmark } from 'lucide-react';
import { dateLabel, formatNumber } from '@/shared/lib/format';
import { SummaryCard } from '@/shared/ui/summary-card';
import { Sparkline } from '@/shared/ui/charts/sparkline';
import { Direction } from '@/shared/ui/status';
import { amount, cadence, useMacro } from './macro-format';

const DIRECTION = { up: 'Subiendo', down: 'Bajando', flat: 'Estable' } as const;

/** Compact macro context for Home (#195): the series the backend marks, read from the FRED cache. */
export function MacroStrip() {
  const query = useMacro();
  const items = query.data?.items.filter((item) => item.home) ?? [];
  if (query.isError || (query.data && !items.length)) return null;
  return (
    <SummaryCard
      title="Cómo está la economía"
      icon={Landmark}
      more={{ to: '/macro', label: 'Ver más datos de la economía' }}
    >
      {query.isPending ? (
        <p className="text-xs text-muted-foreground" role="status">
          Leyendo la caché de FRED…
        </p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {items.map((item) => (
            <li key={item.series_id} className="min-w-0">
              <p className="text-xs text-muted-foreground">{item.label}</p>
              <p className="text-lg font-semibold tabular-nums">
                {item.latest_value == null ? '—' : formatNumber(item.latest_value, { digits: 2 })}{' '}
                <span className="text-xs font-normal">{item.unit}</span>
                {item.change_3m != null && (
                  <span
                    className="ml-2 text-xs font-normal text-muted-foreground"
                    title="Cambio frente a hace 3 meses"
                  >
                    <Direction value={item.change_3m}>
                      {amount(Math.abs(item.change_3m), item.change_unit)} en 3 meses
                    </Direction>
                  </span>
                )}
              </p>
              <p className="text-xs text-muted-foreground">
                {item.latest_value == null ? 'Sin datos guardados' : dateLabel(item.latest_date)} ·{' '}
                {cadence(item)}
              </p>
              {item.trend.direction && (
                <div className="mt-1.5 flex items-center gap-2">
                  {/* The last 12 months only: the 5-year view and its median are on the Macro page. */}
                  <Sparkline
                    values={item.trend.points.slice(-13).map((point) => point.value)}
                    description={item.trend.text ?? ''}
                    width={72}
                    height={20}
                  />
                  <span className="text-xs text-muted-foreground">
                    {DIRECTION[item.trend.direction]} en 12 meses
                  </span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        Datos de la Reserva Federal (FRED) guardados en tu equipo. Son contexto: no cambian la
        puntuación de las empresas.
      </p>
    </SummaryCard>
  );
}
