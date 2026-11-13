# Preregistro: ensemble Valor + Calidad + Expectativas (#53)

Escrito el 2026-10-16, **antes de calcular** el ensemble, sus correlaciones,
rotación o selecciones. La especificación ejecutable está en
[`preregistro.json`](preregistro.json), con huella canónica
`8609a0770a49d00c72bf5bb507d55551eba88b895543b305ca66715292555bca`.
Si hay discrepancia, manda el JSON.

## Punto de partida

- La condición previa de #53 **no se cumple**: ninguna de las 13 señales supera
  Holm (#48), el IC del Composite incluye cero (#40, #50) y QV, QVM, QE y RCF
  fallan sus puertas (#60).
- Todo 2011–2025 ya se ha observado. Los componentes se eligen con esa
  evidencia, así que ese periodo **no puede confirmar** nada del ensemble. El
  periodo anterior a 2010 no es viable (#41) y está reservado.
- Decisión del propietario (2026-10-16): estudiar ahora **solo la robustez sin
  leer retornos** y dejar la evidencia predictiva para un registro prospectivo.

## Modelo `GABI-ENS-VQE-v1`

| Elemento | Valor |
| --- | --- |
| Componentes | bloques `value`, `quality` y `expectations` de #60, sin cambios |
| Excluidos | momentum (IC previo negativo o nulo), riesgo (sin evidencia), Composite de Investor (solo referencia) |
| Agregación | media equiponderada de los tres percentiles de bloque; los tres son obligatorios; sin imputación |
| Pesos | 1/3 cada uno; prohibido optimizarlos |
| Universo | U_t: empresas de `scores.csv` con los tres bloques; fecha no evaluable si tiene menos de 40 |
| Cartera | Top-20, máximo 6 por división SIC, desempate por símbolo, plazas vacías en efectivo |

Las cuatro señales (ENS y cada componente) se comparan sobre el mismo U_t.

## Qué se mide ahora, sin retornos

- **P1, rotación**: 1 − |S_t ∩ S_t−1| / 20 entre trimestres consecutivos
  evaluables. Mejor si es menor.
- **P2, persistencia ante ruido**: se suma ruido uniforme ±5 puntos percentiles
  a cada métrica en 200 réplicas (semilla 20261016) y se mide qué fracción del
  Top-20 permanece. Mejor si es mayor. Sensibilidad descriptiva con ±2 y ±10.
- **Descriptivos**: redundancia (Spearman entre componentes), solapamiento y
  dominancia del ensemble por un solo componente, autocorrelación del score,
  concentración por división SIC y riesgo ex ante del Top-20 (volatilidad,
  drawdown y beta pasados, capitalización).

Inferencia: bootstrap circular de bloques de 4 trimestres, 5.000 réplicas,
semilla 20261017, intervalos bilaterales al nivel 1 − 0,05/6 para las seis
diferencias ENS − componente. Si alguna fecha no es evaluable, ese endpoint
queda sin intervalo; nunca se unen fechas no vecinas.

## Decisión fijada

- **Redundante** si algún par de componentes tiene Spearman medio ≥ 0,80.
- **Equivalente a un componente** si la dominancia media es ≥ 0,75.
- **Más robusto** solo sin redundancia ni dominancia y si, frente a los tres
  componentes, P1 es menor y P2 mayor con intervalos que excluyen cero.
- **Parcial** si se cumple parte; **sin mejora** si nada.

Promediar tres percentiles reduce mecánicamente la sensibilidad al ruido:
superar P2 es esperable y poco informativo; fallarlo sí informaría. Ningún
resultado permite afirmar rentabilidad, promover ENS ni sustituir Investor, ni
cambiar componentes, pesos, ruido, umbrales o Top-N tras verlo.

## Lecturas permitidas y prohibidas

Solo se leen:

- `docs/strategy-discovery/scores.csv`, con la huella publicada por #60 y las
  columnas declaradas;
- de los rankings congelados de las 57 fechas, `volatility`, `max_drawdown`,
  `beta_calc` y `market_cap`, verificados con las huellas de #48.

Antes de nada, recalcular los bloques desde los percentiles de métrica debe
reproducir los publicados.

**Prohibido**:

- cualquier retorno: `forward-*`, `quarterly.csv`, `benchmark_periods.csv`,
  `decisions.csv` y resultados de backtests;
- `data/gabi.db` y cualquier SQLite;
- datos o resultados de #43 y #44;
- rankings fuera de 2011-07-02…2025-07-02;
- la red.

## Plan prospectivo (sellado ahora, activación explícita)

- **Requisito**: implementar antes la puntuación en vivo con SIC fechado y el
  filtro de elegibilidad de GABI. Primer registro en el primer rebalanceo del
  calendario de #43 en o después del 2026-12-21 que llegue con todo terminado;
  nunca se rellena hacia atrás.
- **Registro**: cadena de hashes con la puntuación completa y los cuatro Top-20.
- **Prueba principal**: IC de Spearman trimestral de ENS, z unilateral.
- **Pruebas secundarias**: exceso del Top-20 frente a SPY y RSP con Holm;
  rotación y dispersión frente a los componentes.
- **Revisiones**: 12, 24 y 40 trimestres, umbrales O'Brien-Fleming 3,39 / 2,28
  / 1,68, nunca antes del 2029-12-21, 2032-12-21 y 2036-12-21. ENS comparte
  métricas de valor con `GABI-VALUE-v1`, así que no se adelanta a ninguna
  revisión de #43 ni la influye.
- **Entre revisiones**: solo integridad, cobertura y continuidad; nunca
  retornos, IC ni excesos. Cualquier cambio de modelo termina el registro v1.

## Recuento de pruebas

- ENS-VQE-v1 es **una configuración candidata nueva**: mínimo conocido
  acumulado 35.
- Los Top-20 de cada componente son comparadores de diagnóstico, no
  candidatos. Proponer alguno exige un preregistro nuevo.
- Se añadirá al registro de búsquedas al publicar los resultados.

No se modifican motores congelados, modelos originales, Investor, #43, #44 ni
la prueba ciega id 1.
