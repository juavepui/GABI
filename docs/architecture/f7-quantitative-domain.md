# F7.4: indicadores, riesgo y estadísticas (#90)

Se extraen cinco implementaciones desde `486942af7a92bea5afa7ffec98983eeba701baad`.

| Nombre de compatibilidad | Implementación |
| --- | --- |
| `technicals` | `domain/market/technicals.py` |
| `risk` | `domain/market/risk.py` |
| `portfolio_metrics` | `domain/portfolio/metrics.py` |
| `rotation_policy` | `domain/portfolio/rotation.py` |
| `stats_rigor` | `domain/research/statistics.py` |

El dominio recibe los precios, retornos, ventanas, pesos y tipos libres de riesgo
como argumentos. `TechnicalParameters` es una dataclass inmutable; no accede a
configuración global. Las fórmulas y convenciones financieras se conservan.
Los ajustes de tipos se limitan a declarar el diccionario de resultados y a
nombrar por separado las listas y los arrays del bootstrap/PBO.

Las fachadas conservan las firmas públicas y los valores por defecto de los
consumidores antiguos. En particular, técnicos conserva el periodo RSI capturado
al importar y las otras ventanas leídas por operación; riesgo y Sharpe rodante
conservan la sustitución de `None` por el tipo configurado. Las funciones puras
restantes son alias de la implementación única. Los cinco nombres se mantienen
por sus consumidores actuales, incluidos motores congelados: el inventario
sigue en 82 módulos y reduce sus dependencias. Se retiran las excepciones de
tipado de técnicos y estadísticas, sin añadir otras.

La composición del ranking captura los parámetros técnicos una vez y usa
directamente el cálculo de riesgo del dominio. Los adaptadores de Backtests,
Portfolio Lab y Experimentos usan las métricas/estadísticas nuevas. No cambia el
acceso a datos ni se añade caché; no se atribuye mejora de rendimiento al traslado.

Las capturas futuras del ledger añaden los hashes de las implementaciones reales
de técnicos y riesgo. Eso cambia su procedencia y versión de código; las capturas
ya almacenadas, sus hashes y cadenas permanecen intactas. Los artefactos sellados
y los 18 motores/configuración congelados no se modifican.

## Evidencia

`tests/fixtures/quantitative_migration.json` contiene resultados del código
original y sus hashes LF, obtenidos con precios sintéticos. Nueve escenarios
incluyen vacío, ventana corta, precio constante, ajustados completos/incompletos,
ausencias, hueco del benchmark y pérdida total. Se comparan además ventanas
personalizadas, riesgo, cola, captura, Sharpe rodante, PSR, DSR, bootstrap con
semilla fija y PBO. Los floats usan tolerancia relativa `1e-12` y absoluta
`1e-14` por el redondeo de bibliotecas entre Linux/Windows; ausencias, estados,
fechas y recuentos se comparan exactamente. No se consultan datos de aplicación
ni reservas.

Pasan 116 tests existentes y 16 nuevos de equivalencia, ausencia de I/O,
aislamiento de parámetros, alias y procedencia. Se ejecutan arquitectura
backend/frontend, tests de las guardas, Ruff, tipos y verificación de motores
congelados. La CI completa valida también APIs, contratos y consumidores.

#90 continúa con hojas mixtas, módulos intermedios y núcleo compartido. Las
fachadas se retirarán cuando migren sus consumidores, salvo compatibilidad
exigida por los protocolos publicados.
