# Precios históricos 2010–2015: avance del issue #28

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

El fallback exige al menos 60 retornos diarios comunes, diferencia absoluta
p99 <= 0,005 y los mismos bordes inicial/final en la ventana. Esto detecta
discrepancias de ajustes y evita usar una serie archivada que anteceda a la
cotización Yahoo de esa acción. **ABBV (2013), KHC y QRVO (2015)** parecían
fallbacks válidos al comparar solo retornos solapados, pero FINSABER añadía
una sesión anterior al inicio de Yahoo: se marcan
`archive_boundary_unverified`. En otros **88–117 casos anuales** el archivo
está completo pero no hay solapamiento suficiente o los ajustes discrepan;
se marcan `archive_adjustment_unverified`. El CSV identifica cada caso, además
de conflictos CIK, identidades sin resolver y series incompletas.

Esta entrega no altera `prices`, `historical_prices`, splits, aliases ni el
backtest 2016+. Queda pendiente para completar el #28 verificar con pruebas
independientes la identidad de cada serie FINSABER sin solapamiento y sus
retornos de exclusión/dividendos. Un CIK SEC acredita al emisor, pero no por sí
solo la serie de una clase de acciones ni su retorno de exclusión. Hasta
entonces estos 2010–2015 no son una muestra limpia para la validación #33.

Los CSV/JSON se regeneraron tras el #29, que elevó ligeramente la identidad
acreditada. La tabla anterior refleja ese estado posterior; las series de
precios y las reglas de fallback permanecen iguales.
