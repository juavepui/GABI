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

Queda un bloque que **sí** requiere otra fuente: 36 emisores con identidad
acreditada y sin precios en ninguna de las dos (CA, EMC, DOW, SNDK, STI, MON,
DTV, SE, TE, XL, CHK, DNB…; 575 observaciones, 4,8 %). Son sobre todo
empresas absorbidas en 2016–2019, que el archivo FINSABER perdió y que Yahoo
ya no publica. Las alternativas gratuitas con tickers deslistados (Tiingo,
Nasdaq Data Link WIKI) requieren cuenta/API key; Stooq exige superar un reto
anti-bot y no se usa. Añadirlas es una decisión del usuario, no un paso
automático.

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

Suma de las cuatro fechas trimestrales de cada año
([CSV](historical-prices-quarterly-2010-2015.csv),
[JSON](historical-prices-quarterly-2010-2015.json)):

| Año | Observaciones | Identidad acreditada | Tier A | Tier B | Ventana completa utilizable | Historia corta utilizable | Excluidas |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2010 | 1.992 | 1.941 | 1.210 | 307 | 1.515 | 2 | 475 |
| 2011 | 1.988 | 1.943 | 1.262 | 324 | 1.583 | 3 | 402 |
| 2012 | 1.988 | 1.957 | 1.308 | 276 | 1.573 | 11 | 404 |
| 2013 | 1.988 | 1.964 | 1.359 | 299 | 1.647 | 11 | 330 |
| 2014 | 1.993 | 1.969 | 1.392 | 284 | 1.669 | 7 | 317 |
| 2015 | 2.004 | 1.969 | 1.421 | 263 | 1.674 | 10 | 320 |

Por rebalanceo, la cobertura utilizable es **72,3–85,0 %** (ventana completa
72,3–84,8 %; primera fase 60,3–69,5 %). Se promovieron 403 intervalos Tier A y
140 Tier B, todos con CIK, fuente, base de ajuste y referencias SEC en
`historical_price_provenance`. SPY está completo en los 24 cortes.

Exclusiones (11.953 observaciones): sin precios en ninguna fuente 575; FINSABER
sin dividendos 435; dividendos SEC no disponibles 247; nivel de precio fallido
234 o no disponible 189; identidad 184; fuentes divergentes 175; saltos o
splits sin explicar 77; conflictos de CIK, sucesiones y bajas 132.

**No se alcanza el 90 %** y la exclusión **no es neutral**:

- Miembros que salen del índice en el año siguiente: 45,3 % utilizables
  (183/404), frente a 82,4 % del resto. Salir del índice no implica un mal
  desenlace, pero los ausentes se concentran en empresas que desaparecen.
- Tamaño (quintil de *public float* SEC en cada fecha): 75,3 % en el quintil
  inferior frente a 83,5–86,8 % en los demás; sin float conocido, 22,4 %.
- Sector (SIC de dos dígitos, proxy): comercio minorista de ropa (56) y
  comunicaciones (48) 67 %, metales primarios (33) 70 %, frente a 86–88 % en
  química y refino; sin SIC SEC, 32 %.

Con estas cifras 2010–2015 sigue sin servir para afirmar superioridad frente
al S&P 500 en un backtest estricto: cualquier resultado debe presentarse con
la exclusión documentada y, preferiblemente, tras incorporar una fuente con
precios de las empresas absorbidas en 2016–2019.

### Reproducir

Sin red (con la base y las cachés SEC locales):

```powershell
.venv/Scripts/python.exe -m gabi.historical_identity_audit --build-intervals --intervals-csv docs/historical-identity-intervals.csv --output docs/historical-identity-2010-2015.json
.venv/Scripts/python.exe -m gabi.historical_price_audit --quarterly --terminal-events --promote
.venv/Scripts/python.exe -m gabi.historical_price_audit
.venv/Scripts/python.exe -m pytest tests/test_historical_issuer_evidence.py tests/test_historical_price_audit.py tests/test_historical_price_policy.py tests/test_historical_identity_audit.py -q
```

Descarga de la evidencia (idempotente, ya cacheada):

```powershell
.venv/Scripts/python.exe -m gabi.historical_issuer_evidence --fetch-frames --fetch-submissions <fichero con CIK>
.venv/Scripts/python.exe -m gabi.historical_identity_audit --import-nominated-filings --fetch-candidate-instances 400
.venv/Scripts/python.exe -m gabi.historical_identity_audit --fetch-unresolved-instances 1500 --annual-report-symbols 200
.venv/Scripts/python.exe -m gabi.historical_identity_audit --scan-instances --import-evidence --evidence-csv docs/historical-identity-filing-evidence.csv --build-intervals --intervals-csv docs/historical-identity-intervals.csv --output docs/historical-identity-2010-2015.json
```

Límites conocidos: la banda de nivel no distingue un error de split 2:1; las
sucesiones (Google → Alphabet, Walgreen → WBA) cortan las ventanas que las
atraviesan en lugar de encadenar CIK; los eventos terminales con acciones o
mixtos aún no se calculan; la composición sigue siendo comunitaria (#26).
