# Análisis de potencia: cuánta evidencia hace falta para descartar la suerte (#39)

Entrada: resultados ya publicados del #35 (serie continua acreditada, V1
Top-20). Salida completa en [power.json](power.json); código en
`gabi.power_analysis`. Prueba **unilateral** (α = 5 %), porque la hipótesis es
que GABI supera, y potencia objetivo del 80 %.

## Resumen

1. Con la ventaja observada, **comparar el Top-20 con el SPY es una prueba de
   poca potencia**: hacen falta unos 18 años con el efecto de 2011–2025, o 29
   con el de 2016–2025. Hoy hay 14,25 (potencia actual del 70 %). Añadir años
   ayuda, pero no basta por sí solo.
2. **Comparar con el universo elegible** (el mismo S&P 500 que puntúa GABI,
   equiponderado) quita el ruido del mercado y es la comparación correcta
   para la selección de acciones. Necesita ~12 años, y la serie actual tiene
   una potencia del 86 %.
3. **La prueba de sección cruzada (IC)** usa ~350–450 empresas por trimestre.
   Con los 57 trimestres disponibles, un IC medio de 0,05 se detecta con un
   81–98 % de potencia. Es la prueba principal recomendada para el #40.
4. **La prueba ciega**, con el mismo efecto, necesitaría unos 18 años sola, o
   unos 4 años más si se combina con 2011–2025 mediante una regla fijada de
   antemano (#42).

## Cartera (V1 Top-20, exceso trimestral)

| Prueba | Trimestres | Exceso medio | Desv. típica | IR anual | t | Potencia actual | Años para el 80 % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vs SPY, 2011–2025 | 55 | +1,06 pp | 3,62 pp | 0,59 | 2,18 | 70 % | 17,9 |
| vs SPY, 2016–2025 | 37 | +0,91 pp | 3,92 pp | 0,46 | 1,41 | 41 % | 28,8 |
| vs universo elegible, 2011–2025 | 55 | +1,21 pp | 3,33 pp | 0,73 | 2,70 | 86 % | 11,6 |
| vs universo elegible, 2016–2025 | 37 | +1,16 pp | 3,68 pp | 0,63 | 1,92 | 61 % | 15,4 |

Efecto mínimo detectable frente al SPY (exceso trimestral, 80 %):

| Años de historia | 10 | 14,25 | 20 | 25 |
| --- | ---: | ---: | ---: | ---: |
| Efecto mínimo | 1,42 pp | 1,19 pp | 1,01 pp | 0,90 pp |

**Aviso de transparencia.** Las filas «vs universo elegible» se calcularon
aquí por primera vez con datos ya publicados (t = 2,70). Como ya se han visto,
**no pueden ser la prueba confirmatoria del #40**: allí quedan como
descriptivas. La prueba principal del #40 es el IC, que no se ha calculado.

## Sección cruzada (escenarios; no se ha calculado el IC real)

La dispersión trimestral del IC no puede bajar del mínimo teórico de
1/√N ≈ 0,053 con N ≈ 350. Se usan dos escenarios, 0,10 y 0,15.

| IC medio | Desv. IC | Años para el 80 % | Potencia con 57 trimestres |
| --- | ---: | ---: | ---: |
| 0,02 | 0,10 / 0,15 | 38,6 / 86,9 | 45 % / 26 % |
| 0,03 | 0,10 / 0,15 | 17,2 / 38,6 | 73 % / 45 % |
| 0,05 | 0,10 / 0,15 | 6,2 / 13,9 | 98 % / 81 % |
| 0,08 | 0,10 / 0,15 | 2,4 / 5,4 | 100 % / 99 % |

## Múltiples pruebas

Con las 29 configuraciones documentadas (#12, #23 y #36), el Sharpe anual
máximo esperable por azar es de ~0,19, y el DSR compara el Sharpe elegido
con ese listón. **Cada prueba nueva sube el listón**. Por eso las pruebas
siguientes deben ser pocas, preregistradas y elegidas por su potencia, no por
su resultado.

## Qué implica

- **Ampliar la historia** (#41) aumenta la potencia de todas las pruebas, pero
  pasar de 14 a ~25 años exige fundamentales anteriores a 2009, que no existen
  en XBRL. Primero hay que medir su viabilidad.
- **La vía con más potencia inmediata** es la sección cruzada preregistrada
  (#40).
- **La evidencia definitiva es prospectiva** (#42): hay que fijar ya cómo se
  analizará y combinará, antes de ver ningún dato.
- **Límite**: si el efecto real fuese menor que el observado (lo esperable si
  hubo algo de sobreajuste en el diseño), todos los plazos se alargan.
