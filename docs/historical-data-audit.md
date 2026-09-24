# Issue #25: inventario de datos históricos de GABI

Auditoría local realizada el 24 de septiembre de 2026. Se leyó `data/gabi.db`
sin modificarlo y se usaron las cachés de composición ya existentes. No se
descargó ningún dataset. El código de `main` (`7c9e1f7`) ya incluía composición
histórica, precios, SEC XBRL, identidad por emisor, migración, ranking por fecha y
controles de calidad. `develop` (`907f497`) había añadido además una auditoría
numérica trimestral de 1996–2015. Este inventario integra ambos tramos; no crea
tablas ni sustituye módulos de ingesta o cálculo.
`data_quality.score_block_coverage` ya resume los cuatro bloques de un ranking
calculado, pero no guarda una serie anual de cobertura. Aquí se cuentan los
mismos 13 nombres de `scoring.SCORE_METRICS` en cortes fechados.

Inspección previa al nuevo comando: `README.md`, los informes de `docs/` sobre
identidad, refresco, backfill, validación 1996–2015 y universo completo; los
esquemas y migraciones de `storage.py`, `edgar.py`, `identity.py`,
`entity_master.py`, `entity_migration.py`, `historical_archive.py` y
`sec_history.py`; `universe.py`, `membership_extension.py`, `data_fetch.py`,
`historical_coverage.py`, `screener_asof.py`, `multifactor_backtest.py`,
`portfolio_backtest.py` y `data_quality.py`, más sus tests de migración,
identidad, precios, ranking y cobertura. La comparación `origin/main..develop`
se hizo antes de escribir el script para no confundir funciones recién añadidas
en `develop` con ausencias de `main`.

## Cómo leer la cobertura

Cada fila del [CSV anual](historical-data-audit.csv) usa los miembros enumerados
en la última foto disponible del año. Para 2008–2015 se usa la fuente archivada
`fja05680`; para 2016–2026, la caché operativa comunitaria con la extensión
revisada hasta el 23-09-2026. En 2026 el corte es **22-09-2026**, última fecha
con cierre ajustado de SPY; es un año parcial. Los denominadores incluyen las
clases de acción que enumera cada fuente y pueden diferir de 500.

Los porcentajes de métricas indican que la fórmula devuelve un número finito
con la caché actual. **No** acreditan que la empresa detrás del ticker sea la
correcta, que el sector sea histórico ni que se pudiera haber comprado al precio
mostrado. En 2008–2015 se reutiliza el archivo por empresa y trimestre generado
por `gabi.historical_coverage`; usa hechos atribuidos a CIK pero un mapeo
ticker→CIK candidato. En 2016–2026 se reutiliza `metric_row` y las fórmulas
actuales con `edgar_facts` por ticker, recortado por `filed_date` y `end_date`, y
precios hasta la fecha evaluada. El filtro de publicación es temporalmente
correcto; la atribución histórica del ticker sigue siendo **aproximada**.

`P` significa una fecha o cifra publicada que podía conocerse entonces; `A`
significa una reconstrucción retrospectiva o identidad aproximada; `Ø` significa
que falta la serie necesaria o su acreditación. Estas etiquetas se aplican al
**bloque completo**: una cifra SEC con fecha `filed_date` real puede seguir en
estado `A` si se une a un ticker histórico sin alias acreditado. Los cierres
ajustados de Yahoo incorporan ajustes posteriores y sirven para reconstruir
retornos; su nivel no era el que figuraba en pantalla en el pasado.

## Inventario por fuente y persistencia

| Bloque | Primera y última fecha observada | Fuente y almacenamiento | Estado y límite principal |
| --- | --- | --- | --- |
| Composición S&P 500 | Desde 1996-01-02; archivo fja hasta 2015-12-31 y caché operativa revisada hasta 2026-09-23 | `historical_membership`, `data/sp500_historical_membership.csv`; `historical_archive.py`, `universe.py`, `membership_extension.py` | A: series comunitarias con cambios fechados; el tramo reciente tiene un ledger revisado. Los primeros años pueden omitir miembros y los nombres pueden estar normalizados a posteriori. |
| Identidad de emisor y alias | 822 CIK en `entities`; **0 filas** en `entity_aliases` al auditar | `entities`, `entity_aliases`, `entity_observations`, `entity_candidates`; `identity.py`, `entity_migration.py` | Ø para relación ticker→CIK con vigencia en esta base. `historical_issuer_candidates` contiene pistas, no alias acreditados. Los cuatro alias revisados codificados en la migración no están aplicados a esta base. |
| Precios diarios operativos y ajustados | 1962-01-02 a 2026-09-22 en la tabla completa; SPY, 1993-01-29 a 2026-09-22 | Yahoo, `prices`; `data_fetch.py`, `storage.py` | A para símbolos antiguos sin identidad verificada. Las fechas extremas no implican cobertura de cada miembro. `close` puede estar retroajustado por splits; `adj_close` también incorpora dividendos. |
| Archivo de precios | 2000-01-03 a 2015-12-31 | FINSABER, `historical_prices`, `historical_archive.py` | A: incluye deslistadas, pero la identidad, los ajustes y los retornos de exclusión no están certificados. La cobertura por año se cuenta aparte, sin sumar ciegamente a Yahoo. |
| Splits y dividendos | 147 eventos de split entre 1974-04-30 y 2026-08-17; sin tabla local de dividendos individuales | Yahoo, `splits`, `prices.adj_close`; `data_fetch.py`, `storage.py` | P para eventos registrados; A para retorno total inferido del cierre ajustado. Cero eventos de split no demuestra que la historia de acciones corporativas esté completa. |
| SEC XBRL por ticker | Hechos presentados 2009-04-15 a 2026-09-22 | Company Facts/EDGAR, 1.377.954 filas en `edgar_facts`; `edgar.py` | P para la fecha real `filed_date` y cada contexto, A para el ticker antiguo sin alias acreditado. `edgar_metrics` solo guarda la foto calculada más reciente. |
| Hechos por CIK y archivo SEC | 1.415.983 observaciones `edgar_facts` por entidad, con presentaciones de 1996-09-27 a 2026-09-22; archivo `historical_facts` limitado a 2015 | `historical_facts`, `entity_observations`, `sec_bulk_facts`, `sec_bulk_submissions`; `legacy_filings.py`, `sec_history.py` | P para el emisor y fecha del filing; Ø para atribuir la mayoría a un ticker histórico. Las filas de distintas fuentes se solapan. El piloto pre-XBRL son tres documentos, no un panel completo. |
| Fundamentales para el ranking | Desde filings XBRL de 2009, con cobertura parcial; hasta 2026-09-22 | `edgar_facts` + `compute_edgar_metrics_as_of`; `screener_asof.py` | P respecto al filtro `filed_date <= fecha`; A respecto a la identidad y al sector históricos. `fundamentals` (Yahoo `Ticker.info`) es una foto actual y no un histórico point-in-time. |
| Sector | 503 snapshots con `effective_date=2026-09-18` | `entity_snapshots`; `entity_master.get_sector_asof` | P desde la fecha de observación para el símbolo observado; A si se proyecta la primera foto hacia 2016–2025; Ø para muchas empresas desaparecidas. No hay GICS histórico acreditado anterior. |

La fuente de 2009–2015 importó 28 ZIP estructurados de SEC y concilió 454.341
filas; eso comprueba la ingesta, no la identidad bursátil. Las cifras de primera
y última fecha son mínimos y máximos **reales en la base**, salvo composición,
que combina fuentes externas fechadas. Por ejemplo, el mínimo de `prices`
(1962) no autoriza un backtest del S&P 500 desde 1962.
El antiguo [`identity-coverage.json`](identity-coverage.json) corresponde a una
base de auditoría separada; sus alias de prueba no aparecen en `data/gabi.db`.

## Métricas del Composite actual

`scoring.SCORE_METRICS` define exactamente 13 métricas. La matriz anual indica
cuántas empresas tienen cada bloque **completo**; el CSV da además el numerador
individual de cada métrica (`pe`, `pb`, etc.), el número con las 13 y el que
cumple el mínimo de 7/13 con algún dato Value, Quality y Momentum. Una métrica
indefinida, por ejemplo PER con beneficios negativos, cuenta como ausente aunque
el filing exista.

| Bloque | Métricas | Fechas de cobertura utilizable medidas en cortes anuales | Procedencia y límite |
| --- | --- | --- | --- |
| Value | PER, P/B, EV/EBITDA | 2009-12-31 a 2026-09-22 | `edgar_facts` y acciones SEC × precio nominal reconstruido; `screener_asof.py`, `historical_coverage.py`. No basta una foto actual de múltiplos de Yahoo. |
| Quality | ROIC, margen operativo, CAGR ingresos 3 años, CAGR FCF 3 años | 2010-12-31 a 2026-09-22 | Hechos con fecha de presentación; `edgar.compute_edgar_metrics`. ROIC usa una aproximación a NOPAT y capital invertido; los CAGR requieren varios ejercicios. |
| Momentum | Momentum 12m, fuerza relativa 6m vs SPY, precio/SMA200 | 2008-12-31 a 2026-09-22 | `prices.adj_close`/SPY; `technicals.py`. El ajuste y la identidad bursátil de series antiguas requieren validación. |
| Risk | Deuda/patrimonio, volatilidad, máximo drawdown | 2009-12-31 a 2026-09-22 | Deuda y patrimonio SEC; precios ajustados; `risk.py`. El drawdown depende de la longitud local disponible. |

Primer corte anual con al menos una empresa por métrica: PER, P/B, EV/EBITDA,
ROIC y deuda/patrimonio en **2009**; margen operativo, las tres métricas de
Momentum, volatilidad y máximo drawdown en **2008**; ambos CAGR en **2010**.
Todas siguen presentes en el corte parcial de **2026-09-22**. Estos extremos
describen la capacidad numérica observada, no un intervalo continuo ni
validación de identidad. La primera cifra de margen de 2008 proviene del
pequeño piloto de informes antiguos; ninguna empresa reúne entonces el bloque
Quality completo.

## Cobertura por año al corte

La siguiente matriz usa **porcentaje de miembros** con cada bloque completo.
`Adj. Y/F` cuenta empresas con al menos un cierre ajustado en el año en Yahoo
operativo / FINSABER archivado, **sin sumar ambas fuentes**. `253` exige las
253 sesiones NYSE previas sin huecos. `SEC` es una empresa con un filing por
ticker presentado en los 460 días anteriores. Ni `Adj.` ni `SEC` bastan por sí
solos para calcular una métrica. Las columnas Value, Quality, Momentum y Risk
proceden de los 13 cálculos indicados arriba.
`Spl.` son los eventos registrados en la tabla `splits` en todo el año, no el
número de miembros que hicieron un split. `ID` cuenta miembros con alias
fechado y único de confianza alta. `13` es el número de miembros con las 13
métricas numéricas.
El número anual de emisores con hechos atribuidos por CIK también aparece en el
CSV, pero cuenta todos los emisores de la base, no solo miembros del índice;
no puede transformarse en porcentaje de miembros sin alias fechados.
En cada celda de bloque, **0% equivale a Ø en ese corte**; un porcentaje positivo
es cobertura numérica `A` para el universo histórico porque los alias de ticker
no están acreditados. Las fechas `filed_date` y los emisores SEC subyacentes
siguen siendo datos `P` individualmente.

| Año | Miembros | ID | Adj. Y/F | 253 | Spl. | SEC | Value | Quality | Momentum | Risk | 13 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2008 | 498 | 0 | 309/451 | 448 | 5 | 0 | 0,0% | 0,0% | 90,0% | 0,0% | 0 |
| 2009 | 499 | 0 | 322/460 | 456 | 2 | 251 | 2,2% | 0,0% | 91,6% | 2,8% | 0 |
| 2010 | 497 | 0 | 329/458 | 457 | 1 | 314 | 24,7% | 1,8% | 92,4% | 34,0% | 7 |
| 2011 | 497 | 0 | 340/459 | 456 | 3 | 327 | 38,0% | 17,7% | 92,2% | 58,4% | 59 |
| 2012 | 497 | 0 | 349/465 | 464 | 4 | 338 | 45,1% | 23,9% | 93,4% | 64,8% | 86 |
| 2013 | 497 | 0 | 356/466 | 465 | 2 | 345 | 44,7% | 27,6% | 93,6% | 68,0% | 94 |
| 2014 | 499 | 0 | 363/469 | 470 | 2 | 353 | 49,5% | 30,1% | 94,2% | 70,3% | 114 |
| 2015 | 502 | 0 | 379/476 | 473 | 1 | 373 | 49,8% | 31,5% | 94,2% | 72,1% | 118 |
| 2016 | 484 | 0 | 395/— | 393 | 3 | 395 | 43,0% | 28,3% | 81,2% | 64,9% | 96 |
| 2017 | 491 | 0 | 409/— | 408 | 1 | 412 | 45,8% | 30,5% | 83,1% | 66,4% | 109 |
| 2018 | 497 | 0 | 421/— | 421 | 2 | 425 | 48,3% | 28,2% | 84,7% | 68,0% | 100 |
| 2019 | 499 | 0 | 434/— | 433 | 2 | 441 | 50,7% | 10,0% | 86,8% | 69,5% | 36 |
| 2020 | 501 | 0 | 445/— | 442 | 3 | 452 | 51,5% | 36,9% | 88,2% | 72,5% | 132 |
| 2021 | 501 | 0 | 454/— | 453 | 0 | 463 | 50,3% | 40,1% | 90,4% | 75,6% | 143 |
| 2022 | 498 | 0 | 470/— | 470 | 0 | 479 | 56,8% | 46,4% | 94,4% | 77,9% | 172 |
| 2023 | 503 | 0 | 483/— | 481 | 1 | 491 | 55,1% | 45,5% | 95,6% | 78,9% | 156 |
| 2024 | 503 | 0 | 491/— | 489 | 2 | 502 | 58,3% | 46,5% | 97,2% | 80,3% | 164 |
| 2025 | 503 | 0 | 498/— | 495 | 3 | 502 | 60,8% | 46,7% | 98,6% | 81,9% | 174 |
| 2026¹ | 503 | 0 | 503/— | 496 | 2 | 503 | 61,8% | 47,5% | 99,4% | 83,1% | 180 |

¹ Corte parcial del 22-09-2026. Un `—` indica que el archivo FINSABER se
limitó deliberadamente a 2000–2015, no que se haya buscado esa fuente después.

Los numeradores y las 13 columnas individuales están en
[`historical-data-audit.csv`](historical-data-audit.csv). Las primeras y últimas
fechas utilizables de cada bloque en esta tabla son **cortes anuales medidos**:
no deben confundirse con el primer día exacto en que una métrica empezó a ser
calculable. El tramo 2016–2026 usa la caché por ticker y conserva la limitación
de identidad señalada arriba.

## Reproducción sin red

```powershell
.venv/Scripts/python.exe -m gabi.historical_data_audit
.venv/Scripts/python.exe -m pytest tests/test_historical_data_audit.py -q
```

El comando abre SQLite en modo **solo lectura** y no llama a Yahoo, SEC ni FRED.
Lee `data/sp500_historical_membership.csv` y el detalle local
`data/history_refresh/validation_1996_2015/coverage/company-quarter.csv` de la
auditoría anterior. Si este último no existe o la base ha cambiado, se puede
regenerar con `.venv/Scripts/python.exe -m gabi.historical_coverage` (también sin
red) antes de repetir el inventario. El script rechaza una composición
pre-2016 que difiera del archivo trimestral; no mezcla denominadores.

La [auditoría de rentabilidad 2016–2025](full-universe-audit/README.md) guarda
rankings trimestrales de otra ejecución y otra fecha de corte. Sus empresas
elegibles no son el mismo numerador que «13 métricas disponibles» de este
inventario anual; no se infiere ninguna rentabilidad nueva de estos conteos.

## Huecos priorizados para las siguientes issues

1. **Identidad histórica**: acreditar alias con intervalos y evidencia de
   filings/acciones corporativas. Hoy hay cero alias aplicados, por lo que
   ningún recuento numérico convierte por sí solo un backtest en totalmente
   point-in-time. Conectar por CIK sin validar ticker puede mezclar emisores.
2. **Continuidad entre etiquetas XBRL ya guardadas**: la cobertura del CAGR de
   ingresos cae de 321/497 miembros en 2018 a 125/499 en 2019, y vuelve a
   352/501 en 2020. `edgar._extract_annual_values` elige la primera etiqueta
   con algún dato, incluso si todavía no reúne cuatro ejercicios para el CAGR.
   Apple ilustra el caso: al corte de 2019 la etiqueta preferida tenía tres
   ejercicios anuales, mientras otra etiqueta ya guardada tenía historia más
   antigua. Antes de buscar nuevos informes conviene estudiar una unión de
   etiquetas con fechas y unidades reconciliadas, sin fingir un CAGR sobre
   ejercicios no contiguos ni mirar publicaciones posteriores.
3. **Continuidad de precios y retornos de exclusión**: revisar los 23 símbolos
   con discrepancias entre Yahoo y FINSABER, los 570 sin solapamiento suficiente
   y los miembros desaparecidos. Confirmar ajustes de splits y dividendos; la
   ausencia de una tabla de dividendos impide la verificación evento por evento.
4. **Fundamentales pre-2009 y métricas faltantes**: el piloto de tres informes
   antiguos no crea 13 métricas para los miembros de 2008. En diciembre de 2015
   faltaban EV/EBITDA para 228 empresas y CAGR de FCF para 222, contando
   también los ratios matemáticamente indefinidos.
5. **Sectores anteriores a la primera foto observada**: obtener fuentes GICS
   fechadas o mantener la marca de aproximación. El sector actual no acredita
   comparaciones sectoriales en 2008–2025.

Estas prioridades se deducen de los datos disponibles y condicionan cualquier
ampliación a 2010. Esta issue no altera los backtests ni los archivos congelados.
