# Registro de estudios (ADR 0008, fase 3)

[`register.json`](register.json) clasifica con fecha cada estudio con evidencia
sellada: continuar en paralelo, sustituir por una versión nueva o retirar. Las
decisiones del 2026-10-29 son del propietario.

| Estudio | Issue | Decisión | Próximo hito |
| --- | --- | --- | --- |
| GABI-ENS-VQE-v1 | #53, #237 | Continuar | Primer registro 2026-12-21 (ventana de cinco sesiones) |
| GABI-VALUE-v1 (ciega id 3) | #43 | Continuar | Primer registro 2026-12-21; revisiones 2029, 2032, 2036 |
| GABI-MF-v1 (ciega id 1) | #42 | Continuar | Primer registro 2026-12-21; revisión única 2029-09-21 |
| STAT-4 small/mid | #44 | Terminar y cerrar | Datos congelados como tarde el 2027-01-15; análisis único |

La #60 no es un estudio sino el objetivo de evidencia: continúa mediante #252 y su
contador de intentos no se reinicia.

## Caminos fijados

`pinned_paths` lista el código que cada estudio ejecuta en vivo. Mientras el estudio
esté activo, esos caminos no cambian de semántica: una mejora (por ejemplo las
métricas V2 de #245) va en un módulo o versión nueva. Se permiten cambios de forma
con equivalencia en fixtures. Las tres pruebas prospectivas comparten
`screener_asof.build_ranking_as_of` y `domain/market/sec_facts.py`.

## Cierre

Al cerrar un estudio se cambia `decision` a `closed` y se añaden `closed` (fecha),
`last_record` y el `evidence_state` final, con el motivo. Cerrar no abre reservas ni
reinicia contadores. En el mismo cambio se retiran sus `pinned_paths` sin otros
consumidores, sus entradas de `.github/architecture-compatibility.json` y sus
excepciones de I/O. `backend/tests/test_study_register.py` valida este fichero.
