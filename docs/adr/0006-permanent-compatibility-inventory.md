# ADR 0006: inventario cerrado de compatibilidad permanente

Estado: aceptado, 2026-10-14. Issue: #135, parte de #90 y #91.

## Problema

No todos los módulos planos de `backend/src/gabi` se pueden retirar. Además de los
18 motores y la configuración congelados (`backend/legacy-engine-hashes.json`), otros
módulos se importan desde esos motores o se leen por nombre para calcular huellas
publicadas: `overfitting_audit`, la huella de cachés de `full_universe_audit`,
`historical_validation`/`historical_revalidation.extra_sources()`, el protocolo
sellado de `rotation_experiment` y `live_ledger.model_metadata`. Sin una lista
explícita, #90 y #91 no tienen un final verificable, y un módulo que se queda
"por compatibilidad" podría volver a acumular SQL o HTTP.

## Decisión

1. `.github/architecture-compatibility.json` clasifica **todo** módulo plano que no
   esté congelado:
   - `permanent`: se queda. Cada entrada declara su motivo (interfaz de motores
     congelados, lectura por nombre para una huella publicada, comando de
     reproducción sellado o prueba preregistrada en curso) y sus consumidores.
   - `pending`: deuda de #90/#91, con la issue que lo retira o lo justifica.
2. Un módulo permanente no usa SQL, HTTP ni procesos (`sqlite3`, `requests`,
   `httpx`, `urllib`, `http`, `socket`, `subprocess`, `yfinance`, `lxml`,
   `aiohttp`). La única salida es una excepción `io` justificada en su entrada.
   Hoy solo hay dos, ligadas a la prueba #44: `smallmid_test` (`requests`,
   `yfinance`) y `storage` (`sqlite3`, `get_connection` para `smallmid_test`). Se
   revisan cuando #44 termine.
3. `scripts/check_architecture.py` exige que la lista esté cerrada, que no aparezcan
   congelados ni módulos retirados, que los permanentes no tengan I/O directo no
   declarado y que no queden excepciones sin uso. Con `--baseline-base`, `pending`
   y las excepciones `io` solo pueden bajar; un módulo solo entra en `permanent`
   desde `pending`, y el fichero no puede desaparecer.
4. **Criterio de cierre de #90/#91**: `pending` está vacío y todo módulo plano
   restante es congelado o permanente sin I/O directo (las excepciones `io` de #44
   se cierran con esa prueba).
5. `live_ledger.model_metadata` sigue hasheando las fachadas junto con los módulos
   de dominio. `technicals` y `risk` trasladan valores de `config` (medias, RSI,
   momentum, tasa libre de riesgo) que no entran en el hash por otra vía, y `edgar`,
   `screener` y `live_ledger` aún contienen lógica. Un cambio de una fachada cambia
   `model_version`, también cuando es solo de forma. El criterio se revisa cuando
   esos módulos dejen de tener lógica, con su cambio de versión documentado.

La lógica financiera no se puede comprobar estáticamente. La equivalencia de los
módulos permanentes sigue exigiendo pruebas de paridad y revisión, como dice AGENTS.md.

## Alternativas

- Sin lista, solo la regla de que el inventario de dependencias no crezca: no fija
  un final ni distingue los módulos que se quedan de la deuda.
- Prohibir todo `os`/`pathlib`/`shutil` en permanentes: `config` y `workspace`
  necesitan rutas y variables de entorno, y no son el riesgo que se quiere evitar
  (SQL, red y procesos).
- Hashear en `model_version` solo los módulos de dominio: perdería los parámetros
  que traducen las fachadas y la lógica que todavía vive en ellas.

## Validación

`backend/tests/test_architecture.py`: módulo sin clasificar, congelado listado,
módulo retirado, I/O directo no declarado, excepción sin uso, pendientes que no
crecen, entradas permanentes solo desde pendientes y fichero obligatorio; además,
la lista del repositorio cierra exactamente los módulos planos existentes.
