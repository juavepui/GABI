# ADR 0002: comandos de investigación reproducibles en `gabi_cli research`

Fecha: 2026-10-05. Estado: aceptado. Issue: [#89](https://github.com/juavepui/GABI/issues/89), parte de #91.

## Contexto

Una docena de módulos planos de `backend/src/gabi` no los importa la aplicación:
son comandos de investigación (`python -m gabi.<módulo>`) que generaron
evidencia publicada en `docs/`, más dos herramientas que usa la CI
(`frozen_research_ci` y `search_ledger --verify`). Borrarlos rompería la
reproducibilidad de esos documentos; dejarlos como están mantiene la deuda que
F7 quiere retirar (#91). Además, algunos documentos están sellados: su hash
figura en `docs/search-ledger/ledger.json` (`sources_sha256_lf`) o se publicó
en una issue o en un preregistro, y editarlos invalidaría esa huella.

## Decisión

1. **Dónde viven.** Cada comando pasa a ser un subcomando
   `python -m gabi_cli research <nombre>` con los mismos argumentos. El
   adaptador CLI solo traduce argumentos y salida. El cálculo puro va a
   `domain/research/`, la coordinación a `application/research/` y el acceso a
   ficheros y SQLite a `infrastructure/`. Mientras el núcleo antiguo (#90)
   exista, el comando lo usa a través de un puente pequeño en
   `infrastructure/legacy/`, nunca importándolo desde las capas nuevas.
2. **Herramientas de CI.** `frozen_research_ci` y la verificación del registro
   de búsquedas siguen la misma regla (`gabi_cli research frozen …`,
   `gabi_cli research ledger …`); la CI, `AGENTS.md` y la documentación se
   actualizan en el mismo cambio.
3. **Procedencia.** Un documento no sellado que cite el comando antiguo se
   actualiza en el mismo cambio a la ruta nueva e indica con qué comando y
   commit se produjo originalmente. Un documento sellado **no se edita nunca**:
   se reproduce en el commit que fija, y si el código actual verifica esa
   evidencia (por ejemplo `value_hypothesis.spec_hash()` al leer un
   preregistro), el nombre público que cita se conserva como adaptador fino
   que delega en la ubicación nueva, con el mismo resultado byte a byte.
   Se consideran sellados los documentos de `sources_sha256_lf` y los
   `PREREGISTRO*.md` / `preregistro*.json`.
4. **Equivalencia.** Antes de retirar un módulo, un test con datos temporales
   compara la salida antigua y la nueva (valores, unidades, orden y, si el
   comando escribe un artefacto, sus bytes). Nunca se regeneran documentos
   publicados ni se consultan reservas para validar el traslado.
5. **Retirada.** Un módulo plano se borra cuando no lo importa nada, su
   documento apunta a la nueva ruta y su excepción sale del inventario
   (`.github/architecture-legacy.json`, que solo puede bajar).

## Alternativas descartadas

- **Dejarlos donde están como excepción permanente.** Es lo más barato, pero
  deja documentos citando rutas que nadie mantiene y bloquea #91.
- **Un paquete aparte `gabi_research` con permiso para importar legacy.**
  Traslada la deuda sin reducirla y añade una frontera con reglas propias.
- **Borrarlos y confiar solo en el commit histórico.** Pierde la posibilidad de
  volver a ejecutar un comando con datos nuevos y rompe la verificación de
  preregistros que la API hace hoy.

## Consecuencias

Los comandos ganan un único punto de entrada documentado y sus cálculos quedan
testeables sin ficheros. Mientras dure #90 habrá puentes `infrastructure/legacy`
por comando; desaparecen cuando el núcleo migre. Los nombres antiguos que
verifican evidencia sellada permanecen como adaptadores finos, enumerados en
el inventario, hasta que la verificación pueda citar la ruta nueva sin tocar el
documento sellado.

`rotation_experiment` es la excepción explícita: su ejecución parchea los motores
antiguos de backtest y apunta la configuración antigua a una copia de trabajo del
snapshot congelado. Trasladar eso a las capas nuevas introduciría el patrón que
este repositorio prohíbe, así que el subcomando delega en el módulo antiguo a través
de un puente y el módulo sigue en el inventario hasta que #90 libere esos motores.
