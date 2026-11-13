# STAT-4 (#47): efecto de cola del Composite

Preregistrado el 2026-09-27 **antes de calcular las bandas y contrastes de #47**.
La especificación ejecutable se guarda en [preregistro.json](preregistro.json),
SHA-256 `423016a5919ba9bd2e0065f1687fb8ce0cb3167658d9274af116ab10eb9c234b`.

El Top-20 frente al universo ya dio +1,36 puntos por trimestre en #40 y había
sido seleccionado en el diseño de GABI. Por ello, ni un resultado significativo
de esta muestra histórica se presentará como confirmación independiente.

## Datos y asignación

Se reutilizan los 57 rebalanceos de #40 (2011-07 a 2025-07), sus rankings de
la variante `acreditado-38` y retornos futuros brutos. Elegible significa
`composite_score` finito y `score_coverage >= 0,70`. Cada trimestre se ordena
de mayor a menor puntuación, con el símbolo ascendente para desempatar.
El percentil de la posición `i` entre `N` elegibles es `(i-0,5)/N`. La banda
se asigna **antes** de excluir retornos ausentes.

Bandas fijas: 0–1 %, 1–5 %, 5–10 %, 10–20 %, 20–40 %, 40–60 %, 60–80 % y
80–100 %. Cada retorno de banda es la media equiponderada de las empresas con
retorno observado; se publica el tamaño y cobertura de cada banda. Una banda
sin retorno en algún trimestre impide la prueba, sin cambiar los cortes.

El universo de comparación usa todas las elegibles con retorno observado. SPY
procede del mismo backtest acreditado y se informa descriptivamente. RSP no
forma parte de los datos congelados de esta serie.

## Contrastes y decisión fijados

Se forman tres grupos agregados **directamente con las empresas**, no promediando
las medias de sus bandas: Top 5 %, 5–20 % y 20–100 %.

1. Salto de cola: `Top 5 % − 5–20 % > 0`.
2. Convexidad: `(Top 5 % − 5–20 %) − (5–20 % − 20–100 %) > 0`.

La unidad de inferencia es el trimestre. Para la media de cada serie se usa
Newey-West con kernel Bartlett y tres retardos fijos, prueba unilateral `t`
con 56 grados de libertad. Se aplica Holm a las dos pruebas, `alpha = 0,05`.
Solo si **ambas** son positivas y sus `p` ajustadas son menores de 0,05 se
denominará «patrón histórico compatible con cola, sin confirmación
independiente». En cualquier otro caso, «señal de cola no distinguible de
ruido o selección con esta muestra».

Los ocho excesos de banda frente al universo se examinan con pruebas bilaterales
HAC(3), corregidas conjuntamente por Holm. Son secundarios y no alteran la
decisión. Se publican retornos medios de bandas frente a universo y SPY, y
medias de las ventanas fijas 2011–15, 2016–20 y 2021–25, solo como
descripción. El Top-20 previamente observado tampoco altera la decisión.

El resultado incluirá huellas SHA-256 de código, rankings, retornos y benchmark.
No se cambiarán pesos ni el modelo Investor por esta prueba retrospectiva.
