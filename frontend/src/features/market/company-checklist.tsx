import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ListChecks } from 'lucide-react';
import {
  applyChecklistPreset,
  getChecklistThresholds,
  getCompanyChecklist,
  getCompanyChecklistSector,
  resetChecklistThresholds,
  saveChecklistThresholds,
} from '@/shared/api/client';
import type {
  ChecklistAlarm,
  ChecklistCriterion,
  ChecklistMedian,
  ChecklistThreshold,
  CompanyChecklistResponse,
} from '@/shared/api/generated/types.gen';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card';
import { Folded } from '@/shared/ui/folded';
import { Hint } from '@/shared/ui/hint';
import { HowToRead } from '@/shared/ui/how-to-read';
import { Input } from '@/shared/ui/input';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { dateLabel, formatCompactMoney, formatNumber, formatPercent } from '@/shared/lib/format';
import { sourceLabel } from './provenance';
import { CONCEPTS, reasonText, show, VERDICTS } from './checklist-format';

const COMPARISON: Record<string, string> = { '>=': '≥', '>': '>', '<=': '≤', '<': '<' };

function thresholdText(item: ChecklistCriterion): string {
  if (item.comparison === 'info') return 'Informativo';
  if (item.comparison === '<pe') return '< PER actual';
  return `${COMPARISON[item.comparison] ?? item.comparison} ${show(item.threshold, item.unit)}`;
}

const ALARMS: Record<
  ChecklistAlarm['status'],
  { label: string; variant: 'default' | 'destructive' | 'outline' | 'secondary' }
> = {
  active: { label: 'Activa', variant: 'destructive' },
  clear: { label: 'Sin alarma', variant: 'default' },
  missing: { label: 'Sin dato', variant: 'outline' },
  not_applicable: { label: 'No aplica', variant: 'secondary' },
  manual: { label: 'Revisión manual', variant: 'secondary' },
  info: { label: 'Info', variant: 'secondary' },
};

const SHARE_SOURCES: Record<string, string> = {
  yahoo_no_sec_shares:
    'capitalización de Yahoo: la SEC no tiene número de acciones de esta empresa',
  sec_diluted_average:
    'acciones medias diluidas del 10-K: la SEC no publica el total en circulación (varias clases)',
  yahoo_market_cap:
    'capitalización de Yahoo: las acciones SEC no cuadran con el precio (clases de acciones, split sin registrar o emisión reciente)',
};

/** Why a value that is still shown may be unreliable; the backend decides when it applies. */
const CAVEATS: Record<string, string> = {
  share_classes:
    'Puede no ser fiable: la SEC no publica un total de acciones comparable con el precio (habitual con varias clases de acciones) y Yahoo puede no contar la clase que controlan los fundadores.',
};

function Caveat({ caveat }: { caveat: string | null | undefined }) {
  if (!caveat || !CAVEATS[caveat]) return null;
  return (
    <span role="note" className="mt-1 block text-xs text-amber-700 dark:text-amber-400">
      ⚠ {CAVEATS[caveat]}
    </span>
  );
}

function note(item: ChecklistCriterion): string {
  const detail = item.detail as Record<string, unknown>;
  const parts: string[] = [];
  if (typeof detail.years === 'number' && item.key.endsWith('cagr'))
    parts.push(`${detail.years} años`);
  if (typeof detail.class === 'string') parts.push(detail.class);
  if (typeof detail.shares_source === 'string' && SHARE_SOURCES[detail.shares_source])
    parts.push(SHARE_SOURCES[detail.shares_source]);
  if (Array.isArray(detail.components_not_reported) && detail.components_not_reported.length)
    parts.push(
      'sin declarar: ' +
        detail.components_not_reported.map((name) => CONCEPTS[String(name)] ?? name).join(', '),
    );
  if (item.edited) parts.push(`umbral editado (Excel: ${show(item.default_threshold, item.unit)})`);
  if (item.reason && item.verdict !== 'pass') parts.push(reasonText(item.reason));
  return parts.join(' · ');
}

function CriterionHint({ item }: { item: ChecklistCriterion }) {
  return (
    <>
      <span className="block font-semibold">{item.label}</span>
      <span className="mt-1 block">{item.explanation}</span>
      <span className="mt-2 block text-muted-foreground">Fórmula: {item.formula}</span>
      <span className="block text-muted-foreground">Vídeo: {item.reference}</span>
    </>
  );
}

type Sources = Pick<
  CompanyChecklistResponse,
  'fiscal_year_end' | 'sources' | 'pass_rate_reference'
>;

/** How much of the S&P 500, and of the sector, meets the threshold that applies now (#171). */
function PassRate({ item, data }: { item: ChecklistCriterion; data: Sources }) {
  const rate = item.pass_rate;
  const reference = data.pass_rate_reference;
  if (!rate || !reference || rate.universe.rate == null) return null;
  const sector =
    rate.sector?.rate != null
      ? ` · ${formatPercent(rate.sector.rate, { digits: 0 })} de ${reference.sector ?? 'su sector'}`
      : '';
  return (
    <span className="block text-muted-foreground">
      <Hint
        content={`Emisores del S&P 500 con este criterio evaluado en la auditoría del ${dateLabel(
          reference.as_of,
        )} (${rate.universe.evaluated} de ${reference.issuers}${
          rate.sector ? `; ${rate.sector.evaluated} de su sector` : ''
        }) que cumplen el umbral actual. Es contexto: no cambia el ✔/✘ de esta empresa.`}
      >
        Lo cumple el {formatPercent(rate.universe.rate, { digits: 0 })} del S&P 500{sector}
      </Hint>
    </span>
  );
}

/** Source and period of a criterion value, as the backend declares them. */
function criterionSource(item: ChecklistCriterion, data: Sources): string {
  const year = data.fiscal_year_end ? 'FY' + data.fiscal_year_end.slice(0, 4) : 'sin ejercicio';
  const yahoo = dateLabel(data.sources.yahoo_fetched_at?.slice(0, 10));
  if (item.source === 'sec_10k') return `SEC 10-K · ${year}`;
  if (item.source === 'price+sec') return `Precio + SEC 10-K · ${year}`;
  if (item.source === 'yahoo') return `Yahoo · ${yahoo}`;
  if (item.source === 'price+yahoo') return `Precio + consenso Yahoo · ${yahoo}`;
  return sourceLabel({ source: 'prices', period: item.period });
}

const OWN_SOURCE: Record<ChecklistCriterion['source'], string> = {
  sec_10k: 'SEC',
  'price+sec': 'SEC',
  yahoo: 'Yahoo',
  'price+yahoo': 'Yahoo',
  prices: 'GABI',
};

/** The same concept shown elsewhere on the page with another source or formula; never mixed in. */
function Alternative({ item }: { item: ChecklistCriterion }) {
  const other = item.alternative;
  if (!other) return null;
  const label = (other.difference === 'formula' ? 'Composite · ' : '') + sourceLabel(other);
  const value = show(other.value, item.unit);
  return (
    <span className="mt-0.5 block text-xs text-muted-foreground">
      <Hint content={other.explanation}>
        {item.value == null
          ? `Sin dato ${OWN_SOURCE[item.source]}; ${label} informa ${value} (no se mezcla)`
          : `${label}: ${value}`}
      </Hint>
    </span>
  );
}

function Criteria({ criteria, data }: { criteria: ChecklistCriterion[]; data: Sources }) {
  const blocks = [...new Set(criteria.map((item) => item.block))];
  return (
    <div className="overflow-x-auto" role="region" aria-label="Tabla del checklist" tabIndex={0}>
      <table className="w-full text-left text-xs" aria-label="Criterios del checklist">
        <thead>
          <tr className="border-b">
            {['Métrica', 'Valor', 'Umbral', 'Resultado', 'Nota'].map((title) => (
              <th key={title} className="py-1.5 pr-3 font-medium">
                {title}
              </th>
            ))}
          </tr>
        </thead>
        {blocks.map((block) => (
          <tbody key={block}>
            <tr>
              <th colSpan={5} className="pt-3 pb-1 text-left font-semibold text-muted-foreground">
                {block}
              </th>
            </tr>
            {criteria
              .filter((item) => item.block === block)
              .map((item) => (
                <tr key={item.key} className="border-b last:border-0">
                  <td className="py-1.5 pr-3">
                    <Hint content={<CriterionHint item={item} />}>{item.label}</Hint>
                  </td>
                  <td className="py-1.5 pr-3 tabular-nums">
                    {show(item.value, item.unit)}
                    <span className="block text-xs text-muted-foreground">
                      {criterionSource(item, data)}
                    </span>
                    <Alternative item={item} />
                  </td>
                  <td className="py-1.5 pr-3 tabular-nums">
                    {thresholdText(item)}
                    <PassRate item={item} data={data} />
                  </td>
                  <td className="py-1.5 pr-3">
                    <Badge variant={VERDICTS[item.verdict].variant}>
                      {VERDICTS[item.verdict].label}
                    </Badge>
                  </td>
                  <td className="py-1.5 pr-3 text-muted-foreground">
                    {note(item)}
                    <Caveat caveat={item.caveat} />
                  </td>
                </tr>
              ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

function Alarms({ alarms }: { alarms: ChecklistAlarm[] }) {
  return (
    <ul className="space-y-2" aria-label="Señales de alarma">
      {alarms.map((alarm) => (
        <li
          key={alarm.key}
          className="flex flex-wrap items-start justify-between gap-2 border-b pb-2"
        >
          <span>
            <span className="font-medium">
              <Hint content={alarm.explanation}>{alarm.label}</Hint>
            </span>
            <span className="block text-xs text-muted-foreground">
              {alarm.check}
              {alarm.reason ? ' · ' + reasonText(alarm.reason) : ''}
            </span>
            <Caveat caveat={alarm.caveat} />
          </span>
          <Badge variant={ALARMS[alarm.status].variant}>{ALARMS[alarm.status].label}</Badge>
        </li>
      ))}
    </ul>
  );
}

type Multiple = 'pe' | 'ev_ebitda' | 'ev_ebit' | 'ev_fcf';

const MULTIPLES: [Multiple, string][] = [
  ['pe', 'PER'],
  ['ev_ebitda', 'EV/EBITDA'],
  ['ev_ebit', 'EV/EBIT'],
  ['ev_fcf', 'EV/FCF'],
];

const MULTIPLE_COLUMNS: [string, string][] = [
  ['Múltiplo', 'Pasa el puntero por cada múltiplo para ver qué mide.'],
  ['Actual', 'Múltiplo con el último precio y el último ejercicio fiscal presentado a la SEC.'],
  [
    'Mediana propia',
    'Mediana del múltiplo de la propia empresa en sus últimos ejercicios, cada uno con el precio al cierre de ese ejercicio. Si el actual está muy por encima, cotiza más cara que de costumbre. Entre paréntesis, cuántos años tienen dato.',
  ],
  [
    'Mediana del sector',
    'Mediana del múltiplo actual de las demás empresas de su sector en el universo actual, con las mismas fórmulas. Entre paréntesis, cuántas empresas tienen dato: con pocas, la referencia es débil.',
  ],
];

function median(item: ChecklistMedian | undefined, what: string): string {
  if (!item) return '—';
  if (item.median == null) return reasonText(item.reason) || '—';
  return `${show(item.median, 'ratio')} (${item.count} ${what})`;
}

function Multiples({ data }: { data: CompanyChecklistResponse }) {
  const sector = useQuery({
    queryKey: ['market', 'checklist', data.symbol, 'sector'],
    queryFn: ({ signal }) => getCompanyChecklistSector(data.symbol, signal),
  });
  const current = Object.fromEntries(data.criteria.map((item) => [item.key, item.value]));
  const explained = Object.fromEntries(data.criteria.map((item) => [item.key, item.explanation]));
  const history = data.multiples_history;
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Compara los múltiplos actuales con la mediana de la propia empresa en sus últimos{' '}
        {history.years} ejercicios (precio al cierre de cada ejercicio y cifras de ese 10-K) y con
        la mediana de las demás empresas de su sector en el universo actual, con las mismas fórmulas
        SEC. Que un múltiplo esté por debajo de su referencia no implica que la empresa esté barata:
        también puede reflejar peores perspectivas.
      </p>
      <div className="overflow-x-auto" role="region" aria-label="Tabla de múltiplos" tabIndex={0}>
        <table
          className="w-full text-left text-xs"
          aria-label="Múltiplos frente a su historia y su sector"
        >
          <thead>
            <tr className="border-b">
              {MULTIPLE_COLUMNS.map(([title, help]) => (
                <th key={title} className="py-1.5 pr-3 font-medium">
                  <Hint content={help}>
                    {title === 'Mediana propia' ? `${title} (${history.years} años)` : title}
                  </Hint>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MULTIPLES.map(([key, label]) => (
              <tr key={key} className="border-b last:border-0">
                <th scope="row" className="py-1.5 pr-3 font-normal">
                  <Hint content={explained[key]}>{label}</Hint>
                </th>
                <td className="py-1.5 pr-3 tabular-nums">{show(current[key], 'ratio')}</td>
                <td className="py-1.5 pr-3 tabular-nums">{median(history.median[key], 'años')}</td>
                <td className="py-1.5 pr-3 tabular-nums">
                  {sector.isPending
                    ? 'Calculando…'
                    : sector.isError
                      ? 'No disponible'
                      : median(sector.data.medians[key], 'pares')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sector.isError && <ErrorState error={sector.error} retry={() => void sector.refetch()} />}
      {sector.data && (
        <p className="text-xs text-muted-foreground">
          Sector: {sector.data.sector ?? '—'}
          {sector.data.reason
            ? ` · ${reasonText(sector.data.reason)}`
            : ` · ${sector.data.peers} pares`}
        </p>
      )}
      <ul className="space-y-1 text-xs" aria-label="Múltiplos por ejercicio">
        {history.by_year.map((year) => (
          <li
            key={year.fiscal_year_end}
            className="flex flex-wrap justify-between gap-2 border-b py-1"
          >
            <span className="text-muted-foreground">{dateLabel(year.fiscal_year_end)}</span>
            <span className="tabular-nums">
              {MULTIPLES.map(([key, label]) => `${label} ${show(year[key], 'ratio')}`).join(' · ')}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const DCF_VERDICTS: Record<CompanyChecklistResponse['dcf']['verdict'], string> = {
  reasonable: 'Razonable: el precio descuenta un crecimiento no superior al histórico del CFO.',
  demanding: 'Exigente: el precio descuenta más crecimiento que el histórico del CFO.',
  discard: 'Descartable según el vídeo: el crecimiento implícito supera el máximo fijado.',
  missing: 'Sin dato suficiente para el DCF inverso.',
  not_applicable: 'No aplica a bancos y aseguradoras.',
};

function Dcf({ dcf }: { dcf: CompanyChecklistResponse['dcf'] }) {
  const rows: [string, string, string][] = [
    [
      'Crecimiento implícito del FCF',
      formatPercent(dcf.implied_growth),
      'Crecimiento anual del flujo de caja libre que justifica el precio actual con estos supuestos. Es lo que el mercado da por hecho: cuanto más alto, más exigente es el precio.',
    ],
    [
      'CAGR histórico del CFO',
      formatPercent(dcf.historical_cfo_cagr),
      'Lo que ha crecido de verdad cada año el flujo de caja operativo en la última década (o 5 años). Sirve para juzgar si el crecimiento implícito es alcanzable.',
    ],
    [
      'Valor por acción si crece como el histórico',
      dcf.value_per_share_at_history == null
        ? '—'
        : formatNumber(dcf.value_per_share_at_history, { digits: 2 }) + ' US$',
      'Valor de cada acción si el FCF creciera al ritmo histórico del CFO durante los años proyectados. Es el escenario «se repite el pasado», no una estimación: con crecimientos altos sale muy elevado.',
    ],
    [
      'FCF del último ejercicio',
      formatCompactMoney(dcf.fcf),
      'Flujo de caja libre (CFO − CAPEX) del último 10-K: el punto de partida de la proyección.',
    ],
    [
      'Supuestos',
      `${formatPercent(dcf.dcf_discount_rate)} descuento · ${formatPercent(dcf.dcf_terminal_growth)} perpetuidad · ${formatNumber(dcf.dcf_years, { digits: 0 })} años`,
      'Tasa de descuento (rentabilidad que exiges), crecimiento a perpetuidad tras el último año y años proyectados. Se cambian en la sección de umbrales, al final de la tarjeta.',
    ],
  ];
  return (
    <div className="space-y-2">
      <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
        {rows.map(([label, value, help]) => (
          <div key={label} className="flex justify-between gap-3 border-b py-1">
            <dt className="text-muted-foreground">
              <Hint content={help}>{label}</Hint>
            </dt>
            <dd className="tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs">
        {DCF_VERDICTS[dcf.verdict]}
        {dcf.reason ? ' ' + reasonText(dcf.reason) + '.' : ''}
      </p>
    </div>
  );
}

/** Fractions are edited as percentages; the backend validates and stores the fraction. */
function toInput(value: number | null | undefined, unit: string): string {
  if (value == null) return '';
  return String(unit === 'fraction' ? Math.round(value * 10000) / 100 : value);
}

function ThresholdEditor() {
  const queryClient = useQueryClient();
  const thresholds = useQuery({
    queryKey: ['market', 'checklist-thresholds'],
    queryFn: ({ signal }) => getChecklistThresholds(signal),
  });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const refresh = (data: Awaited<ReturnType<typeof getChecklistThresholds>>) => {
    queryClient.setQueryData(['market', 'checklist-thresholds'], data);
    setDraft({});
    void queryClient.invalidateQueries({ queryKey: ['market', 'checklist'] });
  };
  const save = useMutation({ mutationFn: saveChecklistThresholds, onSuccess: refresh });
  const reset = useMutation({ mutationFn: resetChecklistThresholds, onSuccess: refresh });
  const preset = useMutation({ mutationFn: applyChecklistPreset, onSuccess: refresh });
  if (thresholds.isPending) return <LoadingState />;
  if (thresholds.isError)
    return <ErrorState error={thresholds.error} retry={() => void thresholds.refetch()} />;
  const data = thresholds.data;
  const value = (item: ChecklistThreshold) =>
    draft[item.key] ?? toInput(data.values[item.key], item.unit);
  const submit = () => {
    const values: Record<string, number> = {};
    for (const item of data.catalog) {
      const number = Number(value(item).replace(',', '.'));
      values[item.key] = item.unit === 'fraction' ? number / 100 : number;
    }
    save.mutate({ values });
  };
  const error = save.error ?? reset.error ?? preset.error;
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <p className="text-xs text-muted-foreground">
        Por defecto, los umbrales del Excel. Los porcentajes se escriben en %. Solo cambian el ✔/✘
        del checklist: no afectan a los valores, al Composite ni al ranking.
      </p>
      <fieldset className="space-y-2 rounded-md border p-3 text-xs">
        <legend className="px-1 font-medium">Presets</legend>
        <p className="text-muted-foreground">
          {data.preset
            ? `Umbrales actuales: ${data.presets.find((item) => item.key === data.preset)?.label}.`
            : 'Umbrales actuales: editados a mano.'}{' '}
          Aplicar un preset sustituye todos los umbrales; después se pueden seguir editando.
        </p>
        {data.presets.map((item) => (
          <div key={item.key} className="flex flex-wrap items-start gap-3">
            <Button
              type="button"
              size="sm"
              variant={data.preset === item.key ? 'default' : 'outline'}
              aria-pressed={data.preset === item.key}
              pending={preset.isPending}
              onClick={() => preset.mutate(item.key)}
            >
              {item.label}
            </Button>
            <span className="min-w-56 flex-1 text-muted-foreground">{item.description}</span>
          </div>
        ))}
      </fieldset>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {data.catalog.map((item) => (
          <label key={item.key} className="space-y-1 text-xs">
            <span className="flex justify-between gap-2">
              <span>
                <Hint content={item.explanation}>{item.label}</Hint>{' '}
                {item.comparison in COMPARISON ? COMPARISON[item.comparison] : ''}
              </span>
              {data.edited.includes(item.key) && (
                <span className="text-muted-foreground">
                  editado · Excel {toInput(item.default, item.unit)}
                  {item.unit === 'fraction' ? ' %' : ''}
                </span>
              )}
            </span>
            <Input
              inputMode="decimal"
              aria-label={`Umbral: ${item.label}`}
              value={value(item)}
              onChange={(event) => setDraft({ ...draft, [item.key]: event.target.value })}
            />
          </label>
        ))}
      </div>
      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error.message}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" pending={save.isPending}>
          Guardar umbrales
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          pending={reset.isPending}
          disabled={!data.edited.length}
          onClick={() => reset.mutate()}
        >
          Restablecer valores del Excel
        </Button>
      </div>
    </form>
  );
}

export function CompanyChecklist({ symbol }: { symbol: string }) {
  const checklist = useQuery({
    queryKey: ['market', 'checklist', symbol],
    queryFn: ({ signal }) => getCompanyChecklist(symbol, signal),
  });
  return (
    <Card className="mb-6 gap-4 shadow-none">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ListChecks size={18} aria-hidden="true" />
          Checklist fundamental
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {checklist.isPending ? (
          <LoadingState />
        ) : checklist.isError ? (
          <ErrorState error={checklist.error} retry={() => void checklist.refetch()} />
        ) : (
          <ChecklistContent data={checklist.data} />
        )}
        <Folded title="Editar umbrales" className="rounded-md border p-3 text-sm">
          <ThresholdEditor />
        </Folded>
      </CardContent>
    </Card>
  );
}

function ChecklistContent({ data }: { data: CompanyChecklistResponse }) {
  const summary = data.summary;
  return (
    <>
      <HowToRead>
        Compara la empresa con los criterios y umbrales de tu checklist (vídeos de Javier DV,
        Memorias de Tiburón, Pedro Gutiérrez y La Pizarra de Andrés), usando un único ejercicio de
        los 10-K presentados a la SEC, el último precio de la caché y, cuando se indica, datos de
        Yahoo. Un dato ausente se muestra como «Sin dato», nunca como cero. Los umbrales son reglas
        generales que dependen del sector. Es informativo: no entra en el Composite Score, no es una
        señal validada ni una recomendación de inversión.
      </HowToRead>
      {data.thresholds_warning && (
        <p className="text-xs" role="alert">
          {reasonText(data.thresholds_warning)}.
        </p>
      )}
      <dl className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">
            <Hint content="Cuántos de los criterios con umbral pasa la empresa, sobre los que se han podido evaluar (sin contar los informativos ni los que no tienen dato). El porcentaje es una guía, no una puntuación validada.">
              Criterios cumplidos
            </Hint>
          </dt>
          <dd className="text-lg font-semibold">
            {summary.passed} / {summary.evaluated}
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {formatPercent(summary.score, { digits: 0 })}
            </span>
          </dd>
        </div>
        <div className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">
            <Hint content="Criterios con valor sobre los que aplican a esta empresa: indica cuánto del checklist es utilizable aquí. Los demás no tienen dato porque la SEC no lo declara, es de otro ejercicio o no hay precio; nunca se rellenan con cero y la nota de cada fila explica el motivo.">
              Evaluables
            </Hint>
          </dt>
          <dd className="text-lg font-semibold">
            {summary.with_value} / {summary.applicable}
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {summary.missing} sin dato
            </span>
          </dd>
        </div>
        <div className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">
            <Hint content="Señales de riesgo que saltan, sobre las que se han podido comprobar con datos. Las de revisión manual no cuentan: las valoras tú.">
              Alarmas activas
            </Hint>
          </dt>
          <dd className="text-lg font-semibold">
            {summary.alarms_active} / {summary.alarms_evaluated}
          </dd>
        </div>
        <div className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">
            <Hint content="Cierre del último ejercicio anual (10-K) presentado a la SEC. Todos los ratios usan cifras de ese mismo ejercicio para no mezclar años.">
              Ejercicio fiscal usado
            </Hint>
          </dt>
          <dd className="text-lg font-semibold">{dateLabel(data.fiscal_year_end)}</dd>
        </div>
      </dl>
      <p className="text-xs text-muted-foreground">
        Último 10-K/10-Q conocido: {dateLabel(data.sources.sec_last_filed)} · Precio:{' '}
        {dateLabel(data.sources.price_date)} · Yahoo:{' '}
        {dateLabel(data.sources.yahoo_fetched_at?.slice(0, 10))}
        {data.financial_sector ? ' · Sector financiero: algunos criterios no aplican.' : ''}
      </p>
      <Criteria criteria={data.criteria} data={data} />
      <Folded title="Señales de alarma" className="rounded-md border p-3 text-sm">
        <Alarms alarms={data.alarms} />
      </Folded>
      <Folded
        title="Múltiplos frente a su historia y su sector"
        className="rounded-md border p-3 text-sm"
      >
        <Multiples data={data} />
      </Folded>
      <Folded
        title="DCF inverso: ¿qué crecimiento descuenta el precio?"
        className="rounded-md border p-3 text-sm"
      >
        <Dcf dcf={data.dcf} />
      </Folded>
      <Folded
        id="criterios-cualitativos"
        title="Criterios cualitativos (los evalúas tú)"
        className="rounded-md border p-3 text-sm"
      >
        <ul className="list-disc space-y-1 pl-5 text-xs">
          {data.qualitative.map((item) => (
            <li key={item.key}>
              <span className="font-medium">{item.label}</span>{' '}
              <span className="text-muted-foreground">{item.hint}</span>
            </li>
          ))}
        </ul>
      </Folded>
    </>
  );
}
