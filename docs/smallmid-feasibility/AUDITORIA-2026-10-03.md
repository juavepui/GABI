# Auditoría del piloto de cobertura #44 · 2026-10-03

El [método](AUDIT-METHOD-2026-10-03.md) se publicó en `e883844` antes de
ejecutar `scripts/audit_smallmid_pilot_prices.py` sobre los datos de la prueba.
El [resultado JSON](pilot-price-audit-2026-10-03.json) guarda los SHA-256 de las
tres entradas; la caché de comprobaciones de precio y la validación de Kaggle
tenían fecha de modificación 2026-09-28 UTC. Esta es una auditoría de **cobertura
de inputs**, no una prueba de GABI. No se abrió `data/gabi.db`, ningún ranking,
retorno siguiente ni reserva ciega; tampoco se descargaron fuentes.

## Qué se reproduce del piloto original

Los tres CSV de universo contienen exactamente 1.785, 2.102 y 2.400 CIK
distintos en 2012-06-30, 2017-06-30 y 2022-06-30. Sus float declarados están
en el intervalo publicado (300 M–20.000 M USD) y sus fechas de float caen en los
455 días anteriores a cada corte. La muestra tiene 30 CIK por cohorte y fecha,
sin duplicados. En 2017 la cohorte sin reportes posteriores tiene **7/30 = 23 %**
de candidatos en el catálogo Tiingo; el 33 % del README anterior no coincidía
con `muestra-cobertura.csv` ni `viabilidad.json`.

La regla de «dejar de presentar» mira si faltan posteriores facts SEC de float o
acciones de portada durante 18 meses. No verifica que la acción se deslistara:
fusiones, cambios de CIK, ausencia de XBRL y otros motivos pueden entrar en esa
cohorte. Del mismo modo, un hecho de float con fecha anterior al corte puede
haberse presentado **después** del corte. El caché de frames utilizado guarda
`accn`, `end` y `val`, pero no `filed`; la propia [API de frames de la
SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
selecciona el último hecho presentado para el periodo. El universo grande es
una **candidatura histórica**, aún no un universo con disponibilidad PIT probada.

## Tickers candidatos frente a cotizaciones verificadas

Cada celda es un recuento sobre 30 CIK de la muestra fija. «Verificada en fecha»
aplica la puerta de identidad/nivel SEC preregistrada en #44 a las series ya
recogidas. «Continua 92 d» exige la misma serie hasta 92 días más tarde; no
resuelve el retorno terminal de una empresa que salió antes.

| Fecha | Cohorte | Catálogo Tiingo | Verificada en fecha | Continua 92 d |
| --- | --- | ---: | ---: | ---: |
| 2012-06-30 | Sin reportes posteriores | 7 | 2 | 2 |
| 2012-06-30 | Sigue reportando | 22 | 22 | 22 |
| 2017-06-30 | Sin reportes posteriores | 7 | 5 | 3 |
| 2017-06-30 | Sigue reportando | 28 | 26 | 26 |
| 2022-06-30 | Sin reportes posteriores | 11 | 1 | 1 |
| 2022-06-30 | Sigue reportando | 25 | 20 | 20 |

En conjunto, la cohorte que deja de reportar tiene 8/90 series verificadas en
la fecha y 6/90 continuas 92 días; la otra, 68/90 en ambos casos. Estos son
recuentos **provisionales de la recogida guardada el 2026-09-28**, no la
cobertura final cuando se congele #44. El script da la misma fuente aceptada
que `smallmid_test.usable()` para los 180 CIK/fechas (cero discrepancias).
Las series pueden proceder de Yahoo, Tiingo, WIKI o Kaggle según la prioridad y
la puerta de concordancia de A2. Un ticker del catálogo Tiingo puede carecer de
serie descargada o fallar la identidad, y una serie validada puede venir de otra
fuente. [Tiingo](https://www.tiingo.com/pricing) mantiene un cupo gratuito de
500 símbolos únicos al mes; [WIKI](https://data.nasdaq.com/databases/WIKIP)
dejó de mantenerse en 2018.

## Qué impide decidir la viabilidad acreditada

- No hay medición de fundamentales necesarios para el Composite por CIK y
  fecha con fecha de presentación anterior al corte. La afirmación anterior de
  cobertura total por SEC no se desprende de este piloto.
- Falta rehacer la regla de universo con facts presentados **hasta** la fecha
  de señal, no solo con `end` anterior. Esto puede cambiar tamaños y selección;
  requiere una ampliación explícita del protocolo #44 antes de cualquier ranking.
- La cohorte «sin reportes» necesita contraste de identidad y eventos terminales
  por CIK. La ausencia de 92 días de precio no equivale a retorno perdido.
- La recogida de precios continúa bajo A3: se congela al recorrer Tiingo sin
  detenerse por el cupo o el 2027-01-15, lo que ocurra antes. No se deben abrir
  rankings ni retornos antes de ese hito.

La decisión histórica del propietario de intentar una prueba con cotas se
mantiene. Esas «cotas» P10/P90 del preregistro son escenarios de sensibilidad,
no límites matemáticos sobre los retornos faltantes. **Este piloto no demuestra
que la prueba sea viable ni inviable con
estándar PIT completo**, y no aporta evidencia de que GABI supere al S&P 500.
