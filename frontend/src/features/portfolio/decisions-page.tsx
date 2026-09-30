import { lazy, Suspense, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import type { DecisionPolicy, SavedDecision } from '@/shared/api/generated/types.gen';
import {
  createJob,
  deleteDecision,
  getDecision,
  getDecisionProgress,
  getDecisions,
  getJob,
  getJobResult,
  renameDecision,
  saveDecision,
} from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { Badge } from '@/shared/ui/badge';

const DecisionChart = lazy(() => import('./decision-chart'));

type Preview = {
  decisions: Array<{
    symbol: string;
    action: string;
    current_pct: number;
    target_pct: number;
    change_pct: number;
    reason: string;
    score: number | null;
  }>;
  method: string;
  cash_target_pct: number;
  as_of: string;
  coverage: { universe: number; prices: number; scored: number };
  status: 'EXPERIMENTAL';
};
function isPreview(value: unknown): value is Preview {
  return Boolean(
    value &&
    typeof value === 'object' &&
    'decisions' in value &&
    Array.isArray(value.decisions) &&
    'method' in value &&
    'coverage' in value,
  );
}
const decimal = (value: number | null | undefined) =>
  value == null ? '—' : new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 }).format(value);

function DecisionTable({ decisions }: { decisions: Preview['decisions'] }) {
  if (!decisions.length)
    return <p className="mt-4 text-sm">El plan no tiene decisiones ejecutables.</p>;
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[680px] text-left text-sm">
        <thead className="border-b text-xs text-muted-foreground">
          <tr>
            <th className="py-2">Empresa</th>
            <th>Acción</th>
            <th>Actual %</th>
            <th>Objetivo %</th>
            <th>Cambio %</th>
            <th>Score</th>
            <th>Motivo</th>
          </tr>
        </thead>
        <tbody>
          {decisions.map((row) => (
            <tr key={row.symbol} className="border-b last:border-0">
              <td className="py-3">
                <Link
                  className="text-primary underline"
                  to={'/mercado/empresas/' + encodeURIComponent(row.symbol)}
                >
                  {row.symbol}
                </Link>
              </td>
              <td>{row.action}</td>
              <td>{decimal(row.current_pct)}</td>
              <td>{decimal(row.target_pct)}</td>
              <td>{decimal(row.change_pct)}</td>
              <td>{decimal(row.score)}</td>
              <td>{row.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const defaults: DecisionPolicy = {
  min_score: 65,
  min_coverage: 0.7,
  max_positions: 10,
  max_position_pct: 5,
  max_sector_pct: 20,
  max_invested_pct: 50,
  max_volatility: 0.6,
  min_drawdown: -0.5,
  max_price_age_days: 7,
  trade_threshold_pct: 0.5,
  constrained_optimizer: false,
  turnover_penalty: 0,
};
const fields: Array<{ key: keyof DecisionPolicy; label: string; step: string }> = [
  { key: 'min_score', label: 'Score mínimo', step: '1' },
  { key: 'min_coverage', label: 'Cobertura mínima (0–1)', step: '0.01' },
  { key: 'max_positions', label: 'Máximo de posiciones', step: '1' },
  { key: 'max_position_pct', label: 'Máximo por posición (%)', step: '0.1' },
  { key: 'max_sector_pct', label: 'Máximo por sector (%)', step: '0.1' },
  { key: 'max_invested_pct', label: 'Máximo invertido (%)', step: '0.1' },
  { key: 'max_volatility', label: 'Volatilidad máxima', step: '0.01' },
  { key: 'min_drawdown', label: 'Drawdown mínimo', step: '0.01' },
  { key: 'max_price_age_days', label: 'Edad máxima del precio (días)', step: '1' },
  { key: 'trade_threshold_pct', label: 'Umbral de cambio (%)', step: '0.1' },
  { key: 'turnover_penalty', label: 'Penalización por rotación', step: '0.01' },
];

export function DecisionsPage() {
  const client = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [name, setName] = useState('');
  const plans = useQuery({
    queryKey: ['portfolio', 'decisions'],
    queryFn: ({ signal }) => getDecisions(signal),
  });
  const active = selected ?? plans.data?.items[0]?.id ?? null;
  const saved = useQuery({
    queryKey: ['portfolio', 'decisions', active],
    queryFn: ({ signal }) => getDecision(active!, signal),
    enabled: active != null,
  });
  const progress = useQuery({
    queryKey: ['portfolio', 'decisions', active, 'progress'],
    queryFn: ({ signal }) => getDecisionProgress(active!, signal),
    enabled: active != null,
  });
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: ({ signal }) => getJob(jobId!, signal),
    enabled: jobId != null,
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.status ?? '') ? 2000 : false,
  });
  const result = useQuery({
    queryKey: ['job-result', jobId],
    queryFn: ({ signal }) => getJobResult(jobId!, signal),
    enabled: job.data?.status === 'succeeded',
  });
  const generate = useMutation({
    mutationFn: (input: { policy: DecisionPolicy; holdings: string }) =>
      createJob({
        kind: 'decision_plan',
        decision_policy: input.policy,
        holdings_text: input.holdings,
        idempotency_key: 'dec:' + crypto.randomUUID(),
      }),
    onSuccess: (queued) => setJobId(queued.id),
  });
  const save = useMutation({
    mutationFn: () => saveDecision({ job_id: jobId!, name }),
    onSuccess: (plan) => {
      setSelected(plan.id);
      void client.invalidateQueries({ queryKey: ['portfolio', 'decisions'] });
    },
  });
  const rename = useMutation({
    mutationFn: (newName: string) => renameDecision(active!, { name: newName }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['portfolio', 'decisions'] }),
  });
  const remove = useMutation({
    mutationFn: () => deleteDecision(active!),
    onSuccess: () => {
      setSelected(null);
      void client.invalidateQueries({ queryKey: ['portfolio', 'decisions'] });
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const policy = { ...defaults };
    for (const field of fields) {
      const value = Number(form.get(field.key));
      (policy as Record<string, number | boolean>)[field.key] = value;
    }
    policy.constrained_optimizer = form.get('constrained_optimizer') === 'on';
    setName(String(form.get('name') ?? '').trim());
    setJobId(null);
    generate.mutate({ policy, holdings: String(form.get('holdings_text') ?? '') });
  }
  const preview = isPreview(result.data) ? result.data : null;
  const selectedPlan: SavedDecision | undefined = saved.data;
  return (
    <div className="space-y-6">
      <header>
        <Link className="text-sm text-primary" to="/cartera">
          ← Cartera
        </Link>
        <h1 className="mt-3 text-3xl font-semibold">Decisiones de cartera</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Política experimental de gestión de riesgo; usa scores congelados, pero no equivale al
          Top‑20 validado ni demuestra ventaja frente al S&amp;P 500. Nunca envía órdenes.
        </p>
      </header>
      <form onSubmit={submit} className="rounded-xl border bg-card p-5">
        <h2 className="text-lg font-semibold">Nuevo plan</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Se calcula en el worker local con precios ya cacheados. Los porcentajes se refieren al
          patrimonio total.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {fields.map((field) => (
            <label key={field.key} className="text-sm">
              {field.label}
              <Input
                name={field.key}
                type="number"
                step={field.step}
                required
                defaultValue={String(defaults[field.key])}
                className="mt-1"
              />
            </label>
          ))}
        </div>
        <label className="mt-4 flex items-center gap-2 text-sm">
          <input type="checkbox" name="constrained_optimizer" />
          Optimizar con límites de posición y sector
        </label>
        <label className="mt-4 block text-sm">
          Posiciones actuales (SÍMBOLO,porcentaje; una por línea)
          <textarea
            name="holdings_text"
            rows={3}
            maxLength={5000}
            placeholder={'AAPL,3\nMSFT,4'}
            className="mt-1 block w-full rounded-md border bg-background p-3"
          />
        </label>
        <label className="mt-4 block text-sm">
          Nombre del plan
          <Input
            name="name"
            maxLength={80}
            required
            className="mt-1"
            defaultValue="Plan de decisiones"
          />
        </label>
        <Button className="mt-4" type="submit" disabled={generate.isPending}>
          Generar decisiones
        </Button>
        {generate.isError && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {generate.error.message}
          </p>
        )}
      </form>
      {jobId && (
        <section className="rounded-xl border bg-card p-5">
          <h2 className="font-semibold">Cálculo local</h2>
          <p role="status" className="mt-2 text-sm">
            {job.data?.phase ?? 'En espera'} ({job.data?.status ?? 'queued'})
          </p>
          {job.data?.status === 'failed' && (
            <p className="text-sm text-destructive">
              El cálculo no se completó. Revisa la actividad en Administración y la cobertura de
              datos.
            </p>
          )}
          {result.isError && (
            <ErrorState error={result.error} retry={() => void result.refetch()} />
          )}
          {preview && (
            <>
              <p className="mt-3 text-sm">
                Fecha {preview.as_of} · {preview.coverage.scored}/{preview.coverage.universe} scores
                · {preview.coverage.prices} precios cacheados.
              </p>
              <p className="mt-2 text-sm">
                Método: {preview.method}. Efectivo objetivo: {decimal(preview.cash_target_pct)} %.
              </p>
              <DecisionTable decisions={preview.decisions} />
              <Button
                type="button"
                className="mt-4"
                disabled={save.isPending || !name}
                onClick={() => save.mutate()}
              >
                Guardar plan
              </Button>
              {save.isError && (
                <p role="alert" className="text-sm text-destructive">
                  {save.error.message}
                </p>
              )}
              {save.isSuccess && (
                <p role="status" className="text-sm">
                  Plan #{save.data.id} guardado.
                </p>
              )}
            </>
          )}
        </section>
      )}
      <section className="rounded-xl border bg-card p-5">
        <h2 className="text-lg font-semibold">Planes anteriores</h2>
        {plans.isPending && <LoadingState />}
        {plans.isError && <ErrorState error={plans.error} retry={() => void plans.refetch()} />}
        {plans.data?.items.length === 0 && (
          <p className="mt-3 text-sm">Aún no hay planes guardados.</p>
        )}
        {active != null && (
          <>
            <label className="mt-4 block text-sm">
              Plan guardado
              <select
                className="mt-1 block w-full max-w-lg rounded-md border bg-background p-2"
                value={active}
                onChange={(event) => setSelected(Number(event.target.value))}
              >
                {plans.data?.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · #{item.id}
                  </option>
                ))}
              </select>
            </label>
            {saved.isPending && <LoadingState />}
            {saved.isError && <ErrorState error={saved.error} retry={() => void saved.refetch()} />}
            {selectedPlan && (
              <>
                <p className="mt-3 text-sm text-muted-foreground">
                  {selectedPlan.created_at.slice(0, 10)} · {selectedPlan.method}{' '}
                  <Badge variant="outline">Experimental</Badge>
                </p>
                <DecisionTable decisions={selectedPlan.decisions as Preview['decisions']} />
                <div className="mt-6 border-t pt-5">
                  <h3 className="font-semibold">Progreso desde el plan</h3>
                  {progress.isPending && <LoadingState />}
                  {progress.isError && (
                    <ErrorState error={progress.error} retry={() => void progress.refetch()} />
                  )}
                  {progress.data && (
                    <>
                      <p className="mt-2 text-xs text-muted-foreground">
                        Precios en caché hasta {progress.data.data_as_of ?? 'sin datos'} · cobertura{' '}
                        {progress.data.available}/{progress.data.requested}. Retornos de posiciones
                        con datos, ponderados por su objetivo; costes 0 pb.
                      </p>
                      {progress.data.stale && (
                        <p className="mt-2 text-sm">
                          Aún no hay precios posteriores al plan. Actualiza los datos desde
                          Administración.
                        </p>
                      )}
                      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                        <p>
                          Cartera:{' '}
                          <strong>
                            {progress.data.portfolio_return == null
                              ? '—'
                              : decimal(progress.data.portfolio_return * 100) + ' %'}
                          </strong>
                        </p>
                        <p>
                          SPY:{' '}
                          <strong>
                            {progress.data.benchmark_return == null
                              ? '—'
                              : decimal(progress.data.benchmark_return * 100) + ' %'}
                          </strong>
                        </p>
                        <p>
                          Diferencia:{' '}
                          <strong>
                            {progress.data.excess_return == null
                              ? '—'
                              : decimal(progress.data.excess_return * 100) + ' pp'}
                          </strong>
                        </p>
                      </div>
                      {progress.data.missing.length > 0 && (
                        <p className="mt-2 text-xs">
                          Sin comparación: {progress.data.missing.join(', ')}.
                        </p>
                      )}
                      {progress.data.curve.length > 0 && (
                        <Suspense fallback={<p>Preparando gráfico…</p>}>
                          <DecisionChart curve={progress.data.curve} />
                        </Suspense>
                      )}
                    </>
                  )}
                </div>
                <form
                  className="mt-4 flex gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    rename.mutate(String(new FormData(event.currentTarget).get('new_name')));
                  }}
                >
                  <Input
                    name="new_name"
                    aria-label="Nuevo nombre"
                    defaultValue={selectedPlan.name}
                    maxLength={80}
                    required
                  />
                  <Button type="submit" variant="outline">
                    Cambiar nombre
                  </Button>
                </form>
                <Button
                  type="button"
                  variant="outline"
                  className="mt-3"
                  onClick={() => remove.mutate()}
                >
                  Borrar plan
                </Button>
                {rename.isError && (
                  <p role="alert" className="text-sm text-destructive">
                    {rename.error.message}
                  </p>
                )}
                {remove.isError && (
                  <p role="alert" className="text-sm text-destructive">
                    {remove.error.message}
                  </p>
                )}
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}
