import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BriefcaseBusiness,
  ChartNoAxesCombined,
  CheckCircle2,
  Circle,
  CircleDashed,
  FlaskConical,
  GraduationCap,
  Settings2,
} from 'lucide-react';
import { getHome } from '@/shared/api/client';
import type { HomeResponse } from '@/shared/api/generated/types.gen';
import { dateLabel, formatNumber } from '@/shared/lib/format';
import { Button } from '@/shared/ui/button';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { SectionLinks } from '@/shared/ui/section-links';
import { HomeNotices } from './home-notices';
import { PageHeader } from '@/shared/ui/page-header';

const WARNINGS: Record<string, string> = {
  incomplete_coverage: 'faltan precios, fundamentales o datos SEC de algunas empresas',
  prices_stale: 'hay precios de hace más de 7 días',
  fundamentals_stale: 'hay fundamentales de hace más de 7 días',
  sec_stale: 'hay datos SEC de hace más de 14 días',
  universe_stale: 'la lista del S&P 500 tiene más de 7 días',
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
        className={done ? 'mt-0.5 text-emerald-600' : 'mt-0.5 text-muted-foreground'}
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
        Lo que falta para que GABI tenga datos con los que trabajar.
      </p>
      <ol className="mt-2 divide-y">
        <Step
          done={steps.fred_key}
          title="Guardar la clave de FRED"
          detail="Gratuita; activa el panel macro y el tipo libre de riesgo en vivo."
          action={{ to: '/administracion', label: 'Ir a Administración' }}
        />
        <Step
          done={steps.universe && steps.updated}
          title="Actualizar los datos"
          detail="Empieza con 50 empresas para probar; el universo completo tarda varios minutos."
          action={{ to: '/administracion', label: 'Actualizar datos' }}
        />
        <Step
          done={steps.data_loaded}
          title="Ver el ranking"
          detail={
            steps.data_loaded === null
              ? 'Se comprobará en cuanto termine el cálculo del ranking.'
              : 'Empresas puntuadas con los datos de tu caché.'
          }
          action={{ to: '/mercado', label: 'Abrir Mercado' }}
        />
        <Step
          done={false}
          title="Leer Aprender (opcional)"
          detail="Términos, estrategias y cómo piensa GABI."
          action={{ to: '/cartera/aprender', label: 'Abrir Aprender' }}
        />
      </ol>
    </section>
  );
}

function DataCard({ home, computing }: { home: HomeResponse; computing: boolean }) {
  const data = home.data;
  return (
    <section className="min-w-0 rounded-xl border bg-card p-5" aria-label="Estado de los datos">
      <h2 className="text-lg font-semibold">Estado de los datos</h2>
      {data ? (
        <>
          <p className="mt-2 text-sm">
            {data.status === 'ready' && data.prices_current === true && (
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-800">
                Al día
              </span>
            )}
            {data.status === 'ready' && data.prices_current === false && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-900">
                Falta el último cierre
              </span>
            )}
            {data.status === 'ready' && data.prices_current == null && (
              <span className="rounded-full bg-muted px-2 py-0.5">Listos para el ranking</span>
            )}
            {data.status === 'stale' && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-900">
                Con datos antiguos
              </span>
            )}
            {data.status === 'empty' && (
              <span className="rounded-full bg-rose-100 px-2 py-0.5 text-rose-800">Sin datos</span>
            )}
          </p>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-xs text-muted-foreground">Empresas puntuadas</dt>
              <dd className="font-semibold tabular-nums">
                {data.scored_count} de {data.universe_count}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Último precio</dt>
              <dd className="font-semibold">{dateLabel(data.latest_price_date)}</dd>
            </div>
          </dl>
          {data.prices_current === false && data.last_session && (
            <p className="mt-3 text-xs text-muted-foreground">
              Última sesión cerrada en NYSE: {dateLabel(data.last_session)}. Actualiza los datos
              para incluir su cierre.
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
        <div className="mt-3 space-y-2" role="status">
          <p className="text-sm text-muted-foreground">
            {computing
              ? 'Calculando el ranking con tu caché local. La primera vez tarda unos 30-40 s.'
              : 'El ranking aún no está calculado.'}
          </p>
          {computing && (
            <div className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
              <div className="h-full w-1/3 animate-[pulse_1.2s_ease-in-out_infinite] rounded-full bg-gradient-to-r from-emerald-500 to-teal-500" />
            </div>
          )}
        </div>
      )}
      <p className="mt-4 text-xs text-muted-foreground">
        {home.last_update?.finished_at
          ? 'Última actualización registrada: ' +
            dateLabel(home.last_update.finished_at.slice(0, 10))
          : 'No hay ninguna actualización de datos registrada como trabajo.'}
      </p>
      <Button asChild size="sm" variant="outline" className="mt-3">
        <Link to="/administracion">Actualizar datos</Link>
      </Button>
    </section>
  );
}

function TargetCard({ home }: { home: HomeResponse }) {
  const shown = home.target.slice(0, 8);
  return (
    <section className="min-w-0 rounded-xl border bg-card p-5" aria-label="Cartera objetivo de hoy">
      <h2 className="text-lg font-semibold">Cartera objetivo de hoy</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Hipótesis congelada {home.model_id}: las {home.target_positions} candidatas elegibles con
        más score, a partes iguales. No demuestra una ventaja frente al S&amp;P 500.
      </p>
      {home.data && home.target.length === 0 && (
        <p className="mt-3 text-sm text-muted-foreground">
          Ninguna empresa cumple todavía la cobertura mínima para entrar en la cartera.
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
                to={'/mercado/empresas/' + encodeURIComponent(row.symbol)}
              >
                {row.symbol}
              </Link>
              <span className="min-w-0 flex-1 truncate text-muted-foreground">{row.name}</span>
              <span className="h-1.5 w-20 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                <span
                  className="block h-full rounded-full bg-emerald-500"
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
      <Button asChild size="sm" className="mt-4">
        <Link to="/cartera">Ver la cartera y repartir capital</Link>
      </Button>
    </section>
  );
}

/** The home page: what state GABI is in and what to do next. It never downloads anything. */
export function HomePage() {
  const queryClient = useQueryClient();
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
        description={<>Estado de tus datos, la cartera objetivo y lo que tienes pendiente.</>}
        guide={
          <>
            <p>
              Estado de tus datos, la cartera objetivo y lo que tienes pendiente. Todo se calcula
              con la caché local; nada se descarga sin que lo pidas.
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
              to: '/mercado',
              label: 'Mercado',
              description: 'Ranking, fichas, comparación y macro',
              icon: ChartNoAxesCombined,
              tone: 'sky',
            },
            {
              to: '/cartera',
              label: 'Cartera',
              description: 'Cartera objetivo, diario y decisiones',
              icon: BriefcaseBusiness,
              tone: 'emerald',
            },
            {
              to: '/investigacion',
              label: 'Investigación',
              description: 'Ensayos, backtests y laboratorios',
              icon: FlaskConical,
              tone: 'violet',
            },
            {
              to: '/cartera/aprender',
              label: 'Aprender',
              description: 'Términos y cómo piensa GABI',
              icon: GraduationCap,
              tone: 'amber',
            },
            {
              to: '/administracion',
              label: 'Administración',
              description: 'Datos, claves, modo y calidad',
              icon: Settings2,
              tone: 'teal',
            },
          ]}
        />
      </section>
    </div>
  );
}
