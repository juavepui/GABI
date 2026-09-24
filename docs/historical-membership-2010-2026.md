# Composición histórica del S&P 500: issue #26

Auditoría local realizada el 24 de septiembre de 2026. Se revisaron `main`, la
auditoría del [#25](historical-data-audit.md), README, módulos de universo,
ranking/backtest, esquema, archivo histórico y tests antes de cambiar código.
**No se descargaron nuevos datasets.** La composición ya existía en dos sitios:
`data/sp500_historical_membership.csv` (operativa) y la tabla
`historical_membership` (archivo de fuentes). No se creó una tabla paralela.

## Fuentes y decisión

| Fuente | Uso | Cobertura local | Licencia y procedencia | Límite principal |
| --- | --- | --- | --- | --- |
| [hanshof/sp500_constituents](https://github.com/hanshof/sp500_constituents) + [ledger de eventos revisados](data-refresh-2026-09-23/README.md) | Fuente operativa conservada para no alterar los backtests 2016–2025 | 1996-01-02 a 2026-09-23 | [MIT](https://github.com/hanshof/sp500_constituents/blob/main/LICENSE); CSV local SHA-256 `b82f0b753b96795f81570ee526eb29bfb3eb9fa45a507811af1a4da97fb1a5d3`; eventos posteriores a 2025-08-23 con enlaces y ancla en `src/gabi/resources/sp500_extension.json` | Reconstrucción comunitaria, sin certificación oficial; una fecha duplicada contradictoria en la caché |
| [fja05680/sp500](https://github.com/fja05680/sp500) | Contraste independiente 2010–2015 | 1996-01-02 a 2015-12-31 en SQLite | [MIT](https://github.com/fja05680/sp500/blob/master/LICENSE); commit `a2430f2af0c79ddf0748e91de11bdeb1616ab5a7`, SHA-256 `36326709d46d6cd25834de5df457b16f5f96fad3a06b9beac28f7b88aa0b0d54` en el manifiesto `src/gabi/resources/historical_sources_1996_2015.json` | El autor advierte de miembros posiblemente ausentes al principio y de la necesidad de datos de precios deslistados; la serie usa tickers, no identificadores permanentes |

Las dos fuentes son gratuitas y sus repositorios declaran MIT. Esto describe la
licencia de los repositorios; no convierte las listas en datos oficiales de S&P.
Ambas reconstruyen a posteriori la composición vigente por fecha. **La
pertenencia es aproximadamente point-in-time**, mientras que la identidad de
cada ticker solo se considera acreditada si existe un alias fechado y revisado
en `entity_aliases`. Un candidato de `historical_issuer_candidates` o un CIK
actual no se eleva a identidad histórica.

Se mantiene hanshof como fuente operativa para conservar comparabilidad con los
resultados ya publicados. fja05680 se conserva separada para contraste; las
diferencias se devuelven como conflicto, sin fusionar miembros ni elegir el
resultado más favorable. La mayor cobertura de fja05680 en algunos años no
demuestra por sí sola que cada ticker sea correcto.

## Comparación reproducible

`python -m gabi.historical_membership` compara las dos listas en **cada fecha
de cambio registrada por cualquiera de las dos fuentes** entre 2010-01-01 y
2016-01-01. La diferencia es el tamaño de la diferencia simétrica de tickers
normalizados (punto/guion); no mide rentabilidad ni calidad de señales.
`python -m gabi.historical_membership --date 2010-06-30` muestra un resumen
de una fecha, incluidos conflictos y número de identidades acreditadas.

| Año | Fechas comparadas | Fechas con discrepancia | Diferencia media de tickers | Máxima |
| --- | ---: | ---: | ---: | ---: |
| 2010 | 100 | 100 | 52,65 | 54 |
| 2011 | 106 | 106 | 48,41 | 51 |
| 2012 | 105 | 105 | 41,76 | 44 |
| 2013 | 106 | 106 | 37,42 | 39 |
| 2014 | 100 | 100 | 34,68 | 36 |
| 2015 | 117 | 117 | 33,76 | 35 |

La discrepancia es material: no se debe presentar el universo 2010–2015 como
certificado. Es posible que parte sean cambios de ticker retrospectivos, pero
atribuirlos sin contrastar documentos generaría falsas identidades. En
`2010-06-30`, hanshof enumera **445** símbolos y fja05680 **499**: los
54 adicionales solo aparecen en la segunda fuente. Entre ellos está `AABA`,
etiqueta posterior de Yahoo; por eso un recuento más cercano a 500 tampoco
acredita que las etiquetas fueran utilizables en 2010.

La fecha `2022-06-21` aparece dos veces con composiciones contradictorias en la caché
operativa. La consulta nueva bloquea esa fecha y el tramo hasta el siguiente
snapshot no conflictivo; los intervalos anteriores terminan con
`end_reason="source_gap"`. `2023-05-14` también está duplicada, pero ambas
filas son equivalentes tras normalizar punto/guion; se deduplican sin pérdida
de miembros.

## Consulta temporal

`historical_membership.constituents_as_of("2010-06-30")` lee la caché y la
tabla local, **sin red**. Devuelve símbolos, fuente, fecha de snapshot, ventana
de cobertura, comparación con la segunda fuente y una fila por miembro con
`valid_from` inclusiva, `valid_to` exclusiva, `end_reason`, estado de
pertenencia, `entity_id`/CIK cuando un alias fechado lo acredita, y
`identity_status` (resuelto, no resuelto o ambiguo). Un ticker que sale y
reingresa genera dos intervalos. El límite de cobertura se marca como
`source_boundary`; no se infiere que la empresa saliera del índice. La fuente
fja05680 puede consultarse explícitamente con `source_id=REFERENCE_SOURCE`.

`universe.get_sp500_constituents_asof` conserva su interfaz usada por ranking y
backtest dentro de la cobertura. Después del último snapshot, lanza `ValueError`
en lugar de sustituir silenciosamente la lista por los componentes actuales.
`is_exact=True` significa únicamente fecha cubierta, **no membresía verificada**.
El último snapshot operativo es el 2026-09-23; no hay declaración sobre el
2026-09-24 ni fechas posteriores. La fuente fja05680 termina el 2015-12-31.

## Pendiente antes de un backtest largo fiable

1. Arbitrar las 30–54 discrepancias típicas por fecha en 2010–2015 con avisos
   oficiales y registros corporativos, conservando las decisiones y sus fuentes.
2. Resolver el día contradictorio de 2022 con evidencia primaria; hasta
   entonces, ese tramo queda como cobertura desconocida.
3. Acreditar alias históricos, fusiones, clases de acción y reutilización de
   ticker. La tabla local `entity_aliases` aún no contiene vínculos para los
   cientos de miembros de 2010–2015.
4. Completar precios ajustados, salidas de cotización y fundamentales antiguos
   antes de interpretar una mejora de rentabilidad. Esta issue no los descarga.
