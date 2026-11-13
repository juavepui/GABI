# ADR 0007: rutas desde `config` al retirar un módulo plano del que se dependía

Estado: aceptado, 2026-10-14. Amplía [ADR 0005](0005-legacy-config-path.md). Parte de #90/#91.

## Problema

[ADR 0005](0005-legacy-config-path.md) solo permite que `gabi.config` sustituya a una
dependencia de `gabi.storage`. Al retirar `sec_history` (F7.31),
`historical_issuer_evidence` (permanente: `extra_sources` lo lee por nombre para los
`audit.json` publicados) dependía de él únicamente para el directorio del archivo SEC
(`sec_history.DIRECTORY`) y para la descarga fijada, que necesita la base de
procedencia y el User-Agent de SEC. Sin `config`, el módulo tendría que recibir esas
rutas desde quien lo llama, lo que cambia la interfaz de un módulo cuya huella se publica
y de sus consumidores (`historical_price_audit`, la auditoría de identidad).

## Decisión

Un módulo plano puede sustituir una dependencia `gabi.<módulo>` por `gabi.config` en el
mismo cambio en que ese módulo plano se retira (deja de existir y sale del inventario),
siempre que `config` se use solo para leer por operación rutas de datos, la ruta de la
base o el User-Agent de SEC:

- Solo es una sustitución: la lista del módulo no crece.
- No se modifica `config` por petición ni por job.
- No autoriza ninguna otra dependencia plana nueva ni importar `config` en un módulo cuya
  dependencia sigue existiendo.
- Las condiciones de ADR 0003/0004/0005 siguen vigentes.

Caso aplicado: `historical_issuer_evidence` cambia `gabi.sec_history` por `gabi.config`
y descarga con `infrastructure/storage/sec_archive_download.download_pinned`.

## Alternativas

- Inyectar directorio y descarga desde los llamadores: cambia la interfaz de un módulo
  permanente con huella publicada y de todos sus consumidores.
- Obtener las rutas a través de otro módulo plano: acopla responsabilidades sin relación
  y es igualmente una dependencia nueva.
- Mantener `sec_history` solo como contenedor de rutas: conserva el módulo que se retira.

## Validación

`baseline_growth` acepta `gabi.config` en un módulo solo si, respecto a la base anterior,
ese módulo deja una dependencia `gabi.<módulo>` cuyo fichero plano estaba en el inventario
anterior y ya no está en el nuevo. Rechaza la sustitución cuando el módulo dependido sigue
existiendo, añadir `config` a un módulo sin esa retirada y cualquier otra dependencia nueva
(`backend/tests/test_architecture.py`).
