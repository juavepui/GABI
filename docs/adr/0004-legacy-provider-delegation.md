# ADR 0004: delegación de HTTP desde fachadas de compatibilidad

Estado: aceptado, 2026-10-11.

## Problema

Los proveedores de `infrastructure/providers` (FRED, SEC XBRL, mapa CIK, Form 4,
Fama-French, Tiingo, WIKI) son los que usa el worker: leen por bloques, con
límites de bytes y sin efectos al importar. Las fachadas planas (`macro`, `edgar`,
`insider`, `academic_factors`, `historical_tiingo`, `historical_wiki`, `universe`…)
conservan un transporte `requests` propio con las mismas URL, cabeceras y
errores. [ADR 0003](0003-legacy-storage-delegation.md) solo permite delegar SQL,
así que el transporte HTTP queda duplicado y sin límites mientras haya
consumidores legacy, incluidos motores congelados que no pueden cambiarse.

## Decisión

Un módulo plano existente puede delegar su acceso a una fuente externa en un
módulo concreto de `gabi.infrastructure.providers`, con las condiciones de
ADR 0003:

- Importa el módulo concreto, nunca el paquete agregado `providers`.
- El proveedor recibe por operación lo que necesita (user-agent, clave, rutas);
  no lee ni modifica configuración global. La fachada la resuelve al llamar.
- Los proveedores no importan módulos planos; los ciclos siguen prohibidos.
- Siguen prohibidos los ajustes (`infrastructure.settings`) y los puentes
  `infrastructure.legacy` nuevos desde módulos planos.
- El inventario de excepciones solo disminuye.

Las fachadas conservan su interfaz y sus errores públicos (mensajes de 404,
credenciales rechazadas, clasificación). Una diferencia de transporte —lectura
por bloques con límite de bytes— se documenta y prueba en cada migración.

## Alternativas

- Mantener el transporte duplicado: dos implementaciones de la misma fuente con
  límites distintos.
- Mover todos los consumidores a bootstraps: obligaría a cambiar motores sellados.
- Inyectar proveedores mediante un registro global: estado mutable oculto.

## Validación

La guarda acepta `gabi.infrastructure.providers.<módulo>` desde un módulo plano y
sigue rechazando el paquete agregado, ajustes, puentes legacy, proveedores que
importen módulos planos y ciclos (`backend/tests/test_architecture.py`). Cada
fachada migrada tiene pruebas de paridad con el transporte capturado sin red.
