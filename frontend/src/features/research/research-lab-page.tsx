import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { getExperiment, getExperiments } from '@/shared/api/client';
import type { ExperimentDetail, ExperimentStage } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { DeleteExperiment, ManualExperimentForm } from './experiment-form';
import { BootstrapPanel, PboPanel } from './experiment-jobs';
import { LiveLedgerSection } from './live-ledger';
import { SavedAudits } from './saved-audits';
import { DeflatedSharpePanel, ExperimentTailPanel } from './experiment-statistics';
import { RankCell, RankLegend, RankValue } from '@/shared/ui/rank-cell';
import { formatNumber, formatPercent } from '@/shared/lib/format';
import { PageHeader } from '@/shared/ui/page-header';
import { DataTable } from '@/shared/ui/data-table';
import { Term } from '@/shared/ui/term';

const PAGE_SIZE = 50;

const decimal = (value: number | null | undefined, digits = 2) =>
  formatNumber(value, { digits, fixed: true });

const percent = (value: number | null | undefined) =>
  formatPercent(value, { digits: 1, fixed: true });

function stageLabel(stages: ExperimentStage[], id: string): string {
  const stage = stages.find((item) => item.id === id);
  return stage ? `${stage.emoji} ${stage.label}` : id;
}

function Environment({ id }: { id: number }) {
  const detail = useQuery({
    queryKey: ['research', 'experiment', id],
    queryFn: ({ signal }) => getExperiment(id, signal),
  });
  if (detail.isPending) return <LoadingState />;
  if (detail.isError)
    return <ErrorState error={detail.error} retry={() => void detail.refetch()} />;
  const item: ExperimentDetail = detail.data;
  const fields: [string, string][] = [
    ['Universo', item.universe ?? '—'],
    ['Factores', item.factors ?? '—'],
    ['Modelo de costes', item.cost_model ?? '—'],
    ['Corte de datos', item.data_cutoff ?? '—'],
    [
      'Periodo IS',
      item.is_start || item.is_end ? `${item.is_start ?? '—'} – ${item.is_end ?? '—'}` : '—',
    ],
    [
      'Periodo OOS',
      item.oos_start || item.oos_end ? `${item.oos_start ?? '—'} – ${item.oos_end ?? '—'}` : '—',
    ],
    ['Periodos / por año', `${item.n_periods ?? '—'} / ${item.periods_per_year ?? '—'}`],
    ['Retorno total', percent(item.total_return)],
    ['Retorno anualizado', percent(item.annualized_return)],
    [
      'Serie de retornos',
      item.returns_count
        ? `${item.returns_count} observaciones, ${item.returns_first} – ${item.returns_last}`
        : 'Sin serie guardada',
    ],
    ['Backtest de origen', item.backtest_job_id ?? '—'],
  ];
  return (
    <section className="rounded-xl border bg-card p-5" aria-label={`Experimento ${item.id}`}>
      <h2 className="text-lg font-semibold">
        #{item.id} · {item.model_id}
      </h2>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">Versión de Python</dt>
          <dd>{item.python_version ?? '—'}</dd>
        </div>
        <div>
          <dt
            className="text-muted-foreground"
            title="Hash corto de uv.lock: dos experimentos con el mismo valor instalaron exactamente el mismo árbol de dependencias."
          >
            Huella del entorno (uv.lock)
          </dt>
          <dd className="font-mono">{item.env_fingerprint ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Commit</dt>
          <dd className="font-mono">{item.git_commit ?? '—'}</dd>
        </div>
      </dl>
      <p className="mt-4 text-sm text-muted-foreground">Huella de datos</p>
      <code className="mt-1 block break-all rounded bg-muted p-2 text-xs">
        {item.data_fingerprint ?? 'Sin fingerprint de datos'}
      </code>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {fields.map(([label, value]) => (
          <div key={label}>
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="break-words">{value}</dd>
          </div>
        ))}
      </dl>
      {item.weights && (
        <p className="mt-3 text-sm">
          <span className="text-muted-foreground">Pesos: </span>
          {Object.entries(item.weights)
            .map(([key, value]) => `${key} ${String(value)}`)
            .join(' · ')}
        </p>
      )}
      {item.deps.length > 0 ? (
        <table className="mt-4 text-left text-sm" aria-label="Dependencias registradas">
          <thead>
            <tr>
              <th className="pr-6 font-medium">Paquete</th>
              <th className="font-medium">Versión</th>
            </tr>
          </thead>
          <tbody>
            {item.deps.map((dep) => (
              <tr key={dep.package}>
                <td className="pr-6">{dep.package}</td>
                <td className="font-mono">{dep.version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">
          Este experimento no tiene dependencias registradas (creado antes de esa función).
        </p>
      )}
    </section>
  );
}

const COLUMN_TERMS: Record<string, string> = {
  Sharpe: 'sharpe_ratio',
  Sortino: 'sortino_ratio',
  'Máx. drawdown': 'max_drawdown',
};

const LONG_NOTES = 120;

/** Long notes (lists of hashes, amendments) fold to two lines so each row keeps a readable height. */
function ExperimentNotes({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  if (text.length <= LONG_NOTES) return <span className="[overflow-wrap:anywhere]">{text}</span>;
  return (
    <details className="group">
      <summary className="line-clamp-2 cursor-pointer list-none [overflow-wrap:anywhere] group-open:line-clamp-none">
        {text}
      </summary>
    </details>
  );
}

export function ResearchLabPage() {
  const [params, setParams] = useSearchParams();
  const family = params.get('family') ?? '';
  const stage = params.get('stage') ?? '';
  const requestedPage = Number(params.get('page') ?? '1');
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const selected = Number(params.get('experiment') ?? '0');
  const offset = (page - 1) * PAGE_SIZE;
  const experiments = useQuery({
    queryKey: ['research', 'experiments', family, stage, offset],
    queryFn: ({ signal }) => getExperiments({ family, stage, offset, limit: PAGE_SIZE }, signal),
  });

  function update(changes: Record<string, string>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next);
  }

  const data = experiments.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/investigacion', label: 'Investigación' }}
        eyebrow="Registro de experimentos"
        title="Research Lab"
        description={<>Experimentos de backtesting con su metodología, commit y resultado.</>}
        guide={
          <>
            <p>
              Registro de experimentos de backtesting con su metodología, el commit exacto y el
              resultado. Un resultado en fase Research que parece bueno no es evidencia: es un
              candidato. Solo datos no usados para elegirlo (out-of-sample) o el seguimiento real
              (live forward) pueden confirmarlo.
            </p>
          </>
        }
      />
      {experiments.isPending && <LoadingState />}
      {experiments.isError && (
        <ErrorState error={experiments.error} retry={() => void experiments.refetch()} />
      )}
      {data && (
        <>
          <details className="rounded-xl border bg-card p-4 text-sm">
            <summary className="cursor-pointer font-medium">
              Las cuatro fases, y por qué importa no confundirlas
            </summary>
            <ul className="mt-3 space-y-1">
              {data.stages.map((item) => (
                <li key={item.id}>
                  <strong>
                    {item.emoji} {item.label}
                  </strong>{' '}
                  (<code>{item.id}</code>): {item.help}
                </li>
              ))}
            </ul>
          </details>
          <div
            className="flex flex-wrap gap-4 text-sm"
            role="group"
            aria-label="Filtros de experimentos"
          >
            <label className="grid gap-1">
              Familia
              <NativeSelect
                value={family}
                onChange={(event) => update({ family: event.target.value, page: '' })}
              >
                <NativeSelectOption value="">(todas)</NativeSelectOption>
                {data.families.map((name) => (
                  <NativeSelectOption key={name} value={name}>
                    {name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </label>
            <label className="grid gap-1">
              Fase
              <NativeSelect
                value={stage}
                onChange={(event) => update({ stage: event.target.value, page: '' })}
              >
                <NativeSelectOption value="">(todas)</NativeSelectOption>
                {data.stages.map((item) => (
                  <NativeSelectOption key={item.id} value={item.id}>
                    {item.emoji} {item.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </label>
          </div>
          {data.total === 0 ? (
            <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
              No hay experimentos registrados con estos filtros. Regístralos desde Investigación →
              Ranking histórico tras ejecutar un backtest.
            </p>
          ) : (
            <>
              <div className="space-y-3 sm:hidden" aria-label="Experimentos registrados">
                {data.items.map((item) => (
                  <article
                    className="rounded-xl border bg-card p-4 text-sm"
                    key={item.id}
                    aria-label={`Experimento ${item.id}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <button
                          type="button"
                          className="font-semibold text-primary underline"
                          onClick={() => update({ experiment: String(item.id) })}
                        >
                          Experimento #{item.id}
                        </button>
                        <p className="mt-1 break-words">{item.model_id}</p>
                        <p className="text-xs text-muted-foreground">
                          {stageLabel(data.stages, item.stage)}
                        </p>
                      </div>
                      <div className="text-right text-xs">
                        <span className="block text-muted-foreground">Sharpe</span>
                        <RankValue
                          position={data.positions.sharpe?.[String(item.id)]}
                          scope="de los experimentos del filtro"
                        >
                          {decimal(item.sharpe)}
                        </RankValue>
                      </div>
                    </div>
                    <details className="mt-3">
                      <summary className="cursor-pointer text-primary">
                        Más datos del experimento
                      </summary>
                      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                        <dt>Familia</dt>
                        <dd className="text-right">{item.family ?? '—'}</dd>
                        <dt>Posiciones</dt>
                        <dd className="text-right">{item.n_positions ?? '—'}</dd>
                        <dt>Rebalanceo</dt>
                        <dd className="text-right">{item.rebalance ?? '—'}</dd>
                        <dt>Sortino</dt>
                        <dd className="text-right">
                          <RankValue
                            position={data.positions.sortino?.[String(item.id)]}
                            scope="de los experimentos del filtro"
                          >
                            {decimal(item.sortino)}
                          </RankValue>
                        </dd>
                        <dt>Máx. drawdown</dt>
                        <dd className="text-right">
                          <RankValue
                            position={data.positions.max_drawdown?.[String(item.id)]}
                            scope="de los experimentos del filtro"
                          >
                            {percent(item.max_drawdown)}
                          </RankValue>
                        </dd>
                        <dt>Hipótesis previa</dt>
                        <dd className="text-right">{item.hypothesis_registered ? 'Sí' : 'No'}</dd>
                        <dt>Retornos</dt>
                        <dd className="text-right">{item.has_returns ? 'Sí' : '—'}</dd>
                        <dt>Commit</dt>
                        <dd className="break-all text-right font-mono">{item.git_commit ?? '—'}</dd>
                        <dt>Notas</dt>
                        <dd className="break-words text-right">{item.notes ?? '—'}</dd>
                      </dl>
                    </details>
                  </article>
                ))}
              </div>
              <DataTable
                label="Tabla de experimentos"
                className="hidden rounded-xl border bg-card sm:block"
              >
                <table className="w-full text-left text-sm" aria-label="Experimentos registrados">
                  <thead>
                    <tr className="border-b">
                      {[
                        'id',
                        'Modelo',
                        'Fase',
                        'Familia',
                        'Posiciones',
                        'Rebalanceo',
                        'Sharpe',
                        'Sortino',
                        'Máx. drawdown',
                        'Hipótesis previa',
                        'Commit',
                        'Retornos',
                        'Notas',
                      ].map((label) => (
                        <th key={label} className="px-3 py-2 font-medium">
                          {COLUMN_TERMS[label] ? (
                            <Term k={COLUMN_TERMS[label]}>{label}</Term>
                          ) : (
                            label
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((item) => (
                      <tr
                        key={item.id}
                        className={item.id === selected ? 'border-b bg-muted' : 'border-b'}
                      >
                        <td className="px-3 py-2">
                          <button
                            type="button"
                            className="text-primary underline"
                            aria-label={`Ver entorno del experimento ${item.id}`}
                            onClick={() => update({ experiment: String(item.id) })}
                          >
                            #{item.id}
                          </button>
                        </td>
                        <td className="px-3 py-2">{item.model_id}</td>
                        <td className="px-3 py-2">{stageLabel(data.stages, item.stage)}</td>
                        <td className="px-3 py-2">{item.family ?? '—'}</td>
                        <td className="px-3 py-2">{item.n_positions ?? '—'}</td>
                        <td className="px-3 py-2">{item.rebalance ?? '—'}</td>
                        {(
                          [
                            ['sharpe', decimal(item.sharpe)],
                            ['sortino', decimal(item.sortino)],
                            ['max_drawdown', percent(item.max_drawdown)],
                          ] as const
                        ).map(([metric, text]) => (
                          <RankCell
                            key={metric}
                            className="px-3 py-2"
                            position={data.positions[metric]?.[String(item.id)]}
                            scope="de los experimentos del filtro"
                          >
                            {text}
                          </RankCell>
                        ))}
                        <td className="px-3 py-2">{item.hypothesis_registered ? 'Sí' : 'No'}</td>
                        <td className="px-3 py-2 font-mono">{item.git_commit ?? '—'}</td>
                        <td className="px-3 py-2">{item.has_returns ? 'Sí' : '—'}</td>
                        <td className="w-72 min-w-56 px-3 py-2">
                          <ExperimentNotes text={item.notes} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <RankLegend>
                  Sharpe, Sortino y caída máxima, de rojo (peor) a verde (mejor) entre todos los
                  experimentos del filtro, no solo los de esta página. Una caída máxima más cercana
                  a cero es mejor. Comparar experimentos de familias distintas no los hace
                  equivalentes.
                </RankLegend>
              </DataTable>
              <div className="sm:hidden">
                <RankLegend>
                  Sharpe, Sortino y caída máxima se comparan entre los experimentos del filtro.
                  Comparar familias distintas no las hace equivalentes.
                </RankLegend>
              </div>
            </>
          )}
          {pages > 1 && (
            <div className="flex items-center gap-3 text-sm">
              <Button
                variant="outline"
                disabled={page <= 1}
                onClick={() => update({ page: String(page - 1) })}
              >
                Anterior
              </Button>
              <span>
                Página {page} de {pages}
              </span>
              <Button
                variant="outline"
                disabled={page >= pages}
                onClick={() => update({ page: String(page + 1) })}
              >
                Siguiente
              </Button>
            </div>
          )}
          {selected > 0 && <Environment id={selected} />}
          <DeleteExperiment />
          <ManualExperimentForm stages={data.stages} />
          <DeflatedSharpePanel key={JSON.stringify(data.families)} families={data.families} />
          <ExperimentTailPanel />
          <PboPanel />
          <BootstrapPanel />
          <SavedAudits />
          <LiveLedgerSection />
        </>
      )}
    </div>
  );
}
