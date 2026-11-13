# ADR 0005: ruta de la base desde `config` al retirar `storage`

Estado: aceptado, 2026-10-13.

## Problema

[ADR 0003](0003-legacy-storage-delegation.md) y [ADR 0004](0004-legacy-provider-delegation.md)
permiten que una fachada plana lleve su SQL a `infrastructure/storage` y su
transporte a `infrastructure/providers`. Los adaptadores reciben la ruta de la base
por operación. Algunas fachadas sin `config` (`blind_validation`, `sync_state`,
`price_sync`) importan `storage` solo para obtenerla (`storage.database_path()`).
Los motores congelados cambian `config.DB_PATH` por variante, así que la ruta debe
leerse en cada llamada. Como la guarda impide añadir `gabi.config` a un módulo que no
lo importaba, esas fachadas seguían dependiendo de `storage` sin usar su SQL.

## Decisión

Un módulo plano puede sustituir su dependencia `gabi.storage` por `gabi.config` en el
mismo cambio en que retira `storage`, siempre que `config` se use solo para leer
rutas por operación:

- Solo es una sustitución: el inventario no crece, porque `gabi.storage` desaparece.
- No se modifica `config` por petición ni por job.
- No autoriza ninguna otra dependencia plana nueva ni importar `config` en módulos
  que no tuvieran `storage`.
- Las condiciones de ADR 0003/0004 (módulos concretos, sin ciclos, sin ajustes ni
  puentes legacy nuevos) siguen vigentes.

## Alternativas

- Mantener `storage` solo por `database_path()`: deja una dependencia de la fachada
  que se quiere retirar.
- Obtener la ruta a través de otro módulo plano ya importado (por ejemplo,
  `screener_asof`): acopla responsabilidades sin relación.
- Inyectar la ruta mediante un registro global: estado mutable oculto.

## Validación

`baseline_growth` acepta `gabi.config` en un módulo solo si la base anterior
registraba `gabi.storage` y la nueva ya no lo hace. Rechaza mantener ambas, añadir
`config` a un módulo sin `storage` y cualquier otra dependencia nueva
(`backend/tests/test_architecture.py`).
