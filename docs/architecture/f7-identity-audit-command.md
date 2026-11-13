# Auditoría de identidad como comando de investigación (F7.27, #90/#91)

`historical_identity_audit` deja de ser un módulo plano y pasa a
`python -m gabi_cli research identity-audit`, con los mismos argumentos y las mismas
salidas ([ADR 0002](../adr/0002-reproducible-research-commands.md)). Ningún motor
congelado, huella publicada ni `model_version` lo leía por nombre; su único consumidor
de producción (`infrastructure/legacy/tenk_extraction`) usa ahora
`domain.research.historical_identity_audit._candidate_map` directamente.

| Pieza | Ahora |
| --- | --- |
| Ventanas de las nominaciones revisadas, intervalos objetivo de los 10-K, primer y último 10-K del intervalo, tickers revisados a una fecha | `domain/research/historical_identity_audit.py` |
| Bucle de pruebas de símbolo en 10-K y de historiales de nombres SEC (límites, orden, recuentos, errores) | `application/research/historical_identity_audit.py` (`annual_report_symbol_evidence`, `fetch_issuer_name_histories`) con puertos |
| Composición con el archivo histórico, `sec_history`, la evidencia de emisores, SQLite y los pasos del comando (`command`) | `infrastructure/legacy/historical_identity_audit.py`, que conserva los nombres que parchean las pruebas |
| Argumentos y salida | `gabi_cli/research/bootstrap.py` (`identity-audit`) |

Los pasos se ejecutan en el mismo orden y con las mismas salidas. Única diferencia:
las combinaciones inválidas (`--evidence-csv`/`--import-evidence` sin
`--scan-instances`, `--intervals-csv` sin `--build-intervals`, las dos descargas de
covers a la vez) se rechazan antes de ejecutar ningún paso; el módulo antiguo las
rechazaba después de las importaciones y descargas previas.

Los documentos no sellados que citaban `python -m gabi.historical_identity_audit`
(`historical-identity-2010-2015.md`, `historical-prices-2010-2015.md`,
`historical-sec-2010-2015.md`, `historical-integration-2016-2025.md`) citan la ruta
nueva e indican que el módulo original está en el commit `c324aab` de `develop`.
Los resultados publicados no se regeneran.

## Pruebas

- `test_sec_quarter_ingest_migration`: nuevas pruebas de paridad de
  `annual_report_symbol_evidence` y `fetch_issuer_name_histories` contra el código
  capturado, en 2010-2015 y 2016-2025 con límites 0, 1 y 10/5 (resultados, pruebas
  importadas, descargas, ficheros y salida). Las de importación trimestral y de
  selección de covers siguen comparando con la captura.
- `test_historical_identity_audit`: el subcomando rechaza las combinaciones inválidas
  sin ejecutar ningún paso y pasa las opciones publicadas al puente.
- `test_historical_runners_migration`: la captura antigua de `historical_price_audit`
  importaba `QUARTERS` de este módulo; la prueba se los da desde `P2010.quarters`.

Inventario: 64 módulos planos = 18 congelados + 37 permanentes + 9 pendientes.
