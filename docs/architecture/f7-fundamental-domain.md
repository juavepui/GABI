# F7.4: scoring, periodos y fundamentos SEC (#90)

| Código anterior | Destino |
| --- | --- |
| `scoring` | `domain/market/scoring.py` |
| `historical_period` | `domain/research/periods.py` |
| Cálculos y taxonomías de `edgar` | `domain/market/sec_facts.py` |
| Cálculos de `quality_persistence` | `domain/market/quality_persistence.py` |
| Coordinación point-in-time de calidad | `application/market/quality.py` |

Las fórmulas, ausencia de datos, selección de hechos, unidades, orden de tags,
revisiones, conflictos, duraciones fiscales y umbrales de scoring permanecen.
Scoring y periodos se extrajeron con contenido idéntico al commit anterior `486942a` (LF):
SHA-256 `b51a1b4929cf9f243c6c512b62e250e84f1081197320d8fae16a193d6a20d341`
y `996cbb39d4b42c1e7f486c1460bf66f0fb5758eaa2b3d418a070b780f95e290c`.

Scoring recibe después `ScoringParameters` inmutable para aislar las listas y
umbrales. La fachada captura los valores legacy por llamada, incluidos los
parches de listas del R3 congelado; el ranking nuevo conserva parámetros
independientes. Las fórmulas no cambian y el test original de rescoring R3 pasa.

El dominio SEC recibe `fiscal_alignment` y `tolerance_days` explícitos. No lee
configuración global ni usa contexto mutable. La fachada EDGAR conserva el
contexto histórico para sus consumidores pendientes y delega los cálculos en
dominio. Su red, persistencia y coordinación todavía requieren migración;
esta entrega no considera migrado el módulo EDGAR completo.

La fachada de persistencia de calidad delega su consulta en el caso de uso,
inyectando el lector histórico. El lector recibe símbolo, fecha de presentación
límite e identidad explícitos. El caso de uso no descarga ni escribe datos.
El ranking nuevo usa scoring de dominio directamente. Los nombres antiguos
siguen presentes por sus consumidores, incluidos motores congelados; el
inventario sigue en 82 archivos, con menos dependencias.

Capturas nuevas del ledger incluyen las fuentes reales de scoring y SEC. Cambia
su versión de código; no se alteran capturas almacenadas, cadenas, documentos
sellados ni los 18 motores/configuración congelados. No se añade caché ni se
atribuye mejora de rendimiento a esta extracción.

## Validación

22 tests nuevos y 88 existentes pasan (110 en total). La referencia sintética
`tests/fixtures/fundamental_migration.json` fue calculada con EDGAR y calidad
del commit anterior; guarda sus hashes LF. Ocho escenarios cubren revisión,
conflicto, hueco fiscal, ausencia, antigüedad y ceros, con/sin alineación. Floats
usan tolerancias relativa `1e-12` y absoluta `1e-14`; razones, listas, ausencias
y recuentos son exactos. Se comprueba el corte temporal e identidad del lector,
independencia del contexto legacy, ausencia de red/SQLite, alias y procedencia.

Arquitectura, Ruff, tipos, motores congelados y CI completa acompañan la entrega.
#90 sigue abierta para los módulos mixtos e intermedios y la persistencia del núcleo.
