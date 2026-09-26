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

> Esta sección conserva el estado de la primera entrega. Las fases 2 y 3
> (abajo) sustituyen sus reglas de selección y sus cifras; los CSV/JSON
> actuales corresponden a la fase 3.

## Fases 2 y 3: procedencia, evidencia SEC por emisor y eventos terminales

### ¿Faltaban fuentes o faltaba procesar?

Sobre todo faltaba procesar. Las dos fuentes de precios ya archivadas (caché
Yahoo y FINSABER) cubren la mayor parte del universo; lo que no existía era
evidencia **independiente por emisor** para decidir qué serie pertenece a qué
CIK, en qué intervalo y con qué ajustes. Esa evidencia es gratuita, está en
SEC EDGAR y se ha incorporado:

- `submissions` de unos 720 CIK (historial completo de presentaciones):
  primer informe periódico, sucesiones de sociedad holding (8-K12B),
  registros de salida a bolsa/spin-off y bajas de cotización (Form 25/15
  seguidos de silencio o de ausencia de *public float* posterior, para
  distinguirlas de bajas de deuda o traslados de mercado);
- *XBRL frames* de `dei:EntityPublicFloat`, acciones en circulación y
  dividendos por acción (declarados, pagados y pagos anuales): 186 ficheros
  que cubren a todos los emisores de 2008–2016;
- 8-K de cierre de operación (ítems 1.03/2.01/3.01/5.01) de los miembros que
  dejan de cotizar antes del siguiente rebalanceo, y el texto de 10-K
  («under the symbol …») cuando la portada XBRL no declara ticker.

Todo se descarga con `sec_history.download` (URL + SHA-256 en
`sec_archive_files`) y se reutiliza sin red.

Había un bloque que **sí** requería otra fuente: 36 emisores con identidad
acreditada y sin precios en Yahoo ni en FINSABER (CA, EMC, DOW, SNDK, STI,
MON, DTV, SE, TE, XL, CHK, DNB…; 575 observaciones, 4,8 %), sobre todo
empresas absorbidas en 2016–2019. Se añadieron dos fuentes gratuitas con
cuenta, cuyas claves se guardan localmente desde ⚙️ Configuración
(`data/*_api_key.txt`, excluidos del control de versiones):

- **Nasdaq Data Link, tabla WIKI Prices** (`historical_wiki.py`): congelada
  el 2018-03-27 con los tickers de entonces, por lo que conserva a EMC, CA,
  DOW, STI, MON… antes de que se reutilizaran sus símbolos. Trae cierre
  negociado, dividendo por fecha ex y ratio de split. Se descargaron 213
  símbolos excluidos (186 con datos).
- **Tiingo, plan gratuito** (`historical_tiingo.py`): su API solo sirve el
  valor que usa hoy cada ticker, así que únicamente se piden símbolos cuya
  cotización actual ya cubría 2009–2015 (131); los reciclados (EMC → ETF,
  STI → Solidion, SNDK → SanDisk 2025) se descartan antes de pedirlos. El
  plan limita a ~50 peticiones/hora: la descarga está espaciada, reintenta
  ante cortes de red y es reanudable.

Ambas se tratan exactamente como FINSABER: filas candidatas en
`historical_prices` con su `source_id` y SHA-256 de cada respuesta, y solo
se atribuyen si pasan los controles SEC por CIK. Un ticker también reutilizado
dentro de WIKI (NSM en 2012 ya es Nationstar, SUN en 2014 es Sunoco LP) falla
esos controles y no se atribuye. Stooq exige superar un reto anti-bot y no se
usa.

Siguen sin precios en ninguna de las cuatro fuentes 31 símbolos en alguna de
sus ventanas (204 observaciones, 1,7 %): parte son ventanas incompletas de
emisores que sí se cubren en otros trimestres, y parte empresas que ninguna
fuente gratuita conserva (ADT, BEAM, CEG, KG, LIFE, MI, PGN, SII…).

### Identidad

La auditoría de identidad (#27/#29) se amplió sin rehacerla:

- `resources/historical_identity_corrections_2010_2015.json` recoge 68
  **nominaciones revisadas**: CIK de sucesores posteriores que lawcal aplica
  hacia atrás (XOM → CIK de 2025, DIS, BLK, CI, APA, FTI, XRX, WBA, MYL, ESRX,
  ETN, ICE, MDT, PRGO…), etiquetas retroactivas de la composición (TPR = COH,
  ZBH = ZMH, TGNA = GCI, CBRE = CBG, LB = LTD, DXC = CSC, KDP = DPS…) y
  símbolos con los que las fuentes de precios guardan la historia (LB → BBWI,
  IR → TT, BHGE → BKR, WLP → ELV/ANTM, HCP → DOC, PX → LIN). Una nominación
  **no es evidencia**: solo decide qué CIK probar.
- El nuevo nivel `confirmed_historical_ticker` exige dos portadas SEC del
  mismo CIK con el ticker histórico y que ningún otro CIK use la etiqueta o
  ese ticker en el intervalo. Una nominación con informes repetidos y una
  sola observación de ticker (portada, 10-K o lista de tickers de SEC) llega
  como mucho a `corroborated_candidate`.
- Ningún nivel se concede si el primer informe periódico del CIK (historial
  EDGAR completo) llega más de 200 días después del inicio del intervalo: es
  un sucesor. Esto elimina, por ejemplo, WBA → Walgreens Boots Alliance en
  2010.
- El proceso detecta sus propios errores de nominación: JCI se nominó con el
  CIK 833444 y SEC devolvió el ticker TYC (era Tyco, vehículo de la fusión de
  2016); se corrigió a Johnson Controls Inc (CIK 53669).

Resultado: identidad acreditada del **97,4–98,8 %** de las observaciones
(antes 90,5–93,1 %) y ambigua solo del 0,3–0,45 % (antes 1,9–2,65 %). Siguen
excluidos casos genuinamente ambiguos (CB/ACE, AGN) y 18 intervalos sin
evidencia suficiente (XRX, ETN previo a 2012, BHGE, CCE…).

### Reglas de atribución de precios

`historical_issuer_evidence.py` produce los controles y
`historical_price_audit.py` decide, **fallando cerrado**. Para cada ventana de
253 sesiones:

1. **Vida bursátil SEC**: primer informe periódico ≤ inicio de la ventana; sin
   sucesión dentro; sin baja de cotización antes del final.
2. **Nivel de precio**: *public float* / (acciones de portada × cierre
   negociado) en [0,25; 1,5] en alguna fecha de float entre 200 días antes y
   400 días después (sin sucesión ni baja por medio). Las acciones de portada
   no se reexpresan; los splits entre la fecha de float y la de portada se
   deshacen con los splits observados. Diferencias >100× son errores de
   unidad XBRL (no concluyente). Sobre 2.436 comprobaciones de series
   conocidas como buenas falla el 0,9 %; las series FINSABER erróneas (EP,
   GR, RRD) fallan. Un fallo excluye la ventana.
3. **Ajustes** (series FINSABER y cualquier divergencia): eventos implícitos
   en `close` frente a `adj_close`; splits verificados con el cambio de
   acciones de portada SEC; dividendos conciliados con los dividendos por
   acción SEC (trimestrales o, si solo hay anuales, el ejercicio que acaba en
   la segunda mitad de la ventana); movimientos diarios >25 % sin
   corroboración o distribuciones >10 % bloquean la ventana. «Sin dividendos»
   solo se acepta si SEC lo dice (ceros explícitos, o emisor XBRL sin
   dividendos ni pagos declarados).
4. **Huella de dividendos**: si no es posible comprobar el nivel (emisores
   multiclase como STZ, V o TSN no tienen acciones no dimensionales en los
   frames), identifica la serie que ≥2 dividendos y ≥75 % de los eventos
   coincidan uno a uno con importes SEC del CIK. Nunca sustituye a un nivel
   fallido.
5. **Contraste entre fuentes**: además del p99 ≤ 0,005, un solo día con más de
   5 puntos de diferencia es `divergent_event` (spin-offs mal ajustados:
   MDLZ 2012, CAH 2009, EXPE 2011, DXC 2015). La divergencia solo se resuelve
   a favor de Yahoo cuando ambas fuentes cotizan **los mismos precios
   negociados** (retornos de `close` idénticos) y los dividendos SEC dan la
   razón a Yahoo y no a FINSABER.

Hallazgos de fuente relevantes:

- **FINSABER omite ajustes por dividendo en algunas series** (APD, KMB, JWN,
  UTX…): en cada fecha ex su retorno ajustado es igual al nominal. En
  2009–2015 el 99,7 % de 706.135 retornos coincide con Yahoo, pero esas
  series se excluyen (`archive_dividend_mismatch`) salvo que Yahoo,
  conciliado con SEC, las cubra.
- **La caché Yahoo contiene valores reciclados**: GENZ (Genzyme, absorbida en
  2011) sigue cotizando hasta 2026 y BBT cotiza otro valor (18 $ frente a los
  32 $ reales de BB&T). La primera fase los había atribuido como Tier A; la
  promoción ahora sustituye las filas generadas por la auditoría y ambas
  pierden la atribución.
- FINSABER es en la práctica una instantánea archivada derivada de Yahoo
  (recuentos idénticos en muchos símbolos): su independencia viene de SEC, no
  del contraste Yahoo–FINSABER.

Las series que empiezan dentro de la ventana en una salida a bolsa o spin-off
registrada en SEC (ABBV desde 2013-01-02, KHC desde 2015-07-06, QRVO desde
2015-01-02, HPE, CSRA…) se atribuyen como `short_history` desde su primera
sesión real, nunca con los precios previos que incluía FINSABER. Se cuentan
aparte.

### Eventos terminales

`historical_terminal_events` recoge los 58 miembros cuya baja SEC cae antes del
siguiente rebalanceo. Solo una contraprestación íntegramente en efectivo y sin
otros componentes en su cláusula queda `terminal_return_confirmed` (15 casos:
HNZ 72,50 $, DELL 13,75 $, GR 127,50 $, BEAM, CEPH, GMCR, LSI, MFE, MMI, MOLX,
NOVL, NSM, PETM, PLL, PTV). Efectivo + acciones, elecciones, CVR, canjes
(18 fusiones, 4 canjes) y bajas sin términos legibles (21) quedan
`terminal_return_unknown`; la lectura estricta los rechaza y nunca usa el
último precio. En la revisión se detectaron y corrigieron casos mixtos que un
primer patrón daba como efectivo (CBE, COV, CVH, GENZ con CVR, BRCM con
elección). Dos observaciones (GOOG/GOOGL 2015-09-30) son la sucesión
Google → Alphabet, sin evento económico registrado.

### Cobertura final

Suma de las cuatro fechas trimestrales de cada año, con las cuatro fuentes
([CSV](historical-prices-quarterly-2010-2015.csv),
[JSON](historical-prices-quarterly-2010-2015.json)):

| Año | Observaciones | Identidad acreditada | Tier A (Yahoo) | Tier B (FINSABER / Tiingo / WIKI) | Ventana completa utilizable | Historia corta utilizable | Excluidas | Utilizable |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2010 | 1.992 | 1.941 | 1.210 | 427 (307 / 56 / 64) | 1.635 | 2 | 355 | 82,2 % |
| 2011 | 1.988 | 1.943 | 1.262 | 452 (324 / 57 / 71) | 1.711 | 3 | 274 | 86,2 % |
| 2012 | 1.988 | 1.957 | 1.308 | 379 (276 / 46 / 57) | 1.676 | 11 | 301 | 84,9 % |
| 2013 | 1.988 | 1.964 | 1.359 | 409 (299 / 46 / 64) | 1.757 | 11 | 220 | 88,9 % |
| 2014 | 1.993 | 1.969 | 1.392 | 402 (284 / 52 / 66) | 1.787 | 7 | 199 | 90,0 % |
| 2015 | 2.004 | 1.969 | 1.421 | 343 (263 / 30 / 50) | 1.754 | 10 | 240 | 88,0 % |

> Actualización #32: con el periodo de tenencia verificado la auditoría queda en
> **78,2–90,5 % por rebalanceo (media 86,8 %)**, 399 intervalos Tier A y 206
> Tier B; ver [integración 2010–2015](historical-integration-2010-2015.md).

Por rebalanceo, la cobertura utilizable es **77,6–90,7 %** (media 86,7 %;
ventana completa 77,6–90,3 %). Con solo Yahoo y FINSABER era 72,3–85,0 %, y en
la primera fase 60,3–69,5 %. Tres rebalanceos (2013-12-31, 2014-03-31 y
2014-09-30) superan el 90 %; el peor es 2010-03-31 (77,6 %). Se promovieron
403 intervalos Tier A y 211 Tier B, todos con CIK, fuente, base de ajuste y
referencias SEC en `historical_price_provenance`. Cuatro intervalos no se
promovieron (tres solapes entre fuentes que no coinciden en retornos y uno
que diverge de Yahoo). SPY está completo en los 24 cortes.

Dos intervalos de fuentes distintas del mismo emisor pueden solaparse (las
ventanas de 253 sesiones de trimestres consecutivos se pisan) solo si ambas
fuentes dan los mismos retornos ajustados en el tramo común; la lectura
estricta prefiere entonces la caché Yahoo.

Exclusiones (11.953 observaciones): FINSABER sin dividendos y sin otra fuente
válida 313; dividendos SEC no disponibles 245; sin precios en ninguna fuente
204; identidad 184; nivel de precio no disponible 169 o fallido 158; fuentes
divergentes 102; saltos, splits o ajustes sin explicar 75; conflictos de CIK,
sucesiones y bajas 132; siete ventanas acreditadas cuyo intervalo no se pudo
promover.

**No se alcanza el 90 % en todos los rebalanceos** y la exclusión **no es
neutral**:

- Miembros que salen del índice en el año siguiente: 57,4 % utilizables
  (232/404), frente a 87,7 % del resto (antes de las fuentes nuevas, 45,3 %
  frente a 82,4 %). Salir del índice no implica un mal desenlace, pero los
  ausentes siguen concentrados en empresas que desaparecen.
- Tamaño (quintil de *public float* SEC en cada fecha): 82,0 % en el quintil
  inferior frente a 88,6–92,0 % en los demás; sin float conocido, 26,8 %.
- Sector (SIC de dos dígitos, proxy): comercio minorista de ropa (56) 67 %,
  comunicaciones (48) 79 %, frente a 91–96 % en software, transporte y
  química; sin SIC SEC, 37 %.

## Cierre del #28 y restricción para #32/#33

El #28 se cierra **aceptando este déficit documentado**: todos los criterios
de procedencia, bordes, ajustes, eventos terminales, idempotencia y tests se
cumplen, y la cobertura queda medida, explicada por motivo y sesgada de forma
conocida. Consecuencias obligatorias para la integración (#32) y la validación
(#33):

1. Solo se usan series con intervalo acreditado (`price_history`), nunca la
   caché por ticker; `terminal_return_unknown` y las ventanas excluidas no
   entran en silencio: se informan por rebalanceo.
2. 2010–2015 no sirve para afirmar superioridad frente al S&P 500 sin
   corregir el sesgo. Todo resultado debe acompañarse de:
   - un benchmark construido sobre el **mismo universo cubierto** (además de
     SPY);
   - el **retorno implícito del grupo excluido**: SPY (ponderado por
     capitalización) menos la contribución de los miembros cubiertos, con la
     capitalización aproximada por *public float* SEC;
   - un **análisis de sensibilidad** que acote el efecto suponiendo que los
     excluidos rinden como el peor o el mejor decil del universo cubierto;
   - la cobertura por rebalanceo, marcando como no concluyentes los cortes
     por debajo del 85 %.
3. No se reoptimizan pesos ni umbrales con este periodo.

### Reproducir

Sin red (con la base y las cachés SEC locales):

```powershell
.venv/Scripts/python.exe -m gabi.historical_identity_audit --build-intervals --intervals-csv docs/historical-identity-intervals.csv --output docs/historical-identity-2010-2015.json
.venv/Scripts/python.exe -m gabi.historical_price_audit --quarterly --terminal-events --promote
.venv/Scripts/python.exe -m gabi.historical_price_audit
.venv/Scripts/python.exe -m pytest tests/test_historical_issuer_evidence.py tests/test_historical_price_audit.py tests/test_historical_price_policy.py tests/test_historical_identity_audit.py tests/test_historical_tiingo.py -q
```

Descarga de la evidencia y de las fuentes con clave (idempotente, ya cacheada):

```powershell
.venv/Scripts/python.exe -m gabi.historical_issuer_evidence --fetch-frames --fetch-submissions <fichero con CIK>
.venv/Scripts/python.exe -m gabi.historical_identity_audit --import-nominated-filings --fetch-candidate-instances 400
.venv/Scripts/python.exe -m gabi.historical_identity_audit --fetch-unresolved-instances 1500 --annual-report-symbols 200
.venv/Scripts/python.exe -m gabi.historical_identity_audit --scan-instances --import-evidence --evidence-csv docs/historical-identity-filing-evidence.csv --build-intervals --intervals-csv docs/historical-identity-intervals.csv --output docs/historical-identity-2010-2015.json
.venv/Scripts/python.exe -m gabi.historical_wiki --fetch <fichero con símbolos> --import-cached
.venv/Scripts/python.exe -m gabi.historical_tiingo --fetch <fichero con símbolos> --import-cached
```

Límites conocidos: la banda de nivel no distingue un error de split 2:1; las
sucesiones (Google → Alphabet, Walgreen → WBA) cortan las ventanas que las
atraviesan en lugar de encadenar CIK; los eventos terminales con acciones o
mixtos aún no se calculan; la composición sigue siendo comunitaria (#26).
