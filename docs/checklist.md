# Checklist fundamental descriptivo (#167)

La ficha de empresa (`/mercado/empresas/{símbolo}`) muestra la sección
**Checklist fundamental**. Evalúa la empresa frente a los criterios del checklist
del usuario, extraídos de vídeos de análisis fundamental (Javier DV, Memorias de
Tiburón, Pedro Gutiérrez y La Pizarra de Andrés), con veredicto ✔/✘/sin dato,
fórmula, fuente y ejercicio usado. Además muestra las señales de alarma, un DCF
inverso y los criterios cualitativos.

Es **informativo**. No entra en el Composite Score, no filtra ni selecciona en el
ranking ni en backtests, y no modifica `scoring.py` ni los 18 motores congelados.
Usar cualquiera de sus criterios como señal requiere un experimento preregistrado.

## Código

| Capa | Archivo |
| --- | --- |
| Dominio (fórmulas, umbrales, alarmas, DCF) | `backend/src/gabi/domain/market/checklist.py` |
| Caso de uso | `backend/src/gabi/application/market/checklist.py` |
| Umbrales editados | `backend/src/gabi/infrastructure/storage/checklist_thresholds.py` → `data/checklist_thresholds.json` |
| API | `GET /api/v1/companies/{symbol}/checklist`, `GET/POST /api/v1/checklist/thresholds`, `POST /api/v1/checklist/thresholds/reset` |
| Interfaz | `frontend/src/features/market/company-checklist.tsx` |

## Reglas de datos

- **Fuente**: hechos SEC de 10-K/10-K/A ya guardados, con `filed_date ≤ hoy`.
  Las excepciones se declaran por criterio:
  - precio: último cierre de la caché;
  - acciones: ver «Número de acciones» más abajo;
  - PER forward: registro de Yahoo ya descargado;
  - % de directivos: Yahoo `heldPercentInsiders`;
  - beta: la que calcula GABI frente al SPY (`beta_calc` del ranking), ver «Fuente y
    periodo» más abajo.
- **Un solo ejercicio**: todos los componentes de un ratio se leen en el último
  cierre anual de ingresos (o de beneficio), con una tolerancia de 45 días. Si un
  componente es de otro ejercicio, el criterio queda «sin dato» (`stale_*`).
- **Ausencia ≠ cero**: una partida no declarada nunca se rellena con cero.
  - Sin deuda declarada, la deuda neta queda sin dato (`no_debt_reported`).
  - Si faltan componentes a corto plazo (deuda a corto, inversiones a corto), se
    listan en `components_not_reported`.
  - La cobertura de intereses cumple solo si la deuda declarada es 0.
- **Sector financiero** (`Financials`/`Financial Services`): los criterios basados
  en margen bruto, CFO, CAPEX, EBITDA o EV se marcan «no aplica».
- **Consultar no descarga ni escribe**: el GET solo lee. Editar umbrales es un
  POST explícito.

## Cobertura (#170)

- **Hechos por emisor**: el checklist lee los hechos de la entidad SEC del símbolo
  (`SqliteSecReads.issuer_facts`), incluidos los guardados con un ticker anterior o con
  la clave histórica `CIK…`. Leyendo solo por símbolo, algunos emisores (TWLO, SKYD…)
  tenían medio historial.
- **Series anuales**: `annual_series` toma como base la etiqueta candidata publicada más
  recientemente. Así, un cambio de etiqueta no deja vacío el último ejercicio ni ancla el
  checklist en un año antiguo. Las demás etiquetas solo completan años si los años comunes
  coinciden en un 1 %.
- **CAPEX**: `CHECKLIST_CAPEX_TAGS` añade el CAPEX total (`PaymentsToAcquireProductiveAssets`)
  y las inversiones de petróleo y gas. No incluye partidas parciales ni compras de inmuebles
  de las inmobiliarias.
- **Composite sin cambios**: `sec.CAPEX_TAGS`, `sec.REVENUE_TAGS` y `_extract_annual_values`
  no se tocan.
- **Medición**: `python -m gabi_cli market checklist-coverage`, de solo lectura. Los
  resultados antes y después están en [`checklist-coverage/`](checklist-coverage/README.md).
- **Ficha**: el resumen muestra «Evaluables X / N», es decir, criterios con valor sobre los
  que aplican a la empresa.

## Número de acciones

La capitalización, el EV, los múltiplos, el DCF, la variación de acciones y la historia
de múltiplos dependen de la base de acciones. Por eso se elige y se comprueba así
(`share_basis` y `verified_shares` en el dominio):

1. **Acciones en circulación SEC** (`CommonStockSharesOutstanding` o la de portada
   `EntityCommonStockSharesOutstanding`) si no tienen más de 400 días respecto al
   último ejercicio. Se llevan a la base de splits actual con los splits posteriores.
2. **Si no hay o están caducadas**, se usan las **acciones medias diluidas del 10-K**
   (`WeightedAverageNumberOfDilutedSharesOutstanding`). Las empresas con varias
   clases de acciones (META, ABNB, DASH…) declaran las acciones en circulación solo
   por clase, y la API companyfacts no incluye esos hechos desglosados.
3. **Comprobación con Yahoo**: si precio × acciones SEC se aleja más de un 25 % de
   la capitalización de Yahoo, se usa la de Yahoo (`shares_source =
   yahoo_market_cap`) y la ficha lo indica. La variación de acciones y la historia
   de múltiplos quedan sin dato (`share_basis_mismatch`), porque su base SEC no es
   comparable con el precio. Casos reales en la base de 22-10-2026:
   - BRK-B: acciones en equivalentes de clase A;
   - APH y MNST: un split 2:1 que falta en la caché;
   - BX: la SEC solo cuenta la clase A, sin las participaciones de Holdings;
   - SWKS y VMRK: emisión posterior al último 10-Q.
   Sin capitalización de Yahoo, se usan las acciones SEC sin comprobar.

## Fuente y periodo de cada cifra (#169)

La ficha muestra algunos conceptos dos veces: en los bloques de métricas del ranking y en
el checklist. Cada valor declara su fuente y su periodo, y nunca se mezclan dentro de un
mismo ratio.

- **Bloques de la ficha**: `GET /api/v1/companies/{symbol}` devuelve `metric_sources`
  (`gabi/domain/market/metric_sources.py`), con la fuente (`yahoo`, `sec_10k`, `prices`) y
  el periodo (`ttm`, `mrq`, `fiscal_year`, `cached_history`…) de cada métrica. El PER, el
  EV/EBITDA y el FCF de esos bloques son los de Yahoo a 12 meses.
- **Checklist**: cada criterio devuelve `source` y `period`. La ficha los muestra como
  «SEC 10-K · FY2025», «Precio + SEC 10-K · FY2025» o «Yahoo · fecha de captura».
- **Referencia secundaria** (`alternative`): para la capitalización, el PER, el
  EV/EBITDA, el FCF, el ROIC y la beta, el checklist incluye el valor que muestra el resto
  de la ficha, con su fuente, su periodo y el motivo de la diferencia (periodo, fórmula,
  número de acciones o método). Sale de la fila del ranking de la empresa, no de un
  segundo cálculo. Solo se muestra y no cambia el veredicto. Si el checklist no tiene dato,
  la ficha lo indica: «Sin dato SEC; Yahoo · 12 meses informa 3,80x (no se mezcla)».
- **Beta**: la clasificación defensiva (<0,9), neutral (≤1,1) o agresiva usa la beta que
  calcula GABI frente al SPY con rendimientos diarios de todo el histórico en caché, la
  misma que la ficha muestra como «Beta calculada frente al SPY». La de Yahoo (5 años,
  mensual, metodología propia) es solo informativa. Si GABI no tiene beta, el criterio
  queda sin dato y nunca usa la de Yahoo.

## Diferencias con las métricas del Composite

| Concepto | Checklist (vídeos) | Composite / Research |
| --- | --- | --- |
| ROIC | EBIT × (1 − tipo efectivo) / (deuda total + patrimonio − caja e inversiones c/p) | Beneficio neto / (patrimonio + deuda LP) |
| Deuda neta y EV | Deuda LP + deuda a corto − caja − inversiones a corto | Deuda LP − caja |
| Crecimiento | CAGR a 10 años (o 5) de ingresos y CFO | CAGR a 3 años de ingresos y FCF |
| Conversión de caja | CFO / beneficio neto | `fcf_conversion_mean` es FCF / ingresos (margen de FCF, pese al nombre) |
| DCF inverso | 10 años, 9 % de descuento, 3 % a perpetuidad, sobre la capitalización (hoja del Excel) | `reverse_dcf_growth`: 5 años, 2,5 %, sobre el EV (sin cambios) |
| Método | Umbrales absolutos | Percentiles sectoriales ponderados; momentum pesa un 25 % |

En el factor zoo, ningún factor individual sobrevive a la corrección de Holm. Los
umbrales del Checklist son reglas generales que dependen del sector, no señales
validadas.

## Umbrales

- **Valores por defecto**: los del Excel (`RULES` y `DCF_DEFAULTS` en el dominio,
  versión `THRESHOLDS_VERSION = 1`), con el vídeo de origen de cada uno.
- **Edición**: se hace desde «Editar umbrales» en la ficha y solo se guardan los
  valores que difieren de los del Excel. El backend valida el criterio, el rango,
  que sea un número finito, que los años sean enteros y que el crecimiento a
  perpetuidad sea menor que la tasa de descuento.
- **Fichero no válido**: si `checklist_thresholds.json` está corrupto o tiene otra
  versión, se usan los valores del Excel y la respuesta lo avisa
  (`invalid_saved_thresholds`).
- **Alcance**: los umbrales editados solo cambian el ✔/✘ del Checklist. Los
  parámetros de las alarmas son constantes documentadas del dominio.

## Fases de #167

- **F2** (hecho): la sincronización SEC explícita
  (`gabi/application/market/sec_xbrl.py`) guarda `FACT_TAGS`, que son `TRACKED_TAGS`
  más `CHECKLIST_TAGS` (intereses, SBC, impuestos, deuda e inversiones a corto,
  goodwill, deterioros, emisión de deuda, dividendos, coste de ventas, activos).
  - Las métricas siguen calculándose con `TRACKED_TAGS`.
  - En acciones guarda también `DILUTED_SHARES_TAGS`. La huella cubre los dos conjuntos.
  - El checkpoint guarda la huella del conjunto de etiquetas (`fact_tags`). Si
    cambia, la siguiente sincronización vuelve a descargar y procesar companyfacts
    una vez por emisor, aunque no haya cambiado.
  - Los históricos de research (backfill trimestral, bulk) no incorporan estas
    etiquetas.
- **F3** (hecho): el refresco de fundamentales de Yahoo guarda también
  `heldPercentInsiders` (`EXTRA_INFO_KEYS` en `infrastructure/legacy/data_fetch.py`,
  porque `config.INFO_KEYS` está congelado). Aparece tras el siguiente refresco.
- **F4** (hecho): sección «Múltiplos frente a su historia y su sector» de la ficha,
  para PER, EV/EBITDA, EV/EBIT y EV/FCF, con las mismas fórmulas SEC de los criterios.
  - **Mediana propia**: últimos 5 ejercicios. Cada uno usa el cierre de la caché en
    su fecha de cierre fiscal (o el anterior), las acciones SEC más cercanas
    (±120 días) llevadas a la base de splits actual y las cifras de ese ejercicio
    conocidas hoy (reexpresiones incluidas). Hacen falta 3 ejercicios con valor; si
    falta el precio de un año, ese año queda sin dato.
  - **Mediana del sector**: las demás empresas del mismo sector del universo actual
    (`sp500_constituents.csv`, como el ranking). Hacen falta 5 pares con valor. Se
    sirve en `GET /api/v1/companies/{symbol}/checklist/sector`, que la ficha solo
    pide al abrir la sección. Lee solo `MULTIPLE_TAGS` de cada par.
  - **Caché**: el resultado del sector se guarda en memoria del proceso (16
    sectores como máximo), con una clave formada por la fecha y por el último
    filing y el último precio de cada miembro. Una sincronización cambia la clave,
    así que nunca se sirve una mediana desactualizada. No se escribe nada.
  - **Medición** (lectura sobre la base real, 22-10-2026):
    - ficha con historia propia: 130–270 ms;
    - sector (unas 75 empresas): 5–7 s la primera vez, tras la sincronización de la
      F2 y la comprobación con Yahoo, y unos 60 ms desde la caché, compartida por
      todas las empresas del sector.
    - El tiempo restante está en la lectura SQL acotada y en `companyfacts`. Las
      filas trimestrales en USD se descartan antes de reconstruir.
  - **Sector financiero**: los múltiplos sobre EV no aplican.
  - **Lectura**: que un múltiplo quede por debajo de su referencia no significa que
    la empresa esté barata. También puede reflejar peores perspectivas.
