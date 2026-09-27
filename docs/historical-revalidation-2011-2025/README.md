# Revalidación 2016–2025 y 2011–2025 con datos acreditados (issue #35)

Protocolo registrado antes de ejecutar: [PROTOCOL.md](PROTOCOL.md), commit
`eda8d64`. Sin reoptimizar: pesos 30/35/25/10, Top-10/20, cobertura
≥ 70 %/50 %, rebalanceo trimestral el día 2 y V2 con 1 USD + 10 pb.
Resultados completos en [summary.json](summary.json) y en una carpeta por
vista. Cada una contiene `audit.json`, periodos V1/V2, NAV, cobertura y, en las
vistas acreditadas, cobertura por rebalanceo y benchmarks. La descomposición
está en [pasos/](pasos/).

## Conclusión

**La ventaja frente al SPY sobrevive a los datos acreditados, pero sin
significación estadística** (regla del protocolo: *sobrevive sin
significación*).

- **Vista principal** (capa acreditada + corrección #38, V2 Top-20,
  2016-01 → 2025-10): **19,4 % anual neto frente al 15,0 % del SPY**. El
  Sharpe es 0,77 ± 0,36 frente a 0,61 ± 0,35. El exceso trimestral V1 medio es
  de +0,91 puntos, con t = 1,40 en 37 trimestres, por debajo del umbral 1,96.
- **Respecto a la auditoría publicada** (21,1 %; Top-10, 23,7 %), el resultado
  baja 1,7 puntos. Casi todo lo explican la capa acreditada (−0,9) y la
  corrección #38 (−0,8). La deriva de código entre la auditoría publicada y
  hoy no cambia el Top-20.
- **Serie continua** 2011-07 → 2025-10 (57 trimestres ejecutados, 54
  concluyentes): **18,8 % frente al 14,0 % del SPY**. El Sharpe es
  0,77 ± 0,30 frente a 0,58 ± 0,29, y t = 2,18 en 55 trimestres V1. Es la
  evidencia más favorable, pero incluye 2011–2015, ya evaluado en el #33, y
  no cumple por sí sola la regla (que se define sobre la vista 2016). Además,
  el Sharpe de la estrategia y el del SPY no se separan más allá de sus
  errores estándar.

GABI no pierde frente al SPY con datos acreditados en ningún corte
(2016–2025, 2011–2025, Top-10 ni Top-20). La magnitud del exceso (3–5 puntos
anuales) no es distinguible del ruido con esta historia.

## Desviaciones técnicas (ninguna motivada por resultados)

1. **Hechos SEC por CIK incompletos (fallo del #34).** En la primera ejecución,
   el V1 acreditado solo corrió 6 de 39 trimestres. 128 de los 700 CIK
   acreditados de 2016–2025 (empresas fuera del universo operativo, como GT,
   FLS, LNC o NOV) solo tenían hechos hasta 2015. Eso congelaba sus
   fundamentales y hacía saltar el guard de reciclaje. Se reingirieron sus
   Company Facts y se repitieron las variantes acreditadas con snapshot
   nuevo. Ahora `prepare` comprueba esto antes de empezar (`stale_issuer_facts`).
2. **Dos trimestres V1 descartados** en las vistas acreditadas por falta de
   precio de salida o entrada: NKTR en 2019-10 y JNPR en 2025-07 (HPE cerró la
   compra el mismo 2 de julio). El V1 descarta el periodo en vez de inventar
   un precio, como en el #33. El V2 ejecuta los 39 trimestres.
3. **Régimen (#13).** Por ese hueco la serie V1 no es consecutiva, así que se
   usaron los retornos trimestrales del V2 Top-20 (NAV entre salidas).
4. **DSR/PBO en la capa acreditada no calculable.** La reconstrucción del #12
   marca cada cartera a precio en fechas trimestrales y no admite eventos
   terminales. Falla con RAI (Reynolds American, comprada en 2017). Se
   registra el motivo. En `operativo` sí se calcula.
5. **Anualización.** El compuesto del retorno implícito de los excluidos cae
   por debajo de −100 %; su tasa anual se deja vacía en vez de un número
   complejo. Solo afecta al análisis y se repitió sobre los backtests
   congelados.

## Resultados por vista (V2, 100.000 USD, 2016-01-04 → 2025-10-02)

| Vista | CAGR Top-20 | Sharpe Top-20 (± EE) | Máx. drawdown | ES 95 % diario | Rotación | CAGR Top-10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Auditoría publicada | 21,1 % | 0,86 | −38,2 % | — | — | 23,7 % |
| `operativo` (código de hoy) | 21,1 % | 0,87 ± 0,38 | −35,1 % | 2,99 % | 73 % | 22,8 % |
| `operativo-38` | 20,1 % | 0,84 ± 0,37 | −32,2 % | 2,89 % | 78 % | 22,1 % |
| `acreditado` | 20,2 % | 0,79 ± 0,37 | −35,4 % | 3,10 % | 71 % | 22,2 % |
| **`acreditado-38`** (principal) | **19,4 %** | **0,77 ± 0,36** | **−32,8 %** | 3,00 % | 71 % | 21,0 % |
| SPY | 15,0 % | 0,61 ± 0,35 | −33,7 % | — | — | 15,0 % |

Exceso trimestral V1 Top-20 frente al SPY:

| Vista | Media | t | Trimestres por encima |
| --- | ---: | ---: | ---: |
| `operativo` | +1,28 pp | 2,38 | 27 / 39 |
| `operativo-38` | +1,12 pp | 1,98 | 30 / 39 |
| `acreditado` | +1,16 pp | 1,95 | 27 / 37 |
| **`acreditado-38`** | **+0,91 pp** | **1,40** | **23 / 37** |

**Resultado estricto.** En la vista principal, el Top-20 tiene cinco
posiciones valoradas a su último precio sin evento terminal confirmado:

- AVGO: sucesión a Broadcom Ltd en 2016-01, sin canje 1:1 acreditado;
- RAI: compra mixta por BAT en 2017-07;
- MRO: canje por acciones de ConocoPhillips en 2024-11;
- ALXN (2020-12) y ZION (2024-03): su serie acreditada termina sin evento
  terminal registrado.

El Top-10 solo tiene AVGO.

## Descomposición de la diferencia con la auditoría publicada (Top-20, 39 rebalanceos)

| Paso | CAGR | Jaccard medio de carteras V1 | Elegibles medios |
| --- | --- | ---: | --- |
| publicada → `operativo` (deriva de código y datos) | 21,1 % → 21,1 % | 0,67 | 334 → 385 |
| `operativo` → `acreditado` (capa acreditada) | 21,1 % → 20,2 % | 0,43 | 385 → 409 |
| `acreditado` → `acreditado-38` (corrección #38) | 20,2 % → 19,4 % | 0,64 | 409 → 329 |
| `operativo` → `operativo-38` (control) | 21,1 % → 20,1 % | 0,57 | 385 → 308 |
| publicada → `acreditado-38` (total) | 21,1 % → 19,4 % | 0,31 | 334 → 329 |

Qué cambia en la cartera (posiciones-trimestre del Top-20 que salen y entran;
detalle en `pasos/<paso>/atribucion-*.csv`):

- **Deriva de código.** Sale: 90 cambios de fundamentales, 54 desplazadas y 9
  por fundamentales y precio. Entra: 129 que antes no eran elegibles. Es
  sobre todo el efecto de las fórmulas point-in-time del #30 (CAGR con
  ejercicios consecutivos, reexpresiones por fecha de presentación), que
  hacen elegibles a 50 empresas más por rebalanceo. El CAGR del Top-20 no
  cambia.
- **Capa acreditada.**
  - Sale: 227 por **precio** distinto (la serie acreditada cambia momentum y
    riesgo: otra fuente, otra identidad, historia previa a una OPV descartada),
    93 sin precio acreditado y 2 fuera de la composición.
  - Entra: 236 por precio y 44 que no eran elegibles en la base. Entre ellas
    están miembros que el camino operativo no tenía.
  - **95 posiciones V2 del camino operativo** (de ~780 posiciones-trimestre)
    no superarían la acreditación: 93 sin precio acreditado y 2 fuera de la
    composición.

  La cartera cambia mucho (Jaccard 0,43), pero el resultado apenas (−0,9 pp).
- **Corrección #38.** Sale: 140 que **dejan de ser elegibles** (componentes
  obsoletos: deuda, resultado operativo o amortización de otro ejercicio;
  sus métricas quedan ausentes y bajan del 70 % de cobertura) y 25 por
  fundamentales. Los elegibles bajan de 409 a 329 por rebalanceo, y en el
  camino operativo de 385 a 308. Coste: −0,8 pp de CAGR, con un drawdown
  menor (−35,4 % → −32,8 %).
- **Frente a la publicada**, 72 posiciones-trimestre del V2 publicado no
  superarían la acreditación: 69 sin precio acreditado y 3 fuera de la
  composición.

## Serie continua 2011–2025 (`acreditado-38`, desde 2010-01-02)

- **Rebalanceos**: 63 previstos, 57 ejecutados en V2. Los 6 de 2010-01 a
  2011-04 se saltan por cobertura del universo inferior al 50 %, como en el
  #33: faltan tres ejercicios XBRL.
- **Concluyentes**: 54 de 57, con precio acreditado ≥ 85 % y elegibles ≥ 50 %.
  Los tres no concluyentes son 2012-01, 2012-04 y 2012-07, con precio
  acreditado del 82–85 %.
- **Cobertura por rebalanceo ejecutado**: precio acreditado del 81,7 % al
  95,4 % y elegibles del 51,9 % al 70,2 %
  ([coverage-by-rebalance.csv](acreditado-38-continua/coverage-by-rebalance.csv)).
- **Tramo invertido** (2011-07-05 → 2025-10-02): V2 Top-20 18,8 % frente al
  14,0 % del SPY. Sharpe 0,77 ± 0,30 frente a 0,58 ± 0,29. Drawdown −32,8 %
  frente a −33,7 %.
- **Benchmarks**, anualizados sobre los trimestres V1 ejecutados:

  | Serie | Anual |
  | --- | ---: |
  | V1 Top-20 | 17,8 % |
  | SPY | 13,2 % |
  | Universo elegible, equiponderado | 12,1 % |
  | Universo elegible, por capitalización | 11,9 % |
  | Cubiertos ponderados | 11,4 % |

  GABI supera al SPY y, con más margen, al propio universo que puntúa.
- **Cotas del universo completo** (los excluidos rinden como el peor o el
  mejor decil de los cubiertos): del 6,1 % al 18,2 % anual.
- **Retorno de los excluidos: no identificable.** El residual SPY − cubiertos
  se divide por el peso excluido (~9 %), lo que amplifica ~15 veces cualquier
  error de los pesos proxy. Su compuesto sale por debajo de −100 %. Igual que
  en el #33, no se interpreta.

## Significación

- **Error estándar del Sharpe** (Lo 2002): ±0,36 en 9,75 años y ±0,30 en 14,2.
  El Sharpe de GABI supera al del SPY por menos de un error estándar en todas
  las vistas.
- **PBO/DSR (#12)**: sobre la familia documentada de configuraciones, en los
  36 trimestres 2016-07 → 2025-07.
  - En `operativo` (universo completo): DSR 0,986 y **PBO 0,55**. La
    configuración elegida supera al máximo esperado entre los ensayos, pero la
    probabilidad de que el mejor ensayo dentro de muestra quede por debajo de
    la mediana fuera de muestra es del 55 %.
  - En la capa acreditada no es calculable (desviación 4).
- **Régimen (#13)**, FF5 + Momentum sobre la vista principal (V2 Top-20):
  - **Muestra completa**: alfa anualizado +4,7 %, t HAC 1,51, R² 0,82.
  - **Primera mitad** (2016-07 → 2021-01): +3,3 % (t 1,04).
  - **Segunda mitad** (2021-01 → 2025-07): −1,7 % (t −0,24).
  - Ninguno es significativo y el signo cambia entre mitades, como en el #13.
    La beta de mercado es 0,89, y las exposiciones a tamaño, value y
    rentabilidad son positivas.

## Límites

- 2016–2025 es la muestra en la que se diseñó GABI. La capa acreditada corrige
  los datos, pero no convierte este periodo en fuera de muestra.
- Las salidas no estrictas (5 en el Top-20 principal) se valoran a su último
  precio. Una valoración terminal distinta cambiaría poco el CAGR, pero el
  resultado no es estricto.
- La corrección #38 se aplica como corrección de datos. Reduce la cobertura
  (329 elegibles de media) sin cambiar pesos ni umbrales. Un tratamiento más
  fino, por ejemplo la deuda con evidencia explícita de cero, podría
  recuperar parte de esa cobertura, pero no estaba en el protocolo.
- La auditoría publicada se generó con código anterior. Su comparación directa
  mezcla deriva de código y datos, por eso se descompone por pasos.

## Reproducibilidad

- **Código**: `python -m gabi.historical_revalidation --prepare <variante>`,
  `--evaluate <vista>` y `--summarize`; `--analyze <vista>` rehace solo el
  análisis.
- **Protocolo**: `eda8d64`.
- **Fingerprints**: cada caché (`data/revalidation_2011_2025/<variante>`)
  guarda en `manifest.json` el SHA-256 de su snapshot, de cada ranking y de los
  ficheros de código y datos que lo determinan.
- **Informe**: `summary.json` guarda el hash del código de análisis y de cada
  artefacto.
