import { lazy, Suspense } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ExternalLink, CalendarDays, ShieldCheck } from 'lucide-react';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card';
import { Badge } from '@/shared/ui/badge';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { Folded } from '@/shared/ui/folded';
import { metric, dateLabel } from '@/shared/lib/format';
import { useCompany } from './queries';
import { Evidence } from './evidence';
import { CompanyEvidenceDetail } from './candidate-evidence';
import { AnalysisPrompt, CompanyResearch, FilingChanges, Insiders } from './company-research';
import { patchParams } from './params';
import { BackLink } from '@/shared/ui/section-links';

const PriceChart = lazy(() => import('./price-chart'));
const groups = [
  {
    name: 'Valoración',
    keys: [
      ['pe', 'PER'],
      ['pb', 'Precio / valor contable'],
      ['ev_ebitda', 'EV / EBITDA'],
      ['free_cashflow', 'Flujo de caja libre'],
    ],
  },
  {
    name: 'Calidad',
    keys: [
      ['roe', 'ROE'],
      ['roic', 'ROIC'],
      ['operating_margin', 'Margen operativo'],
      ['debt_to_equity', 'Deuda / patrimonio'],
    ],
  },
  {
    name: 'Momentum y riesgo',
    keys: [
      ['momentum_6m', 'Momentum · 6 meses'],
      ['momentum_12m', 'Momentum · 12 meses'],
      ['volatility', 'Volatilidad'],
      ['max_drawdown', 'Máximo drawdown'],
    ],
  },
  {
    name: 'Otras métricas (informativas, no puntuadas)',
    keys: [
      ['beta_calc', 'Beta calculada frente al SPY'],
      ['alpha', 'Alfa (CAPM)'],
      ['win_rate_monthly', 'Meses positivos'],
      ['beta', 'Beta (Yahoo)'],
      ['dividend_yield', 'Rentabilidad por dividendo'],
      ['avg_volume', 'Volumen medio'],
    ],
  },
] as const;
export function CompanyPage() {
  const { symbol = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const window = Number(params.get('bars') ?? 252);
  const bars = [63, 252, 1000].includes(window) ? window : 252;
  const result = useCompany(symbol, bars);
  const back = patchParams(params, { bars: null }, false);
  const data = result.data;
  const company = data?.company;
  return (
    <>
      <div className="mb-3">
        <BackLink to={'/mercado?' + back.toString()}>Ranking</BackLink>
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
                  Mercado / Ficha de empresa
                </p>
                <h1 className="text-3xl font-semibold tracking-tight">
                  {company.name ?? company.symbol}
                </h1>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge>{company.symbol}</Badge>
                  <Badge variant="outline">{company.sector ?? 'Sector no disponible'}</Badge>
                  <span className="self-center text-xs text-muted-foreground">
                    Posición global #{company.rank}
                  </span>
                </div>
                <Link
                  className="mt-3 inline-block text-sm font-medium text-primary underline"
                  to={'/cartera/diario?symbol=' + encodeURIComponent(company.symbol)}
                >
                  Escribir tesis en el diario →
                </Link>
              </div>
              <div className="text-right">
                <p className="text-3xl font-semibold tabular-nums">
                  {metric(company.metrics.price)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Último cierre · {dateLabel(company.provenance.price_date)}
                </p>
              </div>
            </div>
            <Evidence model={data.model} data={data.data} />
            <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[
                ['Score del modelo', metric(company.metrics.composite_score), 'Puntos · 0 a 100'],
                ['Cobertura ponderada', metric(company.metrics.confidence), 'Puntos · 0 a 100'],
                [
                  'Métricas disponibles',
                  metric(company.metrics.metrics_available) +
                    ' / ' +
                    metric(company.metrics.metrics_possible),
                  metric(company.metrics.score_coverage) + ' de cobertura',
                ],
                [
                  'Capitalización',
                  metric(company.metrics.market_cap, true),
                  'USD · caché de fundamentales',
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
            <Folded
              title="Evidencia de la candidatura · por qué se asigna su nivel de confianza"
              className="mb-6 rounded-xl border bg-card p-5"
            >
              <CompanyEvidenceDetail symbol={company.symbol} />
            </Folded>
            <Card className="mb-6 gap-4 shadow-none">
              <CardHeader className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle>Histórico de precios</CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Cierre ajustado · USD · sesiones disponibles en la caché.
                  </p>
                </div>
                <div className="flex flex-wrap gap-1" aria-label="Ventana del gráfico">
                  {[
                    [63, '63 sesiones'],
                    [252, '252 sesiones'],
                    [1000, '1.000 sesiones'],
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
                          <dt className="text-muted-foreground">{label}</dt>
                          <dd className="whitespace-nowrap font-medium tabular-nums">
                            {metric(company.metrics[key], true)}
                          </dd>
                        </div>
                      ))}
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
                    Modelo y procedencia
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-sm">
                  <dl className="space-y-3">
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-foreground">Modelo</dt>
                      <dd className="break-all text-right">{data.model.model_id}</dd>
                    </div>
                    {[
                      ['value_score', 'Valoración'],
                      ['quality_score', 'Calidad'],
                      ['momentum_score', 'Momentum'],
                      ['risk_score', 'Riesgo'],
                    ].map(([key, label]) => (
                      <div key={key} className="flex justify-between gap-3">
                        <dt className="text-muted-foreground">{label}</dt>
                        <dd className="tabular-nums">{metric(company.metrics[key])} / 100</dd>
                      </div>
                    ))}
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-foreground">Fundamentales · Yahoo</dt>
                      <dd>{dateLabel(company.provenance.fundamentals_fetched_at)}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-foreground">Información · SEC</dt>
                      <dd>{dateLabel(company.provenance.sec_fetched_at)}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-foreground">Identidad del emisor</dt>
                      <dd>
                        {
                          {
                            resolved: 'Resuelta',
                            ambiguous: 'Ambigua',
                            unresolved: 'Sin resolver',
                          }[company.identity.status]
                        }
                      </dd>
                    </div>
                  </dl>
                  <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                    Datos de la caché local. Estas métricas utilizan el histórico disponible y no
                    constituyen un análisis histórico point-in-time.
                  </p>
                </CardContent>
              </Card>
              <Card className="gap-4 shadow-none">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <CalendarDays size={18} aria-hidden="true" />
                    Documentos y próximas cuentas
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
                    <p className="text-sm text-muted-foreground">Sin documentos SEC en la caché.</p>
                  )}
                  <p className="mt-5 text-xs text-muted-foreground">
                    Próxima publicación de resultados
                  </p>
                  <p className="mt-1 text-sm font-medium">
                    {company.next_earnings
                      ? dateLabel(company.next_earnings.event_date) +
                        (company.next_earnings.is_estimate ? ' · Estimada' : '')
                      : 'Fecha no disponible'}
                  </p>
                </CardContent>
              </Card>
            </div>
            <FilingChanges symbol={company.symbol} />
            <div className="mb-6 space-y-3">
              <CompanyResearch symbol={company.symbol} />
              <Insiders symbol={company.symbol} />
              <AnalysisPrompt symbol={company.symbol} />
            </div>
            <p className="text-xs text-muted-foreground">
              Consulta generada el {dateLabel(data.generated_at)}. La lectura no inicia descargas ni
              actualizaciones.
            </p>
          </>
        )
      )}
    </>
  );
}
