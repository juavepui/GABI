# Registro prospectivo de GABI-ENS-VQE-v1 (#237)

Activación del plan prospectivo que autoriza el [preregistro de #53](../ensemble-robustness/PREREGISTRO.md)
(especificación `8609a0770a49d00c72bf5bb507d55551eba88b895543b305ca66715292555bca`,
decisión «parcial», `prospective_v1_allowed: true`). **El modelo no cambia**:
bloques valor, calidad y expectativas de #60, media equiponderada con los tres
presentes y cuatro Top-20 con 20 plazas y un máximo de 6 por división SIC.

## Calendario y revisiones

- Rebalanceos el 21 de marzo, junio, septiembre y diciembre, desde el **2026-12-21**.
- Revisiones a los 12, 24 y 40 trimestres, no antes del 2029-12-21, del 2032-12-21
  ni del 2036-12-21. Antes solo se comprueban integridad, cobertura y continuidad:
  **nunca retornos, IC ni excesos**.
- Ninguna revisión se adelanta a la de #43, y ningún resultado de una modifica la otra.

## Procedimiento de cada trimestre

1. Actualizar precios y SEC del universo (acción explícita y separada).
2. Desde la fecha de señal, y como tarde **cinco sesiones después**:

   ```powershell
   uv run --project backend python -m gabi_cli research ensemble-record --record
   ```

   El comando exige que `backend/src` no tenga cambios sin commit, verifica la
   cadena y el spec sellado, y rechaza precios anteriores a la sesión previa a la
   señal. Nunca sobrescribe un registro.
3. Hacer commit y push del `registro-AAAA-MM-DD.json` **el mismo día**: la marca de
   tiempo de GitHub es la prueba externa de que no hubo relleno hacia atrás.

Si la ventana se cierra sin registro, el siguiente `--record` sella primero ese
trimestre como `not_recorded`. Nunca se rellena.

Verificación, sin red ni retornos:

```powershell
uv run --project backend python -m gabi_cli research ensemble-record --verify
```

## Contenido de cada registro

Un JSON canónico por trimestre, con huella SHA-256 y la huella del anterior.
Contiene: puntuaciones completas de U_t (percentiles de métrica, bloques y ENS),
los cuatro Top-20 con sus plazas en efectivo, el universo (tamaño, mínimo de 40,
excluidos con motivo), la evidencia SIC de cada emisor, el último cierre y cierre
ajustado de cada miembro con fecha hasta la señal, y las entradas: commit del
código, composición del S&P 500 con su huella, alineación #38, spec SIC y motores
usados. El cierre de entrada no es un retorno: sirve para que la revisión no
dependa de reconstruir precios de empresas que dejen de cotizar.

## Nota de implementación

Decisiones aprobadas por el propietario el 28-10-2026, antes del primer registro:

- **D1. Universo e identidad.** La capa acreditada (#34) cubre solo 2010-2025. En
  vivo se usa el S&P 500 vigente por el camino operativo, como #43, con la identidad
  atribuida y, si falta, la vigente ticker→CIK del mapa SEC (incluida la sucesión
  revisada de XOM, #202), y la alineación fiscal #38. Las características salen del
  mismo código que generó los rankings «acreditado-38» (`screener_asof`), en un
  **modo operativo opcional** (`operational_entities`): fundamentales por el CIK
  guardado por la sincronización SEC, con el historial completo del emisor (#201),
  y precios de la caché por ticker. El camino por defecto, que usan los motores
  congelados, no cambia. Hace falta porque en vivo no hay series de precios
  atribuidas, y el camino por ticker lee los fundamentales por símbolo, con medio
  historial en los emisores con alias (#201). En el ensayo inicial, además, los
  alias diarios de las fotos del universo bloqueaban el camino por ticker y nadie
  alcanzaba la cobertura del 70 %; ese bloqueo se corrigió después en el registro
  de identidad, que ya no cuenta las fotos como alias fechados.
- **D2. SIC fechado.** Se aplica la regla congelada de #48b
  (`factor_sector_stability.assign`: 10-K/10-Q y sus enmiendas, ≤ 400 días, sin
  etiquetas futuras), con las presentaciones de EDGAR `submissions` descargadas al
  registrar y la SIC vigente ese día. EDGAR da la hora de aceptación en UTC; se
  convierte a hora del Este, que es el reloj de los ficheros SUB que compara la
  regla. Si las 1.000 entradas recientes no llegan a una presentación periódica
  anterior a la señal (emisores con miles de 424B2), se leen páginas antiguas.
- **D3. Ventana.** Desde la señal hasta cinco sesiones de NYSE después.
- **D4. Almacenamiento.** Este directorio, con commit y push el mismo día.

Una diferencia operativa: en la retrospectiva el 100 % de las 18.289 filas tenía
división SIC. En vivo, un emisor elegible sin división válida (sin identidad, sin
presentación reciente o con SIC ambigua) **queda fuera de U_t y se publica con su
motivo** en `universe.excluded`, sin eliminarlo en silencio. Los bloques usan el
motor congelado, que exige división para todas las filas.

## Ensayo en seco (28-10-2026)

Flujo completo sobre una **copia** de la base y una señal pasada (2026-09-21),
escribiendo fuera del repositorio. No se leyó ni calculó ningún retorno.

| | Retrospectiva, última fecha (2025-07-02) | Ensayo (2026-09-21) |
| --- | ---: | ---: |
| Elegibles (Composite y cobertura ≥ 70 %) | 333 | 348 |
| Con división SIC | 333 | 348 |
| U_t (los tres bloques) | 170 | 169 |
| Bloques valor / calidad / expectativas | 324 / 306 / 174 | 339 / 319 / 175 |

Los cuatro Top-20 se llenaron y los 169 miembros tenían cierre de entrada. La
duración fue de unos 4 minutos para el ranking y 2 para las `submissions` de la SEC.

## Segundo ensayo (12-11-2026)

Repetido con el código actual (`7e051c2`, después de GABI-MF-v5 y de las métricas
del motor) y el mismo camino que `--record`: copia de `gabi.db` hecha con la API de
copia de SQLite, `GABI_DATA_DIR` apuntando a la copia, señal 2026-09-21 y registro
escrito fuera del repositorio. Solo se adelantó en memoria la primera señal. No se
leyó ni calculó ningún retorno.

| | Ensayo 28-10 | Ensayo 12-11 |
| --- | ---: | ---: |
| S&P 500 vigente / con ranking | — | 503 / 503 |
| Elegibles (Composite y cobertura ≥ 70 %) | 348 | 347 |
| Con división SIC (excluidos) | 348 (0) | 347 (0) |
| U_t (los tres bloques) | 169 | 169 |

Los cuatro Top-20 tienen 20 empresas y ninguna plaza en efectivo; los 169 miembros
tienen cierre de entrada del 2026-09-21. `--verify` da 1 registro y la cadena
íntegra; una segunda ejecución en la misma ventana responde «ya registrado» y no
escribe. Duración: unos 9 minutos (ranking más `submissions` de la SEC). El JSON
ocupa unos 250 KB.

## Lista para el primer registro (lunes 21-12-2026)

La ventana va del **21-12 al 29-12** (cinco sesiones de NYSE después de la señal;
el 25-12 no hay sesión). Hacerlo el mismo 21-12 deja margen si algo falla.

Antes (semana del 14-12):

1. `git switch develop` y `git pull`; `git status` sin cambios en `backend/src`
   (el comando se niega a registrar si los hay).
2. `uv run --project backend python -m gabi_cli research ensemble-record --verify`
   debe dar `"records": 0`.
3. Comprobar que las tareas diarias de esa semana terminaron bien (Administración o
   `data/gabi_jobs.db`).

El día 21-12:

1. Precios y SEC al día. El registro exige cierres del 18-12 o posteriores. Si la
   tarea del sábado 19-12 terminó bien, ya están; si no, lanzar «Actualizar todo»
   y esperar a que termine.
2. Con el ordenador enchufado y con internet:

   ```powershell
   uv run --project backend python -m gabi_cli research ensemble-record --record
   ```

   Tarda unos 10 minutos y descarga de la SEC las presentaciones de unos 350
   emisores. Debe responder `"recorded": "2026-12-21"` y `"evaluable": true`.
3. `uv run --project backend python -m gabi_cli research ensemble-record --verify`
   debe dar `"records": 1`.
4. El mismo día, commit y push del fichero:

   ```powershell
   git add docs/ensemble-prospective/registro-2026-12-21.json
   git commit -m "docs(ens): registro prospectivo del 2026-12-21 (#237)"
   git push
   ```

   La marca de tiempo de GitHub es la prueba externa. No mirar retornos ni
   comparar con el índice: el preregistro solo lo permite en las revisiones.

Si falla: no editar el JSON ni repetir con otro código. Se puede volver a ejecutar
`--record` hasta el 29-12 (si no llegó a escribir el fichero). Si la ventana se cierra
sin registro, el trimestre quedará como `not_recorded` y nunca se rellena.
