import { lazy, Suspense } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCompanyResearch } from '@/shared/api/client';
import type { CompanyRow } from '@/shared/api/generated/types.gen';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ExternalLink, CalendarDays, ShieldCheck } from 'lucide-react';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card';
import { Badge } from '@/shared/ui/badge';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { Folded } from '@/shared/ui/folded';
import { metric, dateLabel, formatNumber } from '@/shared/lib/format';
import { useBlockEvidence, useCompany } from './queries';
import { Evidence } from './evidence';
import { CompanyEvidenceDetail } from './candidate-evidence';
import {
  AccountingFlags,
  AnalysisPrompt,
  CompanyResearch,
  CurrentReports,
  FilingChanges,
  Insiders,
} from './company-research';
import { CompanyChecklist } from './company-checklist';
import { FollowButton } from './follow-button';
import { ScoreHistory } from './score-history';

import { CompanyTheses } from './company-theses';
import { InvestmentCardSection } from './investment-card';
import { patchParams } from './params';
import { sourceLabel } from './provenance';
import { BackLink } from '@/shared/ui/section-links';
import { BlockBars } from '@/shared/ui/score-summary';

import { BlockEvidenceBadge, FACTOR_LAB } from '@/shared/ui/block-evidence';
import { Hash } from '@/shared/ui/hash';

import { Term } from '@/shared/ui/term';
import {
  drawdownDates,
  drawdownOf,
  drawdownValue,
  historySpan,
  useRiskWindows,
} from './risk-windows';

const PriceChart = lazy(() => import('./price-chart'));
const groups = [
  {
    name: 'Valoración',
    keys: [
      ['pe', 'PER'],
      ['pb', 'Precio / valor contable'],
      ['ev_ebitda', 'EV / EBITDA'],
      ['free_cashflow', 'Caja libre que genera (FCF)'],
    ],
  },
  {
    name: 'Calidad',
    keys: [
      ['roe', 'ROE'],
      ['roic', 'ROIC'],
      ['operating_margin', 'Margen operativo'],
      ['debt_to_equity', 'Deuda frente a fondos propios'],
    ],
  },
  {
    name: 'Tendencia y riesgo',
    keys: [
      ['momentum_6m', 'Subida en 6 meses (momentum)'],
      ['momentum_12m', 'Subida en 12 meses (momentum)'],
      ['volatility', 'Cuánto se mueve el precio (volatilidad)'],
      ['max_drawdown', 'Mayor caída desde un máximo'],
    ],
  },
  {
    name: 'Otros datos (no cuentan para la puntuación)',
    keys: [
      ['beta_calc', 'Beta: cuánto se mueve con el mercado'],
      ['alpha', 'Alfa: rentabilidad extra frente al mercado'],
      ['win_rate_monthly', 'Meses en los que subió'],
      ['beta', 'Beta (Yahoo)'],
      ['dividend_yield', 'Dividendo (% anual)'],
      ['avg_volume', 'Acciones negociadas al día (media)'],
    ],
  },
] as const;
/** Next results and how much the price usually moves that day (#310); shares the research query's cache. */
function EarningsMove({ symbol, next }: { symbol: string; next: CompanyRow['next_earnings'] }) {
  const query = useQuery({
    queryKey: ['market', 'research', symbol],
    queryFn: ({ signal }) => getCompanyResearch(symbol, signal),
  });
  const move = query.data?.typical_move;
  return (
    <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
      {next
        ? 'Próximos resultados: ' +
          dateLabel(next.event_date) +
          (next.is_estimate ? ' (fecha aproximada). ' : '. ')
        : 'Sin fecha de los próximos resultados. '}
      {move?.text}
      {move &&
        move.count > 0 &&
        ' Un salto así ese día es normal y no cambia, por sí solo, la empresa.'}
    </p>
  );
}

export function CompanyPage() {
  const { symbol = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const window = Number(params.get('bars') ?? 252);
  const bars = [63, 252, 1000].includes(window) ? window : 252;
  const result = useCompany(symbol, bars);
  const evidence = useBlockEvidence();
  const back = patchParams(params, { bars: null }, false);
  const data = result.data;
  const company = data?.company;
  const windows = useRiskWindows(company ? [company.symbol] : []);
  const risk = windows.data?.items[0];
  return (
    <>
      <div className="mb-3">
        <BackLink to={'/descubrir?' + back.toString()}>Ranking</BackLink>
      </div>
      {result.isPending ? (
        <LoadingState />
      ) : result.isError ? (
        <ErrorState error={result.error} retry={() => void result.refetch()} />
      ) : (
        data &&
        company && (
          <>
            <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  Ficha de empresa
                </p>
                <h1 className="text-3xl font-semibold tracking-tight">
                  {company.name ?? company.symbol}
                </h1>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge>{company.symbol}</Badge>
                  <Badge variant="outline">{company.sector ?? 'Sector no disponible'}</Badge>
                  <span className="self-center text-xs text-muted-foreground">
                    Puesto {company.rank} del ranking
                  </span>
                  <FollowButton symbol={company.symbol} />
                </div>
                <section aria-label="En pocas palabras" className="mt-3">
                  <p className="max-w-2xl text-base">{data.headline.text}</p>
                  <EarningsMove symbol={company.symbol} next={company.next_earnings} />
                </section>
                <section
                  aria-label="Por qué está aquí"
                  className="mt-3 max-w-xl"
                  title="Resumen de en qué destaca según la puntuación; no es una recomendación."
                >
                  <p className="mb-2 text-sm font-medium">{company.summary.text}</p>
                  <BlockBars summary={company.summary} />
                </section>
                <a
                  className="mt-3 inline-block text-sm font-medium text-primary underline"
                  href="#tesis"
                >
                  Tus notas sobre {company.symbol} ↓
                </a>
              </div>
              <div className="text-right">
                <p className="text-3xl font-semibold tabular-nums">
                  {metric(company.metrics.price)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Precio al cierre del {dateLabel(company.provenance.price_date)}
                </p>
              </div>
            </div>
            <Evidence model={data.model} data={data.data} />
            <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[
                [
                  'Puntuación GABI',
                  metric(company.metrics.composite_score),
                  'De 0 a 100; más alto es mejor según el modelo',
                ],
                [
                  'Datos disponibles',
                  metric(company.metrics.confidence),
                  'De 0 a 100; cuanto más bajo, menos fiable la puntuación',
                ],
                [
                  'Métricas con dato',
                  metric(company.metrics.metrics_available) +
                    ' de ' +
                    metric(company.metrics.metrics_possible),
                  metric(company.metrics.score_coverage) + ' de las que cuentan para la puntuación',
                ],
                [
                  'Tamaño en bolsa',
                  metric(company.metrics.market_cap, true),
                  'Capitalización en USD · ' + sourceLabel(data.metric_sources.market_cap),
                ],
              ].map(([label, value, detail]) => (
                <Card key={label} className="gap-3 py-5 shadow-none">
                  <CardContent>
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="my-2 text-2xl font-semibold tabular-nums">{value}</p>
                    <p className="text-xs text-muted-foreground">{detail}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
            <ScoreHistory symbol={company.symbol} />
            <Folded
              title="¿Cuánto fiarse de su puntuación? · las pruebas a favor y en contra"
              className="mb-6 rounded-xl border bg-card p-5"
            >
              <CompanyEvidenceDetail symbol={company.symbol} />
            </Folded>
            <Card className="mb-6 gap-4 shadow-none">
              <CardHeader className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle>Evolución del precio</CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Precio de cierre de cada día de bolsa, en USD, ajustado por dividendos y
                    divisiones de acciones.
                  </p>
                </div>
                <div className="flex flex-wrap gap-1" aria-label="Ventana del gráfico">
                  {[
                    [63, '3 meses'],
                    [252, '1 año'],
                    [1000, '4 años'],
                  ].map(([count, label]) => (
                    <Button
                      key={count}
                      size="sm"
                      variant={bars === count ? 'secondary' : 'ghost'}
                      aria-pressed={bars === count}
                      onClick={() => setParams(patchParams(params, { bars: String(count) }, false))}
                    >
                      {label}
                    </Button>
                  ))}
                </div>
              </CardHeader>
              <CardContent>
                <Suspense
                  fallback={
                    <p role="status" className="p-12 text-sm text-muted-foreground">
                      Preparando gráfico…
                    </p>
                  }
                >
                  <PriceChart prices={data.prices} />
                </Suspense>
              </CardContent>
            </Card>
            <div className="mb-6 grid gap-4 lg:grid-cols-3">
              {groups.map((group) => (
                <Card key={group.name} className="gap-4 shadow-none">
                  <CardHeader>
                    <CardTitle className="text-base">{group.name}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <dl className="space-y-4">
                      {group.keys.map(([key, label]) => (
                        <div key={key} className="flex justify-between gap-2 text-sm">
                          <dt className="text-muted-foreground">
                            <Term k={key}>{label}</Term>
                            {data.metric_sources[key] ? (
                              <span className="block text-xs">
                                {sourceLabel(data.metric_sources[key])}
                                {(key === 'volatility' || key === 'max_drawdown') && risk
                                  ? ' ' + historySpan(risk)
                                  : ''}
                              </span>
                            ) : null}
                          </dt>
                          <dd className="whitespace-nowrap text-right font-medium tabular-nums">
                            {metric(company.metrics[key], true)}
                            {key === 'max_drawdown' && risk ? (
                              <span className="block text-xs font-normal text-muted-foreground">
                                {drawdownDates(drawdownOf(risk, 'full'))}
                              </span>
                            ) : null}
                          </dd>
                        </div>
                      ))}
                      {group.name === 'Tendencia y riesgo' &&
                        (['5y', '3y'] as const).map((window) => {
                          const row = drawdownOf(risk, window);
                          return (
                            <div key={window} className="flex justify-between gap-2 text-sm">
                              <dt className="text-muted-foreground">
                                <Term k="max_drawdown">
                                  {'Mayor caída · últimos ' +
                                    (window === '5y' ? '5 años' : '3 años')}
                                </Term>
                                <span className="block text-xs">
                                  No cuenta para la puntuación
                                  {row && !row.complete ? ' · * hay menos años de datos' : ''}
                                </span>
                              </dt>
                              <dd className="whitespace-nowrap text-right font-medium tabular-nums">
                                {windows.isPending ? '…' : drawdownValue(row)}
                                <span className="block text-xs font-normal text-muted-foreground">
                                  {drawdownDates(row)}
                                </span>
                              </dd>
                            </div>
                          );
                        })}
                    </dl>
                  </CardContent>
                </Card>
              ))}
            </div>
            <div className="mb-6 grid gap-4 md:grid-cols-2">
              <Card className="gap-4 shadow-none">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <ShieldCheck size={18} aria-hidden="true" />
                    Cómo se calcula y de dónde salen los datos
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-sm">
                  <dl className="space-y-3">
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-foreground">Versión del modelo</dt>
                      <dd className="break-all text-right">{data.model.model_id}</dd>
                    </div>
                    {(
                      [
                        ['value', 'Valoración'],
                        ['quality', 'Calidad'],
                        ['momentum', 'Momentum'],
                        ['risk', 'Riesgo'],
                      ] as const
                    ).map(([key, label]) => {
                      const block = evidence.data?.blocks.find((row) => row.block === key);
                      const weight = data.model.weights[key];
                      return (
                        <div key={key} className="flex flex-wrap justify-between gap-x-3 gap-y-1">
                          <dt className="text-muted-foreground">
                            {label}
                            {weight != null && (
                              <span className="ml-1 text-xs">
                                · cuenta un {formatNumber(weight * 100, { digits: 0 })} %
                              </span>
                            )}
                          </dt>
                          <dd className="flex items-center gap-2 tabular-nums">
                            {block && <BlockEvidenceBadge block={block} />}
                            {metric(company.metrics[key + '_score'])} / 100
                          </dd>
                        </div>
                      );
                    })}
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-foreground">Datos de sus cuentas (Yahoo)</dt>
                      <dd>{dateLabel(company.provenance.fundamentals_fetched_at)}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-foreground">Informes oficiales (SEC)</dt>
                      <dd>{dateLabel(company.provenance.sec_fetched_at)}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-foreground">
                        Historia de la empresa verificada (fusiones, cambios de nombre)
                      </dt>
                      <dd>
                        {
                          {
                            resolved: 'Sí',
                            ambiguous: 'Dudosa',
                            unresolved: 'Sin verificar',
                          }[company.identity.status]
                        }
                      </dd>
                    </div>
                  </dl>
                  <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                    Datos guardados en tu equipo. Se calculan con la información de hoy, no con lo
                    que se sabía en cada fecha pasada; por eso no sirven para juzgar cómo habría ido
                    elegirla antes.
                  </p>
                  {evidence.data ? (
                    <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                      La etiqueta de cada apartado dice cuánto se ha comprobado con datos del pasado
                      que sirve para elegir acciones. No cambia la puntuación.{' '}
                      <Link className="text-primary underline" to={FACTOR_LAB}>
                        Ver el detalle
                      </Link>
                      <span className="mt-1 block">
                        Versión de esas pruebas <Hash value={evidence.data.catalog_sha256} />
                      </span>
                    </p>
                  ) : (
                    evidence.isError && (
                      <p className="mt-2 text-xs text-muted-foreground">
                        No se han podido cargar las pruebas de cada apartado.
                      </p>
                    )
                  )}
                </CardContent>
              </Card>
              <Card className="gap-4 shadow-none">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <CalendarDays size={18} aria-hidden="true" />
                    Informes oficiales y próximos resultados
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {company.filings.length ? (
                    <ul className="space-y-3">
                      {company.filings.map((f) => (
                        <li
                          key={f.form}
                          className="flex items-center justify-between gap-2 border-b pb-3 text-sm"
                        >
                          <span>
                            {f.form}{' '}
                            <span className="ml-2 text-muted-foreground">
                              {dateLabel(f.filed_date)}
                            </span>
                          </span>
                          {f.url ? (
                            <a
                              href={f.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 font-medium text-primary"
                            >
                              Ver en SEC <ExternalLink size={14} aria-hidden="true" />
                              <span className="sr-only">: {f.form}</span>
                            </a>
                          ) : (
                            <span className="text-xs text-muted-foreground">Sin enlace</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No hay informes de la SEC guardados para esta empresa.
                    </p>
                  )}
                  <p className="mt-5 text-xs text-muted-foreground">
                    Próxima publicación de resultados
                  </p>
                  <p className="mt-1 text-sm font-medium">
                    {company.next_earnings
                      ? dateLabel(company.next_earnings.event_date) +
                        (company.next_earnings.is_estimate ? ' · fecha aproximada' : '')
                      : 'Fecha no disponible'}
                  </p>
                </CardContent>
              </Card>
            </div>
            <CompanyChecklist symbol={company.symbol} />
            <div id="ficha-inversion" className="scroll-mt-4">
              <InvestmentCardSection symbol={company.symbol} />
            </div>
            <div id="tesis" className="scroll-mt-4">
              <CompanyTheses symbol={company.symbol} />
            </div>
            <FilingChanges symbol={company.symbol} />
            <AccountingFlags symbol={company.symbol} />
            <CurrentReports symbol={company.symbol} />
            <div className="mb-6 space-y-3">
              <CompanyResearch symbol={company.symbol} />
              <Insiders symbol={company.symbol} />
              <AnalysisPrompt symbol={company.symbol} />
            </div>
            <p className="text-xs text-muted-foreground">
              Calculado el {dateLabel(data.generated_at)}. Abrir esta ficha no descarga nada.
            </p>
          </>
        )
      )}
    </>
  );
}
