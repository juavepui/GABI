# Preregistro: capacidad predictiva en sección cruzada (#40)

Escrito **antes de calcular ningún retorno ni IC** (2026-09-27). La
especificación exacta está en [`preregistro.json`](preregistro.json), con su
SHA-256 (`cross_section_test.spec_hash()`), y en la tabla `experiments`
(familia `stat_2`).

## Pregunta

¿Ordena el Composite vigente (30/35/25/10, sin cambios) a las empresas del
S&P 500 según su rentabilidad del trimestre siguiente mejor que el azar? Si
no lo hace, la ventaja del Top-20 frente al SPY sería suerte. Si lo hace de
forma consistente, la ventaja tiene una base estadística. El #39 muestra que
esta prueba tiene mucha más potencia que comparar el Top-20 con el SPY.

## Datos

- **Rankings**: los congelados de la variante principal del #35 (capa
  acreditada + corrección #38), en los 57 rebalanceos invertidos
  (2011-07-02 → 2025-07-02).
- **Elegibles**: los mismos que usa el backtest (composite no vacío y
  cobertura ≥ 70 %), unas 250–450 empresas por trimestre.
- **Retorno siguiente**: de la sesión posterior a la señal a la primera sesión
  tras +3 meses, sobre la serie acreditada. Si la serie termina antes, se usa
  el evento terminal o el último precio no estricto, como en el backtest.

## Pruebas

**Principal.** IC de Spearman por trimestre entre `composite_score` y el
retorno siguiente. Media de los 57 trimestres y error estándar Newey-West.
Hipótesis unilateral: IC medio > 0, con α = 5 %.

**Secundarias** (corrección de Holm sobre las dos, unilateral):

1. Fama-MacBeth: pendiente del percentil del composite (0–1) con dummies de
   sector y log de la capitalización; t Newey-West de la pendiente media.
2. Diferencia de quintiles Q5 − Q1, equiponderada, con t Newey-West.

**Descriptivas**, que no deciden nada:

- Top-20 frente al universo elegible. Se vio en el #39 (t = 2,70), así que no
  es confirmatoria.
- IC de cada bloque y por ventana (2011–15, 2016–20, 2021–25).
- Medias de los quintiles y trimestres con IC positivo.

## Decisión

| Resultado | Condición |
| --- | --- |
| Capacidad predictiva robusta | principal p < 0,05 y las dos secundarias significativas tras Holm |
| Capacidad predictiva confirmada | principal p < 0,05 y las dos secundarias con estimación > 0 |
| Indicio no concluyente | IC medio > 0 con p ≥ 0,05 |
| Sin capacidad predictiva | IC medio ≤ 0 |

No cambia el modelo ni la prueba ciega. El resultado se publicará sea cual sea.

## Límites conocidos de antemano

- **Retrospectivo**: incluye la muestra de diseño (2016–2025) y los datos de
  2011–2015 ya usados en el #33 y el #35.
- **IC ≠ cartera**: un IC positivo indica capacidad de ordenar, no que el
  Top-20 supere al SPY después de costes. Ambas pruebas son complementarias.
- **Sectores aproximados** para empresas que ya no existen: su sector
  histórico no está disponible en fuentes gratuitas.
