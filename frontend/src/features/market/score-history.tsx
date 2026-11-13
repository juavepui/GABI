import { useQuery } from '@tanstack/react-query';
import { getCompanyScoreHistory } from '@/shared/api/client';
import { dateLabel, formatNumber } from '@/shared/lib/format';
import { ChartFrame } from '@/shared/ui/charts/chart-frame';
import { Sparkline } from '@/shared/ui/charts/sparkline';

/** «¿Mejora o empeora con el tiempo?» (#328): the scores the daily task stored; other models are not mixed in. */
export function ScoreHistory({ symbol }: { symbol: string }) {
  const query = useQuery({
    queryKey: ['market', 'score-history', symbol],
    queryFn: ({ signal }) => getCompanyScoreHistory(symbol, signal),
  });
  const data = query.data;
  if (!data) return null;
  const same = data.points.filter((point) => point.model_id === data.model_id);
  return (
    <section aria-label="Evolución de la puntuación" className="mb-6 rounded-xl border bg-card p-5">
      <ChartFrame
        title="¿Mejora o empeora con el tiempo?"
        conclusion={data.reading.text}
        note={
          <>
            Cada día de bolsa, la tarea diaria guarda la puntuación GABI y el puesto de todas las
            empresas. Solo se comparan días del mismo modelo ({data.model_id}).
          </>
        }
        table={
          data.points.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b text-muted-foreground">
                  <tr>
                    <th className="pb-1.5">Día</th>
                    <th className="pb-1.5">Modelo</th>
                    <th className="pb-1.5 text-right">Puntuación</th>
                    <th className="pb-1.5 text-right">Puesto</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {data.points.map((point) => (
                    <tr key={point.day + point.model_id} className="border-b last:border-0">
                      <td className="py-1">{dateLabel(point.day)}</td>
                      <td className="py-1">{point.model_id}</td>
                      <td className="py-1 text-right">
                        {formatNumber(point.score, { digits: 1, fixed: true })}
                      </td>
                      <td className="py-1 text-right">
                        {point.rank} de {point.universe}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-muted-foreground">Sin días guardados todavía.</p>
          )
        }
      >
        {same.length >= 2 && (
          <Sparkline
            values={same.map((point) => point.score)}
            description={data.reading.text}
            width={480}
            height={56}
            className="w-full max-w-xl"
          />
        )}
      </ChartFrame>
    </section>
  );
}
