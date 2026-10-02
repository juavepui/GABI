import { lazy, Suspense, useEffect, type ReactNode } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getMetricGlossary } from '@/shared/api/client';
import { ErrorState } from '@/shared/ui/resource-state';
import {
  BIASES,
  ENGINE_COMPARISON,
  GLOSSARY,
  HABITS,
  LOOK_AHEAD_DIAGRAM,
  PIPELINE_DIAGRAM,
  PSYCHOLOGY_INTRO,
  RESEARCH_TERMS,
  SIGNAL_TO_PORTFOLIO_DIAGRAM,
  STRATEGIES,
  STRATEGIES_INTRO,
} from './learn-content';
import { PageHeader } from '@/shared/ui/page-header';

const HiddenDrawdownChart = lazy(() => import('./hidden-drawdown-chart'));

const topics = [
  {
    title: 'Qué significa el score',
    text: 'El Composite Score combina bloques de valor, calidad, momentum y riesgo. Una puntuación alta no garantiza una rentabilidad futura; comprueba cobertura, fecha y procedencia de cada dato.',
    path: '/mercado',
    action: 'Examinar el ranking',
  },
  {
    title: 'Cómo se construye la cartera',
    text: 'La hipótesis congelada usa las 20 candidatas elegibles con más score y el mismo peso para cada una. Si hay menos de 20, se reparte entre las disponibles. La pantalla de Cartera aplica esa regla, calculada en el backend.',
    path: '/cartera',
    action: 'Ver cartera objetivo',
  },
  {
    title: 'Qué dicen las pruebas',
    text: 'Las pruebas retrospectivas y el seguimiento en vivo tienen límites distintos. GABI todavía no ha demostrado de forma independiente una ventaja clara frente al S&P 500. Cambiar el número de posiciones es un experimento, no un modelo validado.',
    path: '/investigacion',
    action: 'Ver Investigación',
  },
  {
    title: 'De una cifra a una tesis',
    text: 'Antes de operar, escribe qué tendría que pasar para que una empresa merezca su precio, qué invalidaría tu idea y cuándo la revisarás. El diario conserva esas notas en la base local.',
    path: '/cartera/diario',
    action: 'Abrir diario',
  },
];

const TABS = [
  ['inicio', 'Primeros pasos'],
  ['terminos', 'Términos útiles'],
  ['estrategias', 'Estrategias de inversión'],
  ['psicologia', 'Psicología de la inversión'],
  ['gabi', 'Cómo piensa GABI'],
  ['glosario', 'Glosario'],
] as const;
type Tab = (typeof TABS)[number][0];

function Item({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="rounded-lg border bg-card px-4 py-3 text-sm">
      <summary className="cursor-pointer font-medium">{title}</summary>
      <div className="mt-2 space-y-2 leading-relaxed text-muted-foreground">{children}</div>
    </details>
  );
}

function Heading({ children }: { children: ReactNode }) {
  return <h2 className="pt-2 text-lg font-semibold">{children}</h2>;
}

function Diagram({ text, label }: { text: string; label: string }) {
  return (
    <pre
      aria-label={label}
      className="overflow-x-auto rounded-lg border bg-muted/40 p-4 font-mono text-xs leading-snug"
    >
      {text}
    </pre>
  );
}

function Note({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-relaxed text-muted-foreground">{children}</p>;
}

function Start() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {topics.map((topic) => (
        <section key={topic.title} className="rounded-xl border bg-card p-6">
          <h2 className="text-lg font-semibold">{topic.title}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{topic.text}</p>
          <Link
            className="mt-5 inline-block text-sm font-medium text-primary underline"
            to={topic.path}
          >
            {topic.action} →
          </Link>
        </section>
      ))}
    </div>
  );
}

function Terms() {
  const glossary = useQuery({
    queryKey: ['learn', 'metrics'],
    queryFn: ({ signal }) => getMetricGlossary(signal),
    staleTime: Infinity,
  });
  const definition = (metric: string) =>
    glossary.data?.terms[metric] ?? (glossary.isPending ? 'Cargando definición…' : '—');
  return (
    <div className="space-y-4">
      <p className="text-sm">
        Vocabulario básico, agrupado por tema. Empieza por «Básicos» si vienes de cero.
      </p>
      {glossary.isError && (
        <ErrorState error={glossary.error} retry={() => void glossary.refetch()} />
      )}
      {GLOSSARY.map((group) => (
        <section key={group.category} className="space-y-2" aria-label={group.category}>
          <Heading>{group.category}</Heading>
          {group.terms.map((term) => (
            <Item key={term.term} title={term.term}>
              <p>{term.metric ? definition(term.metric) : term.text}</p>
            </Item>
          ))}
        </section>
      ))}
      <section className="space-y-3" aria-label="Métricas que usa GABI">
        <Heading>Métricas que usa GABI</Heading>
        <Note>
          Repaso de las métricas que verás en Mercado, la ficha y Comparar. Solo 13 puntúan en el
          Composite Score; el resto se muestran como contexto.
        </Note>
        {glossary.data?.blocks.map((block) => (
          <Item key={block.block} title={block.label}>
            <ul className="space-y-2">
              {block.metrics.map((metric) => (
                <li key={metric.key}>
                  <strong className="text-foreground">{metric.label}</strong>
                  {metric.scored ? ' (puntúa)' : ''}: {metric.help}
                </li>
              ))}
            </ul>
          </Item>
        ))}
      </section>
    </div>
  );
}

function Strategies() {
  return (
    <div className="space-y-3">
      <p className="text-sm">{STRATEGIES_INTRO}</p>
      {STRATEGIES.map((strategy) => (
        <Item key={strategy.title} title={strategy.title}>
          <p className="text-foreground">{strategy.text}</p>
          <Note>{strategy.notes}</Note>
        </Item>
      ))}
    </div>
  );
}

function Psychology() {
  return (
    <div className="space-y-3">
      <p className="text-sm">{PSYCHOLOGY_INTRO}</p>
      {BIASES.map((bias) => (
        <Item key={bias.title} title={bias.title}>
          <p>{bias.text}</p>
        </Item>
      ))}
      <Heading>Tres hábitos prácticos</Heading>
      <ol className="list-decimal space-y-2 pl-5 text-sm">
        {HABITS.map((habit) => (
          <li key={habit.title}>
            <strong>{habit.title}</strong> {habit.text}
          </li>
        ))}
      </ol>
    </div>
  );
}

function HowGabiThinks() {
  return (
    <div className="space-y-4 text-sm leading-relaxed">
      <p>
        Todo lo de aquí describe <strong>decisiones de diseño reales de GABI</strong>, no teoría
        general, con las cifras reales que se midieron al construirlas. El detalle técnico completo
        vive en <code>README.md</code> y <code>HIPOTESIS_CONGELADA.md</code>; esto es la versión
        explicada para entenderlo sin leer código.
      </p>

      <Heading>1. El pipeline point-in-time: nunca mirar al futuro</Heading>
      <p>
        Un ranking «tal y como se habría visto» una fecha pasada solo es honesto si cada pieza de
        información usa exclusivamente lo que se conocía ese día: universo, fundamentales y precio.
      </p>
      <Diagram text={PIPELINE_DIAGRAM} label="Pipeline point-in-time" />
      <Note>
        Cada flecha de este diagrama es una decisión de diseño concreta en el código:{' '}
        <code>universe.get_sp500_constituents_asof</code>, <code>edgar.get_value_as_of</code>{' '}
        (filtra por <code>filed_date</code>) y el histórico de precios truncado en{' '}
        <code>screener_asof.py</code>.
      </Note>

      <Heading>
        2. Tres sesgos que GABI evita, con el fallo real que se encontró en cada uno
      </Heading>
      <Item title="Sesgo de supervivencia">
        <p>
          Si el ranking de 2016 usara la lista ACTUAL del S&amp;P 500, todas las empresas que
          quebraron o fueron excluidas desde entonces desaparecerían del universo: el backtest solo
          vería a las que sobrevivieron, y parecería mucho mejor de lo que habría sido en la
          realidad.
        </p>
        <Note>
          Arreglado con un histórico de composición del índice día a día. Hallazgo real al intentar
          usarlo a fondo: ~16 % de los símbolos necesarios para cubrir 2016-2025 no resuelven CIK en
          SEC EDGAR (empresas deslistadas antes de 2022), un límite estructural de la fuente
          gratuita, documentado, no oculto.
        </Note>
      </Item>
      <Item title="Look-ahead bias (mirar datos del futuro sin darse cuenta)">
        <Diagram
          text={LOOK_AHEAD_DIAGRAM}
          label="Fecha de presentación frente a fecha del ranking"
        />
        <p>
          Cada dato de SEC EDGAR lleva su propia fecha real de presentación (<code>filed_date</code>
          ): un resultado trimestral no «existe» para el mercado hasta que la empresa lo publica,
          aunque se refiera a un trimestre ya cerrado. Usar la última cifra disponible HOY para
          rankear una fecha pasada sería tan irreal como invertir con información privilegiada del
          futuro.
        </p>
      </Item>
      <Item title="Reciclaje de ticker">
        <p>
          Cuando una empresa quiebra o se excluye del índice, la bolsa puede reasignar su símbolo a
          una empresa completamente distinta años después. Caso real comprobado:{' '}
          <strong>BBBY</strong> devuelve cotización viva en yfinance hoy, pero Bed Bath &amp; Beyond
          quebró y fue excluida en 2023: el precio «vivo» bajo ese ticker pertenece a otra cosa.
        </p>
        <Note>
          GABI descarta un símbolo si lleva más de 450 días sin ningún filing SEC (señal de que ya
          no es una «reporting company» viva), comprobando la fecha del filing en el momento exacto
          del backtest, no la más reciente conocida hoy (que podría ser de la empresa nueva).
        </Note>
      </Item>

      <Heading>3. ¿Cuánto te puedes fiar de un resultado de backtest?</Heading>
      <p>
        Con pocos años de historia, un Sharpe algo más alto puede ser pura casualidad de muestreo,
        no una estrategia mejor. Con ~9 años de datos, el error típico de estimación de un Sharpe
        ronda <strong>±0,35-0,39</strong>: una diferencia de 0,1-0,15 entre dos variantes{' '}
        <strong>no demuestra nada</strong>, aunque en una tabla parezca una la clara ganadora.
      </p>
      <Note>
        Comprobado con datos reales: el Sharpe trimestral (0,71) parecía mejor que el anual (0,61),
        pero la diferencia (0,10) es una fracción de un error estándar. La conclusión honesta es que
        la frecuencia de rebalanceo casi no importa, no que el trimestral gane.
      </Note>
      <p>
        Otro problema, más visual: medir el riesgo solo en las fechas de rebalanceo esconde lo que
        pasa <strong>entre medias</strong>. Aquí tienes una caída (sintética, para ilustrar) dentro
        de un solo trimestre: empieza en 100 y termina en 104, así que si solo miras el punto de
        inicio y el de fin, esa caída del 28 % es completamente invisible.
      </p>
      <Suspense fallback={<div className="h-56" />}>
        <HiddenDrawdownChart />
      </Suspense>
      <Note>
        Solo una curva de capital DIARIA muestra la caída del -28 % a mitad de camino: exactamente
        lo que corrige el motor V2 (ver más abajo).
      </Note>

      <Heading>4. Score, cobertura y confianza de evidencia</Heading>
      <p>
        <strong>Score</strong> resume la posición relativa según las métricas.{' '}
        <strong>Cobertura ponderada</strong> (antes Confidence) mide cuántos datos hay disponibles y
        cuánto pesan. <strong>Confianza de evidencia</strong> (BAJA/MEDIA/ALTA) evalúa el respaldo
        estadístico, la estabilidad y la calidad con reglas conservadoras. Una empresa puede tener
        score alto, datos completos y confianza BAJA si sus factores no están confirmados. Ninguno
        de estos valores es una probabilidad de subir en el futuro.
      </p>
      <Note>
        En Mercado, Cartera y la ficha de cada empresa puedes consultar la confianza, la
        persistencia del Top-20 y las razones a favor y en contra. Los niveles no se ajustan para
        maximizar retornos históricos.
      </Note>

      <Heading>5. De la señal a la cartera: son dos decisiones distintas</Heading>
      <Diagram
        text={SIGNAL_TO_PORTFOLIO_DIAGRAM}
        label="Modelo de selección frente a modelo de cartera"
      />
      <p>
        Es perfectamente legítimo construir una cartera con reglas propias (límite por empresa,
        filtro de tendencia, optimización de riesgo); el problema sería presentarla como si heredara
        la validación del backtest, cuando en realidad comparte solo el punto de partida (el score).
      </p>

      <Heading>6. V1 vs V2 del backtest: contabilidad real de cartera</Heading>
      <p>
        El motor original (V1) simula el retorno como un porcentaje agregado: cobra el mismo coste
        sobre el 100 % de cada posición cada rebalanceo, se mantenga o no, y rota el SPY como si
        fuera parte de la estrategia. El motor V2 (en Investigación → Ranking histórico) lleva
        contabilidad real de acciones y caja: solo paga comisión sobre lo que de verdad se compra o
        vende, y el SPY se compra una vez y se mantiene, como haría un inversor pasivo real.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs" aria-label="Motor V1 frente a V2">
          <thead>
            <tr className="border-b">
              <th className="py-1.5 pr-3" />
              <th className="py-1.5 pr-3 font-medium">V1</th>
              <th className="py-1.5 pr-3 font-medium">V2</th>
            </tr>
          </thead>
          <tbody>
            {ENGINE_COMPARISON.map((row) => (
              <tr key={row.row} className="border-b last:border-0">
                <th className="py-1.5 pr-3 font-medium">{row.row}</th>
                <td className="py-1.5 pr-3">{row.v1}</td>
                <td className="py-1.5 pr-3">{row.v2}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Note>
        La lectura honesta no es «V2 rinde más»: es que V1 sobreestimaba el margen real frente al
        SPY en aproximadamente un 26 %. V2 no cambia la estrategia, cambia cuánto te puedes fiar del
        número.
      </Note>

      <Heading>7. Costes reales del bróker: fijo vs proporcional, depositar vs operar</Heading>
      <p>
        Un bróker como eToro cobra un importe <strong>fijo</strong> por operación (no un %), así que
        pesa mucho más en una posición pequeña que en una grande: 1 $ es un 0,18 % de una posición
        de 550 $ pero solo un 0,01 % de una de 10.000 $. Y hay dos costes que NO son lo mismo:{' '}
        <strong>depositar</strong> dinero nuevo desde el banco (conversión de divisa, una vez por
        aportación) y <strong>operar</strong> dentro de la cuenta (abrir o cerrar una posición, en
        cada rebalanceo). Un backtest simula mover dinero entre empresas, no traerlo del banco: por
        eso solo modela el segundo.
      </p>
      <Note>
        El coste real por lado depende del tamaño de cada posición (ver README, «Costes reales del
        bróker»).
      </Note>

      <Heading>
        8. «Hipótesis congelada», Research Lab, Blind Validation... ¿qué es todo esto?
      </Heading>
      <p>
        Si solo quieres invertir, <strong>no necesitas entrar en nada de esto</strong>: Cartera ya
        aplica lo que salió de este trabajo. Esta sección existe para cuando te encuentres estos
        nombres (en Investigación, en modo Research, o en la base de datos) y te preguntes qué son.
      </p>
      {RESEARCH_TERMS.map((term) => (
        <Item key={term.title} title={term.title}>
          <p>{term.text}</p>
        </Item>
      ))}
      <Note>
        Todo esto vive en modo Research (se cambia en Administración); en modo Investor queda fuera
        de la navegación para aplicar las reglas de la hipótesis congelada. Su validación
        independiente y el objetivo de superar claramente al S&amp;P 500 siguen pendientes.
      </Note>
    </div>
  );
}

function Glossary() {
  const glossary = useQuery({
    queryKey: ['learn', 'metrics'],
    queryFn: ({ signal }) => getMetricGlossary(signal),
    staleTime: Infinity,
  });
  const { hash } = useLocation();
  useEffect(() => {
    if (glossary.data && hash) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [glossary.data, hash]);
  if (glossary.isError)
    return <ErrorState error={glossary.error} retry={() => void glossary.refetch()} />;
  return (
    <div className="space-y-3">
      <p className="text-sm">
        Los términos técnicos que aparecen en GABI, con la misma definición que muestra el icono ⓘ
        junto a cada uno.
      </p>
      <dl className="divide-y rounded-xl border bg-card">
        {glossary.data?.glossary.map((entry) => (
          <div
            key={entry.key}
            id={'termino-' + entry.key}
            className={'scroll-mt-24 p-4 ' + (hash === '#termino-' + entry.key ? 'bg-accent' : '')}
          >
            <dt className="font-semibold">{entry.term}</dt>
            <dd className="mt-1 text-sm leading-relaxed text-muted-foreground">
              {entry.definition}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function LearnPage() {
  const [params, setParams] = useSearchParams();
  const requested = params.get('tab');
  const tab: Tab = TABS.some(([id]) => id === requested) ? (requested as Tab) : 'inicio';
  const setTab = (next: Tab) =>
    setParams(next === 'inicio' ? {} : { tab: next }, { replace: true });
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/cartera', label: 'Cartera' }}
        title="Aprender a usar GABI"
        description={<>Vocabulario, estrategias, psicología y cómo piensa GABI por dentro.</>}
        guide={
          <>
            <p>
              Para cuando estás empezando: vocabulario, formas de pensar sobre qué comprar y por
              qué, los errores mentales más comunes al invertir dinero real y cómo funciona GABI por
              dentro, con el rigor que hay (y el que no hay) detrás de sus números. No sustituye a
              un buen libro, pero es un punto de partida conectado con el resto de la aplicación.
            </p>
          </>
        }
      />
      <div role="tablist" aria-label="Secciones de Aprender" className="flex flex-wrap gap-2">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            role="tab"
            id={`learn-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="learn-panel"
            className={`rounded-full border px-3 py-1.5 text-sm ${
              tab === id ? 'border-primary bg-primary text-primary-foreground' : 'bg-card'
            }`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id="learn-panel"
        aria-labelledby={`learn-tab-${tab}`}
        className="max-w-4xl"
      >
        {tab === 'inicio' && <Start />}
        {tab === 'terminos' && <Terms />}
        {tab === 'glosario' && <Glossary />}
        {tab === 'estrategias' && <Strategies />}
        {tab === 'psicologia' && <Psychology />}
        {tab === 'gabi' && <HowGabiThinks />}
      </div>
    </div>
  );
}
