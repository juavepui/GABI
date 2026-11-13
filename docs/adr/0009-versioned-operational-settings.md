# ADR 0009: ajustes operativos versionados fuera de `config.py`

Estado: aceptado, 2026-11-02. Amplía [ADR 0007](0007-config-for-retired-flat-dependency.md)
y concreta el punto 4 de [ADR 0008](0008-versioned-models-and-evidence.md). Issue #270.

## Problema

`config.py` está sellado en `backend/legacy-engine-hashes.json`. Varios módulos seguían
leyendo de él ajustes operativos: `BENCHMARK_SYMBOL`, `CACHE_MAX_AGE_HOURS`,
`EDGAR_CACHE_MAX_AGE_HOURS` e `INFO_KEYS` (este último ampliado aparte por
`data_fetch` con `EXTRA_INFO_KEYS`). Cambiar cualquiera de ellos obligaba a reesellar
o a mantener dos fuentes.

Pasar los valores por parámetro no es posible en todos los caminos. Los motores
congelados llaman a `multifactor_backtest` y este a `identity`, y los tres son módulos
planos; no hay un adaptador intermedio que pueda inyectar el benchmark sin cambiar
caminos congelados o fijados en `docs/studies/register.json`. Una guarda (ADR
0003/0004) impide que un módulo plano importe `gabi.infrastructure.*` salvo
`storage` y `providers`.

## Decisión

1. **Fuente única versionada:** `gabi.infrastructure.operational_settings`
   (`operational-settings-v1`).
   - Es declarativa: sin I/O y sin estado mutable.
   - El benchmark sale del modelo activo (`ModelVersion.benchmark_symbol`).
   - Las edades de caché y los campos de Yahoo, de la versión declarada.
   - Cambiar un valor es un commit que declara una versión nueva.
2. **Adaptadores** (`infrastructure/legacy/*`): leen esta fuente en cada operación.
3. **Módulos planos permanentes:** pueden importar **solo este módulo** además de
   `storage` y `providers`. La guarda lo nombra en `DECLARED_SETTINGS`. No es una
   excepción general: no autoriza ningún otro módulo de `infrastructure`.
4. **Lo que no cambia:** `config.py` y los motores congelados conservan sus
   constantes.
5. **Verificación por test:**
   - los valores reproducen exactamente los sellados;
   - ningún adaptador ni módulo no congelado lee esas constantes de `config`.
6. **Huella de `live_ledger`:** `live_ledger.model_metadata` incluye este módulo en
   su huella de código. El cambio de código de esta migración altera **una vez**
   `model_version` del libro en vivo, sin cambio de semántica. Los registros
   anteriores conservan su `model_version` y su cadena.

## Alternativas

- **Inyectar por parámetro desde los llamadores:** cambia los caminos de los
  motores congelados y de los estudios fijados.
- **Duplicar los valores en adaptadores y módulos planos:** dos fuentes que pueden
  separarse.
- **Ubicar la fuente en `infrastructure/storage`:** no es almacenamiento, y
  disfrazaría la dependencia en vez de declararla.

## Validación

- `tests/test_operational_settings.py`: equivalencia exacta, ausencia de lecturas
  desde `config` y huella del libro en vivo.
- Guarda de arquitectura y `--check-frozen`.
- Suite completa.

Los tests de paridad con capturas de Yahoo sin `heldPercentInsiders` sustituyen la
lista operativa por la sellada, como antes hacían con `EXTRA_INFO_KEYS`.
