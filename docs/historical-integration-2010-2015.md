# Ranking histórico y Backtest V2 desde 2010: issue #32

Integración de la capa histórica acreditada en #26–#28 con el flujo real de
**Ranking histórico** y **Backtest V1/V2**, sin crear un segundo motor ni
cambiar pesos, fórmulas o umbrales del Composite.

## Qué había antes

Se revisaron `screener_asof.py`, `universe.py`, `identity.py`,
`portfolio_backtest.py` (V2), `multifactor_backtest.py` (V1), la página
🕰️ Ranking histórico y sus tests. El motor **no tenía un corte duro en 2016**;
solo la interfaz recomendaba empezar en 2016-07. Pero antes de 2016 fallaba
en tres puntos:

1. **Identidad**: `identity.resolve` solo consultaba alias operativos
   (`entity_aliases`, dos filas). La identidad acreditada del #27 no estaba
   conectada, así que casi todo quedaba «sin resolver».
2. **Precios**: con `strict_identity=False` (valor por defecto), una empresa sin
   alias leía la **caché por ticker**, justo lo que el #28 prohíbe (tickers
   reciclados, series previas a una OPV, bases de ajuste distintas).
3. **Universo**: usaba la composición operativa (hanshof), mientras que
   identidad y precios se acreditaron sobre las etiquetas de la composición de
   referencia fja05680 (con la corrección WLP/ANTM).

Además, las series acreditadas solo cubrían la ventana de 12 meses **anterior**
a cada rebalanceo; el backtest necesita también los precios del **periodo de
tenencia** hasta el siguiente, y para una empresa que sale del índice ese
tramo nunca se había auditado.

## Qué se ha cambiado

- **`historical_pit.py`** (adaptador, sin motor nuevo). Para fechas en
  `[2010-01-01, 2016-01-01)`:
  - universo: composición de referencia con su corrección fechada;
  - identidad: solo niveles acreditados por intervalo
    (`confirmed_by_multiple_evidence`, `confirmed_historical_ticker`,
    `corroborated_candidate`); una prueba SEC de un único día no basta y nunca
    se crea un alias operativo;
  - precios: solo intervalos de `historical_price_provenance`, una fuente por
    lectura, sin concatenar ni rellenar sesiones;
  - salida de posiciones: evento terminal confirmado (efectivo o sucesión 1:1
    acreditada por el 8-K12B) o, si no lo hay, último precio **marcado como no
    estricto**.
- **Enganches mínimos** en el motor existente, todos condicionados a
  2010–2015: `universe.get_sp500_constituents_asof`, `identity.resolve`,
  `identity.price_history`, `identity.backtest_prices` y
  `screener_asof.build_ranking_as_of` (sin caché por ticker en ese periodo,
  cierre negociado de la serie acreditada para los múltiplos y un resumen
  `historical_coverage` con motivos de exclusión).
- **Periodo de tenencia verificado** (`historical_price_audit.forward_coverage`):
  cada ventana acreditada se extiende, con la misma fuente, hasta el primer día
  de sesión posterior al siguiente rebalanceo, si hay todas las sesiones, no
  hay baja ni sucesión SEC por medio ni un ajuste inexplicado, y la etiqueta
  no pasa a otro CIK. Si la empresa deja de cotizar, termina en su último día
  y se aplica su evento terminal.
- **Coherencia con la auditoría**: una serie solo entra en el ranking si la
  ventana de la **última fecha auditada** (fin de trimestre) igual o anterior
  al ranking fue acreditada y el ranking cae dentro de su periodo de tenencia
  verificado. Una ventana rechazada nunca se sustituye por otra más antigua y
  nunca se usa una acreditación posterior. (Regla afinada en el #33: la
  primera versión permitía, entre fechas auditadas, recurrir a una ventana
  anterior aunque la última hubiera sido rechazada.)
- **Backtest V2/V1**: una posición cuya serie termina dentro del periodo se
  liquida en caja a su valor de salida; el resultado expone `exit_events` y
  `strict_result`. Los periodos sin cobertura suficiente se saltan con su
  motivo, como antes.
- **Fundamentales**: se descargaron los *companyfacts* de los 19 CIK
  antecesores corregidos en el #28 (XOM 34088, DIS, APA, CI, FTI, MDT, MYL,
  GOOGL, BLK, CLF, ICE, JCI…), atribuidos solo por CIK
  (`sec_history.ingest_issuer_companyfacts`, símbolo marcador `CIK##########`).
- **Interfaz**: el Ranking histórico muestra la cobertura acreditada de la
  fecha y las exclusiones; el V2 lista las posiciones liquidadas y avisa si el
  resultado no es estricto. Las ayudas ya no recomiendan empezar en 2016.

## Resultados

> Las cifras del Backtest V2 de esta sección se obtuvieron con la primera
> versión de la regla de coherencia y con rebalanceos que derivan al día 30.
> La validación definitiva, con la regla afinada y la configuración de la
> auditoría 2016+, está en [historical-validation-2010-2015](historical-validation-2010-2015/README.md) (#33).

Tras la integración se regeneró la auditoría del #28 con el periodo de
tenencia verificado: cobertura acreditada **78,2–90,5 % por rebalanceo (media
86,8 %)**, 399 intervalos Tier A y 206 Tier B. La tenencia hasta el siguiente
rebalanceo queda verificada en 10.119 ventanas utilizables; el resto termina
en huecos (129, todos FINSABER en el último trimestre, porque ese archivo
acaba el 31-12-2015), límites de identidad (78), ajustes inexplicados (27),
sucesiones (11) o bajas con evento terminal (9). Se registraron 3 sucesiones
1:1 confirmadas por el 8-K12B del sucesor (ICE → ICE Group, Google →
Alphabet en GOOG y GOOGL) y una sin texto acreditativo.

**Ranking histórico** con el universo completo (sin cambiar pesos ni fórmulas):

| Fecha | Miembros | Identidad acreditada | Precio acreditado | Con score | Cobertura de métricas ≥ 70 % |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2010-06-30 | 499 | 485 | 443 | 232 | 79 |
| 2012-12-31 | 497 | 491 | 459 | 421 | 363 |
| 2015-06-30 | 499 | 493 | 457 | 434 | 389 |

Fuentes de precio en 2012-12-31: caché Yahoo 340, FINSABER 83, WIKI 21,
Tiingo 15.

**Backtest V2**, modo validación (universo completo, 20 posiciones,
trimestral, parámetros por defecto: cobertura de métricas ≥ 70 % en al menos
la mitad del universo), 2010-03-31 → 2016-03-31, 49 minutos:

- Se ejecutan **19 rebalanceos** (2011-06-30 → 2015-12-30). Los **5 primeros
  (2010-03 a 2011-03) se saltan** con el motivo explícito «cobertura
  insuficiente del universo» (75–237 de ~498): no es un problema de precios,
  sino de fundamentales. Varias métricas de calidad exigen tres ejercicios
  anuales y el XBRL de SEC empieza en 2009, así que en 2010 casi ninguna
  empresa llega al 70 % de métricas. No se ha rebajado ese umbral.
- Dos posiciones terminaron sin evento terminal confirmado y se valoraron a su
  último precio, marcadas como no estrictas (`strict_result=False`): NVLS
  (canje por 1,125 acciones de Lam Research, que requiere el precio atribuido
  del sucesor) y AVGO (sucesión a Broadcom Ltd en 2016, fuera del periodo con
  identidad acreditada).
- Métricas diarias como **comprobación de funcionamiento**, no como evidencia
  de rendimiento: la interpretación, el benchmark del universo cubierto y las
  correcciones de sesgo corresponden al #33.

| 2011-06 → 2016-03 | Anualizado | Volatilidad | Sharpe | Sortino | Máx. drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| GABI V2 (Top 20) | 13,8 % | 15,9 % | 0,62 | 0,87 | −21,0 % |
| SPY | 12,1 % | 16,0 % | 0,50 | 0,71 | −18,6 % |

Rotación media 65,4 % por rebalanceo; costes totales 1.356 USD sobre
100.000 USD iniciales.

## Tests

Sin red, sobre bases temporales (`tests/test_historical_pit.py`,
`tests/test_historical_price_audit.py`):

- fecha 2012 con un constituyente que ya no está en el índice actual;
- identidad antes y después de un cambio de ticker (mismo CIK, sin alias);
- un filing presentado después de la fecha del ranking no es visible;
- empresas que entran y salen del índice según la composición fechada;
- periodo con cobertura insuficiente rechazado explícitamente por el V2;
- 2010–2015 nunca lee la caché por ticker; nombres sin serie acreditada quedan
  fuera y se cuentan;
- liquidación de una posición por evento terminal confirmado, sucesión 1:1 y
  último precio no estricto;
- periodo de tenencia: cubierto, baja, hueco y límite de identidad;
- regla de coherencia entre ranking y ventanas auditadas;
- regresión 2016+: los rankings de 2016-06-30 y 2018-06-29 son idénticos (mismo
  hash) con el código anterior y el nuevo, y toda la suite previa pasa.

## Restricciones heredadas (#28 → #32/#33)

Se cumplen los puntos de integración: solo precios acreditados, exclusiones y
eventos visibles por fecha, sin reoptimizar. Quedan para el #33 (validación)
el benchmark del mismo universo cubierto, el retorno implícito de los
excluidos, el análisis de sensibilidad y marcar como no concluyentes los
rebalanceos con cobertura inferior al 85 %.

## Reproducir

```powershell
.venv/Scripts/python.exe -m gabi.historical_price_audit --quarterly --terminal-events --promote
.venv/Scripts/python.exe -m pytest tests/test_historical_pit.py tests/test_historical_price_audit.py -q
```

El Ranking histórico y el Backtest V2 se ejecutan desde 🕰️ Ranking histórico
eligiendo fechas desde 2010, o con
`portfolio_backtest.run("2010-03-31", "2016-03-31", months=3, top_n=20, mode="validation")`.
