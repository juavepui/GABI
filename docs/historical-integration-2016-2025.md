# Capa acreditada 2016–2025: issue #34

Aplicación a **2016–2025** de la misma capa acreditada (composición, identidad
SEC, procedencia de precios y eventos terminales) que #26–#32 construyeron para
2010–2015. No se evalúa rentabilidad ni se toca el Composite; la revalidación
es el #35.

## Infraestructura: la misma, parametrizada por periodo

`historical_period.py` define los dos periodos. Cada uno tiene su fuente de
composición, su fuente de intervalos de identidad, su productor de la auditoría
de precios y su **horizonte de evidencia**. Así, reconstruir un periodo nunca
sustituye la evidencia del otro.

| | 2010–2015 (#26–#33) | 2016–2025 (#34) |
| --- | --- | --- |
| Composición | `fja05680:a2430f2…` (importada hasta 2016) | `fja05680:a2430f2…:full` (mismo fichero y SHA-256, hasta 2026-08-18) |
| Intervalos de identidad | `sec-identity-evidence:2010-2015:v1` | `sec-identity-evidence:2016-2025:v1` |
| Productor de precios | `historical_price_audit:v2` | `historical_price_audit:v2:2016-2025` |
| Tiingo | `tiingo:daily-2026-09` | `tiingo:daily-2026-09:2016-2025` |
| Horizonte | frames SEC hasta CY2016, FINSABER hasta 2015-12-31, baja «sin float posterior» solo antes de 2016 | frames hasta CY2025, FINSABER hasta 2024-12-31, regla de baja hasta 2025 |

Los módulos `historical_identity_audit`, `historical_price_audit`,
`historical_issuer_evidence`, `historical_membership`, `historical_tiingo` y
`historical_pit` reciben el periodo (`--period 2016-2025` en línea de comandos).
El valor por defecto sigue siendo 2010–2015.

**2010–2015 queda congelado y se ha comprobado.** Con toda la evidencia nueva
ya en la base de datos:

- los 620 intervalos de identidad de 2010–2015 se reconstruyen idénticos;
- la auditoría trimestral de precios 2010–2015 reproduce **byte a byte**
  `historical-prices-quarterly-2010-2015.csv` (11 977 × 52).

Para lograrlo, cada periodo solo ve las pruebas SEC presentadas dentro de su
ventana de evidencia. Además, la atribución de precios y `historical_pit` solo
leen los intervalos del productor de los periodos activos.

## 1. Composición

La composición operativa de 2016+ (hanshof + extensión revisada) es un
**subconjunto** de fja05680. Le faltan justo los miembros con tickers
reciclados o reetiquetados:

| Fecha | fja05680 | hanshof | Solo en fja | Solo en hanshof |
| --- | ---: | ---: | ---: | ---: |
| 2016-01-02 | 502 | 470 | 32 | 0 |
| 2017-07-02 | 506 | 489 | 17 | 0 |
| 2019-07-02 | 505 | 497 | 8 | 0 |
| 2021-07-02 | 505 | 501 | 4 | 0 |
| 2023-07-02 → 2025-07-02 | 503 | 503 | 0 | 0 |

Ejemplos de los que faltan: AABA, AGN, ARNC, BHGE, CCE, CHK, DNB, DOW, FOX/FOXA,
HCP, IR o CEG. **Decisión: fja05680 para 2016–2025**, por continuidad con
2010–2015 y porque es la fuente completa. fja aplica etiquetas retroactivas en
2016–2019, igual que hacía con ANTM/WLP: por ejemplo BHGE por BHI, KDP por DPS,
WYND por WYN, AABA por YHOO o CPRI por KORS. Se resuelven con nominaciones
fechadas (ver identidad), no cambiando la fuente.

## 2. Identidad SEC

Mismas reglas y niveles que el #27. Las pruebas y sus resultados:

- **Presentaciones**: submissions de los Financial Statement Data Sets de SEC,
  2016q1–2025q4 (solo la tabla SUB, para los 700 CIK candidatos más los
  nominados).
- **Portadas XBRL**: 2 242 descargadas; dan 1 710 pruebas de ticker y 0
  conflictos con lawcal.
  - Desde 2019 las portadas inline listan todos los valores registrados
    (acciones, preferentes, bonos). La prueba es el símbolo de la **acción
    ordinaria**, identificado por su contexto (`CommonStockMember`, sin
    dimensión) o por su `Security12bTitle`.
  - Dos clases ordinarias (GOOGL/GOOG, FOXA/FOX, NWSA/NWS, UAA/UA) prueban
    ambas solo si hay una nominación multiclase revisada. Sin ella siguen
    siendo ambiguas, como en LEN o BF-B.
- **Texto del 10-K** para los intervalos abiertos. Hay un patrón nuevo para
  «common stock (XRX) is listed», y cuando el texto menciona símbolos de
  terceros (SKY en 21CF, AMSG en Envision, CNDT en Xerox) se usa el ticker
  revisado de ese CIK, solo si es único.
- **70 nominaciones nuevas**
  (`resources/historical_identity_corrections_2016_2025.json`):
  - **CIK sucesores** que lawcal asigna antes de tiempo: XOM, DIS (hasta
    2019-03-20), BLK (2024-10-01), CI, APA, AVGO (tres CIK), FTI, WRK, XRX,
    LLL, BG, EVHC y ENDP. Se detectan porque el CIK candidato no presentaba
    10-K/10-Q en la fecha.
  - **Etiquetas retroactivas**: AABA, BHGE, CCEP, KDP, WYND, CPRI, ARNC, CBRE,
    TPR e IQV.
  - **Huecos de lawcal**: D, SRE, TROW, IR, FOX/FOXA de 21CF y KORS.
  - **Multiclase** y **ventanas de evidencia** para salidas a principios de
    2016 y entradas a finales de 2025.

Resultado: **756 intervalos** (631 `confirmed_by_multiple_evidence`, 21
`confirmed_historical_ticker`, 99 `corroborated_candidate`, 0 ambiguos, 8 sin
resolver). Informe completo en
[historical-identity-2016-2025.json](historical-identity-2016-2025.json) e
intervalos con su procedencia en
[historical-identity-intervals-2016-2025.csv](historical-identity-intervals-2016-2025.csv).

| Año | Observaciones miembro-trimestre | Identidad acreditada | % |
| --- | ---: | ---: | ---: |
| 2016 | 2 022 | 2 018 | 99,8 |
| 2017 | 2 023 | 2 021 | 99,9 |
| 2018 | 2 022 | 2 022 | 100,0 |
| 2019 | 2 020 | 2 016 | 99,8 |
| 2020 | 2 020 | 2 016 | 99,8 |
| 2021 | 2 020 | 2 015 | 99,8 |
| 2022 | 2 014 | 2 006 | 99,6 |
| 2023 | 2 012 | 2 011 | 100,0 |
| 2024 | 2 013 | 2 013 | 100,0 |
| 2025 | 2 012 | 2 011 | 100,0 |

Sin resolver:

- **FRC** (2019–2023) y **SBNY** (2021–2023). Presentaban sus informes ante
  sus reguladores bancarios, no ante la SEC, así que no hay evidencia SEC
  posible. Quedan excluidos.
- **BHGE** (Baker Hughes Inc, 2016 → 2017-07). Sus portadas no traen ticker y
  su 10-K no lo menciona.
- **BRCM, GMCR, PCL**: salen antes del primer cierre auditado (2016-03-31).
- **Q, SOLS**: entran a finales de 2025 y no tienen dos informes antes del
  cierre del periodo.

## 3. Precios

Auditoría trimestral en los **40 cierres de 2016-03-31 a 2025-12-31**, con las
mismas reglas del #28:

- vida bursátil SEC;
- nivel de precio (float público / acciones × cierre);
- conciliación de splits y dividendos;
- contraste entre fuentes;
- periodo de tenencia verificado hasta el siguiente rebalanceo;
- ventanas acreditadas por intervalo.

Fuentes: caché Yahoo (Tier A), FINSABER 2014–2024, WIKI hasta 2018-03 y
Tiingo. FINSABER y Tiingo son las únicas fuentes Tier B que aportan
intervalos; ver la tabla.

Dos añadidos exclusivos de 2016–2025:

- **Continuidad de símbolo.** Yahoo guarda la historia de un emisor bajo su
  ticker actual. Si la etiqueta ya no es un ticker SEC actual del CIK, se
  prueba ese ticker: FB → META, PCLN → BKNG, WYN → TNL… Elegir el símbolo no
  atribuye nada; deciden las comprobaciones. Así se evita, por ejemplo, el
  Yahoo «FB» de 2025–2026, que es otro valor.
- **Tiingo 2014–2026** para 32 valores cuyo listado actual cubre el tramo
  necesario, sobre todo empresas absorbidas en 2025 (ANSS, DFS, HES, JNPR,
  WBA, K, IPG…), porque FINSABER termina en 2024 y la caché Yahoo no las tiene.
  Los tickers reciclados (CA, STI, INFO, CHK…) no se piden.

**Cobertura acreditada por rebalanceo: 87,4–95,4 % (media 92,5 %)**, frente a
78,2–90,5 % en 2010–2015. Se promovieron **590 intervalos Tier A y 128 Tier B**.
Detalle en [historical-prices-quarterly-2016-2025.csv](historical-prices-quarterly-2016-2025.csv)
y [.json](historical-prices-quarterly-2016-2025.json).

| Año | Observaciones | Tier A | Tier B (FINSABER / Tiingo / WIKI) | Excluidas |
| --- | ---: | ---: | --- | ---: |
| 2016 | 2 022 | 1 548 | 244 (205 / 16 / 23) | 230 |
| 2017 | 2 023 | 1 617 | 201 (186 / 15 / 0) | 205 |
| 2018 | 2 022 | 1 675 | 165 (161 / 4 / 0) | 182 |
| 2019 | 2 020 | 1 706 | 144 (143 / 1 / 0) | 170 |
| 2020 | 2 020 | 1 738 | 109 (109 / 0 / 0) | 173 |
| 2021 | 2 020 | 1 775 | 112 (112 / 0 / 0) | 133 |
| 2022 | 2 014 | 1 825 | 81 (81 / 0 / 0) | 108 |
| 2023 | 2 012 | 1 857 | 49 (49 / 0 / 0) | 106 |
| 2024 | 2 013 | 1 873 | 47 (43 / 4 / 0) | 93 |
| 2025 | 2 012 | 1 872 | 24 (0 / 24 / 0) | 116 |

Motivos de exclusión (1 516 de 20 178 observaciones), siempre visibles en la
fila correspondiente:

- sin float SEC para comprobar el nivel: 505;
- dividendos del archivo que no cuadran con SEC: 174;
- precios incompletos: 136;
- archivo sin dividendos SEC para conciliar: 108;
- fuentes divergentes: 100;
- nivel de precio fallido: 93;
- salto sin corroborar en el archivo: 90;
- sucesión dentro de la ventana: 71;
- varios CIK en la ventana: 60;
- cotización que empieza después de la ventana: 51;
- baja antes del final de la ventana: 32;
- identidad sin resolver: 29;
- ajuste inexplicado en el archivo: 4;
- ventanas elegidas cuyo intervalo no pudo promoverse (JCI, LLL, COL, PXD,
  TIF): 63.

Periodo de tenencia de las ventanas acreditadas:

- cubierto hasta el siguiente rebalanceo: 18 394;
- cortado en un límite de identidad: 165;
- huecos: 41;
- ajuste sin conciliar: 23;
- baja con evento terminal: 20;
- sucesión: 19.

Una nota de ajuste Yahoo sin conciliar en una ventana Tier A aceptada (por
ejemplo, el salto de UAL en marzo de 2020) se guarda como evidencia que cita la
fila de la auditoría. Antes hacía rechazar el intervalo entero.

## 4. Eventos terminales y sucesiones

Cada miembro que deja de cotizar antes del siguiente rebalanceo tiene su evento
explícito:

- **Confirmados**: 27 compras en efectivo (el importe sale del 8-K de cierre)
  y 7 sucesiones 1:1 (del 8-K12B del sucesor).
- **Desconocidos**: 29 bajas, 27 fusiones, 7 canjes por acciones y 1
  sucesión. En un backtest cuentan como resultado **no estricto**, igual que
  en 2010–2015.

Ninguna empresa desaparecida se elimina en silencio.

## 5. Motor: capa activable, camino actual intacto

`historical_pit.accredited_periods("2010-2015", "2016-2025")` activa la capa
2016–2025 para universo, identidad, precios, múltiplos y salidas del motor
existente (`universe`, `identity`, `screener_asof`, backtests V1/V2):

- sin caché por ticker;
- fundamentales por CIK: se descargaron los Company Facts de 36 CIK
  antecesores acreditados, como 21CF, Xerox Corp o L-3.

**Sin activarla, 2016+ sigue en el camino operativo.** Los rankings 2016+ de la
auditoría de universo completo se calculan sobre su `snapshot.db` congelado y
no dependen de ningún fichero modificado aquí. El #35 comparará ambos caminos.

Ranking en el motor real (camino operativo frente a capa acreditada):

| Fecha | Miembros (op. / acr.) | Con precio y capitalización (op. / acr.) | Identidad acreditada | Precio acreditado | Con score (acr.) | PER % (op. / acr.) | Momentum % (op. / acr.) |
| --- | --- | --- | ---: | ---: | ---: | --- | --- |
| 2016-07-02 | 479 / 504 | 369 / 432 | 503 | 442 | 423 | 88,9 / 89,1 | 99,2 / 99,3 |
| 2018-01-02 | 491 / 505 | 390 / 449 | 505 | 460 | 439 | 87,2 / 87,8 | 99,7 / 99,8 |
| 2019-07-02 | 497 / 505 | 408 / 447 | 504 | 458 | 441 | 90,0 / 90,8 | 99,8 / 99,6 |
| 2021-01-02 | 501 / 505 | 431 / 459 | 504 | 468 | 449 | 89,1 / 89,5 | 99,3 / 99,3 |
| 2022-07-02 | 498 / 503 | 451 / 471 | 501 | 480 | 466 | 92,0 / 91,5 | 100,0 / 99,8 |
| 2024-01-02 | 503 / 503 | 470 / 464 | 503 | 473 | 460 | 88,5 / 90,1 | 99,6 / 99,8 |
| 2025-07-02 | 503 / 503 | 476 / 462 | 503 | 474 | 460 | 92,4 / 93,3 | 100,0 / 100,0 |

PER y momentum se miden como porcentaje de las empresas con capitalización.

- **2016–2019**: la capa acreditada tiene más miembros (los que faltan en
  hanshof) y más empresas con precio y capitalización (+39 a +63).
- **2024–2025**: tiene algo menos, porque exige evidencia SEC donde el camino
  operativo usa el precio por ticker sin verificar.
- **Métricas**: su cobertura es parecida en ambos caminos. La diferencia
  2016–2017 que motivó el issue (PER 58 %) procede de otra base de medida: se
  debe a quién entra en el universo con precio, no a la cobertura de las
  métricas.

## 6. Sesgo de exclusión

Cobertura acreditada por grupo (observaciones miembro-trimestre):

| Grupo | Observaciones | Utilizables | % |
| --- | ---: | ---: | ---: |
| Sale del índice en los 12 meses siguientes | 895 | 646 | 72,2 |
| Sigue en el índice | 19 283 | 18 016 | 93,4 |
| Quintil de float 1 (menor) | 4 003 | 3 600 | 89,9 |
| Quintil de float 5 (mayor) | 3 989 | 3 753 | 94,1 |
| Sin float SEC | 270 | 82 | 30,4 |
| SIC 73 (software y servicios) | 2 180 | 1 938 | 88,9 |
| SIC 20 (alimentación) | 804 | 643 | 80,0 |
| SIC 49 (utilities) | 1 390 | 1 377 | 99,1 |

El sesgo va en la dirección esperada: las empresas que salen del índice,
normalmente por caída o absorción, están peor cubiertas (72 % frente a 93 %).
Una evaluación con esta capa sigue sesgada hacia supervivientes, aunque mucho
menos que el camino operativo, que no incluye esas empresas. El SIC es un proxy
de sector del emisor, no el GICS histórico, y las observaciones trimestrales
repetidas no son independientes.

## Límites

- FRC y SBNY no son acreditables vía SEC.
- Un Form 25 de bonos poco antes de una compra puede adelantar la «baja» de un
  emisor. Pasa con EVHC, que se excluye desde 2017-07, y es un error
  conservador.
- Los eventos terminales desconocidos no se valoran; el backtest los marca como
  no estrictos.
- En 2025 el Tier B depende solo de Tiingo, porque FINSABER termina en 2024.
- Reproducir: `python -m gabi.historical_membership --import-full-reference`;
  `python -m gabi.historical_identity_audit --period 2016-2025 …`;
  `python -m gabi.historical_price_audit --period 2016-2025 --quarterly --terminal-events --promote`.
