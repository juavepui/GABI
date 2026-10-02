import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import type { PlanRequest } from '@/shared/api/generated/types.gen';
import { getEvidenceTop, getPortfolioPlan } from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Badge } from '@/shared/ui/badge';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { EvidenceTable } from '@/shared/ui/evidence-table';
import { Folded } from '@/shared/ui/folded';
import { SectionLinks } from '@/shared/ui/section-links';
import { Compass, FlaskRound, GraduationCap, NotebookPen } from 'lucide-react';
import { formatMoney, formatNumber } from '@/shared/lib/format';
import { PageHeader } from '@/shared/ui/page-header';
export { JournalPage } from './journal-page';
export { LearnPage } from './learn-page';
export { SimulationsPage } from './simulations-page';
export { DecisionsPage } from './decisions-page';

const euro = (value: number) => formatMoney(value, { currency: 'EUR', digits: 2 });
const decimal = (value: number | null | undefined, digits = 1) => formatNumber(value, { digits });
const initial: PlanRequest = {
  n_positions: 20,
  capital_eur: 1000,
  holdings_text: '',
  new_capital_eur: 1000,
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

export function PortfolioPage() {
  const [submitted, setSubmitted] = useState(initial);
  const plan = useQuery({
    queryKey: ['portfolio', 'plan', submitted],
    queryFn: ({ signal }) => getPortfolioPlan(submitted, signal),
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSubmitted({
      n_positions: Number(form.get('n_positions')),
      capital_eur: Number(form.get('capital_eur')),
      holdings_text: String(form.get('holdings_text') ?? ''),
      new_capital_eur: Number(form.get('new_capital_eur')),
    });
  }
  const data = plan.data;
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Cartera / Plan"
        title="Mi cartera objetivo"
        description="Selección Top-N con los pesos congelados y cobertura mínima del 70 %. El cálculo y reparto de capital se hacen en Python sobre la caché local. No se envían órdenes."
      >
        <SectionLinks
          label="Apartados de Cartera"
          links={[
            {
              to: '/cartera/diario',
              label: 'Diario de inversión',
              description: 'Tesis antes de comprar y revisión',
              icon: NotebookPen,
              tone: 'amber',
            },
            {
              to: '/cartera/aprender',
              label: 'Aprender',
              description: 'Términos, estrategias y cómo piensa GABI',
              icon: GraduationCap,
              tone: 'emerald',
            },
            {
              to: '/cartera/simuladas',
              label: 'Carteras simuladas',
              description: 'Operaciones hipotéticas frente a SPY',
              icon: FlaskRound,
              tone: 'sky',
            },
            {
              to: '/cartera/decisiones',
              label: 'Decisiones',
              description: 'Plan experimental de compra y venta',
              icon: Compass,
              tone: 'violet',
            },
          ]}
        />
      </PageHeader>
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
          </label>
        </div>
        <label className="mt-4 block text-sm font-medium" htmlFor="holdings">
          Posiciones actuales (SÍMBOLO,euros; una por línea)
        </label>
        <textarea
          id="holdings"
          name="holdings_text"
          maxLength={5000}
          rows={3}
          placeholder={'AAPL,300\nMSFT,200'}
          className="mt-1.5 w-full rounded-md border bg-background p-3 text-sm"
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
          <section className="rounded-xl border bg-card p-5">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-xl font-semibold">Objetivo · {data.target.length} posiciones</h2>
              <Badge variant={data.status === 'FROZEN' ? 'secondary' : 'outline'}>
                {data.status === 'FROZEN' ? 'Top-20 congelado' : 'Variante experimental'}
              </Badge>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{data.evidence_note}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Cobertura local: {data.data.scored_count} de {data.data.universe_count} empresas con
              score. Precio de referencia en USD; importes del plan en EUR. No se calculan acciones
              sin un tipo de cambio explícito.
            </p>
            {data.target.length === 0 ? (
              <p className="mt-5 text-sm">Ninguna empresa supera hoy el umbral de cobertura.</p>
            ) : (
              <div className="mt-5 overflow-x-auto">
                <table className="w-full min-w-[680px] text-left text-sm">
                  <thead className="border-b text-xs text-muted-foreground">
                    <tr>
                      <th className="pb-3">Empresa</th>
                      <th className="pb-3">Score</th>
                      <th className="pb-3">Cobertura</th>
                      <th className="pb-3">Precio USD</th>
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
                            to={'/mercado/empresas/' + encodeURIComponent(row.symbol)}
                          >
                            {row.symbol}
                          </Link>
                          <span className="ml-2 text-muted-foreground">{row.name}</span>
                        </td>
                        <td>{decimal(row.score_points)}</td>
                        <td>
                          {row.score_coverage_fraction == null
                            ? '—'
                            : decimal(row.score_coverage_fraction * 100, 0) + ' %'}
                        </td>
                        <td>{decimal(row.price_usd, 2)}</td>
                        <td>{decimal(row.weight_percent, 1)} %</td>
                        <td>{euro(row.amount_eur)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          <section className="rounded-xl border bg-card p-5">
            <h2 className="text-xl font-semibold">Dónde aportar capital nuevo</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Solo aproxima los pesos objetivo con aportaciones. No propone ventas ni considera
              impuestos o costes de ejecución.
            </p>
            {data.allocations.length ? (
              <ul className="mt-4 divide-y">
                {data.allocations.map((item) => (
                  <li key={item.symbol} className="flex justify-between gap-4 py-3 text-sm">
                    <Link
                      to={'/mercado/empresas/' + encodeURIComponent(item.symbol)}
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
    </div>
  );
}
