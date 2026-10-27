import { lazy, Suspense, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import type {
  DecisionFreshness,
  DecisionPolicy,
  SavedDecision,
} from '@/shared/api/generated/types.gen';
import { useResearchMode } from '@/shared/api/use-model';
import { useFormDefaults } from '@/shared/api/use-form-defaults';
import { AdvancedOptions, HelpField } from '@/shared/ui/advanced-options';
import {
  createJob,
  decisionsCsvUrl,
  deleteDecision,
  getDecision,
  getDecisionFreshness,
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
import { dateText, formatNumber } from '@/shared/lib/format';
import { NativeSelect } from '@/shared/ui/native-select';
import { Textarea } from '@/shared/ui/textarea';

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
const decimal = (value: number | null | undefined) => formatNumber(value, { digits: 2 });

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
                  to={'/empresas/' + encodeURIComponent(row.symbol)}
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

type PolicyField = {
  key: keyof DecisionPolicy;
  label: string;
  step: string;
  help: string;
  /** Shown in % while the request takes a fraction (coverage, as in the Ranking). */
  percent?: boolean;
};
/** The two the investor usually sets; the rest are «Opciones avanzadas». Values from the backend. */
const essential: PolicyField[] = [
  {
    key: 'max_positions',
    label: 'Máximo de posiciones',
    step: '1',
    help: 'Número de empresas. Más posiciones reparten el riesgo, pero bajan el score medio.',
  },
  {
    key: 'min_score',
    label: 'Score mínimo',
    step: '1',
    help: 'Puntos de 0 a 100. Solo entran empresas con un score igual o superior.',
  },
];
const advanced: PolicyField[] = [
  {
    key: 'min_coverage',
    label: 'Métricas disponibles mínimas (%)',
    step: '1',
    percent: true,
    help: 'Porcentaje de las métricas del score con dato, como en el Ranking. Más alto descarta empresas con datos incompletos.',
  },
  {
    key: 'max_position_pct',
    label: 'Máximo por posición (%)',
    step: '0.1',
    help: '% del patrimonio total en una sola empresa. Limita el daño de un error.',
  },
  {
    key: 'max_sector_pct',
    label: 'Máximo por sector (%)',
    step: '0.1',
    help: '% del patrimonio total en un sector. Evita concentrar el riesgo en una industria.',
  },
  {
    key: 'max_invested_pct',
    label: 'Máximo invertido (%)',
    step: '0.1',
    help: '% del patrimonio que puede estar invertido; el resto queda en liquidez.',
  },
  {
    key: 'max_volatility',
    label: 'Volatilidad máxima',
    step: '0.01',
    help: 'Volatilidad anualizada en fracción (0,60 = 60 %). Descarta las empresas más volátiles.',
  },
  {
    key: 'min_drawdown',
    label: 'Drawdown mínimo',
    step: '0.01',
    help: 'Caída máxima tolerada en fracción negativa (−0,50 = −50 %). Descarta caídas mayores.',
  },
  {
    key: 'max_price_age_days',
    label: 'Edad máxima del precio (días)',
    step: '1',
    help: 'Días desde el último cierre en caché. Con precios más antiguos no se propone operar.',
  },
  {
    key: 'trade_threshold_pct',
    label: 'Umbral de cambio (%)',
    step: '0.1',
    help: 'Puntos de peso que debe cambiar una posición para proponer comprar o vender. Evita operaciones pequeñas.',
  },
  {
    key: 'turnover_penalty',
    label: 'Penalización por rotación',
    step: '0.01',
    help: 'De 0 a 0,20. Con el optimizador, penaliza cambiar mucho la cartera actual.',
  },
];
const shown = (field: PolicyField, policy: DecisionPolicy) => {
  const value = Number(policy[field.key]);
  return String(field.percent ? Math.round(value * 10000) / 100 : value);
};

function PolicyInput({ field, policy }: { field: PolicyField; policy: DecisionPolicy }) {
  return (
    <Input
      id={'policy-' + field.key}
      name={field.key}
      type="number"
      step={field.step}
      required
      defaultValue={shown(field, policy)}
      className="mt-1"
    />
  );
}

/** Age of a saved plan and, when today's ranking no longer supports it, a warning (#191). */
export function PlanFreshness({ data }: { data: DecisionFreshness }) {
  const age =
    data.age_days === 0 ? 'hoy' : data.age_days === 1 ? 'hace 1 día' : `hace ${data.age_days} días`;
  if (!data.material)
    return (
      <p className="mt-2 text-xs text-muted-foreground">
        Guardado {age}. Sus {data.positions} posiciones siguen respaldadas por el ranking actual
        (ningún score ha cambiado {formatNumber(data.threshold_points)} puntos o más).
      </p>
    );
  return (
    <div
      role="alert"
      className="mt-3 rounded-lg border border-amber-500/50 bg-amber-50 p-3 text-sm"
    >
      <p className="font-medium">
        Plan desfasado: guardado {age}, el ranking ha cambiado en {data.changes.length} de sus{' '}
        {data.positions} posiciones.
      </p>
      <ul className="mt-2 space-y-1 text-xs">
        {data.changes.map((change) => (
          <li key={change.symbol}>
            <strong>{change.symbol}</strong>: {change.label} (score {decimal(change.saved_score)} →{' '}
            {change.current_score == null ? 'sin score' : decimal(change.current_score)})
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs">Genera un plan nuevo antes de actuar sobre este.</p>
    </div>
  );
}

/** The experimental plan of the single plan page (#191): risk limits of its own over frozen
 *  scores; never presented as the validated rule. */
export function ExperimentalPlan() {
  const client = useQueryClient();
  // Investor mode plans with the default policy; its parameters are a Research experiment.
  const research = useResearchMode();
  const formDefaults = useFormDefaults();
  const defaults = formDefaults.data?.decision_policy;
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
  const freshness = useQuery({
    queryKey: ['portfolio', 'decisions', active, 'freshness'],
    queryFn: ({ signal }) => getDecisionFreshness(active!, signal),
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
    if (!defaults) return;
    const policy = { ...defaults };
    if (research) {
      for (const field of [...essential, ...advanced]) {
        const value = Number(form.get(field.key));
        (policy as Record<string, number | boolean>)[field.key] = field.percent
          ? value / 100
          : value;
      }
      policy.constrained_optimizer = form.get('constrained_optimizer') === 'on';
    }
    setName(String(form.get('name') ?? '').trim());
    setJobId(null);
    generate.mutate({ policy, holdings: String(form.get('holdings_text') ?? '') });
  }
  const preview = isPreview(result.data) ? result.data : null;
  const selectedPlan: SavedDecision | undefined = saved.data;
  return (
    <div className="space-y-6">
      <p className="flex flex-wrap items-center gap-2 rounded-xl border bg-secondary/40 p-4 text-sm">
        <Badge variant="outline">Experimental</Badge>
        Plan de compra y venta con límites de riesgo propios sobre los scores congelados. No es la
        regla validada ni demuestra ventaja frente al S&amp;P 500. Nunca envía órdenes.
      </p>
      <form onSubmit={submit} className="rounded-xl border bg-card p-5">
        <h2 className="text-lg font-semibold">Nuevo plan</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Se calcula en el worker local con precios ya cacheados. Los porcentajes se refieren al
          patrimonio total.
        </p>
        {!defaults &&
          (formDefaults.isError ? (
            <ErrorState error={formDefaults.error} retry={() => void formDefaults.refetch()} />
          ) : (
            <LoadingState />
          ))}
        {defaults && !research && (
          <p className="mt-4 rounded-lg border bg-secondary/40 p-3 text-sm">
            Se usa la política por defecto: hasta {defaults.max_positions} posiciones, score mínimo{' '}
            {defaults.min_score}, máximo {defaults.max_position_pct} % por posición y{' '}
            {defaults.max_sector_pct} % por sector. Sus parámetros se ajustan en el modo Research.
          </p>
        )}
        {defaults && research && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {essential.map((field) => (
              <HelpField
                key={field.key}
                id={'policy-' + field.key}
                label={field.label}
                help={field.help}
              >
                <PolicyInput field={field} policy={defaults} />
              </HelpField>
            ))}
          </div>
        )}
        <label className="mt-4 block text-sm">
          Posiciones actuales (SÍMBOLO,porcentaje; una por línea)
          <Textarea
            name="holdings_text"
            rows={3}
            maxLength={5000}
            placeholder={'AAPL,3\nMSFT,4'}
            className="mt-1 w-full"
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
        {defaults && research && (
          <AdvancedOptions id="decisiones" className="mt-4">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {advanced.map((field) => (
                <HelpField
                  key={field.key}
                  id={'policy-' + field.key}
                  label={field.label}
                  help={field.help}
                >
                  <PolicyInput field={field} policy={defaults} />
                </HelpField>
              ))}
            </div>
            <label className="mt-3 flex items-center gap-2">
              <input
                type="checkbox"
                name="constrained_optimizer"
                defaultChecked={defaults.constrained_optimizer}
              />
              Optimizar con límites de posición y sector
            </label>
          </AdvancedOptions>
        )}
        <Button className="mt-4" type="submit" disabled={generate.isPending || !defaults}>
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
                Fecha {dateText(preview.as_of)} · {preview.coverage.scored}/
                {preview.coverage.universe} scores · {preview.coverage.prices} precios cacheados.
              </p>
              <p className="mt-2 text-sm">
                Método: {preview.method}. Efectivo objetivo: {decimal(preview.cash_target_pct)} %.
              </p>
              <DecisionTable decisions={preview.decisions} />
              <a
                className="mt-2 inline-block text-sm font-medium text-primary underline"
                href={decisionsCsvUrl({ jobId: jobId! })}
                download
              >
                Descargar decisiones CSV
              </a>
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
              <NativeSelect
                className="mt-1 w-full max-w-lg"
                value={active}
                onChange={(event) => setSelected(Number(event.target.value))}
              >
                {plans.data?.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · #{item.id}
                  </option>
                ))}
              </NativeSelect>
            </label>
            {saved.isPending && <LoadingState />}
            {saved.isError && <ErrorState error={saved.error} retry={() => void saved.refetch()} />}
            {selectedPlan && (
              <>
                <p className="mt-3 text-sm text-muted-foreground">
                  {selectedPlan.created_at.slice(0, 10)} · {selectedPlan.method}{' '}
                  <Badge variant="outline">Experimental</Badge>
                </p>
                {freshness.isError && (
                  <ErrorState error={freshness.error} retry={() => void freshness.refetch()} />
                )}
                {freshness.data && <PlanFreshness data={freshness.data} />}
                <DecisionTable decisions={selectedPlan.decisions as Preview['decisions']} />
                <a
                  className="mt-2 inline-block text-sm font-medium text-primary underline"
                  href={decisionsCsvUrl({ planId: selectedPlan.id })}
                  download
                >
                  Descargar decisiones CSV
                </a>
                <div className="mt-6 border-t pt-5">
                  <h3 className="font-semibold">Progreso desde el plan</h3>
                  {progress.isPending && <LoadingState />}
                  {progress.isError && (
                    <ErrorState error={progress.error} retry={() => void progress.refetch()} />
                  )}
                  {progress.data && (
                    <>
                      <p className="mt-2 text-xs text-muted-foreground">
                        Precios en caché hasta {progress.data.data_as_of ?? 'sin datos'} ·
                        posiciones con precio {progress.data.available}/{progress.data.requested}.
                        Retornos de posiciones con datos, ponderados por su objetivo; costes 0 pb.
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
