# Estabilidad ante perturbaciones pequeñas (#51)

Preregistro `bc02a10`; motor y UI `f9d79d4`. El análisis lee únicamente los 57 rankings acreditados de julio de 2011 a julio de 2025. No consulta retornos posteriores, no elimina empresas por falta de retorno y no vuelve a ejecutar backtests.

## Resultados

| Diagnóstico | Media entre fechas |
|---|---:|
| Spearman del ranking completo | 0,99829 |
| Kendall del ranking completo | 0,97010 |
| Persistencia Top-10 | 96,72 % |
| Persistencia Top-20 (score de estabilidad) | 97,21 % |
| Persistencia Top-30 | 97,09 % |
| Entradas/salidas del Top-20 por perturbación | 0,558 |

La persistencia media del Top-20 por fecha va del 94,58 % al 100 %. Una perturbación individual sustituye como máximo tres integrantes. De 1.140 observaciones empresa-fecha inicialmente en el Top-20, 992 permanecen en todas las perturbaciones y 148 son frágiles en alguna. Estas últimas se identifican individualmente en `companies.csv` y en la app.

El ranking presenta poca fragilidad en esta vecindad concreta. **Esto no demuestra que prediga retornos**, no corrige selección retrospectiva y no autoriza elegir otros pesos. Tampoco prueba robustez frente a fuentes de datos, universos o parámetros distintos. Las fracciones describen 24 cambios deterministas, no probabilidades futuras.

Los sectores históricos no están disponibles: se declara su ausencia y no se usan sectores actuales. La concentración por empresa de una cesta equiponderada es mecánicamente 1/N. El código y las pruebas sintéticas verifican el diagnóstico sectorial cuando sí hay datos contemporáneos completos.

## Uso y trazabilidad

`python -m gabi.rank_stability --analyze` verifica la especificación y genera métricas por perturbación, fecha y empresa, además del resultado agregado. `resultado.json` contiene la huella de la especificación, el commit del motor y los hashes de los 57 rankings, el manifiesto y todos los CSV exportados. `load_saved()` detecta alteraciones de los artefactos publicados.

Investor muestra persistencia y rango de posiciones del Top-20 con los pesos congelados. Research muestra también todas las empresas, métricas y transferencias para los pesos experimentales actuales. Research Lab permite consultar las fechas históricas. La elegibilidad se calcula antes de aplicar filtros visuales y la estabilidad no cambia scores, cobertura, pesos ni asignación de capital.

Validación: 22 pruebas enfocadas superadas, incluidas las interacciones reales de Screener y Research Lab, rankings sintéticos estables/frágiles, límites de pesos, empates, datos ausentes y detección de artefactos alterados. Ruff y mypy pasan para los módulos nuevos; permanecen las incidencias globales de lint/tipos previamente documentadas en #50.
