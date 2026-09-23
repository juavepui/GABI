# Rentabilidad sobre el universo histórico completo

Reconstrucción del 22 de septiembre de 2026. Esta ejecución responde a la
petición de medir GABI desde 2016 sin limitar el ranking a una muestra de 200
empresas. Es una simulación retrospectiva con la caché actual, no rentabilidad
de una cuenta real ni una prueba independiente de las decisiones de diseño.

## Alcance fijado antes del cálculo

- Primer ranking: 2016-01-02; primera compra: 2016-01-04.
- Último ranking: 2025-07-02; valoración final: 2025-10-02.
- 39 trimestres previstos. Se consideran todos los constituyentes que la fuente
  histórica enumera en cada fecha; `max_symbols=None`.
- Top-10 y Top-20 equiponderados, rebalanceo trimestral, sin filtro de mercado
  ni banda de permanencia. No se buscaron nuevos pesos, fechas o variantes.
- Pesos Value/Quality/Momentum/Risk: 30/35/25/10. Cobertura mínima por empresa:
  70%; mínima del universo por fecha: 50%.
- Resultado principal: motor V2, capital inicial de 100.000 USD, 1 USD por
  operación y spread total de 10 pb (5 pb por lado). Se conserva la caja y se
  valora diariamente. SPY se compra una vez al inicio y se mantiene.
- Comparación auxiliar: motor V1 con 10 pb por lado. Sus retornos agregados por
  trimestre y su modelo de costes difieren de la contabilidad diaria de V2.

La caché contiene precios de SPY hasta 2026-09-22, pero la composición histórica
del índice termina en 2025-08-23. Se puede mantener la cartera elegida en julio
de 2025 hasta octubre, pero no reconstruir el siguiente rebalanceo con una
composición histórica verificada. No se sustituye por el universo actual.

Se han considerado **686 símbolos distintos** a lo largo del intervalo, entre
470 y 504 por fecha. **463 símbolos distintos** resultan elegibles al menos una
vez, entre 254 y 398 por fecha. La cobertura elegible varía entre **54,04% y
79,13%**. El benchmark dispone de precios ajustados en las **2.452 sesiones**
del intervalo, sin huecos.

## Resultado de esta ejecución

| Cartera | Capital final (100.000 USD iniciales) | Retorno total | CAGR neto | Máximo drawdown | SPY CAGR neto |
|---|---:|---:|---:|---:|---:|
| V2 Top-10 | 793.050,94 USD | 693,05% | **23,68%** | −35,93% | 15,00% |
| V2 Top-20 | 647.145,39 USD | 547,15% | **21,12%** | −38,17% | 15,00% |

Las dos carteras tienen 39/39 periodos ejecutados y ninguna comprobación de
valoración diaria detectó sesiones sin precio para una posición mantenida. El
turnover medio fue 77,24% por rebalanceo en Top-10 y 74,72% en Top-20; las
comisiones sumaron 530 USD y 1.048 USD respectivamente. El exceso histórico
frente a SPY es, por tanto, de aproximadamente **8,68 puntos porcentuales de
CAGR** para Top-10 y **6,12 puntos** para Top-20, dentro de esta reconstrucción.

Como contraste, V1 (retorno trimestral agregado, 10 pb por lado) da 23,30% y
21,04% de CAGR para Top-10 y Top-20, respectivamente. Se conserva como control
del motor anterior; la cifra que debe citarse para esta auditoría es la V2, que
incluye caja, operaciones y costes explícitos.

## Cómo se calcula y se conserva

El CAGR principal se calcula como
`(capital_final / 100000) ** (365.25 / días_transcurridos) - 1`, desde el primer
día de inversión al último. Incluye el coste inicial: usar el primer NAV como
denominador lo eliminaría. Las métricas de riesgo diarias utilizan sesiones
bursátiles; su anualización de 252 sesiones puede diferir de ese CAGR de
calendario. Los retornos están en USD, con precios ajustados por dividendos y
splits, antes de impuestos personales y conversión de divisa. El capital final
es una valoración de la cartera, sin liquidación final.

```powershell
.venv/Scripts/python.exe -m gabi.full_universe_audit
```

La preparación guarda una copia consistente de SQLite, un manifiesto y los
rankings de las 39 fechas en `data/full_universe_audit/` (ignorado por Git).
Es reanudable y rechaza cambios de los inputs congelados. `--prepare-only`
prepara los rankings; `--run-only` evalúa los ya guardados. Los dos motores y
los dos tamaños de cartera usan exactamente los mismos rankings completos.
El informe conserva hashes de los inputs y de los artefactos publicados.

## Límites de interpretación

Usar el universo completo elimina el recorte aleatorio a 200 empresas. No
rellena los datos de empresas excluidas por cobertura. La ausencia de compañías
deslistadas o adquiridas puede sesgar la selección. La fuente histórica tampoco
enumera exactamente 500 títulos en cada fecha. Se publican los recuentos y las
listas elegibles/excluidas, no se afirma una cobertura del 100%.

Persisten las limitaciones de identidad histórica y de sector aproximado de la
caché. Los resultados de PBO/DSR y de regresiones de factores de las auditorías
anteriores corresponden a sus propias series; no se trasladan automáticamente
a esta ejecución.

El 22,95% del Top-10 correspondía a otra reconstrucción: motor V1, muestra de
200 empresas y 36 trimestres desde julio de 2016 hasta julio de 2025. No es la
rentabilidad del universo completo. Tampoco se han reconciliado las series de
las antiguas tablas de 17,70% y 19,52%, que deben conservarse como resultados de
versiones anteriores y no combinarse con esta medición.
