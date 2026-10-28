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
  atribuidas, y los alias diarios de las fotos del universo bloquean el camino por
  ticker: sin este modo, ninguna empresa alcanzaba la cobertura del 70 %.
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
