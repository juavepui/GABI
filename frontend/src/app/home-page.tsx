import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BriefcaseBusiness,
  ChartNoAxesCombined,
  CheckCircle2,
  Circle,
  CircleDashed,
  Database,
  FlaskConical,
  GraduationCap,
  Settings2,
} from 'lucide-react';
import { getHome } from '@/shared/api/client';
import { useResearchMode } from '@/shared/api/use-model';
import type { HomeResponse } from '@/shared/api/generated/types.gen';
import { dateLabel, formatNumber } from '@/shared/lib/format';
import { Button } from '@/shared/ui/button';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { SectionLinks } from '@/shared/ui/section-links';
import { StatusTag } from '@/shared/ui/status';
import { SummaryCard } from '@/shared/ui/summary-card';
import { HomeNotices } from './home-notices';
import { MacroStrip, MarketHealthCard } from '@/features/market/index';
import { HomeAlerts } from './home-alerts';
import { HomeSummaryCard } from './home-summary';
import { PageHeader } from '@/shared/ui/page-header';

const WARNINGS: Record<string, string> = {
  incomplete_coverage: 'a algunas empresas les faltan precios o datos de sus cuentas',
  prices_stale: 'hay precios de hace más de una semana',
  fundamentals_stale: 'hay datos de las cuentas de hace más de una semana',
  sec_stale: 'hay informes oficiales (SEC) sin revisar desde hace más de dos semanas',
  universe_stale: 'la lista de empresas del S&P 500 tiene más de una semana',
};

function Step({
  done,
  title,
  detail,
  action,
}: {
  done: boolean | null;
  title: string;
  detail: string;
  action?: { to: string; label: string };
}) {
  const Icon = done ? CheckCircle2 : done === null ? CircleDashed : Circle;
  return (
    <li className="flex items-start gap-3 py-3">
      <Icon
        size={20}
        aria-hidden="true"
        className={done ? 'mt-0.5 text-success' : 'mt-0.5 text-muted-foreground'}
      />
      <div className="min-w-0 flex-1">
        <p className={'text-sm font-medium ' + (done ? 'text-muted-foreground line-through' : '')}>
          {title}
          <span className="sr-only">
            {done ? ' (hecho)' : done === null ? ' (comprobando)' : ''}
          </span>
        </p>
        <p className="text-xs text-muted-foreground">{detail}</p>
      </div>
      {action && !done && (
        <Button asChild size="sm" variant="outline">
          <Link to={action.to}>{action.label}</Link>
        </Button>
      )}
    </li>
  );
}

function FirstSteps({ home }: { home: HomeResponse }) {
  const { steps } = home;
  const pending =
    !steps.fred_key || !steps.universe || steps.data_loaded === false || !steps.updated;
  if (!pending) return null;
  return (
    <section className="rounded-xl border bg-card p-5" aria-label="Primeros pasos">
      <h2 className="text-lg font-semibold">Primeros pasos</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Lo que falta para que GABI tenga datos con los que trabajar. Solo hay que hacerlo una vez.
      </p>
      <ol className="mt-2 divide-y">
        <Step
          done={steps.fred_key}
          title="Guardar la clave de FRED (opcional)"
          detail="Una contraseña gratuita de la Reserva Federal de EE. UU. que permite ver los datos de la economía (tipos de interés, inflación)."
          action={{ to: '/administracion', label: 'Ir a Administración' }}
        />
        <Step
          done={steps.universe && steps.updated}
          title="Actualizar los datos"
          detail="Descarga precios y cuentas de las empresas. Empieza con 50 para probar; las 500 del S&P 500 tardan varios minutos."
          action={{ to: '/administracion', label: 'Actualizar datos' }}
        />
        <Step
          done={steps.data_loaded}
          title="Ver el ranking"
          detail={
            steps.data_loaded === null
              ? 'Se comprobará en cuanto termine el cálculo del ranking.'
              : 'Las empresas ordenadas por su puntuación GABI.'
          }
          action={{ to: '/descubrir', label: 'Abrir el Ranking' }}
        />
        <Step
          done={false}
          title="Leer la Ayuda (opcional)"
          detail="Qué significa cada término, estrategias y cómo decide GABI."
          action={{ to: '/ayuda', label: 'Abrir la Ayuda' }}
        />
      </ol>
    </section>
  );
}

function DataCard({ home, computing }: { home: HomeResponse; computing: boolean }) {
  const data = home.data;
  return (
    <SummaryCard
      title="Estado de los datos"
      icon={Database}
      more={{ to: '/administracion/calidad', label: 'Ver calidad de los datos' }}
    >
      {data ? (
        <>
          <p className="text-sm">
            {data.status === 'ready' && data.prices_current === true && (
              <StatusTag tone="good" label="Al día" />
            )}
            {data.status === 'ready' && data.prices_current === false && (
              <StatusTag tone="caution" label="Falta el último cierre" />
            )}
            {data.status === 'ready' && data.prices_current == null && (
              <StatusTag tone="neutral" label="Listos para usar" />
            )}
            {data.status === 'stale' && <StatusTag tone="caution" label="Con datos antiguos" />}
            {data.status === 'empty' && <StatusTag tone="bad" label="Sin datos" />}
          </p>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-xs text-muted-foreground">Empresas puntuadas</dt>
              <dd className="font-semibold tabular-nums">
                {data.scored_count} de {data.universe_count}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Precios hasta el</dt>
              <dd className="font-semibold">{dateLabel(data.latest_price_date)}</dd>
            </div>
          </dl>
          {data.prices_current === false && data.last_session && (
            <p className="mt-3 text-xs text-muted-foreground">
              El último día de bolsa fue el {dateLabel(data.last_session)}. Actualiza los datos para
              tener sus precios.
            </p>
          )}
          {data.warnings.length > 0 && (
            <ul className="mt-3 list-disc pl-5 text-xs text-muted-foreground">
              {data.warnings.map((warning) => (
                <li key={warning}>{WARNINGS[warning] ?? warning}</li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="space-y-2" role="status">
          <p className="text-sm text-muted-foreground">
            {computing
              ? 'Calculando el ranking con los datos de tu equipo. Tras arrancar o actualizar los datos tarda entre 20 segundos y un minuto; después es inmediato.'
              : 'El ranking aún no está calculado.'}
          </p>
          {computing && (
            <div className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
              <div className="h-full w-1/3 animate-[pulse_1.2s_ease-in-out_infinite] rounded-full bg-gradient-to-r from-success to-success" />
            </div>
          )}
        </div>
      )}
      <p className="mt-4 text-xs text-muted-foreground">
        {home.last_update?.finished_at
          ? 'Última actualización de datos: ' + dateLabel(home.last_update.finished_at.slice(0, 10))
          : 'Todavía no se han actualizado los datos desde GABI.'}
      </p>
      <Button asChild size="sm" variant="outline" className="mt-3">
        <Link to="/administracion">Actualizar datos</Link>
      </Button>
    </SummaryCard>
  );
}

function TargetCard({ home }: { home: HomeResponse }) {
  const shown = home.target.slice(0, 8);
  return (
    <SummaryCard
      title="Cartera objetivo de hoy"
      icon={BriefcaseBusiness}
      more={{ to: '/cartera', label: 'Ver la cartera propuesta' }}
    >
      <p className="text-xs text-muted-foreground">
        Las {home.target_positions} empresas con más puntuación, con el mismo dinero en cada una. Es
        la regla fija de GABI ({home.model_id}); todavía no está demostrado que gane al S&amp;P 500.
      </p>
      {home.data && home.target.length === 0 && (
        <p className="mt-3 text-sm text-muted-foreground">
          Ninguna empresa tiene todavía datos suficientes para entrar en la cartera.
        </p>
      )}
      {shown.length > 0 && (
        <ol className="mt-3 space-y-1.5">
          {shown.map((row, index) => (
            <li key={row.symbol} className="flex items-center gap-3 text-sm">
              <span className="w-5 text-right text-xs tabular-nums text-muted-foreground">
                {index + 1}
              </span>
              <Link
                className="w-16 shrink-0 font-semibold text-primary"
                to={'/empresas/' + encodeURIComponent(row.symbol)}
              >
                {row.symbol}
              </Link>
              <span className="min-w-0 flex-1 truncate text-muted-foreground">{row.name}</span>
              <span className="hidden w-40 shrink-0 truncate text-xs text-muted-foreground sm:inline">
                {row.sector ?? 'Sin sector'}
              </span>
              <span className="h-1.5 w-20 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                <span
                  className="block h-full rounded-full bg-success"
                  style={{ width: `${Math.min(Math.max(row.composite_score, 0), 100)}%` }}
                />
              </span>
              <span className="w-10 text-right text-xs tabular-nums">
                {formatNumber(row.composite_score, { digits: 1 })}
              </span>
            </li>
          ))}
        </ol>
      )}
      {home.target.length > shown.length && (
        <p className="mt-2 text-xs text-muted-foreground">
          y {home.target.length - shown.length} más, con un{' '}
          {formatNumber(home.target[0].weight_pct, { digits: 1 })} % cada una.
        </p>
      )}
    </SummaryCard>
  );
}

/** The home page: what state GABI is in and what to do next. It never downloads anything. */
export function HomePage() {
  const queryClient = useQueryClient();
  const research = useResearchMode();
  const home = useQuery({
    queryKey: ['home'],
    queryFn: ({ signal }) => getHome(false, signal),
  });
  const compute = useQuery({
    queryKey: ['home', 'compute'],
    queryFn: ({ signal }) => getHome(true, signal),
    enabled: home.data?.ranking_ready === false,
    staleTime: Infinity,
  });
  useEffect(() => {
    if (compute.data) queryClient.setQueryData(['home'], compute.data);
  }, [compute.data, queryClient]);
  const data = home.data;
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Inicio"
        title="Tu GABI hoy"
        description={
          <>
            Qué ha cambiado en tus empresas, lo que tienes pendiente, cómo están tus datos y la
            cartera que GABI propone hoy.
          </>
        }
        guide={
          <>
            <p>
              <strong>Qué es GABI.</strong> Una herramienta que puntúa de 0 a 100 las empresas del
              S&amp;P 500 (las 500 mayores de EE. UU.) según cuatro apartados: si su precio es
              razonable, si es una buena empresa, si su cotización viene subiendo y cuánto riesgo
              tiene. Con las mejor puntuadas propone una cartera.
            </p>
            <p>
              <strong>Por dónde empezar.</strong> Mira el Ranking en Descubrir, abre la ficha de las
              empresas que te interesen y, antes de comprar, escribe en el Diario por qué lo harías.
            </p>
            <p>
              Todo se calcula con los datos guardados en tu equipo; nada se descarga sin que lo
              pidas.
            </p>
          </>
        }
      />
      <HomeNotices />
      {home.isPending && <LoadingState />}
      {home.isError && <ErrorState error={home.error} retry={() => void home.refetch()} />}
      {compute.isError && <ErrorState error={compute.error} retry={() => void compute.refetch()} />}
      {data && (
        <>
          <FirstSteps home={data} />
          <HomeSummaryCard summary={data.summary} rankingReady={data.ranking_ready} />
          <HomeAlerts alerts={data.alerts ?? []} />
          <MarketHealthCard />
          <MacroStrip />
          <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <DataCard home={data} computing={compute.isFetching} />
            <TargetCard home={data} />
          </div>
        </>
      )}
      <section aria-label="Ir a">
        <h2 className="text-lg font-semibold">Ir a</h2>
        <SectionLinks
          label="Secciones de GABI"
          links={[
            {
              to: '/descubrir',
              label: 'Descubrir',
              description: 'Ranking de empresas, fichas y comparaciones',
              icon: ChartNoAxesCombined,
            },
            {
              to: '/cartera',
              label: 'Cartera',
              description: 'La cartera propuesta, tus compras y tu diario de inversión',
              icon: BriefcaseBusiness,
            },
            {
              to: '/investigacion',
              label: 'Investigación',
              description: 'Ensayos, backtests y laboratorios',
              icon: FlaskConical,
            },
            {
              to: '/ayuda',
              label: 'Ayuda',
              description: 'Qué significa cada término y cómo decide GABI',
              icon: GraduationCap,
            },
            {
              to: '/administracion',
              label: 'Administración',
              description: 'Actualizar datos y ajustes',
              icon: Settings2,
            },
          ].filter((link) => research || link.to !== '/investigacion')}
        />
      </section>
    </div>
  );
}
