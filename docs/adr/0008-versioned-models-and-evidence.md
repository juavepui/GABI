# ADR 0008: el producto evoluciona por versiones; la evidencia queda ligada a la suya

Estado: aceptado, 2026-10-28. Issue: #243, parte de #242. Fase 1 de 4.

## Problema

Las reglas vigentes protegen bien la evidencia, pero también inmovilizan el producto:

- `backend/legacy-engine-hashes.json` sella `config.py` junto a otros 17 motores, y 21
  adaptadores de `infrastructure/legacy/` lo importan. Contiene a la vez rutas, claves,
  parámetros técnicos y los pesos por defecto. Un ajuste operativo obliga a elegir
  entre no hacerlo y reesellar evidencia.
- `domain/market/model_policy.py` solo reconoce como modelo propio la hipótesis
  GABI-MF-v1 (2026-09-17). Cualquier otro modelo se muestra como desviación
  `EXPERIMENTAL` de esa hipótesis, no como una versión con identidad propia.
- `AGENTS.md` prohíbe mover o reformatear los congelados y no distingue entre motor de
  un estudio y camino activo del producto.
- Las revisiones de ENS-VQE-v1 (2029, 2032, 2036) y de #43 (2032, 2036) se leen como
  plazos del producto, aunque solo fijan cuándo se puede mirar su evidencia.

El resultado es que corregir una métrica (#245) o un motor de backtest (#249) parece
exigir esperar a estudios que acaban dentro de años.

## Decisión

1. **La evidencia pertenece a una versión.** Un estudio queda identificado por su id,
   el commit de su código y un manifiesto con la especificación, los hashes de código y
   configuración, la huella de datos y los resultados. Sus afirmaciones valen solo para
   esa versión. Una versión nueva empieza sin evidencia y no hereda la de la anterior.
2. **El modelo activo tiene identidad de versión.** El producto usa un modelo activo
   `<familia>-vN` declarado en configuración operacional versionada. Cambiarlo es
   legítimo en cualquier momento y no espera a revisiones de estudios. El estado
   visible usa `MODEL_STATUSES`: una versión nueva sin acreditación es `EXPERIMENTAL`
   por sí misma, no por desviarse de GABI-MF-v1. `VALIDATED` sigue reservado para una
   acreditación independiente; ningún cambio de producto la otorga.
3. **Los caminos de estudios activos no cambian de semántica.** Si un estudio
   prospectivo ejecuta código vivo en cada registro (ENS-VQE-v1 mediante
   `screener_asof`, #43), un cambio semántico de ese camino se hace en un módulo o
   versión nueva, y el estudio sigue usando el suyo hasta cerrarse. Se permiten cambios
   de forma con equivalencia en fixtures. El primer registro de ENS-VQE-v1 (ventana del
   2026-12-21 al 2026-12-28) no se interrumpe.
4. **`config.py` queda como snapshot sellado de los estudios.** La configuración
   operacional nueva (modelo activo, pesos, parámetros técnicos, rutas) vive en
   infraestructura, con versión, y se inyecta por operación. `config.py` no se edita.
5. **Cada estudio se clasifica con fecha:** continuar en paralelo, sustituir por una
   versión nueva o retirar. Un cierre registra fecha, motivo, último registro y estado
   de evidencia. Cerrar no abre reservas: los datos vistos siguen vistos, un protocolo
   nuevo no restaura independencia y el contador de intentos de #60 no se reinicia.
6. **Los hashes esperados no cambian.** La guarda actual de congelados sigue activa
   hasta que exista una verificación equivalente por commit y manifiesto. Solo entonces
   un motor sin consumidores activos puede salir del árbol, retirando a la vez su
   entrada de inventario y su fachada.
7. **Equivalencia solo para migraciones sin cambio semántico.** Dos modelos distintos
   se comparan y se documentan sus diferencias; no se exige que coincidan.

## Impacto

Este cambio solo modifica reglas: `AGENTS.md` y `docs/architecture.md`. No cambia
código, motores, hashes, inventarios ni guardas. El modo Investor sigue fijado a
GABI-MF-v1 hasta la fase 2.

## Migración

1. Este ADR y las reglas que lo enlazan.
2. Configuración operacional versionada fuera de `config.py` y modelo activo con
   identidad propia en `model_policy`. Equivalencia exacta en fixtures con los valores
   actuales; `ensemble_live` sigue operativo.
3. Clasificación fechada de #43, #44, ENS-VQE-v1 y #60.
4. Verificación por commit y manifiesto que sustituye a la guarda de rutas vivas;
   retirada de fachadas y excepciones que solo sostenían estudios cerrados, con
   inventarios y pruebas en el mismo cambio.

## Alternativas

- Esperar a las revisiones: bloquea correcciones durante años sin proteger más la
  evidencia, que ya está sellada.
- Reesellar hashes al cambiar un motor: destruye la prueba de que la evidencia no se
  alteró.
- Una rama o copia del repositorio por estudio: diverge, duplica correcciones de
  infraestructura y no aclara cuál es el modelo activo.
- Desactivar las guardas: deja de detectar alteraciones de evidencia.

## Validación

Fase 1: los controles de arquitectura y la comprobación de congelados de `AGENTS.md`
pasan sin cambios. Cada fase siguiente trae sus pruebas: equivalencia de configuración
en fixtures (2), registros de cierre (3) y reproducción de un estudio desde su commit
en un checkout temporal con fixtures (4). Ninguna lee `data/gabi.db` ni holdouts.
