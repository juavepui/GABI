# Precios históricos 2010–2015: auditoría y fase 2 del issue #28

Auditoría local del 24 de septiembre de 2026, posterior al #27. Antes de
añadir lógica se revisaron `main`, README, documentación de las auditorías
#25–#27, `storage.py`, `data_fetch.py`, `history_refresh.py`,
`historical_archive.py`, `identity.py`, el esquema SQLite y tests. GABI ya
conservaba precios Yahoo y FINSABER para 2010–2015; no se descargó nada.

La base local tenía 5.302.967 filas en `prices` (Yahoo operativo), 2.604.620
en `historical_prices` (FINSABER archivado), 147 eventos en `splits` y
1.510 cierres ajustados válidos de SPY durante 2010–2015. `prices` conserva
OHLCV y `adj_close` pero no una columna de fuente por fila: su procedencia
operativa es Yahoo. El archivo lleva `source_id`, `close_basis=as_traded` y
el mismo formato de precios; no debe reemplazar automáticamente los cierres
Yahoo, cuyos ajustes de split/dividendo siguen una semántica distinta.

Se reproduce sin red con:

```powershell
.venv/Scripts/python.exe -m gabi.historical_price_audit
.venv/Scripts/python.exe -m pytest tests/test_historical_price_audit.py -q
```

El script lee la base sin escribirla y produce el
[detalle por símbolo y año](historical-prices-2010-2015.csv) y el
[resumen JSON](historical-prices-2010-2015.json). Para cada cierre anual exige
ambos cierres positivos en las **253 sesiones XNYS anteriores**, sin rellenar
fines de semana, suspensiones, IPO ni sesiones sin observación. El CSV guarda
fecha inicial y final observada de cada fuente, sesiones cubiertas, CIK y
nivel de identidad, estado del contraste de retornos, fuente candidata y
motivo de exclusión. La composición procede de la serie fja05680 archivada,
con la corrección temporal WLP/ANTM del #27; sigue siendo una fuente
comunitaria. Los niveles `confirmed_by_multiple_evidence` y
`corroborated_candidate` se mantienen separados. Ni la identidad ni los
precios legacy se convierten aquí en `entity_observations` de precios.

| Año | Miembros | Yahoo completo | FINSABER completo | Yahoo con identidad acreditada y sin conflicto detectado | Fallback FINSABER admisible | Excluidos |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2010 | 497 | 328 | 454 | 304 | 0 | 193 |
| 2011 | 497 | 336 | 453 | 312 | 0 | 185 |
| 2012 | 497 | 348 | 461 | 326 | 0 | 171 |
| 2013 | 497 | 352 | 461 | 333 | 0 | 164 |
| 2014 | 499 | 362 | 468 | 340 | 0 | 159 |
| 2015 | 502 | 375 | 470 | 348 | 0 | 154 |

SPY tiene la ventana completa en los seis cierres. Los recuentos Yahoo y
FINSABER son disponibilidad bruta, **no** empresas elegibles para backtest.
La fuente candidata Yahoo con identidad acreditada cubre solo el 61–69 % de
los miembros. Además, el precio legacy sigue atribuido al símbolo, no al CIK:
ni siquiera esa columna acredita todavía un backtest point-in-time estricto.

En la primera entrega, el fallback exigía al menos 60 retornos diarios comunes, diferencia absoluta
p99 <= 0,005 y los mismos bordes inicial/final en la ventana. Esto detecta
discrepancias de ajustes y evita usar una serie archivada que anteceda a la
cotización Yahoo de esa acción. **ABBV (2013), KHC y QRVO (2015)** parecían
fallbacks válidos al comparar solo retornos solapados, pero FINSABER añadía
una sesión anterior al inicio de Yahoo: se marcan
`archive_boundary_unverified`. En otros **88–117 casos anuales** el archivo
está completo pero no hay solapamiento suficiente o los ajustes discrepan;
se marcan `archive_adjustment_unverified`. El CSV identifica cada caso, además
de conflictos CIK, identidades sin resolver y series incompletas.

La primera entrega no alteró `prices`, `historical_prices`, splits, aliases ni el
backtest 2016+. Queda pendiente para completar el #28 verificar con pruebas
independientes la identidad de cada serie FINSABER sin solapamiento y sus
retornos de exclusión/dividendos. Un CIK SEC acredita al emisor, pero no por sí
solo la serie de una clase de acciones ni su retorno de exclusión. Hasta
entonces estos 2010–2015 no son una muestra limpia para la validación #33.

Los CSV/JSON se regeneraron tras el #29, que elevó ligeramente la identidad
acreditada. La tabla anterior refleja ese estado posterior; las series de
precios y las reglas de fallback permanecen iguales.

## Fase 2: procedencia, salida de cotización y cobertura trimestral

La segunda pasada reutiliza esta auditoría y la evidencia SEC de #27/#29.
`historical_price_provenance` guarda por intervalo `entity_id`, CIK, ticker,
fechas, fuente, base de ajuste, tier y referencias exactas. El comando
`--quarterly --promote-tier-a` une ventanas Yahoo solapadas y registra los
intervalos completos con identidad acreditada y referencias SEC; es
idempotente y no copia precios a `entity_observations` ni altera `prices` o
`historical_prices`. En la base local se atribuyeron **363 intervalos Yahoo**.
La identidad SEC se acredita retrospectivamente; no se convierte una prueba
presentada después de un rebalanceo en un fundamental disponible entonces.
Para Yahoo, `close` es el cierre nominal almacenado y `adj_close` se usa con
la convención operativa de GABI (splits + dividendos); el caché legacy no
conserva la descarga original por fila, por lo que se guarda el hash de cada
intervalo promovido. Para FINSABER, `close_basis=as_traded` describe `close`,
pero la convención de `adjusted_close` sigue sin acreditarse.
El lector `historical_price_policy.price_history` exige un único intervalo de
fuente y CIK, fechas válidas y, si se indican las sesiones de bolsa, todas las
observaciones reales. Devuelve `price_source_status`, base de ajuste y
evidencia; nunca concatena fuentes, rellena sesiones ni extiende un ticker a
otro emisor. El backtest V1/V2 existente sigue usando su ruta 2016+; la
integración histórica completa corresponde al #32.

Para Tier B se permite ausencia de solapamiento Yahoo **solo** con pruebas
independientes de primera/última negociación, identidad, acciones corporativas
y reconciliación de splits y dividendos. Un solapamiento divergente bloquea la
serie aunque tenga esos documentos. La [ficha del archivo FINSABER](https://huggingface.co/datasets/finsaber-team/FINSABER-reproduce)
etiqueta la columna `adjusted_close`, pero no especifica una convención de
retorno total, metodología de dividendos o retorno de exclusión para cada
acción. Por ello **ningún fallback FINSABER local está acreditado todavía**.
ABBV, KHC y QRVO no se reparan con los precios anteriores de FINSABER sin
prueba de la fecha de inicio de cada acción.

`historical_terminal_events` separa adquisición en efectivo, canje de acciones,
fusión, liquidación, exclusión y spin-off; sus estados son retorno confirmado,
acotado o desconocido. El retorno confirmado usa contraprestación y convierte
precio nominal a la base ajustada. Un canje requiere el precio del sucesor; un
evento desconocido/acotado, o una solicitud que atraviesa un evento incluso
confirmado, se rechaza en la lectura estricta hasta contabilizarlo de forma
explícita. **No hay eventos terminales históricos con términos económicos
acreditados importados aún**. Una salida del índice por sí sola no demuestra
una exclusión bursátil ni fija un retorno; los casos siguen visibles en el
diagnóstico, sin asignarles cero ni el último precio.

El [CSV trimestral por miembro](historical-prices-quarterly-2010-2015.csv) y
su [resumen JSON](historical-prices-quarterly-2010-2015.json) cubren los 24
rebalanceos de 2010–2015. Cada uno exige 253 sesiones XNYS hasta esa fecha.
La tabla siguiente suma las cuatro observaciones trimestrales de cada año:

| Año | Observaciones | Identidad acreditada | Precio Tier A atribuido | Tier B | Cobertura utilizable |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2010 | 1.992 | 1.802 | 1.210 | 0 | 60,7 % |
| 2011 | 1.988 | 1.810 | 1.229 | 0 | 61,8 % |
| 2012 | 1.988 | 1.831 | 1.275 | 0 | 64,1 % |
| 2013 | 1.988 | 1.847 | 1.322 | 0 | 66,5 % |
| 2014 | 1.993 | 1.855 | 1.351 | 0 | 67,8 % |
| 2015 | 2.004 | 1.848 | 1.389 | 0 | 69,3 % |

El rango por rebalanceo es **60,32–69,54 %**; SPY tiene las 253 sesiones en
los 24 cortes. La identidad por sí sola está en torno al 90–93 %, pero no
convierte los precios archivados en retornos válidos. En las 11.953
observaciones del período, 2.567 quedan fuera por evidencia insuficiente de
FINSABER, además de identidades, sesiones o conflictos faltantes (desglose
exacto por fecha en JSON). No se alcanza el objetivo orientativo del 90 %.

La exclusión tampoco parece inocua. Entre miembros que salen del índice en
los 365 días posteriores al rebalanceo, solo **58/404 (14,4 %)** tienen precio
atribuido; entre los demás son **7.718/11.549 (66,8 %)**. Una salida del índice
no equivale necesariamente a quiebra, pero la diferencia impide defender que
los ausentes no estén relacionados con desenlaces difíciles. Por SIC de dos
dígitos (proxy, no GICS histórico), las observaciones de extracción de
petróleo/gas `13` tienen 209/494 (42,3 %) utilizables; las de utilities `49`,
680/854 (79,6 %). Otras 1.312 observaciones no tienen SIC point-in-time
acreditado, de las que 163 son utilizables. Tampoco hay capitalizaciones
históricas fiables de muchas acciones excluidas para descartar sesgo por
tamaño. Las observaciones trimestrales repiten emisores; estos cocientes son
diagnósticos de cobertura, no pruebas estadísticas independientes.

Reproducir sin red sobre la misma base local:

```powershell
.venv/Scripts/python.exe -m gabi.historical_price_audit --quarterly --promote-tier-a
.venv/Scripts/python.exe -m gabi.historical_price_audit
.venv/Scripts/python.exe -m pytest tests/test_historical_price_audit.py tests/test_historical_price_policy.py -q
```

El #28 sigue abierto. Los siguientes bloqueos son reconciliar FINSABER con
fuentes independientes de fechas de negociación, splits/dividendos y
contraprestaciones de adquisición/liquidación; resolver las identidades aún
ambiguas; y medir concentración por tamaño con capitalizaciones de época.
Hasta entonces, **2010–2015 no debe incorporarse a un backtest estricto ni
usarse para afirmar superioridad frente al S&P 500**.
