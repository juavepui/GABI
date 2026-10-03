import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getRankingCoverage } from '@/shared/api/client';
import { CoverageThreshold, WarningText } from '@/shared/ui/coverage';
import { Folded } from '@/shared/ui/folded';
import { Input } from '@/shared/ui/input';
import { ErrorState } from '@/shared/ui/resource-state';
import { DateField, HealthStatus, RunButton, Section, Table } from './data-health';
import { age, pct, useHealthJob, useToday, type Row } from './data-health-job';
import { PageHeader } from '@/shared/ui/page-header';
import { Term } from '@/shared/ui/term';
import { HowToRead } from '@/shared/ui/how-to-read';
import { dateText } from '@/shared/lib/format';

type SourceSummary = {
  label: string;
  coverage: number;
  fresh: number;
  threshold_hours: number | null;
  oldest_hours: number | null;
  oldest_date?: string | null;
  have?: number;
  total?: number;
  with_facts_pct?: number;
  latest_dates?: Record<string, string | null>;
};
type UniverseHealth = {
  universe: { symbol: string; name: string | null }[];
  summary: {
    n_symbols: number;
    sources: Record<string, SourceSummary>;
    cik: { resolved: number; total: number; pct: number } | null;
    macro: { n_series: number; oldest_hours: number | null; threshold_hours: number } | null;
    structural_limitations: string[];
  };
  recent_errors: Row[];
  recent_errors_total: number;
};
type SourceAge = { age_hours: number | null; threshold_hours: number };
type CompanyHealth = {
  symbol: string;
  as_of: string;
  provenance: {
    cik: string | null;
    prices: SourceAge & { latest_date: string | null; adjusted_sessions: number };
    fundamentals: SourceAge;
    edgar: SourceAge & {
      has_facts: boolean;
      latest_10k_date: string | null;
      latest_10q_date: string | null;
    };
    insider: SourceAge;
    entity_master: {
      status: 'missing' | 'approximate' | 'point_in_time';
      sector: string | null;
      effective_date: string | null;
    };
  };
  identity: {
    resolution: { status: string; entity_id: string | null; candidates: string[] };
    name_candidates: Row[];
  };
  recent_errors: Row[];
};
type Identities = { as_of: string; rows: Row[]; without_cik: number };
type Archive = {
  sources: { source: string; data: string; rows: number; first: string; last: string }[];
  window: [string, string];
  quarterly: Row[] | null;
};

const freshness = (fraction: number) =>
  fraction >= 0.9 ? 'alta' : fraction >= 0.5 ? 'media' : 'baja';

function UniverseSection({ state }: { state: ReturnType<typeof useHealthJob<UniverseHealth>> }) {
  const data = state.result.data;
  const sources = data ? Object.entries(data.summary.sources) : [];
  return (
    <Section title="Resumen del universo">
      <p className="text-xs text-muted-foreground">
        Cobertura y frescura de cada fuente en la caché local. La comprobación lee la base y los
        ficheros sin descargar nada; tarda unos segundos.
      </p>
      <RunButton running={state.running} onClick={() => state.run({ scope: 'universe' })}>
        Comprobar calidad del universo
      </RunButton>
      <HealthStatus
        state={state}
        failure="La comprobación no terminó. ¿Existe el universo local?"
      />
      {data && (
        <>
          <div role="alert" className="space-y-1 rounded-md border border-amber-500/40 p-3 text-xs">
            {data.summary.structural_limitations.map((text) => (
              <p key={text}>
                <strong>Limitación estructural conocida:</strong> {text}
              </p>
            ))}
          </div>
          <p className="text-xs">
            {data.summary.n_symbols} empresas en el universo actual (S&amp;P 500). Estado global:
            degradado por limitaciones estructurales conocidas. La frescura de una fuente no
            certifica calidad point-in-time.
          </p>
          <Table
            label="Cobertura y frescura por fuente"
            columns={[
              ['source', 'Fuente'],
              ['coverage', 'Cobertura'],
              ['fresh', 'Frescura'],
              ['threshold', 'Umbral de frescura'],
              ['oldest', 'Dato más antiguo'],
            ]}
            rows={sources.map(([, s]) => ({
              source: s.label,
              coverage: pct(s.coverage) + (s.have != null ? ` (${s.have}/${s.total})` : ''),
              fresh: `${pct(s.fresh)} · ${freshness(s.fresh)}`,
              threshold: age(s.threshold_hours),
              oldest: s.oldest_date ?? age(s.oldest_hours),
            }))}
          />
          <p className="text-xs text-muted-foreground">
            Frescura alta: al menos el 90 % dentro del umbral de esa fuente; media: al menos el 50
            %. «Cobertura» es si existe algún dato en caché; «frescura», si es reciente según el
            umbral (24 h fundamentales e insider, 7 días SEC EDGAR, 5 días naturales precios).
          </p>
          {data.summary.sources.edgar?.with_facts_pct != null && (
            <p className="text-xs">
              Del universo completo, {pct(data.summary.sources.edgar.with_facts_pct)} tienen además
              el histórico XBRL completo que hace falta para reconstruir rankings pasados.
            </p>
          )}
          <dl className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md border p-3">
              <dt className="text-xs text-muted-foreground">
                <Term k="cik">CIK</Term> resueltos (SEC)
              </dt>
              <dd className="text-lg font-semibold">
                {data.summary.cik
                  ? `${pct(data.summary.cik.pct)} (${data.summary.cik.resolved}/${data.summary.cik.total})`
                  : 'Mapeo de la SEC aún no descargado'}
              </dd>
            </div>
            <div className="rounded-md border p-3">
              <dt className="text-xs text-muted-foreground">Series macro descargadas (FRED)</dt>
              <dd className="text-lg font-semibold">
                {data.summary.macro
                  ? `${data.summary.macro.n_series} · la más antigua hace ${age(data.summary.macro.oldest_hours)}`
                  : 'Sin datos macro todavía'}
              </dd>
            </div>
          </dl>
          <Folded title="FRED: última observación disponible por serie">
            <Table
              label="Última observación FRED"
              columns={[
                ['series', 'Serie'],
                ['latest', 'Última observación'],
              ]}
              rows={Object.entries(data.summary.sources.fred?.latest_dates ?? {}).map(
                ([series, latest]) => ({ series, latest: latest ?? 'ausente' }),
              )}
            />
          </Folded>
          {data.recent_errors_total === 0 ? (
            <p className="text-xs">
              Sin fallos de actualización registrados en los últimos 7 días.
            </p>
          ) : (
            <Folded
              title={`${data.recent_errors_total} fallos de actualización en los últimos 7 días`}
            >
              <Table
                label="Fallos recientes"
                columns={[
                  ['source', 'Fuente'],
                  ['symbol', 'Símbolo'],
                  ['reason', 'Motivo'],
                  ['occurred_at', 'Cuándo'],
                ]}
                rows={data.recent_errors}
              />
              {data.recent_errors_total > data.recent_errors.length && (
                <p className="text-xs text-muted-foreground">
                  Se muestran los {data.recent_errors.length} más recientes.
                </p>
              )}
            </Folded>
          )}
        </>
      )}
    </Section>
  );
}

function BlockCoverage() {
  const [threshold, setThreshold] = useState(0.7);
  const [requested, setRequested] = useState(false);
  const coverage = useQuery({
    queryKey: ['ranking-coverage', threshold],
    queryFn: ({ signal }) => getRankingCoverage(threshold, signal),
    enabled: requested,
  });
  return (
    <Section title="Cobertura por bloque del score">
      <p className="text-xs text-muted-foreground">
        Qué parte del universo tiene datos completos en cada bloque, no solo si la fuente está
        fresca. Calcula el ranking completo con la caché local y puede tardar.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <CoverageThreshold value={threshold} onChange={setThreshold} />
        <RunButton running={coverage.isFetching} onClick={() => setRequested(true)}>
          Calcular cobertura
        </RunButton>
      </div>
      {coverage.isError && (
        <ErrorState error={coverage.error} retry={() => void coverage.refetch()} />
      )}
      {coverage.data && (
        <>
          <Table
            label="Cobertura por bloque"
            columns={[
              ['block', 'Bloque'],
              ['n_metrics', 'Nº métricas'],
              ['complete', 'Completo (todas)'],
              ['any', 'Al menos una'],
              ['none', 'Ninguna'],
            ]}
            rows={coverage.data.blocks.map((block) => ({
              block: block.block.charAt(0).toUpperCase() + block.block.slice(1),
              n_metrics: block.n_metrics,
              complete: pct(block.complete),
              any: pct(block.any),
              none: pct(block.none),
            }))}
          />
          {coverage.data.warnings.map((text) => (
            <p key={text} className="text-xs">
              <WarningText text={text} />
            </p>
          ))}
        </>
      )}
    </Section>
  );
}

function sourceRow(name: string, info: SourceAge, detail = ''): Row {
  const status =
    info.age_hours == null
      ? 'Sin descargar'
      : info.age_hours <= info.threshold_hours
        ? 'Fresco'
        : `Desactualizado (${age(info.age_hours)} > ${age(info.threshold_hours)})`;
  return {
    source: name,
    downloaded: info.age_hours == null ? '—' : `hace ${age(info.age_hours)}`,
    status,
    detail,
  };
}

function CompanySection({ universe }: { universe: UniverseHealth['universe'] }) {
  const today = useToday();
  const [symbol, setSymbol] = useState('');
  const [asOf, setAsOf] = useState(today);
  const company = useHealthJob<CompanyHealth>('health-company');
  const identities = useHealthJob<Identities>('health-identities');
  const data = company.result.data;
  const p = data?.provenance;
  const entity = p?.entity_master;
  return (
    <Section title="Procedencia de una empresa">
      <p className="text-xs text-muted-foreground">
        Qué fuente y qué fecha respalda cada dato detrás del resultado de una empresa concreta.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-xs font-medium">
          Empresa
          <Input
            list="health-universe"
            value={symbol}
            placeholder="AAPL"
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
          />
          <datalist id="health-universe">
            {universe.map((row) => (
              <option key={row.symbol} value={row.symbol}>
                {row.name ?? row.symbol}
              </option>
            ))}
          </datalist>
        </label>
        <DateField
          label="Fecha de referencia del sector point-in-time"
          value={asOf}
          max={today}
          onChange={setAsOf}
        />
        <RunButton
          running={company.running || !symbol.trim() || !asOf}
          onClick={() => company.run({ scope: 'company', symbol: symbol.trim(), as_of: asOf })}
        >
          Ver procedencia
        </RunButton>
      </div>
      <HealthStatus state={company} failure="No se pudo comprobar la empresa." />
      {data && p && entity && (
        <div className="space-y-3" role="region" aria-label={`Procedencia de ${data.symbol}`}>
          <p>
            Identidad a {dateText(data.as_of)}: <strong>{data.identity.resolution.status}</strong> ·
            entidad: {data.identity.resolution.entity_id ?? 'sin acreditar'} · CIK:{' '}
            {p.cik ?? 'no resuelto'}
          </p>
          {data.identity.resolution.candidates.length > 0 && (
            <p className="text-xs">
              Entidades candidatas: {data.identity.resolution.candidates.join(', ')}
            </p>
          )}
          {data.recent_errors.length > 0 && (
            <p role="alert" className="text-xs text-destructive">
              {data.recent_errors.length} errores recientes de actualización para {data.symbol}.
            </p>
          )}
          <Table
            label="Procedencia por fuente"
            columns={[
              ['source', 'Fuente'],
              ['downloaded', 'Última descarga'],
              ['status', 'Estado'],
              ['detail', 'Detalle'],
            ]}
            rows={[
              sourceRow(
                'Precios (Yahoo)',
                p.prices,
                p.prices.latest_date
                  ? `${p.prices.adjusted_sessions} sesiones, última: ${dateText(p.prices.latest_date)}`
                  : 'sin precios en caché',
              ),
              sourceRow('Fundamentales (Yahoo)', p.fundamentals),
              sourceRow(
                'SEC EDGAR',
                p.edgar,
                `10-K: ${p.edgar.latest_10k_date ?? '—'} · 10-Q: ${p.edgar.latest_10q_date ?? '—'} · histórico XBRL: ${p.edgar.has_facts ? 'sí' : 'no'}`,
              ),
              sourceRow('Insider (Form 4)', p.insider),
              {
                source: 'Entity Master (sector)',
                downloaded: entity.effective_date ?? '—',
                status:
                  entity.status === 'missing'
                    ? 'Sin foto'
                    : entity.status === 'approximate'
                      ? 'Aproximado'
                      : 'Point-in-time real',
                detail:
                  entity.status === 'missing'
                    ? 'no hay sector point-in-time para esta empresa'
                    : entity.status === 'approximate'
                      ? `sector actual (${entity.sector ?? '—'}), no el real de una fecha pasada`
                      : `sector: ${entity.sector ?? '—'}`,
              },
            ]}
          />
          <p className="text-xs text-muted-foreground">
            «Última descarga» es cuándo GABI trajo el dato, no la fecha del informe: una descarga de
            ayer puede seguir respaldada por un 10-K de hace más de un año (columna Detalle).
          </p>
          {data.recent_errors.length > 0 && (
            <Table
              label="Errores recientes de la empresa"
              columns={[
                ['source', 'Fuente'],
                ['reason', 'Motivo'],
                ['occurred_at', 'Cuándo'],
              ]}
              rows={data.recent_errors}
            />
          )}
          {data.identity.name_candidates.length > 0 && (
            <>
              <p className="text-xs">
                Coincidencias por nombre pendientes de evidencia temporal; no se usan para el score.
              </p>
              <Table
                label="Candidatas por nombre"
                columns={[
                  ['entity_id', 'Entidad'],
                  ['name', 'Nombre'],
                  ['source', 'Fuente'],
                  ['reason', 'Motivo'],
                ]}
                rows={data.identity.name_candidates}
              />
            </>
          )}
          <Link
            className="text-xs underline"
            to={`/mercado/empresas/${encodeURIComponent(data.symbol)}`}
          >
            Ver su score y cobertura ponderada en la ficha
          </Link>
        </div>
      )}
      <Folded title="Diagnóstico de identidad del universo" className="rounded-md border p-3">
        <RunButton
          running={identities.running || !asOf}
          onClick={() => identities.run({ scope: 'identities', as_of: asOf })}
        >
          Comprobar identidades a {asOf || 'la fecha'}
        </RunButton>
        <HealthStatus state={identities} failure="No se pudo comprobar las identidades." />
        {identities.result.data && (
          <>
            <p className="text-xs">
              {identities.result.data.without_cik} símbolos sin CIK acreditado a{' '}
              {dateText(identities.result.data.as_of)}.
            </p>
            <Table
              label="Identidades por fecha"
              columns={[
                ['symbol', 'Símbolo'],
                ['status', 'Estado'],
                ['entity_id', 'Entidad'],
                ['cik', 'CIK'],
                ['source', 'Fuente'],
                ['confidence', 'Confianza'],
              ]}
              rows={identities.result.data.rows}
            />
          </>
        )}
      </Folded>
    </Section>
  );
}

const QUARTERLY: [string, string][] = [
  ['date', 'Trimestre'],
  ['members', 'Miembros enumerados'],
  ['all_13', '13 métricas calculables'],
  ['eligible_by_metric_rule', 'Cumplen mínimo del ranking'],
  ['all_13_fresh_prices_and_filing', '13 métricas con precios completos e informe reciente'],
];

function download(rows: Row[]) {
  const columns = Object.keys(rows[0] ?? {});
  const csv = [columns.join(','), ...rows.map((row) => columns.map((c) => row[c] ?? '').join(','))];
  const url = URL.createObjectURL(new Blob([csv.join('\n')], { type: 'text/csv' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'gabi-cobertura-2010-2015.csv';
  link.click();
  URL.revokeObjectURL(url);
}

function ArchiveSection() {
  const archive = useHealthJob<Archive>('health-archive', 'archive');
  const members = useHealthJob<{ source_date: string; symbols: string[]; total: number }>(
    'health-members',
  );
  const prices = useHealthJob<{ symbol: string; rows: Row[]; total: number }>('health-prices');
  const [date, setDate] = useState('2010-01-04');
  const [symbol, setSymbol] = useState('ATVI');
  const data = archive.result.data;
  const membership = data?.sources.find((row) => row.data === 'Composición')?.source;
  const priceSource = data?.sources.find((row) => row.data === 'Precios')?.source;
  return (
    <Section title="Archivo histórico 2010-2015">
      <HowToRead>
        Fuentes históricas descargadas para investigación. Solo se exploran 2010-2015: el periodo
        anterior sigue cerrado por la reserva del #43. Los precios archivados conservan los ajustes
        de su fuente y requieren validar la identidad de cada empresa antes de usarlos en un
        backtest. Los fundamentales estructurados de SEC empiezan en 2009.
      </HowToRead>
      <RunButton running={archive.running} onClick={() => archive.run({ scope: 'archive' })}>
        Consultar cobertura del archivo
      </RunButton>
      <HealthStatus state={archive} failure="No se pudo consultar el archivo." />
      {data && (
        <>
          <Table
            label="Fuentes del archivo"
            columns={[
              ['source', 'Fuente'],
              ['data', 'Datos'],
              ['rows', 'Filas'],
              ['first', 'Desde'],
              ['last', 'Hasta'],
            ]}
            rows={data.sources}
          />
          {membership && (
            <div className="flex flex-wrap items-end gap-3">
              <DateField
                label="Fecha de composición archivada"
                value={date}
                min={data.window[0]}
                max={data.window[1]}
                onChange={setDate}
              />
              <RunButton
                running={members.running || !date}
                onClick={() =>
                  members.run({ scope: 'archive_members', source: membership, as_of: date })
                }
              >
                Ver miembros del índice
              </RunButton>
            </div>
          )}
          <HealthStatus state={members} failure="El archivo no tiene esa composición." />
          {members.result.data && (
            <Folded
              title={`${members.result.data.total} valores en la composición registrada el ${members.result.data.source_date}`}
            >
              <p className="text-xs">{members.result.data.symbols.join(', ')}</p>
            </Folded>
          )}
          {priceSource && (
            <div className="flex flex-wrap items-end gap-3">
              <label className="grid gap-1 text-xs font-medium">
                Símbolo para consultar precios archivados
                <Input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
              </label>
              <RunButton
                running={prices.running || !symbol.trim()}
                onClick={() =>
                  prices.run({
                    scope: 'archive_prices',
                    source: priceSource,
                    symbol: symbol.trim(),
                  })
                }
              >
                Ver precios del archivo
              </RunButton>
            </div>
          )}
          <HealthStatus state={prices} failure="No se pudo consultar los precios." />
          {prices.result.data &&
            (prices.result.data.total === 0 ? (
              <p className="text-xs">El archivo no tiene precios de ese símbolo en 2010-2015.</p>
            ) : (
              <Folded
                title={`${prices.result.data.total} sesiones de ${prices.result.data.symbol}`}
              >
                <p className="text-xs text-muted-foreground">
                  Cierre original y cierre ajustado según la fuente.
                </p>
                <Table
                  label="Precios archivados"
                  columns={[
                    ['date', 'Fecha'],
                    ['close', 'Cierre'],
                    ['adj_close', 'Cierre ajustado'],
                    ['volume', 'Volumen'],
                  ]}
                  rows={prices.result.data.rows}
                />
              </Folded>
            ))}
          {data.quarterly && data.quarterly.length > 0 && (
            <Folded title="Cobertura trimestral 2010-2015">
              <p className="text-xs text-muted-foreground">
                Las 13 métricas calculables no acreditan por sí solas un backtest: todavía hay que
                validar identidad, sectores y ajustes de precios. El control de precios exige las
                253 sesiones previas completas.
              </p>
              <Table label="Cobertura trimestral" columns={QUARTERLY} rows={data.quarterly} />
              <button className="text-xs underline" onClick={() => download(data.quarterly!)}>
                Descargar cobertura trimestral
              </button>
            </Folded>
          )}
        </>
      )}
    </Section>
  );
}

export function DataHealthPage() {
  const universe = useHealthJob<UniverseHealth>('health-universe', 'universe');
  return (
    <div className="space-y-8">
      <PageHeader
        back={{ to: '/administracion', label: 'Administración' }}
        eyebrow="Administración"
        title="Calidad de los datos"
        description={<>Cobertura, frescura y procedencia de cada fuente de datos.</>}
        guide={
          <>
            <p>
              Cobertura, frescura y procedencia de cada fuente: no solo qué score produce un
              símbolo, sino con qué calidad de dato se calculó. Nada se descarga: cada comprobación
              es un trabajo local que lee la caché.
            </p>
          </>
        }
      />
      <UniverseSection state={universe} />
      <BlockCoverage />
      <CompanySection universe={universe.result.data?.universe ?? []} />
      <ArchiveSection />
    </div>
  );
}
