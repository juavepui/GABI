# Archivo estructurado SEC como comando de investigación (F7.31, #90/#91)

`sec_history` deja de ser un módulo plano. Ya era composición de casos de uso de
`application/research` (`sec_bulk`, `sec_quarter_ingest`, `sec_archive_download`); ahora:

| Pieza | Ahora |
| --- | --- |
| Descarga fijada del archivo SEC (fichero una vez, URL, SHA-256 y tamaño registrados) | `infrastructure/storage/sec_archive_download.download_pinned`, una sola composición para todos |
| Importación trimestral, instancias originales, huecos de Company Facts, Company Facts por CIK | `infrastructure/legacy/sec_history.py`, con los mismos nombres (`download`, `import_quarter`, `parse_instance`, `run_bulk`, `recover_instances`, `recover_companyfacts_gaps`, `ingest_issuer_companyfacts`, `SCHEMA`, `DIRECTORY`, `TRACKED`) |
| Argumentos | `gabi_cli research sec-history` (`--instances`, `--quarterly`, `--companyfacts-gaps`, `--unmatched`; sin ninguno, la importación por lotes) |

`historical_issuer_evidence` (permanente, leído por nombre por `extra_sources`; ya
cambia en la pila) tiene su propia `download` sobre `download_pinned` y define su
directorio desde `config`. Su excepción del inventario legacy cambia
`gabi.sec_history` por `gabi.config`: el número no crece y `config` solo aporta la ruta
de datos, la base y el User-Agent, como en [ADR 0005](../adr/0005-legacy-config-path.md).
`tenk_extraction`, la auditoría de identidad y el piloto pre-XBRL usan el puente;
el piloto localiza `resources/legacy_filings_pilot.json` junto a `historical_archive`.

`docs/historical-validation-1996-2015/README.md` (no sellado) cita la ruta nueva y el
commit `c324aab` de `develop` con el módulo original.

## Pruebas

- Las pruebas de paridad existentes (`test_sec_archive_download_migration`,
  `test_sec_bulk_migration`, `test_sec_quarter_ingest_migration`,
  `test_historical_audits_migration`, `test_http_providers_migration`) usan el puente
  o `historical_issuer_evidence.download`; el reloj de la descarga se sustituye en el
  almacén.
- Las capturas antiguas que importaban `gabi.sec_history` lo reciben como el puente
  solo dentro de su prueba.
- Una comprobación de todos los `import gabi.*` de `src`, `tests` y `scripts` encontró
  tres scripts de medida que seguían importando `historical_identity_audit` (retirado en
  F7.27): `measure_f7_historical_audits`, `measure_f7_sec_quarter_ingest` y
  `measure_f7_identity_instances`. Se corrigen aquí y vuelven a dar paridad.

Inventario: 60 módulos planos = 18 congelados + 40 permanentes + 2 pendientes.
