import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import streamlit as st

from gabi import scoring
from gabi.ui_helpers import METRIC_INFO

st.title("🎓 Aprender")
st.caption(
    "Para cuando estás empezando: vocabulario, formas de pensar sobre qué comprar y por qué, y los "
    "errores mentales más comunes al invertir dinero real. No sustituye a un buen libro, pero es un "
    "punto de partida rápido y conectado con el resto de GABI."
)

tab_terminos, tab_estrategias, tab_psicologia = st.tabs(
    ["📖 Términos útiles", "🧭 Estrategias de inversión", "🧠 Psicología de la inversión"]
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
