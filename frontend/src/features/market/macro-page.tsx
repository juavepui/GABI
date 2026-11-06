import { Link } from 'react-router-dom';
import { dateLabel, formatNumber } from '@/shared/lib/format';
import type { MacroLabel, MacroPoint } from '@/shared/api/generated/types.gen';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { PageHeader } from '@/shared/ui/page-header';
import { HowToRead } from '@/shared/ui/how-to-read';
import { Term } from '@/shared/ui/term';
import { Sparkline } from '@/shared/ui/charts/sparkline';
import { Direction } from '@/shared/ui/status';
import { amount, cadence, useMacro } from './macro-format';

const TONE: Record<MacroLabel['tone'], string> = {
  good: 'border-success-border bg-success-soft text-success-ink',
  bad: 'border-warning-border bg-warning-soft text-warning-ink',
  neutral: 'border-border bg-muted/40',
};

/** The block's state in words (#309); the backend applies the rule and says which value it read. */
function LabelCard({ label }: { label: MacroLabel }) {
  const value =
    label.value == null
      ? null
      : label.block === 'liquidity'
        ? formatNumber(label.value, { digits: 1, signed: true }) + ' % en 3 meses'
        : formatNumber(label.value, { digits: 2 }) +
          (label.series_id === 'NFCI' ? '' : label.block === 'growth_jobs' ? ' p. p.' : ' %');
  return (
    <li className={'min-w-0 rounded-xl border p-4 ' + TONE[label.tone]}>
      <p className="text-xs font-medium opacity-80">{label.title}</p>
      <p className="mt-1 text-lg font-semibold">{label.label}</p>
      <p className="mt-1 text-xs opacity-80">
        {label.series_id
          ? `${value} · FRED ${label.series_id}, dato del ${dateLabel(label.date)}`
          : 'Sin datos guardados'}
      </p>
      <p className="mt-2 text-xs opacity-80">{label.rule}</p>
    </li>
  );
}

function SeriesCard({ item }: { item: MacroPoint }) {
  return (
    <article className="rounded-xl border bg-card p-5">
      <p className="text-xs font-medium text-muted-foreground">{item.label}</p>
      <p className="mt-3 text-2xl font-semibold tabular-nums">
        {item.unit === 'USD' ? (
          amount(item.latest_value, item.unit)
        ) : (
          <>
            {formatNumber(item.latest_value, { digits: item.unit === 'personas' ? 0 : 2 })}{' '}
            <span className="text-sm font-normal">{item.unit}</span>
          </>
        )}
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        {item.latest_value == null
          ? 'Sin datos guardados'
          : 'Dato del ' + dateLabel(item.latest_date)}
        {item.change_3m != null && (
          <>
            {' · En 3 meses: '}
            <Direction value={item.change_3m}>
              {amount(Math.abs(item.change_3m), item.change_unit)}
            </Direction>
          </>
        )}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Fuente: FRED ({item.series_id}) · {cadence(item)}
      </p>
      {item.trend.text && (
        <div className="mt-3 space-y-1">
          <Sparkline
            values={item.trend.points.map((point) => point.value)}
            reference={item.trend.median}
            description={item.trend.text}
            width={240}
            height={48}
            className="w-full"
          />
          <p className="text-xs">{item.trend.text}</p>
          {item.trend.median != null && (
            <p className="text-xs text-muted-foreground">
              Un punto por mes; la línea discontinua es su mediana de esos años.
            </p>
          )}
        </div>
      )}
      <p className="mt-4 text-xs leading-relaxed text-muted-foreground">{item.help}</p>
    </article>
  );
}

export function MacroPage() {
  const query = useMacro();
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/', label: 'Hoy' }}
        title="Economía (macro)"
        description={
          <>
            Cómo está la economía de EE. UU.: tipos de interés, inflación, dólar y señales de
            recesión. Es contexto para tus decisiones; no cambia la puntuación de las empresas.
          </>
        }
        guide={
          <>
            <p>
              Útil para tus notas del{' '}
              <Link className="text-primary underline" to="/cartera/diario">
                diario de inversión
              </Link>
              : por ejemplo, si los tipos de interés suben, las empresas cuyo beneficio está muy
              lejos en el futuro suelen sufrir más. Los datos son de FRED (la base de datos pública
              de la Reserva Federal) y se leen de tu equipo; abrir esta página no descarga nada.
            </p>
          </>
        }
      />
      {query.isPending && <LoadingState />}
      {query.isError && <ErrorState error={query.error} retry={() => void query.refetch()} />}
      {query.data && (
        <>
          {!query.data.fred_key_configured && (
            <p
              role="note"
              className="rounded-xl border border-warning-border bg-warning-soft p-4 text-sm text-warning-ink"
            >
              Falta la clave de FRED, así que estos datos no se pueden actualizar: ves los que ya
              estaban guardados. Es gratuita; guárdala en{' '}
              <Link className="underline" to="/administracion">
                Administración
              </Link>{' '}
              para refrescarlas.
            </p>
          )}
          <section aria-label="La economía en palabras" className="space-y-2">
            <h2 className="text-lg font-semibold">
              La economía en palabras <Term k="macro_labels" name="Etiquetas de la economía" />
            </h2>
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {query.data.labels.map((label) => (
                <LabelCard key={label.block} label={label} />
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">
              Describen cómo está la economía ahora; no predicen lo que hará la bolsa ni cambian la
              puntuación de las empresas.
            </p>
            <HowToRead>
              Cada etiqueta sale de una regla fija sobre un solo dato de FRED, escrita debajo de la
              etiqueta, para que puedas comprobarla. Los límites (por ejemplo, el 3 % de inflación)
              son referencias razonables, no umbrales demostrados para invertir. Cada dato lleva su
              fecha porque FRED los publica con ritmos distintos: unos cada día y otros cada mes.
            </HowToRead>
          </section>
          {query.data.labels.map((label) => {
            const items = query.data.items.filter((item) => item.block === label.block);
            if (!items.length) return null;
            return (
              <section key={label.block} aria-label={label.title} className="space-y-3">
                <h2 className="text-lg font-semibold">{label.title}</h2>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {items.map((item) => (
                    <SeriesCard key={item.series_id} item={item} />
                  ))}
                </div>
              </section>
            );
          })}
          <p className="text-sm text-muted-foreground">
            Para actualizar las series, usa «Actualizar todo» en{' '}
            <Link className="text-primary underline" to="/administracion">
              Administración
            </Link>
            . La fecha del próximo dato de inflación (IPC) no se muestra porque habría que
            consultarla en internet.
          </p>
        </>
      )}
    </div>
  );
}
