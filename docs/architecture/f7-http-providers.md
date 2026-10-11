# Transporte HTTP de las fachadas en proveedores (F7.17)

[ADR 0004](../adr/0004-legacy-provider-delegation.md) permite que una fachada plana
delegue su acceso a una fuente externa en un módulo concreto de
`infrastructure/providers`. Este bloque elimina el transporte `requests` duplicado
de siete fachadas; las fachadas resuelven por operación el user-agent y las claves.

| Fachada | Proveedor | Dependencias retiradas |
| --- | --- | --- |
| `macro.fetch_series`, `fetch_next_release_date` | `FredSource` (`require_complete=False` conserva el truncado histórico a `limit`) | `requests` |
| `edgar.fetch_company_facts`, `fetch_submissions`, mapa CIK | `SecXbrl`, `SecTickerMap` | `requests` |
| `insider._Documents.xml` | `SecForm4Documents.xml` | `requests` |
| `academic_factors._download_zip_csv` | `FrenchFactorSource.csv` | `io`, `requests` |
| `historical_tiingo` / `historical_wiki` | `TiingoPrices`, `NasdaqWikiSource` | `requests` |
| `sec_history._download_chunks` | nuevo `SecArchiveChunks` (pausa 0,15 s, timeouts 20/90 s, bloques de 1 MiB) | — |
| `universe`, página de Wikipedia de `history_refresh` | nuevo `SP500Sources` | `io`, `requests` |

Inventario: −11 dependencias. Las constantes públicas (`FF5_URL`, `MOM_URL`,
`GITHUB_CSV_URL`, `WIKI_URL`, `HISTORICAL_MEMBERSHIP_URL`, `historical_wiki.URL`,
`_wiki_ticker`) y los puntos de enganche usados por tests y motores
(`academic_factors._download_zip_csv`, `sec_history._download_chunks`,
`insider._Documents`) se conservan.

## Contratos y diferencias

- Mismas URL, parámetros, cabeceras SEC, timeouts, mensajes de 404 y de
  credencial FRED rechazada, `PriceResponse`/`FetchResponse` y categorías de error.
- Todas las respuestas se leen por bloques con límite de bytes y fallan sin
  truncar: FRED 32 MiB, SEC 64 MiB, mapa SEC 16 MiB, ZIP Fama-French 2 MB
  (CSV 8 MB), Tiingo y WIKI 8 MB, fuentes del S&P 500 32 MiB.
- Los errores de red FRED ya no incluyen la URL con la clave; el mensaje pasa a
  ser el tipo (`ConnectionError`, `ReadTimeout`) y la clasificación no cambia.
  Los HTTP ≥ 400 de FRED se describen como `FRED HTTP <código>`.
- `SecXbrl` normaliza el CIK antes de construir la URL; un CIK inválido falla
  antes de la petición.
- `universe` usaba `pandas.read_csv/read_html(URL)` (urllib, sin user-agent propio
  ni timeout). Ahora usa `requests` con el user-agent configurado, como ya hacía
  `history_refresh` para Wikipedia, y un timeout de 60 s.
- `yfinance` (`data_fetch`, `price_sync`, `history_refresh`) queda para un bloque
  posterior: los tests sustituyen `module.yf` en muchos sitios y conviene
  migrarlo con su propio contrato.

## Validación

Referencia `c324aabadf3c7b517129f5cd55ffff880921d865` en
`fixtures/http_providers_migration.json`. `test_http_providers_migration.py`
compara con el transporte capturado, mediante una respuesta simulada válida para
ambos protocolos y sin red: resultado, tipo y categoría de error y peticiones
emitidas para FRED (observaciones con truncado, 401, 429, 500, conexión y timeout;
publicaciones), SEC (hechos, presentaciones, 404/503, mapa CIK, XML Form 4),
Fama-French, Tiingo (200, 429, conexión), WIKI (200, 404, timeout), archivo SEC
(contenido y 403) y fuentes del S&P 500 (CSV, Wikipedia, histórico y límite).
También comprueba que la clave FRED no aparece en el error. Tres mutaciones
deliberadas (truncado FRED, mensaje 404 SEC, ticker Tiingo) hacen fallar pruebas.
`test_architecture.py` cubre el nuevo límite. Los tests que sustituían
`module.requests` usan ahora una respuesta en streaming sobre `requests.get`.

No hay tabla de tiempos: el coste depende de la red, que las pruebas no usan, y
el cambio local se limita a leer por bloques en lugar de cargar el cuerpo de una vez.
