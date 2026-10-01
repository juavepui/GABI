# Entrega F1: estructura y compatibilidad — #63

> **Documento histórico.** Describe el estado de su fase. Streamlit se retiró en F6
> ([#68](https://github.com/juavepui/GABI/issues/68)); la interfaz es React y se arranca con
> `uv run --project backend python -m gabi_cli serve`.

El proyecto Python se ha trasladado a `backend/`: paquete, tests, configuración
de construcción y lockfile. `frontend/` tiene su propio manifiesto de proyecto y delimita el futuro cliente React; aún
no tiene cliente ni dependencias JavaScript. `app/` conserva Streamlit.

```text
GABI/
  backend/
    src/gabi/
    tests/
    pyproject.toml
    uv.lock
    legacy-engine-hashes.json
  frontend/
  app/                  # cliente Streamlit de transición
  data/                 # misma carpeta, sin traslado ni copia
  docs/
  scripts/
  .github/
  pyproject.toml        # configuración de herramientas desde la raíz
```

## Rutas independientes del directorio de trabajo

`gabi.workspace` localiza la raíz a partir del código instalado en el checkout.
Una instalación por wheel fuera del checkout necesita `GABI_PROJECT_ROOT` con
la ruta absoluta al repositorio. `GABI_DATA_DIR` permite un directorio absoluto
de datos alternativo. Un valor relativo se rechaza para impedir que cambie la
base usada según dónde se ejecuta el comando. Importar el paquete no crea
carpetas ni bases de datos.

Se conservan los bytes originales de `config.py`: el inicializador del paquete
aplica las rutas nuevas a sus constantes `Path` antes de cargar sus consumidores.
Así se preservan las huellas que los manifiestos antiguos atribuyen a ese archivo,
sin que los consumidores calculen erróneamente `backend/data`.

## Resolución de nombres históricos

| Nombre guardado | Ubicación física actual |
| --- | --- |
| `src/gabi/...` | `backend/src/gabi/...` |
| `uv.lock` | `backend/uv.lock` |
| `pyproject.toml` | `backend/pyproject.toml` |
| `data/...` | `data/...`, o directorio absoluto elegido explícitamente |
| `docs/...` | `docs/...` |

`config.BASE_DIR` y las constantes de datos usan `RepositoryPath`, un adaptador
de filesystem limitado a esos nombres. Los manifiestos conservan sus claves
históricas; la lectura apunta al archivo físico nuevo. No se crean enlaces de
sistema, carpetas duplicadas de código ni copias de las bases.

Dos motores, `overfitting_audit` y `full_universe_audit`, crean claves de fuentes
a partir de `Path(__file__)`. Su cargador acotado usa el mismo `RepositoryPath`
para mantener `src/gabi/...` al calcular nombres relativos. El `Path` de la
librería estándar y los demás módulos no se modifican. El adaptador cambia la
resolución/nombre de archivos, no las fórmulas ni las decisiones de cartera.
Una prueba ejecuta el constructor original de cachés con un manifiesto histórico
completo y comprueba que no abre la base ni reconstruye rankings.

Los 18 motores/configuración enumerados en `backend/legacy-engine-hashes.json`
conservan exactamente su contenido UTF-8 con LF anterior al traslado. CI verifica
esas huellas, además de la guarda histórica de los tres motores con deuda de
tipos. Los informes, protocolos, CSV, snapshots y reservas se conservan sin
reesellar resultados. Un cambio futuro de un motor publicado debe versionarse
explícitamente con su evidencia, no sustituir el hash del informe anterior.

Las nuevas capturas del ledger incluyen también `workspace.py` y `__init__.py`
en su versión de código y detectan cambios sobre `backend/src/gabi`. Por ello,
la versión registrada de una captura nueva refleja la capa de compatibilidad;
las capturas antiguas y sus cadenas de integridad no se reescriben.

En una instalación fuera del checkout, `src/gabi/...` se resuelve al código del
paquete realmente cargado, no a otra copia del repositorio. Los documentos,
lockfile y datos siguen anclados a `GABI_PROJECT_ROOT`. Una prueba de instalación
externa comprueba esas referencias y CI construye también el wheel del backend.

## Instalación, CI y tareas periódicas

El backend se usa desde la raíz con `uv ... --project backend` o directamente
desde `backend`. La configuración raíz permite ejecutar pytest y Ruff sobre
todo el repositorio. Mypy usa explícitamente la configuración y el paquete del
backend (ampliado a todo `backend/src` por las reglas de arquitectura); solo
traduce el prefijo físico de `gabi` a `src/gabi` para comparar
el baseline de 25 diagnósticos. Líneas, mensajes, severidad y códigos deben
seguir coincidiendo exactamente; no se amplía la deuda tolerada.

La CI trabaja en `backend`, instala con lockfile, verifica motores y registro,
ejecuta lint sobre el repositorio, tipos, imports, compilación de las 17 páginas
y tests. Los tests usan bases temporales aisladas. Una prueba de arranque
ejecuta también la portada y las 17 páginas con AppTest: caché vacía aislada,
sin pulsar botones y con conexiones externas bloqueadas. Comprueba el arranque,
no sustituye las pruebas de cada flujo con datos completos.

La fixture ahora aísla también los pesos, claves, cachés y modo: cambiar solo
`DATA_DIR` y `DB_PATH` dejaba constantes calculadas al importar apuntando al
directorio real. Una regresión comprueba que esas escrituras quedan en temporal.

`scripts/programar_tareas.ps1` elige `backend/.venv` para instalaciones nuevas,
con fallback al entorno raíz existente. Las tareas ya registradas siguen siendo
compatibles si se reinstala el paquete editable en su intérprete anterior. Este
traslado no registra ni modifica tareas del Programador de Windows. La CLI de
estado se prueba con una base/caché temporal inicializada; no se ejecutan
descargas o rebalanceos reales para comprobar el traslado.

Después de actualizar una instalación existente, reiniciar Streamlit y cualquier
proceso Python de GABI que estuviera abierto: un proceso anterior puede conservar
en memoria módulos y rutas del layout antiguo. Las siguientes ejecuciones del
scheduler cargan el backend instalado de nuevo.

Los comandos `uv run ...` de informes históricos se ejecutan ahora desde
`backend`, o añadiendo `--project backend` desde la raíz. Sus textos sellados
no se modifican para cambiar instrucciones de instalación.

## Recuperación

No hay cambios de esquema ni conversión de datos en esta fase. Para volver a
la disposición previa, guardar los cambios propios en una rama y hacer checkout
del commit anterior a F1; reinstalar el proyecto editable desde la raíz en el
intérprete que utilice Streamlit o el scheduler. La carpeta `data/` permanece
compartida. No usar `git reset --hard` ni eliminar datos para volver atrás.

El frontend visual y la API son las fases #64/#65. Esta entrega conserva la
evidencia y permite separar sus proyectos; no cambia el objetivo pendiente #60.
