# Método cerrado para auditar la cobertura de precios del piloto #44

Fijado el 2026-10-03 antes de calcular la tabla de esta auditoría. No modifica el
preregistro de la prueba #44 ni su regla de congelación A3. La muestra sigue siendo
la publicada el 2026-09-27: 30 CIK que dejan de tener *public float* o acciones de
portada SEC en 18 meses y 30 que continúan, en cada una de las fechas
2012-06-30, 2017-06-30 y 2022-06-30. «Dejan de reportar» es un **proxy**, no una
deslistación demostrada.

Entradas: `muestra-cobertura.csv` publicada; las comprobaciones de identidad y
nivel de precio ya recogidas en `data/smallmid_test/level_checks.csv`; el estado de
concordancia de Kaggle en `data/smallmid_test/kaggle_agreement.json`. El script
`scripts/audit_smallmid_pilot_prices.py` lee estos archivos, calcula sus SHA-256 y
solo produce recuentos por fecha y cohorte. No descarga, no consulta `gabi.db`, no
abre rankings ni retornos y no calcula el Composite.

Se publicarán tres medidas distintas, siempre con denominador 30:

1. **Candidato de catálogo Tiingo:** el ticker actual o recuperado figura en la
   lista de Tiingo con fechas que cubren la ventana que usó el piloto original.
   Es una posibilidad de descarga, no una cotización acreditada.
2. **Serie identificada en la fecha:** existe una serie descargada que cumple la
   regla de #44: comienza al menos 400 días antes, llega a la fecha, tiene una
   comprobación SEC de nivel `passed` en esos 400 días y ninguna `failed` en la
   misma ventana. Prioridad Yahoo, Tiingo, WIKI y Kaggle; Kaggle solo si la
   concordancia global supera su puerta y para fechas hasta 2021-01-02.
3. **Serie continua 92 días:** la misma regla, con datos hasta 92 días después.
   Es una cota conservadora de continuidad; una empresa absorbida o deslistada
   puede tener salida acreditable sin 92 días de precios. No se infiere retorno.

La segunda y tercera medidas describen el **estado de recogida actual**, no una
cobertura definitiva. A3 prohíbe rankings y análisis hasta completar la cola de
Tiingo o el 2027-01-15, lo primero que ocurra. Los SHA del informe fijarán qué
versión mutable de las entradas se observó. La documentación de la [SEC sobre
frames](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
explica que la API entrega el último hecho presentado para el periodo; los frames
usados por el piloto carecen de fecha de presentación en el caché local. Por eso
el universo actual no acredita por sí solo disponibilidad *point-in-time*.
[Nasdaq Data Link](https://data.nasdaq.com/databases/WIKIP) señala que WIKI dejó de
mantenerse en 2018; no puede cubrir el tramo posterior. La cobertura de
fundamentales y la identidad de todas las salidas siguen sin medirse en este
piloto; no se inferirán de la presencia de un *public float*.
