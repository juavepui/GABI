import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import type { PlanRequest } from '@/shared/api/generated/types.gen';
import { getEvidenceTop, getPortfolioPlan, saveSnapshot } from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Badge } from '@/shared/ui/badge';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { EvidenceTable } from '@/shared/ui/evidence-table';
import { Folded } from '@/shared/ui/folded';
import { SectionLinks } from '@/shared/ui/section-links';
import { FlaskRound, NotebookPen, Radar, Wallet } from 'lucide-react';
import { formatMoney, formatNumber } from '@/shared/lib/format';
import { PageHeader } from '@/shared/ui/page-header';
import { Textarea } from '@/shared/ui/textarea';
import { Term } from '@/shared/ui/term';
import { BlockBars, SummaryText } from '@/shared/ui/score-summary';
import { SectorBreakdown } from './sector-breakdown';
import { ExperimentalPlan } from './decisions-page';
export { JournalPage } from './journal-page';
export { LearnPage } from './learn-page';
export { SimulationsPage } from './simulations-page';
export { HoldingsPage } from './holdings-page';

const euro = (value: number) => formatMoney(value, { currency: 'EUR', digits: 2 });
const decimal = (value: number | null | undefined, digits = 1) => formatNumber(value, { digits });
const initial: PlanRequest = {
  n_positions: 20,
  capital_eur: 1000,
  holdings_text: '',
  new_capital_eur: 1000,
  sector_limit_percent: 25,
  industry_limit_percent: 15,
  use_saved_holdings: true,
};

function PlanEvidenceContent() {
  const evidence = useQuery({
    queryKey: ['portfolio', 'evidence'],
    queryFn: ({ signal }) => getEvidenceTop(true, signal),
  });
  return (
    <>
      <p className="text-xs text-muted-foreground">
        Confianza de evidencia BAJA/MEDIA/ALTA según reglas publicadas; no es probabilidad de
        subida. El detalle de cada candidata está en su ficha.
      </p>
      {evidence.isPending && <LoadingState />}
      {evidence.isError && (
        <ErrorState error={evidence.error} retry={() => void evidence.refetch()} />
      )}
      {evidence.data && <EvidenceTable rows={evidence.data.rows} />}
    </>
  );
}

function PlanEvidence() {
  return (
    <Folded title="Evidencia de las candidatas (pesos congelados)">
      <PlanEvidenceContent />
    </Folded>
  );
}

/** «Guardar esta cartera para seguirla» (#193): the backend saves exactly today's target, the same
 *  eligible Top-N, and Seguimiento compares it with SPY from today on. */
function TrackTarget({ positions }: { positions: number }) {
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: () =>
      saveSnapshot({
        name: 'Cartera objetivo · Top-' + positions,
        top_n: positions,
        target: true,
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['market', 'snapshots'] }),
  });
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={save.isPending || save.isSuccess}
        onClick={() => save.mutate()}
      >
        Guardar esta cartera para seguirla
      </Button>
      {save.isSuccess && (
        <p role="status">
          Guardada. Su evolución frente a SPY está en{' '}
          <Link className="text-primary underline" to="/cartera/seguimiento">
            Seguimiento
          </Link>
          .
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-destructive">
          {save.error.message}
        </p>
      )}
    </div>
  );
}

/** The two answers to «what do I buy and how much?», chosen in the URL so either can be shared. */
const PLANS = [
  { id: 'regla', label: 'Regla congelada · Top-N equiponderado' },
  { id: 'experimental', label: 'Plan experimental con límites' },
] as const;

export function PortfolioPage() {
  const [params, setParams] = useSearchParams();
  const experimental = params.get('plan') === 'experimental';
  const [submitted, setSubmitted] = useState(initial);
  const plan = useQuery({
    queryKey: ['portfolio', 'plan', submitted],
    queryFn: ({ signal }) => getPortfolioPlan(submitted, signal),
    enabled: !experimental,
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSubmitted({
      n_positions: Number(form.get('n_positions')),
      capital_eur: Number(form.get('capital_eur')),
      holdings_text: String(form.get('holdings_text') ?? ''),
      new_capital_eur: Number(form.get('new_capital_eur')),
      sector_limit_percent: Number(form.get('sector_limit_percent')),
      industry_limit_percent: Number(form.get('industry_limit_percent')),
      use_saved_holdings: true,
    });
  }
  const data = plan.data;
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Cartera / Plan"
        title="Mi cartera objetivo"
        description={
          <>
            Las candidatas de la hipótesis congelada y cómo repartir tu capital. No se envían
            órdenes.
          </>
        }
        guide={
          <>
            <p>
              Selección Top-N con los pesos congelados y al menos un 70 % de métricas disponibles.
              El cálculo y reparto de capital se hacen en Python sobre la caché local. No se envían
              órdenes.
            </p>
          </>
        }
      >
        <SectionLinks
          label="Apartados de Cartera"
          links={[
            {
              to: '/cartera/mi-cartera',
              label: 'Mi cartera',
              description: 'Tus compras reales frente al objetivo y SPY',
              icon: Wallet,
            },
            {
              to: '/cartera/diario',
              label: 'Diario de inversión',
              description: 'Tesis antes de comprar y revisión',
              icon: NotebookPen,
            },
            {
              to: '/cartera/seguimiento',
              label: 'Seguimiento',
              description: 'Cestas guardadas frente a SPY',
              icon: Radar,
            },
            {
              to: '/cartera/simuladas',
              label: 'Carteras simuladas',
              description: 'Operaciones hipotéticas frente a SPY',
              icon: FlaskRound,
            },
          ]}
        />
      </PageHeader>
      <div role="radiogroup" aria-label="Tipo de plan" className="flex flex-wrap gap-2">
        {PLANS.map(({ id, label }) => {
          const selected = (id === 'experimental') === experimental;
          return (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={selected}
              className={
                'rounded-full border px-4 py-1.5 text-sm ' +
                (selected ? 'border-primary bg-primary text-primary-foreground' : 'bg-card')
              }
              onClick={() => setParams(id === 'experimental' ? { plan: id } : {})}
            >
              {label}
            </button>
          );
        })}
      </div>
      {experimental ? (
        <ExperimentalPlan />
      ) : (
        <>
          <form onSubmit={submit} className="rounded-xl border bg-card p-5">
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="text-sm font-medium">
                Posiciones objetivo
                <Input
                  className="mt-1.5"
                  name="n_positions"
                  type="number"
                  min={5}
                  max={30}
                  defaultValue={20}
                  required
                />
              </label>
              <label className="text-sm font-medium">
                Capital ilustrativo (€)
                <Input
                  className="mt-1.5"
                  name="capital_eur"
                  type="number"
                  min={0}
                  max={1e9}
                  step="0.01"
                  defaultValue={1000}
                  required
                />
                <span className="mt-1 block text-xs font-normal text-muted-foreground">
                  Solo traduce los pesos objetivo a importes en la tabla.
                </span>
              </label>
              <label className="text-sm font-medium">
                Capital nuevo (€)
                <Input
                  className="mt-1.5"
                  name="new_capital_eur"
                  type="number"
                  min={0}
                  max={1e9}
                  step="0.01"
                  defaultValue={1000}
                  required
                />
                <span className="mt-1 block text-xs font-normal text-muted-foreground">
                  Dinero que vas a aportar ahora; se reparte en «Dónde aportar capital nuevo».
                </span>
              </label>
            </div>
            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <label className="text-sm font-medium">
                Aviso si un sector supera (%)
                <Input
                  className="mt-1.5"
                  name="sector_limit_percent"
                  type="number"
                  min={1}
                  max={100}
                  step="1"
                  defaultValue={25}
                  required
                />
              </label>
              <label className="text-sm font-medium">
                Aviso si una industria supera (%)
                <Input
                  className="mt-1.5"
                  name="industry_limit_percent"
                  type="number"
                  min={1}
                  max={100}
                  step="1"
                  defaultValue={15}
                  required
                />
              </label>
            </div>
            <label className="mt-4 block text-sm font-medium" htmlFor="holdings">
              ¿Y si…? Posiciones hipotéticas (SÍMBOLO,euros; una por línea)
            </label>
            <p className="mt-1 text-xs text-muted-foreground">
              Vacío: el plan de aportación parte de las compras guardadas en{' '}
              <Link className="text-primary underline" to="/cartera/mi-cartera">
                Mi cartera
              </Link>
              .
            </p>
            <Textarea
              id="holdings"
              name="holdings_text"
              maxLength={5000}
              rows={3}
              placeholder={'AAPL,300\nMSFT,200'}
              className="mt-1.5 w-full"
            />
            <Button className="mt-4" type="submit" disabled={plan.isFetching}>
              Calcular plan
            </Button>
          </form>
          {plan.isPending && <LoadingState />}
          {plan.isError && <ErrorState error={plan.error} retry={() => void plan.refetch()} />}
          <PlanEvidence />
          {data && (
            <>
              <section aria-label="Cartera objetivo" className="rounded-xl border bg-card p-5">
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="text-xl font-semibold">
                    Objetivo · {data.target.length} posiciones
                  </h2>
                  <Badge variant={data.status === 'FROZEN' ? 'secondary' : 'outline'}>
                    {data.status === 'FROZEN' ? 'Top-20 congelado' : 'Variante experimental'}
                  </Badge>
                </div>
                <p className="mt-2 text-sm text-muted-foreground">{data.evidence_note}</p>
                {data.target.length > 0 && <TrackTarget positions={data.n_positions} />}
                <p className="mt-1 text-xs text-muted-foreground">
                  Empresas con score en la caché local: {data.data.scored_count} de{' '}
                  {data.data.universe_count}. Precio de referencia en USD; importes del plan en EUR.
                  No se calculan acciones sin un tipo de cambio explícito.
                </p>
                {data.target.length === 0 ? (
                  <p className="mt-5 text-sm">
                    Ninguna empresa llega hoy al mínimo de métricas disponibles.
                  </p>
                ) : (
                  <div className="mt-5 overflow-x-auto">
                    <table className="w-full text-left text-xs sm:min-w-[680px] sm:text-sm">
                      <thead className="border-b text-xs text-muted-foreground">
                        <tr>
                          <th className="pb-3">Empresa</th>
                          <th className="hidden pb-3 sm:table-cell">Sector</th>
                          <th className="hidden pb-3 sm:table-cell">Score</th>
                          <th className="hidden pb-3 sm:table-cell">
                            <Term k="score_coverage">Métricas disponibles</Term>
                          </th>
                          <th className="hidden pb-3 sm:table-cell">Precio USD</th>
                          <th className="pb-3">Peso</th>
                          <th className="pb-3">Importe</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.target.map((row) => (
                          <tr key={row.symbol} className="border-b last:border-0">
                            <td className="py-3">
                              <Link
                                className="font-medium text-primary underline-offset-2 hover:underline"
                                to={'/empresas/' + encodeURIComponent(row.symbol)}
                              >
                                {row.symbol}
                              </Link>
                              <span className="ml-2 text-muted-foreground">{row.name}</span>
                              <SummaryText summary={row.summary} className="mt-1" />
                              <BlockBars summary={row.summary} compact />
                              <details className="mt-1 sm:hidden">
                                <summary className="cursor-pointer text-primary">
                                  Más datos de {row.symbol}
                                </summary>
                                <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1">
                                  <dt>Sector</dt>
                                  <dd className="text-right">{row.sector ?? '—'}</dd>
                                  <dt>Score</dt>
                                  <dd className="text-right">{decimal(row.score_points)}</dd>
                                  <dt>Métricas disponibles</dt>
                                  <dd className="text-right">
                                    {row.score_coverage_fraction == null
                                      ? '—'
                                      : decimal(row.score_coverage_fraction * 100, 0) + ' %'}
                                  </dd>
                                  <dt>Precio USD</dt>
                                  <dd className="text-right">{decimal(row.price_usd, 2)}</dd>
                                </dl>
                              </details>
                            </td>
                            <td className="hidden sm:table-cell">
                              {row.sector ?? '—'}
                              {row.industry && (
                                <span className="block text-xs text-muted-foreground">
                                  {row.industry}
                                </span>
                              )}
                            </td>
                            <td className="hidden sm:table-cell">{decimal(row.score_points)}</td>
                            <td className="hidden sm:table-cell">
                              {row.score_coverage_fraction == null
                                ? '—'
                                : decimal(row.score_coverage_fraction * 100, 0) + ' %'}
                            </td>
                            <td className="hidden sm:table-cell">{decimal(row.price_usd, 2)}</td>
                            <td>{decimal(row.weight_percent, 1)} %</td>
                            <td>{euro(row.amount_eur)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
              {data.target.length > 0 && <SectorBreakdown data={data} />}
              <section className="rounded-xl border bg-card p-5">
                <h2 className="text-xl font-semibold">Dónde aportar capital nuevo</h2>
                <p className="mt-2 text-sm">
                  {data.holdings_source === 'saved' &&
                    'Calculado sobre Mi cartera, con su valor en euros en caché.'}
                  {data.holdings_source === 'text' &&
                    'Calculado sobre las posiciones hipotéticas escritas, no sobre Mi cartera.'}
                  {data.holdings_source === 'none' && (
                    <>
                      Sin posiciones: se reparte como si empezaras de cero.{' '}
                      <Link className="text-primary underline" to="/cartera/mi-cartera">
                        Registra tus compras en Mi cartera
                      </Link>
                      .
                    </>
                  )}
                  {data.holdings_unvalued.length > 0 &&
                    ' Sin valorar (falta precio o tipo de cambio): ' +
                      data.holdings_unvalued.join(', ') +
                      '.'}
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  Solo aproxima los pesos objetivo con aportaciones. No propone ventas ni considera
                  impuestos o costes de ejecución.
                </p>
                {data.allocations.length ? (
                  <ul className="mt-4 divide-y">
                    {data.allocations.map((item) => (
                      <li key={item.symbol} className="flex justify-between gap-4 py-3 text-sm">
                        <Link
                          to={'/empresas/' + encodeURIComponent(item.symbol)}
                          className="font-medium text-primary"
                        >
                          {item.symbol} · {item.name}
                        </Link>
                        <span className="tabular-nums">{euro(item.amount_eur)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-4 text-sm">No hay aportaciones asignables con estos datos.</p>
                )}
                {data.remaining_eur > 0.01 && (
                  <p className="mt-3 text-sm">Capital sin asignar: {euro(data.remaining_eur)}.</p>
                )}
                {data.outside_target.length > 0 && (
                  <p className="mt-3 text-sm text-muted-foreground">
                    Fuera del Top actual: {data.outside_target.join(', ')}. Esto no indica vender.
                  </p>
                )}
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
