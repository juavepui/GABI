import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import scoring
from gabi.ui_helpers import METRIC_INFO

st.title("🎓 Aprender")
st.caption(
    "Para cuando estás empezando: vocabulario, formas de pensar sobre qué comprar y por qué, los "
    "errores mentales más comunes al invertir dinero real, y — en la última pestaña — cómo funciona "
    "GABI por dentro y qué rigor hay (y no hay) detrás de sus números. No sustituye a un buen libro, "
    "pero es un punto de partida rápido y conectado con el resto de la app."
)

tab_terminos, tab_estrategias, tab_psicologia, tab_gabi = st.tabs(
    ["📖 Términos útiles", "🧭 Estrategias de inversión", "🧠 Psicología de la inversión",
     "🔬 Cómo piensa GABI"]
)

# ----------------------------------------------------------------------------
# TAB 1: Términos útiles
# ----------------------------------------------------------------------------
with tab_terminos:
    st.markdown("Vocabulario básico, agrupado por tema. Empieza por 'Básicos' si vienes de cero.")

    GLOSSARY = {
        "Básicos": {
            "Acción": "Un título que representa una parte de la propiedad de una empresa. Comprar acciones te convierte en copropietario, con derecho a una parte del beneficio (si reparte dividendo) y del valor de la empresa.",
            "Cartera (portfolio)": "El conjunto de todas las inversiones que tienes — acciones, fondos, efectivo... Su comportamiento conjunto importa más que el de cada posición por separado.",
            "Índice bursátil": "Una cesta representativa de acciones (ej. S&P 500 = las 500 mayores empresas de EE.UU.) que se usa como termómetro del mercado y como referencia (benchmark) para saber si lo estás haciendo mejor o peor que 'el mercado'.",
            "ETF": "Un fondo cotizado que replica un índice (u otra cesta de activos) y se compra y vende como una acción. Forma barata y diversificada de invertir en todo un mercado de una vez.",
            "Capitalización bursátil": "Precio de la acción × número de acciones en circulación. El 'tamaño' de la empresa en bolsa. Large cap (grande), mid cap (mediana), small cap (pequeña) — a menor tamaño, normalmente más riesgo y más potencial de crecimiento.",
            "Dividendo": "Parte del beneficio que la empresa reparte a sus accionistas, normalmente en efectivo. No repartir dividendo no es necesariamente malo: puede significar que la empresa prefiere reinvertir el dinero en crecer.",
            "OPV / IPO": "Oferta Pública de Venta (Initial Public Offering): el momento en que una empresa privada empieza a cotizar en bolsa por primera vez.",
        },
        "Valoración (¿está cara o barata?)": {
            "PER": METRIC_INFO["pe"]["help"],
            "EV/EBITDA": METRIC_INFO["ev_ebitda"]["help"],
            "Capitalización vs. valor de empresa (EV)": "La capitalización es solo el valor de las acciones. El Enterprise Value (EV) le suma la deuda y le resta la caja — el precio 'real' que pagarías si compraras la empresa entera, deudas incluidas.",
            "Múltiplo": "Forma coloquial de referirse a ratios como el PER o el EV/EBITDA — 'cotiza a un múltiplo alto' significa que es cara respecto a sus beneficios o su caja.",
            "Margen": "Porcentaje de las ventas que la empresa se queda como beneficio en cada etapa (bruto, operativo, neto). Márgenes altos y estables suelen indicar poder de fijación de precios (pricing power).",
        },
        "Riesgo y volatilidad": {
            "Volatilidad": METRIC_INFO["volatility"]["help"],
            "Drawdown": METRIC_INFO["max_drawdown"]["help"],
            "Diversificación": "Repartir el dinero entre distintas empresas, sectores o países para que un problema puntual en una sola inversión no arruine toda la cartera. Una sola acción, por muy buena que parezca, nunca está diversificada.",
            "Beta": "Cuánto se mueve una acción en relación al mercado. Beta > 1 = más volátil que el mercado; beta < 1 = más defensiva.",
            "Mercado alcista / bajista (bull / bear market)": "Periodos prolongados de subidas (bull) o caídas (bear) generalizadas en el mercado. Suelen definirse informalmente como una caída de más del 20% desde el último máximo para el mercado bajista.",
            "Corrección": "Caída del mercado de en torno al 10% desde un máximo — más habitual y menos grave que un mercado bajista completo.",
            "Liquidez": "Facilidad para comprar o vender un activo rápidamente sin mover mucho su precio. Empresas con poco volumen de negociación son menos líquidas y más arriesgadas de entrar/salir.",
        },
        "Operativa": {
            "Apalancamiento": "Invertir con dinero prestado (o mediante productos derivados) para multiplicar tanto las ganancias como las pérdidas. Herramienta avanzada, no recomendable para quien empieza.",
            "Comisiones": "Lo que cobra el bróker/plataforma por comprar, vender o mantener una posición. Parecen pequeñas pero erosionan la rentabilidad a largo plazo, sobre todo si operas mucho.",
            "Fiscalidad (ganancias/pérdidas patrimoniales)": "Vender con beneficio genera una ganancia sujeta a impuestos (varía por país). Las pérdidas normalmente se pueden compensar con ganancias futuras — infórmate de las reglas de tu país antes de operar mucho.",
            "Dollar-cost averaging (DCA)": "Invertir una cantidad fija de forma periódica (ej. cada mes) en vez de todo de golpe. Suaviza el efecto de comprar justo en un mal momento, a cambio de renunciar a intentar acertar el mejor momento.",
            "Rebalanceo": "Ajustar periódicamente la cartera para que vuelva a los porcentajes objetivo que te marcaste (ej. si una posición ha crecido mucho y ahora pesa más de la cuenta, vender un poco).",
        },
    }

    for category, terms in GLOSSARY.items():
        st.subheader(category)
        for term, definition in terms.items():
            with st.expander(term):
                st.write(definition)

    st.divider()
    st.subheader("📎 Métricas que usa GABI")
    st.caption(
        "Repaso rápido de las métricas que verás en Screener/Ficha/Comparar — con más detalle en el "
        "tooltip de cada columna, donde aparecen."
    )
    METRIC_BLOCKS = {
        "Value": scoring.VALUE_METRICS_LOWER_BETTER,
        "Quality": scoring.QUALITY_METRICS_HIGHER_BETTER,
        "Momentum": scoring.MOMENTUM_METRICS_HIGHER_BETTER,
        "Risk": scoring.RISK_METRICS_LOWER_BETTER + scoring.RISK_METRICS_HIGHER_BETTER,
    }
    metric_tabs = st.tabs(list(METRIC_BLOCKS.keys()))
    for tab, (block_name, metric_keys) in zip(metric_tabs, METRIC_BLOCKS.items()):
        with tab:
            for key in metric_keys:
                info = METRIC_INFO.get(key)
                if info:
                    st.markdown(f"**{info['label']}** — {info['help']}")

# ----------------------------------------------------------------------------
# TAB 2: Estrategias de inversión
# ----------------------------------------------------------------------------
with tab_estrategias:
    st.markdown(
        "No existe 'la' estrategia correcta — existen distintas formas de pensar sobre qué comprar, "
        "con distintos riesgos, horizontes y exigencias de tiempo. GABI combina varias de estas ideas "
        "en un único score (Value/Quality/Momentum/Risk); ajustando los pesos en ⚙️ Configuración te "
        "acercas más a una u otra."
    )

    STRATEGIES = [
        (
            "Value investing (inversión en valor)",
            "Comprar empresas que cotizan por debajo de lo que 'valen' según sus fundamentales (PER, "
            "EV/EBITDA bajos frente a su sector), apostando a que el mercado corregirá esa infravaloración "
            "con el tiempo. Escuela clásica de Benjamin Graham y Warren Buffett.",
            "✅ Suele implicar menos riesgo de pagar de más; históricamente ha batido al mercado a muy "
            "largo plazo. ⚠️ Una empresa puede estar barata por una buena razón (negocio en declive) — "
            "la 'trampa de valor' (value trap). Corresponde al bloque **Value** de GABI.",
        ),
        (
            "Growth investing (inversión en crecimiento)",
            "Comprar empresas con crecimiento de ingresos y beneficios muy por encima de la media, "
            "aunque coticen a múltiplos altos, apostando a que ese crecimiento seguirá compensando el "
            "precio pagado hoy.",
            "✅ Puede generar rentabilidades muy altas si el crecimiento se mantiene. ⚠️ Muy sensible a "
            "decepciones: si el crecimiento se frena, el múltiplo se contrae rápido y de golpe. Parte del "
            "bloque **Quality** de GABI (crecimiento de ingresos/FCF).",
        ),
        (
            "Dividend / income investing",
            "Priorizar empresas que reparten dividendos consistentes y crecientes, buscando ingresos "
            "recurrentes además de (o en vez de) la revalorización del precio.",
            "✅ Genera caja periódica, suele asociarse a empresas maduras y estables. ⚠️ Un dividendo muy "
            "alto puede ser una señal de alarma (el mercado espera que lo recorten) — mira siempre si es "
            "sostenible con el flujo de caja libre, no solo el porcentaje.",
        ),
        (
            "Momentum / trend following",
            "Comprar lo que ya está subiendo (y en su versión más técnica, vender lo que está bajando), "
            "apostando a que las tendencias tienden a continuar más de lo que la intuición sugiere.",
            "✅ Funciona sorprendentemente bien en estudios académicos a 6-12 meses. ⚠️ Los giros de "
            "tendencia hacen daño (comprar tarde, justo antes de que se acabe la subida). Corresponde al "
            "bloque **Momentum** de GABI — por eso, si estás empezando, quizá quieras darle menos peso "
            "que a Value/Quality.",
        ),
        (
            "Indexación pasiva (buy & hold)",
            "En vez de elegir empresas, comprar un ETF que replica todo un índice (ej. el S&P 500 entero) "
            "y mantenerlo a muy largo plazo, aportando de forma periódica (dollar-cost averaging).",
            "✅ Diversificación máxima, comisiones mínimas, exige poco tiempo y conocimiento, y bate a la "
            "mayoría de gestores activos a largo plazo. ⚠️ Renuncias a poder batir al mercado — te "
            "conformas con la media. Es, con diferencia, la opción con menos curva de aprendizaje: si "
            "dudas por dónde empezar, muchos empezarían aquí mientras aprenden el resto.",
        ),
        (
            "Análisis fundamental vs. análisis técnico",
            "El fundamental estudia el negocio (cuentas, competitividad, sector) para estimar qué vale una "
            "empresa. El técnico estudia el propio gráfico de precio (medias móviles, RSI, patrones) para "
            "anticipar hacia dónde va a moverse.",
            "GABI combina ambos: Value/Quality son fundamentales, Momentum es técnico. Si estás "
            "empezando, prioriza entender el fundamental — el técnico es más fácil de malinterpretar sin "
            "experiencia.",
        ),
        (
            "Inversión por catalizadores",
            "Comprar de cara a un evento concreto que puede hacer que el mercado revalúe la empresa: "
            "resultados, un recorte de tipos, el lanzamiento de un producto, una recompra de acciones... "
            "Una empresa puede estar barata durante años si no hay ningún catalizador a la vista.",
            "Encaja con el hueco de 'Catalizadores' que puedes rellenar tú mismo al escribir una tesis en "
            "el 📓 Diario de inversión.",
        ),
    ]

    for title, description, notes in STRATEGIES:
        with st.expander(title):
            st.write(description)
            st.caption(notes)

# ----------------------------------------------------------------------------
# TAB 3: Psicología de la inversión
# ----------------------------------------------------------------------------
with tab_psicologia:
    st.markdown(
        "La parte que parece secundaria hasta que hay dinero real en juego. La mayoría de errores de "
        "inversores novatos no son de análisis — son de comportamiento. El 📓 **Diario de inversión** "
        "existe precisamente para poner freno a varios de estos sesgos: escribir la tesis *antes* te "
        "obliga a pensar con la cabeza fría, sin la presión del momento."
    )

    BIASES = [
        (
            "FOMO (miedo a quedarse fuera)",
            "Comprar solo porque algo está subiendo mucho y 'todo el mundo habla de ello', sin haber "
            "hecho tu propio análisis. Si tu único motivo para comprar es que el precio ya ha subido "
            "mucho, no es una tesis, es pánico social con otro nombre.",
        ),
        (
            "Sesgo de confirmación",
            "Buscar (y quedarte solo con) la información que confirma lo que ya querías creer, e ignorar "
            "la que lo contradice. Antes de comprar, busca activamente el mejor argumento en contra de tu "
            "propia tesis.",
        ),
        (
            "Anclaje (anchoring)",
            "Fijarte en un precio de referencia (el precio al que compraste, un máximo histórico) y "
            "juzgar todo en relación a él, aunque ya no sea relevante. 'Está barata porque ha caído un "
            "40%' no es una tesis si no sabes por qué valía eso antes.",
        ),
        (
            "Aversión a la pérdida (loss aversion)",
            "El dolor de perder una cantidad de dinero duele psicológicamente más que el placer de ganar "
            "la misma cantidad. Lleva a vender ganadoras demasiado pronto (para 'asegurar' la ganancia) y "
            "a aguantar perdedoras demasiado tiempo (para no 'materializar' la pérdida) — justo al revés "
            "de lo que suele convenir.",
        ),
        (
            "Efecto disposición",
            "La consecuencia práctica del punto anterior: vender lo que sube y quedarte con lo que baja, "
            "sistemáticamente. Pregúntate siempre: '¿compraría esta posición hoy, al precio actual, si no "
            "la tuviera ya?' Si la respuesta es no, es una señal.",
        ),
        (
            "Sesgo de recencia",
            "Dar demasiado peso a lo que ha pasado últimamente y extrapolarlo hacia el futuro (\"ha subido "
            "los últimos 3 meses, seguirá subiendo\"). Los ciclos de mercado son más largos que la memoria "
            "reciente.",
        ),
        (
            "Exceso de confianza",
            "Sobreestimar lo bien que entiendes una inversión o lo buena que es tu capacidad de acertar. "
            "Cuantas más operaciones ganadoras seguidas, más fácil es caer en esto — justo cuando conviene "
            "más ser prudente.",
        ),
        (
            "Falacia de los costes hundidos (sunk cost fallacy)",
            "Seguir invirtiendo tiempo o dinero en algo solo porque ya has invertido mucho, en vez de "
            "evaluar la situación desde cero. Lo que ya has perdido no vuelve decidas lo que decidas ahora "
            "— la única pregunta relevante es qué hacer de aquí en adelante.",
        ),
        (
            "Efecto rebaño (herding)",
            "Seguir lo que hace la mayoría por sentirte más seguro, en vez de por convicción propia. "
            "Cuando todo el mundo está de acuerdo en algo, normalmente ya está en el precio.",
        ),
    ]

    for title, description in BIASES:
        with st.expander(title):
            st.write(description)

    st.divider()
    st.subheader("🛡️ Tres hábitos prácticos")
    st.markdown(
        """
1. **Escribe la tesis antes de comprar, no después.** Precio de entrada, por qué, qué esperas, qué te
   haría venderla — el 📓 Diario de inversión está pensado exactamente para esto.
2. **Define el tamaño de la posición antes de convencerte del todo.** Por muy segura que parezca una
   idea, puedes estar equivocado — no apuestes una parte desproporcionada de la cartera a una sola
   convicción.
3. **Revisa tus decisiones pasadas, no solo el resultado.** Una decisión bien tomada puede salir mal, y
   una mala decisión puede salir bien por suerte. Vuelve a leer tu tesis del Diario pasados unos meses:
   se aprende más de por qué que de si ganaste o perdiste.
        """
    )

# ----------------------------------------------------------------------------
# TAB 4: Cómo piensa GABI (mecánica interna, rigor y sus límites)
# ----------------------------------------------------------------------------
with tab_gabi:
    st.markdown(
        "Todo lo de aquí describe **decisiones de diseño reales de GABI**, no teoría general — con las "
        "cifras reales que se midieron al construirlas. El detalle técnico completo vive en "
        "`README.md` y `HIPOTESIS_CONGELADA.md`; esto es la versión explicada para entenderlo sin leer "
        "código."
    )

    st.subheader("1. El pipeline point-in-time: nunca mirar al futuro")
    st.markdown(
        "Un ranking 'tal y como se habría visto' una fecha pasada solo es honesto si **cada pieza** de "
        "información usa exclusivamente lo que se conocía ese día — universo, fundamentales y precio:"
    )
    st.code(
        """\
Universo histórico          SEC EDGAR                    Precios
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
                  Ranking tal y como se habría visto ESE día""",
        language=None,
    )
    st.caption(
        "Cada flecha de este diagrama es una decisión de diseño concreta en el código: "
        "`universe.get_sp500_constituents_asof`, `edgar.get_value_as_of` (filtra por `filed_date`), "
        "y el histórico de precios truncado en `screener_asof.py`."
    )

    st.divider()
    st.subheader("2. Tres sesgos que GABI evita — con el fallo real que se encontró en cada uno")
    with st.expander("📉 Sesgo de supervivencia"):
        st.write(
            "Si el ranking de 2016 usara la lista ACTUAL del S&P 500, todas las empresas que quebraron o "
            "fueron excluidas desde entonces (ej. la que sea que era el 'perdedor' de su sector) "
            "desaparecerían del universo — el backtest solo vería a las que sobrevivieron, y parecería "
            "mucho mejor de lo que habría sido en la realidad."
        )
        st.caption(
            "Arreglado con un histórico de composición del índice día a día. Hallazgo real al intentar "
            "usarlo a fondo: ~16% de los símbolos necesarios para cubrir 2016-2025 no resuelven CIK en "
            "SEC EDGAR (empresas deslistadas antes de 2022) — un límite estructural de la fuente gratuita, "
            "documentado, no oculto."
        )
    with st.expander("🔮 Look-ahead bias (mirar datos del futuro sin darse cuenta)"):
        st.code(
            """\
                      fecha del ranking
                             |
  ──────────────────────────┼───────────────────────────▶ tiempo
  filed_date: 2019-02-01    |      filed_date: 2019-08-15
  (ya se conocía)           |      (todavía NO existía ese día)
        ✅ se usa            |             ❌ se descarta""",
            language=None,
        )
        st.write(
            "Cada dato de SEC EDGAR lleva su propia fecha real de presentación (`filed_date`) — un "
            "resultado trimestral no 'existe' para el mercado hasta que la empresa lo publica, aunque se "
            "refiera a un trimestre ya cerrado. Usar la última cifra disponible HOY para rankear una "
            "fecha pasada sería tan irreal como invertir con información privilegiada del futuro."
        )
    with st.expander("🔁 Reciclaje de ticker"):
        st.write(
            "Cuando una empresa quiebra o se excluye del índice, la bolsa puede reasignar su símbolo a "
            "una empresa completamente distinta años después. Caso real comprobado: **BBBY** devuelve "
            "cotización viva en yfinance hoy, pero Bed Bath & Beyond quebró y fue excluida en 2023 — el "
            "precio 'vivo' bajo ese ticker pertenece a otra cosa."
        )
        st.caption(
            "GABI descarta un símbolo si lleva más de 450 días sin ningún filing SEC — señal de que ya no "
            "es una 'reporting company' viva, comprobando la fecha del filing en el momento exacto del "
            "backtest, no la más reciente conocida hoy (que podría ser de la empresa nueva)."
        )

    st.divider()
    st.subheader("3. ¿Cuánto te puedes fiar de un resultado de backtest?")
    st.markdown(
        "Con pocos años de historia, un Sharpe algo más alto puede ser pura casualidad de muestreo, no "
        "una estrategia mejor. Con ~9 años de datos, el error típico de estimación de un Sharpe ronda "
        "**±0,35-0,39** — así que una diferencia de 0,1-0,15 entre dos variantes **no demuestra nada**, "
        "aunque en una tabla parezca una la clara ganadora."
    )
    st.caption(
        "Comprobado con datos reales esta sesión: el Sharpe trimestral (0,71) parecía mejor que el anual "
        "(0,61), pero la diferencia (0,10) es una fracción de un error estándar — la conclusión honesta es "
        "que la frecuencia de rebalanceo casi no importa, no que el trimestral gane."
    )
    st.markdown(
        "Otro problema, más visual: medir el riesgo solo en las fechas de rebalanceo esconde lo que pasa "
        "**entre medias**. Aquí tienes una caída real (sintética, para ilustrar) dentro de un solo "
        "trimestre — empieza en 100 y termina en 104, así que si solo miras el punto de inicio y el de "
        "fin, esa caída del 28% es completamente invisible:"
    )
    _demo_dates = pd.date_range("2020-01-01", periods=63, freq="B")
    _mid = len(_demo_dates) // 2
    _demo_prices = []
    for i in range(len(_demo_dates)):
        if i <= _mid:
            _demo_prices.append(100 - 28 * i / _mid)
        else:
            frac = (i - _mid) / (len(_demo_dates) - 1 - _mid)
            _demo_prices.append(72 + 32 * frac)
    st.line_chart(pd.Series(_demo_prices, index=_demo_dates, name="Capital (ejemplo sintético)"))
    st.caption(
        "Capital al inicio y al final del trimestre: idéntico patrón de 'sin caída' que verías si solo "
        "midieras en fechas de rebalanceo. La caída real del -28% a mitad de camino solo aparece con una "
        "curva de capital DIARIA — exactamente lo que corrige el motor V2 (ver más abajo)."
    )

    st.divider()
    st.subheader("4. Score vs Confidence: un número alto no siempre significa lo mismo")
    st.markdown(
        "**Score** = cuán atractiva parece la empresa. **Confidence** = cuánto te puedes fiar de ese "
        "score. Son cosas distintas: si a una empresa solo le falta un dato de Quality y el que tiene es "
        "excelente, puede sacar el mismo Quality Score que otra con los 4 datos completos — Confidence es "
        "lo que te avisa de la diferencia."
    )
    st.caption(
        "Ejemplo real (S&P 500, 2024-01-02): AAPL confidence=100 (13/13 métricas disponibles), "
        "XOM confidence=32 (mucho dato ausente) — mira siempre los dos números juntos en 📊 Screener o "
        "🔎 Ficha de Empresa, no solo el Composite."
    )

    st.divider()
    st.subheader("5. De la señal a la cartera: son dos decisiones distintas")
    st.code(
        """\
   MODELO DE SELECCIÓN                      MODELO DE CARTERA
   "¿qué empresas parecen atractivas?"       "¿cuánto dinero pongo en cada una?"

   Composite Score                    -->    decision_engine.Policy
   (Value/Quality/Momentum/Risk)              máx. 10 posiciones, filtro SMA200,
                                               reparto por mínima volatilidad,
                                               límites de posición/sector

   Validado en HIPOTESIS_CONGELADA.md         Estrategia DISTINTA, nunca
   (20 posiciones, equiponderado,             contrastada en un backtest --
    trimestral)                               ver el aviso en 🧭 Decisiones""",
        language=None,
    )
    st.markdown(
        "Es perfectamente legítimo construir una cartera con reglas propias (límite por empresa, filtro "
        "de tendencia, optimización de riesgo) — el problema sería presentarla como si heredara la "
        "validación del backtest, cuando en realidad comparte solo el punto de partida (el score)."
    )

    st.divider()
    st.subheader("6. V1 vs V2 del backtest: contabilidad real de cartera")
    st.markdown(
        "El motor original (V1) simula el retorno como un porcentaje agregado: cobra el mismo coste "
        "sobre el 100% de cada posición cada rebalanceo, se mantenga o no, y rota el SPY como si fuera "
        "parte de la estrategia. El motor V2 (pestaña **Motor V2** en 🕰️ Ranking histórico) lleva "
        "contabilidad real de acciones + caja: solo paga comisión sobre lo que de verdad se compra o "
        "vende, y el SPY se compra una vez y se mantiene, como haría un inversor pasivo real."
    )
    st.dataframe(
        pd.DataFrame([
            {"": "Turnover medido", "V1": "63,0% (solo nombres, 1 lado)", "V2": "127,4% (importe real, 2 lados)"},
            {"": "SPY", "V1": "rotado cada trimestre", "V2": "comprado una vez y mantenido"},
            {"": "Sharpe estrategia", "V1": "0,71", "V2": "0,70 (dentro del ruido de muestreo)"},
            {"": "Margen de Sharpe vs SPY", "V1": "0,151", "V2": "0,111 (~26% menor, medido bien)"},
        ]),
        hide_index=True, width="stretch",
    )
    st.caption(
        "La lectura honesta no es 'V2 rinde más' — es que V1 sobreestimaba el margen real frente al SPY "
        "en aproximadamente un 26%. V2 no cambia la estrategia, cambia cuánto te puedes fiar del número."
    )

    st.divider()
    st.subheader("7. Costes reales del bróker: fijo vs proporcional, depositar vs operar")
    st.markdown(
        "Un bróker como eToro cobra un importe **fijo** por operación (no un %), así que pesa mucho más "
        "en una posición pequeña que en una grande — 1$ es un 0,18% de una posición de 550$ pero solo un "
        "0,01% de una de 10.000$. Y hay dos costes que NO son lo mismo: **depositar** dinero nuevo desde "
        "el banco (conversión de divisa, una vez por aportación) y **operar** dentro de la cuenta "
        "(abrir/cerrar una posición, en cada rebalanceo). Un backtest simula mover dinero entre empresas, "
        "no traerlo del banco — por eso solo modela el segundo."
    )
    st.caption(
        "La calculadora de 🕰️ Ranking histórico (pestaña Motor V1) convierte tu capital y nº de "
        "posiciones al coste real por lado — pruébala con tus propios números."
    )
