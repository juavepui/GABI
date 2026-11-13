# ADR 0003: delegación de SQL desde fachadas de compatibilidad

Estado: aceptado, 2026-10-08.

## Problema

EDGAR delega cálculos en dominio y aplicación, pero conserva lectores SQL que
inicializan esquemas. `SqliteSecReads` ofrece el mismo contrato con conexiones
de solo lectura y presupuestos explícitos. La guarda clasificaba su import
desde la fachada como nueva deuda legacy, impidiendo retirar el SQL sin
eliminar simultáneamente consumidores congelados cuyos bytes deben conservarse.

## Decisión

Un módulo plano existente puede delegar su persistencia en un módulo concreto
de `gabi.infrastructure.storage`. No se permite importar el paquete agregado
`storage`, proveedores, ajustes ni puentes `infrastructure.legacy` nuevos desde
esos módulos. La composición de código nuevo sigue en los bootstraps; esta
dirección conserva interfaces antiguas mientras se retira su I/O.

El adaptador recibe la ruta por operación. No importa módulos planos ni cambia
configuración global. Las reglas de infraestructura y la detección de ciclos
siguen vigentes. El inventario de excepciones solo disminuye; no se añade una
excepción por archivo ni se habilitan dependencias legacy nuevas.

## Alternativas

- Mantener SQL duplicado conservaría las escrituras implícitas de lectura.
- Registrar un lector global introduciría estado mutable y composición oculta.
- Migrar todos los consumidores a la vez requeriría modificar motores sellados.
- Llevar SQLite a aplicación violaría la separación de I/O.

## Migración y validación

EDGAR construye `SqliteSecReads` con la ruta de compatibilidad por operación y
conserva la política fiscal explícita. Sus consumidores históricos obtienen las
mismas métricas y atribuciones sin inicializar tablas al consultar. La ausencia
de almacenamiento devuelve datos ausentes; exceder presupuestos falla sin
truncar. No hay caché adicional: la siguiente conexión observa las revisiones.

Las pruebas de arquitectura admiten esta dirección y rechazan proveedores,
ajustes, puentes, imports inversos y ciclos. Las fixtures SEC temporales verifican
paridad, fechas, unidades, aliases, política fiscal y ausencia de escrituras.
Los hashes congelados permanecen intactos.
