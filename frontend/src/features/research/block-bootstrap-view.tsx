import { useState } from 'react';
import type { BlockBootstrapView } from '@/shared/api/generated/types.gen';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';

const num = (value: number | null | undefined, digits = 4) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits }).format(value);
const pct = (value: number | null | undefined) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 }).format(value * 100) + ' %';

function Histogram({ view, column }: { view: BlockBootstrapView; column: string }) {
  const item = view.histograms.find((entry) => entry.column === column);
  if (!item) return null;
  if (item.bins.length === 0)
    return (
      <p className="text-sm text-muted-foreground">
        Esta métrica no es estimable en ninguna réplica; no se dibuja una distribución artificial.
      </p>
    );
  const width = 640;
  const height = 180;
  const first = item.bins[0].start;
  const last = item.bins[item.bins.length - 1].end;
  const span = last - first || 1;
  const top = Math.max(...item.bins.map((bin) => bin.fraction)) || 1;
  const x = (value: number) => ((value - first) / span) * width;
  const marks: [number | null | undefined, string, string][] = [
    [item.lower, 'Inferior', 'currentColor'],
    [item.upper, 'Superior', 'currentColor'],
    [item.observed, 'Observado', 'rgb(220 38 38)'],
  ];
  return (
    <figure className="space-y-1">
      <svg
        viewBox={`0 0 ${width} ${height + 20}`}
        className="w-full max-w-3xl text-muted-foreground"
        role="img"
        aria-label={`Distribución del remuestreo: ${item.label}`}
      >
        {item.bins.map((bin) => (
          <rect
            key={bin.start}
            x={x(bin.start)}
            width={Math.max(1, x(bin.end) - x(bin.start) - 1)}
            y={height - (bin.fraction / top) * height}
            height={(bin.fraction / top) * height}
            className="fill-primary/70"
          >
            <title>
              {num(bin.start)} – {num(bin.end)}: {pct(bin.fraction)} de réplicas
            </title>
          </rect>
        ))}
        {marks.map(([value, label, color]) =>
          value == null || value < first || value > last ? null : (
            <line
              key={label}
              x1={x(value)}
              x2={x(value)}
              y1={0}
              y2={height}
              stroke={color}
              strokeDasharray={label === 'Observado' ? undefined : '4 3'}
            />
          ),
        )}
        <text x={0} y={height + 15} fontSize={11} fill="currentColor">
          {num(first)}
        </text>
        <text x={width} y={height + 15} fontSize={11} fill="currentColor" textAnchor="end">
          {num(last)}
        </text>
      </svg>
      <figcaption className="text-xs text-muted-foreground">
        Fracción de réplicas válidas ({item.valid_draws}). Líneas discontinuas: intervalo percentil
        ({num(item.lower)} – {num(item.upper)}); línea roja: observado ({num(item.observed)}).
      </figcaption>
    </figure>
  );
}

export function BlockBootstrapResult({
  view,
  downloads,
}: {
  view: BlockBootstrapView;
  downloads: { json: string; csv: string };
}) {
  const [column, setColumn] = useState(view.histograms[0]?.column ?? '');
  const primary = view.intervals.filter((row) => row.block_size === view.primary_block);
  return (
    <div className="space-y-4 text-sm">
      <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-amber-800 dark:text-amber-300">
        Remuestrear el pasado no genera evidencia OOS nueva. Las fracciones bootstrap no son
        p-valores ni probabilidades de éxito futuro.
      </p>
      <p className="text-xs text-muted-foreground">
        {view.n_obs} observaciones · {view.periods_per_year} por año ·{' '}
        {view.n_boot.toLocaleString('es-ES')} réplicas · bloque principal {view.primary_block} ·
        intervalo percentil {pct(view.ci)}. Dependencia dentro de bloques, con uniones artificiales.
        Retornos, volatilidad, drawdown y ES en fracción (0,10 = 10 %); Sharpe e IC sin unidades. ES
        tiene el horizonte de una observación original. Drawdown negativo incluye capital inicial.
        Los rangos de drawdown/ES son descriptivos y no tienen cobertura garantizada.
        {view.has_series &&
          ' El drawdown es el máximo durante toda la trayectoria remuestreada, de la misma duración que el histórico; su fracción no describe el riesgo de un solo año.'}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-xs" aria-label="Intervalos bootstrap">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="py-2">Serie</th>
              <th>Métrica</th>
              <th>Observado</th>
              <th>Inferior</th>
              <th>Mediana bootstrap</th>
              <th>Superior</th>
              <th>Media bootstrap</th>
              <th>Réplicas válidas</th>
              <th>No estimables</th>
            </tr>
          </thead>
          <tbody>
            {primary.map((row) => (
              <tr key={row.series + row.metric} className="border-b last:border-0">
                <td className="py-1.5">{row.series_label}</td>
                <td>{row.metric_label}</td>
                <td>{num(row.observed)}</td>
                <td>{num(row.lower)}</td>
                <td>{num(row.median)}</td>
                <td>{num(row.upper)}</td>
                <td>{num(row.bootstrap_mean)}</td>
                <td>{row.valid_draws}</td>
                <td>{row.undefined_draws}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <table className="text-left text-xs" aria-label="Fracciones bootstrap">
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="py-2 pr-4">Serie</th>
            <th className="pr-4">Condición</th>
            <th className="pr-4">Fracción bootstrap</th>
            <th className="pr-4">Réplicas válidas</th>
            <th>No estimables</th>
          </tr>
        </thead>
        <tbody>
          {view.fractions.map((row) => (
            <tr key={row.series + row.condition} className="border-b last:border-0">
              <td className="py-1.5 pr-4">{row.series}</td>
              <td className="pr-4">{row.condition}</td>
              <td className="pr-4">{num(row.fraction, 2)}</td>
              <td className="pr-4">{row.valid_draws}</td>
              <td>{row.undefined_draws}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {view.tail_sparse && (
        <p className="text-xs text-muted-foreground">
          Cola ES5 escasa: masa de {num(view.tail_mass, 2)} observaciones. Las réplicas no crean
          nuevos episodios extremos.
        </p>
      )}
      <label className="grid w-fit gap-1">
        Distribución del remuestreo
        <NativeSelect value={column} onChange={(event) => setColumn(event.target.value)}>
          {view.histograms.map((item) => (
            <NativeSelectOption key={item.column} value={item.column}>
              {item.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </label>
      <Histogram view={view} column={column} />
      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer font-medium">
          Sensibilidad de bloques y comparación con HAC/Newey-West
        </summary>
        <p className="mt-2 text-xs text-muted-foreground">
          Las longitudes se fijaron antes del análisis. Se presentan todas; no se selecciona la más
          favorable.
        </p>
        <div className="mt-2 overflow-x-auto">
          <table
            className="w-full min-w-[760px] text-left text-xs"
            aria-label="Todas las longitudes"
          >
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-2">Bloque</th>
                <th>Serie</th>
                <th>Métrica</th>
                <th>Observado</th>
                <th>Inferior</th>
                <th>Mediana</th>
                <th>Superior</th>
              </tr>
            </thead>
            <tbody>
              {view.intervals.map((row) => (
                <tr
                  key={String(row.block_size) + row.series + row.metric}
                  className="border-b last:border-0"
                >
                  <td className="py-1.5">{row.block_size}</td>
                  <td>{row.series_label}</td>
                  <td>{row.metric_label}</td>
                  <td>{num(row.observed)}</td>
                  <td>{num(row.lower)}</td>
                  <td>{num(row.median)}</td>
                  <td>{num(row.upper)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {view.comparisons.length > 0 && (
          <>
            <div className="mt-3 overflow-x-auto">
              <table
                className="w-full min-w-[760px] text-left text-xs"
                aria-label="Comparación con HAC"
              >
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="py-2">Bloque</th>
                    <th>Serie</th>
                    <th>Media</th>
                    <th>Bootstrap inferior</th>
                    <th>Bootstrap superior</th>
                    <th>HAC inferior</th>
                    <th>HAC superior</th>
                    <th>Retardos HAC</th>
                    <th>Difieren al excluir cero</th>
                  </tr>
                </thead>
                <tbody>
                  {view.comparisons.map((row) => (
                    <tr
                      key={String(row.block_size) + row.series}
                      className="border-b last:border-0"
                    >
                      <td className="py-1.5">{row.block_size}</td>
                      <td>{row.series}</td>
                      <td>{num(row.mean, 6)}</td>
                      <td>{num(row.bootstrap_lower, 6)}</td>
                      <td>{num(row.bootstrap_upper, 6)}</td>
                      <td>{num(row.hac_lower, 6)}</td>
                      <td>{num(row.hac_upper, 6)}</td>
                      <td>{row.hac_lags}</td>
                      <td>{row.zero_conclusion_differs ? 'Sí' : 'No'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              HAC compara medias, no CAGR, Sharpe ni drawdown. Diferencias al excluir cero reflejan
              métodos y aproximaciones distintos; no deciden cuál es correcto.
            </p>
          </>
        )}
      </details>
      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer font-medium">Parámetros y descarga reproducible</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
          {view.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
        <div className="mt-3 flex flex-wrap gap-4">
          <a className="text-primary underline" href={downloads.json} download>
            Descargar parámetros e intervalos
          </a>
          <a className="text-primary underline" href={downloads.csv} download>
            Descargar todas las réplicas
          </a>
        </div>
      </details>
    </div>
  );
}
