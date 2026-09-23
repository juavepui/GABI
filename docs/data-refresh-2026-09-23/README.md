# Actualización gratuita de datos: 23 de septiembre de 2026

La base operativa es `data/gabi.db`. La composición del índice se guarda en
`data/sp500_historical_membership.csv` y el universo actual en
`data/sp500_constituents.csv`. Los datos y las copias de seguridad son locales,
excluidos de Git; el código, las fuentes y el resumen de cobertura sí se versionan.

## Resultado comprobado

| Conjunto | Antes | Después |
| --- | --- | --- |
| Composición histórica | Hasta 2025-08-23; 3.482 filas | Hasta 2026-09-23; 3.508 filas |
| Precios diarios | 5.033.331 filas | 5.087.907 filas: +54.576 |
| Datos contables SEC | 1.185.439 filas; presentaciones hasta 2026-09-15 | 1.377.954 filas: +192.515; hasta 2026-09-22 |
| Observaciones FRED | 2.314 filas | 34.937 filas: +32.623; nueve series |

Estas diferencias cuentan filas en todo el histórico descargado, incluidas fechas
anteriores a 2025 y hechos contables registrados bajo distintos tickers del mismo
emisor. No son necesariamente observaciones económicas independientes.
Coste de proveedores: **0 €**.

Se actualizaron los fundamentales SEC de **544 símbolos** presentes en 2025–2026,
incluidos tickers anteriores y empresas retiradas. Los 503 valores actuales tienen
datos contables y precios: **500** llegan al **2026-09-22**; **BE, ILMN y P** llegan
al **2026-09-21**, porque Yahoo no devolvió un cierre válido para el día 22.
Las filas vacías se descartan. Para BRK-B y BF-B se recuperaron las observaciones
ya existentes con grafía BRK.B/BF.B, comprobando que coincidían los cinco cierres
previos y sus ajustes. Los datos del día 23 en curso no se incorporaron como cierres.

Los precios de **ANSS, CTRA, DAY, DFS, HES, HOLX, IPG, JNPR, K y WBA** siguen sin
cobertura en esta base. **EA** conserva un solo día y **AVB**, 27: sus informes SEC
sí se recuperaron, pero Yahoo no proporcionó sus series completas. Por tanto,
no se presenta el histórico como un universo totalmente libre de sesgo de cobertura.

FRED llega al 22 de septiembre en T10Y2Y; DGS10, DFII10 y high yield al 21;
dólar al 18; balance de la Fed al 16; las series mensuales, a agosto de 2026.
Esas fechas son las de observación, no las de publicación. También se amplió
el pasado: por ejemplo, CPI llega ahora hasta 1948 y Fed Funds hasta 1954.

La comprobación de integridad SQLite devuelve `ok`; se verificó que las 3.482
filas originales de composición permanecen iguales. La suite completa pasó
**664 pruebas**; las últimas comprobaciones de composición y normalización
pasaron **19 pruebas**. Ruff, mypy y compilación de la página pasan.
Detalle reproducible en [`summary.json`](summary.json) y
[`coverage.csv`](coverage.csv), con cobertura por símbolo y por fecha.

## Fuentes y método

- **Composición:** se conserva el histórico comunitario existente hasta
  2025-08-23. Se añaden 36 eventos contrastados con comunicados de S&P DJI
  y de los emisores: incorporaciones, exclusiones y cinco cambios de ticker.
  Las fechas efectivas se distinguen de las fechas de publicación. Las
  escisiones que elevan temporalmente el número de valores a 504 se respetan.
- **Conciliación:** se reconstruyen los 503 valores observados el 2026-09-23,
  incluidos los cambios del 2026-09-21. La última fila del CSV es una observación
  de composición vigente, no un cambio del índice ocurrido ese día. No se usa la
  composición actual para rellenar retrospectivamente 2025 o principios de 2026.
- **Yahoo Finance:** precios diarios con cierre ajustado y splits. Se solicitan
  series completas para los tickers pendientes, evitando concatenar ajustes
  de ventanas distintas. Se excluye la sesión que todavía no ha cerrado.
  Los cambios de ticker acreditados pueden usar la serie del sucesor hasta
  la víspera del cambio; no se sustituye una empresa adquirida por su comprador.
- **SEC EDGAR:** Company Facts y Submissions, con CIK y fecha real de presentación.
  Se conservan datos históricos y se incorporan nuevas observaciones, sin fingir
  que un informe de 2026 estaba disponible en 2025. Doce antiguos miembros
  requieren CIK documentado porque han desaparecido del mapa de tickers actual.
- **FRED:** se usa la clave gratuita ya configurada, sin registrarla en los
  informes. Se piden hasta 10.000 observaciones por serie; las 260 habituales
  no cubrían todo 2025 en las series diarias. CPI se guarda con la transformación
  interanual `pc1` que ya utiliza GABI; las demás series conservan `lin`.

El registro reproducible está en
[`sp500_extension.json`](../../src/gabi/resources/sp500_extension.json), y los
CIK de antiguos miembros en
[`former_issuers_2025_2026.json`](../../src/gabi/resources/former_issuers_2025_2026.json).
[`sources.json`](sources.json) incluye las URL oficiales revisadas y las huellas
de los documentos que admitieron descarga directa. Algunos PDF bloquean esa
descarga; se contrastaron mediante lectura en el navegador, sin archivar su binario.

## Repetición y seguridad de los datos

```powershell
.venv/Scripts/python.exe -m gabi.history_refresh
```

El comando exige un registro de composición revisado hasta la fecha de ejecución.
Para una fecha posterior hay que ampliar y conciliar ese registro; no se prolonga
su validez automáticamente. Antes de escribir se crea una copia consistente de
SQLite (incluido WAL) y de los CSV en `data/history_refresh/<fecha-hora>/`.
El informe de esa ejecución registra cobertura, descargas y fallos por símbolo.
Un refresco del CSV comunitario antiguo no elimina la extensión local.

El snapshot congelado de `data/full_universe_audit/` y los resultados del
experimento anterior no se actualizan. Para nuevos experimentos debe crearse
otro snapshot e identificarse su fecha y sus fuentes.

## Límites que esta actualización no resuelve

- La composición original anterior a la extensión sigue siendo una fuente
  comunitaria; se preserva, incluidas sus filas duplicadas anteriores a 2025.
- Descargar informes de una empresa deslistada no recupera automáticamente
  sus precios. Los huecos se contabilizan y no se rellenan por interpolación.
- Las series FRED son la versión revisada disponible hoy, no un histórico de
  vintages ALFRED para simular qué se conocía en cada fecha.
- Los sectores históricos y la migración completa de identidades conservan
  las limitaciones documentadas en `docs/entity-identity.md`.
- 2026 es un año parcial; esta descarga no constituye un nuevo resultado de
  rentabilidad ni una validación fuera de muestra de la estrategia.
