# F7.4: retirada de Factor Lab (#90)

`application/research/factor_engine.py` coordina lectores explícitos de membresía,
ranking, muestreo y precios, con fecha de observación obligatoria. El dominio
`domain/research/factors.py` conserva sesiones de entrada/salida, retornos futuros
sin costes, quintiles, IC de Spearman, neutralización sectorial, turnover,
estadísticas y orden de las tablas. Devuelve el estado entre periodos sin modificar
el estado ni rankings recibidos. El umbral mínimo de filas es explícito; el
valor de producción sigue siendo cuatro empresas por quintil.

El worker compone el mismo caso de uso con el puente histórico acotado de
`infrastructure/legacy/factors.py` y `SqliteFactorPrices`. El reloj del worker se
inyecta; no se cambia configuración global. El puente mantiene las consultas
legacy de membresía/ranking y su comprobación de directorio compartido hasta
migrar esos módulos del núcleo. Los precios siempre usan las sesiones mínima y
máxima necesarias por periodo, con límites y corte de reservas de F6.

Estimaciones y sus jobs utilizan las sesiones/retornos del mismo dominio; dejan
de importar el módulo plano. Se elimina `gabi/factor_lab.py` y su excepción de
tipos: no tiene otros consumidores ni manifiestos sellados que exijan conservarlo.
El inventario baja a 80. Los contratos, artefactos guardados y etiquetas de
evidencia exploratoria no cambian; no se consultan reservas ni fuentes externas.

## Equivalencia y medición

46 tests sobre Factor Lab, Estimaciones y jobs, incluidos diez nuevos.
`tests/fixtures/factor_migration.json` registra resultados y SHA LF del código
anterior `486942a` sobre lectores en memoria. Siete escenarios cubren empates,
ausencia/ausencia parcial de sector, precio de salida faltante, cobertura
insuficiente y membresía inexacta. Se verifica el día explícito, las ventanas
exactas, estado sin mutación, ausencia de red/SQLite en dominio e inyección del
reloj desde el worker. Las pruebas anteriores declaran lectores temporales y
umbrales por parámetros, en lugar de parches de dependencias de producción.

`scripts/measure_f7_factor_analysis.py` compara el flujo completo anterior y
nuevo con el mismo lector SQL acotado usado por el job F6: SQLite temporal,
50 empresas, 2 rebalanceos, 4 horizontes y 2.216 sesiones almacenadas. Se calientan
las bibliotecas/calendario y se toman tres repeticiones. Los cuatro DataFrames y
periodos omitidos coinciden exactamente. Mediana local Windows:

| Implementación | Segundos | Pico Python trazado (MiB) |
| --- | ---: | ---: |
| Anterior | 2,8188 | 4,400 |
| Nueva | 2,7911 | 4,346 |

Se conserva el camino de datos de F6; no se atribuye una mejora de rendimiento
al traslado. Son tiempos de esta fixture y memoria Python trazada, no RSS.
No se añade caché; siguen la invalidación y límites del lector F6. La medición
auxiliar de lectura completa frente a ventana sigue disponible en
`scripts/measure_f6_factor_prices.py`; no se confunde con el flujo completo.

Arquitectura, Ruff, tipos y motores congelados acompañan la entrega. La CI
completa valida consumidores, contratos y navegador antes de integrar.
