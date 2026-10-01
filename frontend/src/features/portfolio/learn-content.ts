/** Text of the old Aprender tutorial. Metric definitions are not here: they come from the backend. */

/** A glossary entry is either text or the key of a metric whose backend help defines it. */
export type Term = { term: string; text?: string; metric?: string };

export const GLOSSARY: { category: string; terms: Term[] }[] = [
  {
    category: 'Básicos',
    terms: [
      {
        term: 'Acción',
        text: 'Un título que representa una parte de la propiedad de una empresa. Comprar acciones te convierte en copropietario, con derecho a una parte del beneficio (si reparte dividendo) y del valor de la empresa.',
      },
      {
        term: 'Cartera (portfolio)',
        text: 'El conjunto de todas las inversiones que tienes: acciones, fondos, efectivo... Su comportamiento conjunto importa más que el de cada posición por separado.',
      },
      {
        term: 'Índice bursátil',
        text: "Una cesta representativa de acciones (por ejemplo, S&P 500 = las 500 mayores empresas de EE. UU.) que se usa como termómetro del mercado y como referencia (benchmark) para saber si lo estás haciendo mejor o peor que 'el mercado'.",
      },
      {
        term: 'ETF',
        text: 'Un fondo cotizado que replica un índice (u otra cesta de activos) y se compra y vende como una acción. Forma barata y diversificada de invertir en todo un mercado de una vez.',
      },
      {
        term: 'Capitalización bursátil',
        text: "Precio de la acción × número de acciones en circulación. El 'tamaño' de la empresa en bolsa. Large cap (grande), mid cap (mediana), small cap (pequeña): a menor tamaño, normalmente más riesgo y más potencial de crecimiento.",
      },
      {
        term: 'Dividendo',
        text: 'Parte del beneficio que la empresa reparte a sus accionistas, normalmente en efectivo. No repartir dividendo no es necesariamente malo: puede significar que la empresa prefiere reinvertir el dinero en crecer.',
      },
      {
        term: 'OPV / IPO',
        text: 'Oferta Pública de Venta (Initial Public Offering): el momento en que una empresa privada empieza a cotizar en bolsa por primera vez.',
      },
    ],
  },
  {
    category: 'Valoración (¿está cara o barata?)',
    terms: [
      { term: 'PER', metric: 'pe' },
      { term: 'EV/EBITDA', metric: 'ev_ebitda' },
      {
        term: 'Capitalización vs. valor de empresa (EV)',
        text: "La capitalización es solo el valor de las acciones. El Enterprise Value (EV) le suma la deuda y le resta la caja: el precio 'real' que pagarías si compraras la empresa entera, deudas incluidas.",
      },
      {
        term: 'Múltiplo',
        text: "Forma coloquial de referirse a ratios como el PER o el EV/EBITDA: 'cotiza a un múltiplo alto' significa que es cara respecto a sus beneficios o su caja.",
      },
      {
        term: 'Margen',
        text: 'Porcentaje de las ventas que la empresa se queda como beneficio en cada etapa (bruto, operativo, neto). Márgenes altos y estables suelen indicar poder de fijación de precios (pricing power).',
      },
    ],
  },
  {
    category: 'Riesgo y volatilidad',
    terms: [
      { term: 'Volatilidad', metric: 'volatility' },
      { term: 'Drawdown', metric: 'max_drawdown' },
      {
        term: 'Diversificación',
        text: 'Repartir el dinero entre distintas empresas, sectores o países para que un problema puntual en una sola inversión no arruine toda la cartera. Una sola acción, por muy buena que parezca, nunca está diversificada.',
      },
      {
        term: 'Beta',
        text: 'Cuánto se mueve una acción en relación al mercado. Beta > 1 = más volátil que el mercado; beta < 1 = más defensiva.',
      },
      {
        term: 'Mercado alcista / bajista (bull / bear market)',
        text: 'Periodos prolongados de subidas (bull) o caídas (bear) generalizadas en el mercado. Suelen definirse informalmente como una caída de más del 20 % desde el último máximo para el mercado bajista.',
      },
      {
        term: 'Corrección',
        text: 'Caída del mercado de en torno al 10 % desde un máximo: más habitual y menos grave que un mercado bajista completo.',
      },
      {
        term: 'Liquidez',
        text: 'Facilidad para comprar o vender un activo rápidamente sin mover mucho su precio. Empresas con poco volumen de negociación son menos líquidas y más arriesgadas de entrar y salir.',
      },
    ],
  },
  {
    category: 'Operativa',
    terms: [
      {
        term: 'Apalancamiento',
        text: 'Invertir con dinero prestado (o mediante productos derivados) para multiplicar tanto las ganancias como las pérdidas. Herramienta avanzada, no recomendable para quien empieza.',
      },
      {
        term: 'Comisiones',
        text: 'Lo que cobra el bróker o plataforma por comprar, vender o mantener una posición. Parecen pequeñas pero erosionan la rentabilidad a largo plazo, sobre todo si operas mucho.',
      },
      {
        term: 'Fiscalidad (ganancias/pérdidas patrimoniales)',
        text: 'Vender con beneficio genera una ganancia sujeta a impuestos (varía por país). Las pérdidas normalmente se pueden compensar con ganancias futuras: infórmate de las reglas de tu país antes de operar mucho.',
      },
      {
        term: 'Dollar-cost averaging (DCA)',
        text: 'Invertir una cantidad fija de forma periódica (por ejemplo, cada mes) en vez de todo de golpe. Suaviza el efecto de comprar justo en un mal momento, a cambio de renunciar a intentar acertar el mejor momento.',
      },
      {
        term: 'Rebalanceo',
        text: 'Ajustar periódicamente la cartera para que vuelva a los porcentajes objetivo que te marcaste (por ejemplo, si una posición ha crecido mucho y ahora pesa más de la cuenta, vender un poco).',
      },
    ],
  },
];

export const STRATEGIES_INTRO =
  "No existe 'la' estrategia correcta: existen distintas formas de pensar sobre qué comprar, con distintos riesgos, horizontes y exigencias de tiempo. GABI combina varias de estas ideas en un único score (Value/Quality/Momentum/Risk); en modo Research, ajustar los pesos en Administración te acerca más a una u otra.";

export const STRATEGIES: { title: string; text: string; notes: string }[] = [
  {
    title: 'Value investing (inversión en valor)',
    text: "Comprar empresas que cotizan por debajo de lo que 'valen' según sus fundamentales (PER, EV/EBITDA bajos frente a su sector), apostando a que el mercado corregirá esa infravaloración con el tiempo. Escuela clásica de Benjamin Graham y Warren Buffett.",
    notes:
      "A favor: suele implicar menos riesgo de pagar de más; históricamente ha batido al mercado a muy largo plazo. Cuidado: una empresa puede estar barata por una buena razón (negocio en declive), la 'trampa de valor' (value trap). Corresponde al bloque Value de GABI.",
  },
  {
    title: 'Growth investing (inversión en crecimiento)',
    text: 'Comprar empresas con crecimiento de ingresos y beneficios muy por encima de la media, aunque coticen a múltiplos altos, apostando a que ese crecimiento seguirá compensando el precio pagado hoy.',
    notes:
      'A favor: puede generar rentabilidades muy altas si el crecimiento se mantiene. Cuidado: muy sensible a decepciones; si el crecimiento se frena, el múltiplo se contrae rápido y de golpe. Parte del bloque Quality de GABI (crecimiento de ingresos y FCF).',
  },
  {
    title: 'Dividend / income investing',
    text: 'Priorizar empresas que reparten dividendos consistentes y crecientes, buscando ingresos recurrentes además de (o en vez de) la revalorización del precio.',
    notes:
      'A favor: genera caja periódica y suele asociarse a empresas maduras y estables. Cuidado: un dividendo muy alto puede ser una señal de alarma (el mercado espera que lo recorten); mira siempre si es sostenible con el flujo de caja libre, no solo el porcentaje.',
  },
  {
    title: 'Momentum / trend following',
    text: 'Comprar lo que ya está subiendo (y en su versión más técnica, vender lo que está bajando), apostando a que las tendencias tienden a continuar más de lo que la intuición sugiere.',
    notes:
      'A favor: funciona sorprendentemente bien en estudios académicos a 6-12 meses. Cuidado: los giros de tendencia hacen daño (comprar tarde, justo antes de que se acabe la subida). Corresponde al bloque Momentum de GABI; por eso, si estás empezando, quizá quieras darle menos peso que a Value/Quality.',
  },
  {
    title: 'Indexación pasiva (buy & hold)',
    text: 'En vez de elegir empresas, comprar un ETF que replica todo un índice (por ejemplo, el S&P 500 entero) y mantenerlo a muy largo plazo, aportando de forma periódica (dollar-cost averaging).',
    notes:
      'A favor: diversificación máxima, comisiones mínimas, exige poco tiempo y conocimiento, y bate a la mayoría de gestores activos a largo plazo. Cuidado: renuncias a poder batir al mercado; te conformas con la media. Es, con diferencia, la opción con menos curva de aprendizaje: si dudas por dónde empezar, muchos empezarían aquí mientras aprenden el resto.',
  },
  {
    title: 'Análisis fundamental vs. análisis técnico',
    text: 'El fundamental estudia el negocio (cuentas, competitividad, sector) para estimar qué vale una empresa. El técnico estudia el propio gráfico de precio (medias móviles, RSI, patrones) para anticipar hacia dónde va a moverse.',
    notes:
      'GABI combina ambos: Value/Quality son fundamentales, Momentum es técnico. Si estás empezando, prioriza entender el fundamental; el técnico es más fácil de malinterpretar sin experiencia.',
  },
  {
    title: 'Inversión por catalizadores',
    text: 'Comprar de cara a un evento concreto que puede hacer que el mercado revalúe la empresa: resultados, un recorte de tipos, el lanzamiento de un producto, una recompra de acciones... Una empresa puede estar barata durante años si no hay ningún catalizador a la vista.',
    notes:
      "Encaja con el hueco de 'Catalizadores' que puedes rellenar tú mismo al escribir una tesis en el Diario de inversión.",
  },
];

export const PSYCHOLOGY_INTRO =
  'La parte que parece secundaria hasta que hay dinero real en juego. La mayoría de errores de inversores novatos no son de análisis, son de comportamiento. El Diario de inversión existe precisamente para poner freno a varios de estos sesgos: escribir la tesis antes te obliga a pensar con la cabeza fría, sin la presión del momento.';

export const BIASES: { title: string; text: string }[] = [
  {
    title: 'FOMO (miedo a quedarse fuera)',
    text: "Comprar solo porque algo está subiendo mucho y 'todo el mundo habla de ello', sin haber hecho tu propio análisis. Si tu único motivo para comprar es que el precio ya ha subido mucho, no es una tesis, es pánico social con otro nombre.",
  },
  {
    title: 'Sesgo de confirmación',
    text: 'Buscar (y quedarte solo con) la información que confirma lo que ya querías creer, e ignorar la que lo contradice. Antes de comprar, busca activamente el mejor argumento en contra de tu propia tesis.',
  },
  {
    title: 'Anclaje (anchoring)',
    text: "Fijarte en un precio de referencia (el precio al que compraste, un máximo histórico) y juzgar todo en relación a él, aunque ya no sea relevante. 'Está barata porque ha caído un 40 %' no es una tesis si no sabes por qué valía eso antes.",
  },
  {
    title: 'Aversión a la pérdida (loss aversion)',
    text: "El dolor de perder una cantidad de dinero duele psicológicamente más que el placer de ganar la misma cantidad. Lleva a vender ganadoras demasiado pronto (para 'asegurar' la ganancia) y a aguantar perdedoras demasiado tiempo (para no 'materializar' la pérdida), justo al revés de lo que suele convenir.",
  },
  {
    title: 'Efecto disposición',
    text: "La consecuencia práctica del punto anterior: vender lo que sube y quedarte con lo que baja, sistemáticamente. Pregúntate siempre: '¿compraría esta posición hoy, al precio actual, si no la tuviera ya?' Si la respuesta es no, es una señal.",
  },
  {
    title: 'Sesgo de recencia',
    text: 'Dar demasiado peso a lo que ha pasado últimamente y extrapolarlo hacia el futuro («ha subido los últimos 3 meses, seguirá subiendo»). Los ciclos de mercado son más largos que la memoria reciente.',
  },
  {
    title: 'Exceso de confianza',
    text: 'Sobreestimar lo bien que entiendes una inversión o lo buena que es tu capacidad de acertar. Cuantas más operaciones ganadoras seguidas, más fácil es caer en esto, justo cuando conviene más ser prudente.',
  },
  {
    title: 'Falacia de los costes hundidos (sunk cost fallacy)',
    text: 'Seguir invirtiendo tiempo o dinero en algo solo porque ya has invertido mucho, en vez de evaluar la situación desde cero. Lo que ya has perdido no vuelve decidas lo que decidas ahora: la única pregunta relevante es qué hacer de aquí en adelante.',
  },
  {
    title: 'Efecto rebaño (herding)',
    text: 'Seguir lo que hace la mayoría por sentirte más seguro, en vez de por convicción propia. Cuando todo el mundo está de acuerdo en algo, normalmente ya está en el precio.',
  },
];

export const HABITS: { title: string; text: string }[] = [
  {
    title: 'Escribe la tesis antes de comprar, no después.',
    text: 'Precio de entrada, por qué, qué esperas, qué te haría venderla: el Diario de inversión está pensado exactamente para esto.',
  },
  {
    title: 'Define el tamaño de la posición antes de convencerte del todo.',
    text: 'Por muy segura que parezca una idea, puedes estar equivocado: no apuestes una parte desproporcionada de la cartera a una sola convicción.',
  },
  {
    title: 'Revisa tus decisiones pasadas, no solo el resultado.',
    text: 'Una decisión bien tomada puede salir mal, y una mala decisión puede salir bien por suerte. Vuelve a leer tu tesis del Diario pasados unos meses: se aprende más de por qué que de si ganaste o perdiste.',
  },
];

export const PIPELINE_DIAGRAM = `Universo histórico          SEC EDGAR                    Precios
(qué empresas formaban  +   (fundamentales con la    +   (histórico truncado a
 el índice ESE día,          fecha REAL en que se          la fecha del ranking,
 no las de hoy)               presentaron, no la            nunca un precio
                               fecha a la que se             futuro)
                               refieren)
        |                          |                            |
        +--------------------------+----------------------------+
                                    |
                                    v
                    Scoring (Value / Quality / Momentum / Risk)
                                    |
                                    v
                  Ranking tal y como se habría visto ESE día`;

export const LOOK_AHEAD_DIAGRAM = `                      fecha del ranking
                             |
  ──────────────────────────┼───────────────────────────▶ tiempo
  filed_date: 2019-02-01    |      filed_date: 2019-08-15
  (ya se conocía)           |      (todavía NO existía ese día)
        se usa               |             se descarta`;

export const SIGNAL_TO_PORTFOLIO_DIAGRAM = `   MODELO DE SELECCIÓN                      MODELO DE CARTERA
   "¿qué empresas parecen atractivas?"       "¿cuánto dinero pongo en cada una?"

   Composite Score                    -->    decision_engine.Policy
   (Value/Quality/Momentum/Risk)              máx. 10 posiciones, filtro SMA200,
                                               reparto por mínima volatilidad,
                                               límites de posición/sector

   Validado en HIPOTESIS_CONGELADA.md         Estrategia DISTINTA, nunca
   (20 posiciones, equiponderado,             contrastada en un backtest:
    trimestral)                               ver el aviso en Decisiones`;

export const ENGINE_COMPARISON: { row: string; v1: string; v2: string }[] = [
  {
    row: 'Turnover medido',
    v1: '63,0 % (solo nombres, 1 lado)',
    v2: '127,4 % (importe real, 2 lados)',
  },
  { row: 'SPY', v1: 'rotado cada trimestre', v2: 'comprado una vez y mantenido' },
  { row: 'Sharpe estrategia', v1: '0,71', v2: '0,70 (dentro del ruido de muestreo)' },
  { row: 'Margen de Sharpe vs SPY', v1: '0,151', v2: '0,111 (~26 % menor, medido bien)' },
];

export const RESEARCH_TERMS: { title: string; text: string }[] = [
  {
    title: 'Hipótesis congelada',
    text: 'El documento (HIPOTESIS_CONGELADA.md) donde se declaró por escrito, con fecha, antes de tener datos nuevos, la configuración que se cree buena (20 posiciones equiponderadas, pesos Value/Quality/Momentum/Risk 30/35/25/10). Así no se puede ir ajustando la estrategia a posteriori para que «funcione mejor» cada vez que se mira el resultado. Es la única configuración con un backtest histórico real detrás, y es exactamente la que usa Cartera.',
  },
  {
    title: 'Blind Forward Validation (validación ciega)',
    text: 'La forma de comprobar si la hipótesis congelada funciona de verdad, hacia delante, no solo mirando el pasado: cada rebalanceo real queda registrado de forma inmutable, y el resultado frente al SPY se queda oculto hasta una fecha de desbloqueo. La tentación que esto evita: mirar a medias y ajustar la estrategia porque «llevamos unos meses perdiendo»; en cuanto se hace eso, la prueba deja de servir para nada, aunque nadie haga trampa a propósito.',
  },
  {
    title: 'Research Lab',
    text: 'El cuaderno de bitácora de cualquier prueba o experimento que se haga con GABI (qué se probó, con qué datos, en qué fecha y el resultado) para poder distinguir después una idea que se validó de verdad de una que solo «parecía funcionar» la primera vez que se miró.',
  },
  {
    title: 'Factor Lab / Portfolio Lab',
    text: 'Herramientas para investigar, no para decidir hoy: Factor Lab comprueba si el score ordena bien el retorno futuro real (no solo si una cesta concreta ganó); Portfolio Lab compara formas distintas de repartir el capital entre las mismas candidatas. Sirven para poner a prueba ideas antes de que entren (o no) en la hipótesis congelada, no para generar tu cartera del día.',
  },
];

/** The synthetic quarter of the old page: starts at 100, falls 28 % mid-way and ends at 104. */
export function hiddenDrawdown(): { day: number; value: number }[] {
  const days = 63;
  const mid = Math.floor(days / 2);
  return Array.from({ length: days }, (_, i) => ({
    day: i + 1,
    value: i <= mid ? 100 - (28 * i) / mid : 72 + (32 * (i - mid)) / (days - 1 - mid),
  }));
}
