# Ampliación histórica gratuita: 1996–2015

Ejecutada el 23 de septiembre de 2026 sobre `data/gabi.db`, después de la
[actualización de 2025–2026](../data-refresh-2026-09-23/README.md). Coste de
proveedores: **0 €**. Se han descargado y guardado los datos disponibles;
la cobertura sigue sin permitir un backtest fundamental completo desde 1996.

## Resultado comprobado

| Datos | Resultado |
| --- | --- |
| Composición de fja05680 | 2.231 snapshots de 1996–2015, con 984 tickers distintos |
| Diferencia frente al histórico comunitario anterior | 64 tickers adicionales en el conjunto del periodo |
| Precios FINSABER | 2.604.620 observaciones de 788 tickers, entre 2000-01-03 y 2015-12-31 |
| Precios Yahoo añadidos | 21 series completas; 215.060 filas nuevas en la tabla operativa, incluyendo fechas fuera de 1996–2015 |
| Cobertura operativa de precios anteriores a 2016 | De 396 a 417 de los 984 tickers históricos |
| Informes SEC recuperados | 151.444 hechos contables archivados, 203 CIK y 205 tickers candidatos; presentados entre 2009-04-29 y 2015-12-21 |
| FRED | Se conserva la ampliación anterior: nueve series, con fechas iniciales diferentes |

La base operativa termina con **5.302.967 precios**, **1.377.954 hechos SEC
en la tabla por ticker** y **34.937 observaciones macro**. Los precios del
archivo y sus 151.444 hechos SEC se cuentan aparte. Varios tickers candidatos
pueden corresponder al mismo CIK; esos hechos no son observaciones económicas
independientes. Tener alguna fila no implica cobertura continua ni elegibilidad
para el ranking.

El detalle está en [summary.json](summary.json),
[coverage-by-date.csv](coverage-by-date.csv) y
[coverage-by-symbol.csv](coverage-by-symbol.csv).
La cobertura por fecha exige al menos un precio en los diez días naturales
anteriores, incluido el día consultado. Los conteos de hechos contables exigen
alguna presentación anterior a esa fecha: no certifican frescura, todas las
métricas necesarias ni identidad histórica.

## Fuentes y tratamiento

- [fja05680/sp500](https://github.com/fja05680/sp500) proporciona **miembros del
  índice, no precios ni balances**. Su autor advierte de posibles miembros
  ausentes en los primeros años. El primer snapshot enumera 487 valores frente
  a los 469 de nuestra fuente anterior. También contiene etiquetas renombradas
  retrospectivamente y posibles tickers reciclados. Se guarda como fuente
  adicional, sin sustituir automáticamente el universo usado en las auditorías.
- [FINSABER](https://huggingface.co/datasets/finsaber-team/FINSABER-reproduce)
  publica un CSV de precios con valores deslistados, bajo licencia Apache 2.0.
  Se han importado las filas de 2000–2015 que corresponden a los 984 tickers
  enumerados. El cierre original tiene ajustes distintos a Yahoo: por ejemplo,
  AAPL el 2000-01-03 aparece con cierre 111,9328 y ajustado 0,8421. Se conservan
  ambos campos, sin concatenarlos con los precios operativos ni usarlos para
  calcular capitalizaciones. Se validan valores positivos, finitos y orden
  OHLC, pero eso no certifica identidad, ajustes corporativos ni retornos de
  exclusión. No se ejecuta código descargado ni se cargan archivos pickle.
- [lawcal/sp500-components-history](https://github.com/lawcal/sp500-components-history)
  aporta 1.002 registros de candidatos ticker/CIK con nombres y fechas,
  algunas aproximadas. Se descartan conflictos con los mapas locales y actuales:
  36 tickers presentan conflicto o reutilización. La ausencia de conflicto no
  acredita la relación histórica: un CIK puede pertenecer al comprador o sucesor.
- **Yahoo Finance:** solo se solicitaron series nuevas para candidatos presentes
  también en el mapa SEC actual. Se exige que los precios coincidan temporalmente
  con alguna pertenencia histórica al índice. BUD se rechazó porque su serie
  actual no coincide con el periodo del miembro antiguo. Se guardan series
  completas para mantener ajustes coherentes y se excluye la sesión en curso.
- **SEC Company Facts:** se comprueba el CIK de cada respuesta y se conservan
  las fechas reales de presentación. De 249 candidatos consultados, 205 tienen
  hechos anteriores a 2016; el informe enumera los fallos y respuestas sin esos
  hechos. Los datos se guardan en el archivo y por entidad/CIK, **sin crear
  alias históricos ni introducir candidatos en la tabla operativa por ticker**.
  Una posterior acreditación del alias permitirá utilizar los hechos del emisor
  correcto. El campo `candidate_symbol` registra la pista de búsqueda, no una
  identidad certificada.

Las revisiones y los SHA-256 de las tres fuentes comunitarias están fijados en
[sources.json](sources.json). Los informes Company Facts son respuestas de la
SEC, conservadas localmente por CIK. No se incluyen claves de API en los informes.

## Qué falta para utilizar 1996 como inicio de un backtest

1. Completar y verificar la composición e identidad de los primeros años,
   incluidos cambios de nombre, fusiones y reutilización de tickers.
2. Completar precios de empresas desaparecidas en 1996–1999 y validar los
   ajustes, discontinuidades y retornos finales de las series archivadas.
3. Extraer fundamentales anteriores a 2009 de informes antiguos. La
   [API estructurada de SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
   se apoya en XBRL, obligatorio desde 2009; los
   [conjuntos estructurados](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets)
   comienzan en enero de 2009. Hay documentos anteriores en EDGAR, pero requieren
   otro proceso de extracción y comprobación. Un comparativo de 2006 publicado
   en 2009 no puede tratarse como información disponible en 2006.

No se han recalculado rentabilidades, cambiado pesos ni modificado el snapshot
congelado de la auditoría anterior.

## Consulta y reproducción

En **Calidad de los datos → Archivo histórico anterior a 2016** se puede consultar
la cobertura, la composición por fecha y los precios archivados. Las tablas
`historical_membership`, `historical_prices`, `historical_issuer_candidates` y
`historical_facts` están en la misma base SQLite que los datos anteriores, con
procedencia explícita. Los hechos por CIK también están en `entity_observations`.

```powershell
.venv/Scripts/python.exe -m gabi.historical_backfill
```

El comando descarga CSV/JSON gratuitos, comprueba hashes y crea una copia
consistente de SQLite antes de escribir. La ejecución y sus respuestas originales
se conservan en `data/history_refresh/1996_2015/`; son datos locales excluidos de
Git. Repetir una fuente fijada no duplica sus filas. Los candidatos permanecen
pendientes de revisión aunque la descarga tenga éxito.

Validación: integridad SQLite `ok`; suite completa de 670 pruebas y cinco pruebas
específicas tras el ajuste final de atribución SEC; Ruff, mypy y compilación de
las páginas modificadas sin errores.
