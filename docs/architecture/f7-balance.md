# Balance de F7 y evidencia de cierre (#156)

Estado reconciliado el 2026-10-15 sobre `1a1320b` (incluye la integración F7
`5467954`). Este documento concentra el balance; el detalle por módulo pertenece
al [inventario de compatibilidad](compatibility-inventory.md) y el historial de
entregas al [plan de migración](legacy-migration.md).

## Objetivo y resultado

GABI separa cálculos financieros, casos de uso, acceso a datos y presentación
en un monolito modular local. React, API, CLI y worker reutilizan las operaciones
compartidas. SQLite y los archivos continúan siendo locales; no se ha convertido
la aplicación en microservicios ni se han versionado de nuevo los motores publicados.

F2–F6 migraron los recorridos de Mercado, Cartera, Investigación y Administración,
el contrato tipado y la ejecución persistente. Streamlit se retiró tras la
[auditoría de recorridos F6](f6-research.md). F7 extrajo responsabilidades y retiró
fachadas sin consumidores, conservando las necesarias para interfaces, huellas
y reproducción de investigación publicada.

## Recuento y alcance

Fuentes contrastables sin abrir `data/`:

- Archivos `backend/src/gabi/*.py`, excluidos `__init__.py` y `__main__.py`:
  **58 módulos planos**.
- `backend/legacy-engine-hashes.json`: **18 congelados**, comprobados por SHA-256.
- `.github/architecture-compatibility.json`: **40 permanentes, 0 pendientes**.
- `.github/architecture-legacy.json`: las mismas **58 rutas planas**, además de
  `__init__.py`; registra dependencias, no una lista de ubicaciones permitidas.

La unión disjunta de congelados, permanentes y pendientes debe ser exactamente
la de archivos planos existentes. `scripts/check_architecture.py` comprueba esta
clasificación y las dependencias. Cero pendientes significa que la extracción
prevista tiene destino justificado; no significa cero compatibilidad ni cero I/O
excepcional. Las cifras de 102, 82 o 76 en entregas fechadas describen estados
anteriores, no contradicen este recuento.

En esta reconciliación pasaron las 79 pruebas de `test_api.py`,
`test_architecture.py` y `test_http_measurement.py`, la guarda backend, las nueve
pruebas y la guarda frontend, el contrato OpenAPI, Ruff y el control de tipos
existente. La verificación de congelados confirmó los 18 hashes. No se ejecutó
la suite Python completa ni se consultaron bases operativas para este balance.

## Criterios de #90/#91

| Criterio | Estado | Evidencia y límite |
| --- | --- | --- |
| Extraer hojas, intermedios y núcleo; retirar o justificar cada pendiente | Cumplido en el inventario | F7.1–F7.33 y `pending` vacío; algunas fachadas conservan traducción de parámetros o lógica documentada, no son archivos prescindibles |
| No introducir módulos planos ni dependencias nuevas | Guarda disponible | Inventario exacto, límites y ciclos comprobados por arquitectura; la CI contrasta con la base Git |
| Conservar 18 archivos congelados | Verificable por hash | `gabi_cli research frozen --check-frozen`; no prueba por sí solo toda la equivalencia financiera |
| Conservar resultados, fechas, unidades y procedencia | Evidencia por flujo | Pruebas de paridad y efectos y medidas enlazadas desde las entregas F2–F7; no constituye una prueba exhaustiva de toda combinación |
| Todos los permanentes sin I/O directo excepcional | **Pendiente de #44** | `smallmid_test`: requests/yfinance; `storage`: sqlite3/get_connection para esa prueba |
| Cierre global de #90/#91 | **Pendiente** | ADR 0006 exige también resolver las dos excepciones; no cerrar por el mero recuento cero |

## Compatibilidad que permanece

Las fachadas justificadas por motores congelados, nombres públicos o huellas
publicadas se conservan. No se eliminan para mejorar una cifra. Algunas participan
en `model_version`; cambiarlas puede producir una versión nueva aunque se mantenga
la fórmula. El inventario documenta los motivos y consumidores de cada una.

Al terminar #44, como tarde tras su congelado A3 previsto el **2027-01-15**, revisar:

1. Las excepciones de `smallmid_test` y `storage.get_connection`.
2. `historical_archive`, `historical_tiingo` e `historical_wiki`, conservados por
   los imports de la prueba preregistrada; revisar también sus demás consumidores.
3. El inventario, las guardas y la evidencia de cierre global.

Esta secuencia sigue en [#135](https://github.com/juavepui/GABI/issues/135),
[#44](https://github.com/juavepui/GABI/issues/44) y ADR 0006. No autoriza cambiar
el protocolo en curso, abrir reservas o retirar hoy esas interfaces.

## Beneficios demostrados y trabajo siguiente

- Los flujos migrados tienen reglas compartidas, contratos y dependencias
  explícitas; los tests comprueban paridad y consultas sin red/escrituras.
- La cola y el worker persisten estados y separan ejecución larga del navegador;
  una interrupción falla de forma explícita, no garantiza reanudación universal.
- [F2 y optimizaciones de Mercado](../local-api.md) documentan mejoras concretas
  de caché y lecturas. Otras entregas registran también regresiones. No hay una
  mejora general de velocidad o RAM demostrada para toda GABI.
- [#157: línea base HTTP](http-api-baseline.md) añade una medida actual con datos sintéticos. #158 medirá worker
  y concurrencia; #159/#160 revisarán presentación y recuperación.
- La [#60](https://github.com/juavepui/GABI/issues/60) sigue pendiente de evidencia
  financiera independiente. La arquitectura no demuestra superioridad de una estrategia.
