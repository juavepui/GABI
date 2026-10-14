# Retirada de `blind_validation` (F7.26, #90/#91)

La validación ciega prospectiva (`HIPOTESIS_CONGELADA.md`) deja de ser un módulo plano.
Su almacenamiento ya estaba en infraestructura (#140); ahora también sus reglas y su flujo:

| Pieza | Ahora |
| --- | --- |
| Elegibles (puntuación y cobertura ≥ 0,7), precio de entrada, hash encadenado, instantánea del ranking, valoración a mercado, revelado y próximo rebalanceo | `domain/research/blind.py` (puro) |
| Crear, registrar un rebalanceo inmutable, activar instantáneas, integridad, estado sellado, romper el sello, listar, exportar al registro de experimentos | `application/research/blind_ledger.BlindLedger`, con puertos explícitos: almacén, ranking a fecha, precios, commit git, día, sello horario local y registro de experimentos |
| Nombres públicos de siempre (`create_validation`, `record_rebalance`, `get_status`…) | `infrastructure/legacy/blind_validation.py`: construye `BlindLedger` en cada operación con `config.DB_PATH` (ADR 0005), `screener_asof.build_ranking_as_of`, la caché de precios, `research_environment.git_commit` y `research_lab.log_experiment` |

El código se ha movido sin cambiar fórmulas, el orden de las escrituras ni el texto de
los errores. Las marcas de tiempo siguen siendo la hora local de `pd.Timestamp.now()`
y el día el de `date.today()`, como antes. `get_status` verifica la cadena con los
periodos que ya ha leído en lugar de releerlos (mismo resultado, una lectura menos).

Consumidores: `infrastructure/legacy/blind.py` (escrituras de la API y trabajos del
worker), `periodic.record_rebalance` y `value_hypothesis` importan el adaptador.
Ningún motor congelado, huella publicada ni `model_version` leía el módulo por nombre;
`r3_experiment` y `app_mode` solo usan la cadena `"blind_validation"` como etiqueta.

## Pruebas y medida

`test_research_ledgers_migration.test_blind_validation_matches_capture` recorre la
sesión completa (crear, rebalanceos con y sin cobertura, duplicados, ruptura del sello,
estado, exportación) contra el módulo capturado antes de #140: mismos resultados y
mismas tablas. La comprobación de `app_mode` capturado inyecta el módulo plano
capturado solo dentro de su contexto. El resto de pruebas de la validación ciega
(`test_blind_validation`, `test_app_mode`, `test_research_blind_*`,
`test_periodic_tasks`) usa el adaptador.

`scripts/measure_f7_research_ledgers.py` (Windows/Python 3.12, base temporal,
2.000 experimentos, 40 periodos): paridad exacta; estado de la validación 0,71 s con la
referencia capturada y 0,69 s ahora.

Inventario: 65 módulos planos = 18 congelados + 37 permanentes + 10 pendientes.
