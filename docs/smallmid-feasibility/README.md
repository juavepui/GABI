# Viabilidad de probar GABI fuera del S&P 500 con datos gratuitos (#44)

Código: `gabi.smallmid_feasibility`. Datos en esta carpeta.

## Regla de universo (fijada antes de mirar resultados)

En cada fecha (30 de junio de 2012, 2017 y 2022), las empresas con *public
float* SEC (XBRL) fechado en los 15 meses anteriores, entre 300 millones y
20.000 millones de USD, sin los emisores del S&P 500 de esa fecha. Sale solo de
datos SEC, así que **incluye a las empresas que después desaparecen**.

## 1. Tamaño del universo: muy bueno

| Fecha | Empresas | Dejan de presentar informes en 18 meses | Float mediano |
| --- | ---: | ---: | ---: |
| 2012-06-30 | 1.785 | 47 (2,6 %) | 1.024 M USD |
| 2017-06-30 | 2.102 | 71 (3,4 %) | 1.322 M USD |
| 2022-06-30 | 2.400 | 200 (8,3 %) | 1.243 M USD |

Es entre 3,5 y 5 veces el S&P 500. Para la prueba de sección cruzada (#39,
#40), eso multiplica la potencia estadística.

**Fundamentales**: la SEC los cubre para todas estas empresas desde 2009–2010
(mismo mecanismo que en el S&P 500).

## 2. Precios de las empresas que desaparecen: el obstáculo

Muestra de 60 empresas por fecha, la mitad de ellas de las que desaparecen:

| Cohorte | Ticker SEC actual | Ticker recuperado del último 10-K | Algún precio gratuito (Tiingo + WIKI) |
| --- | ---: | ---: | ---: |
| 2012, desaparecidas | 7 % | 67 % | **23 %** |
| 2012, supervivientes | 50 % | 30 % | 73 % |
| 2017, desaparecidas | 3 % | 67 % | **33 %** |
| 2017, supervivientes | 80 % | 17 % | 93 % |
| 2022, desaparecidas | 0 % | 73 % | **37 %** |
| 2022, supervivientes | 80 % | 20 % | 83 % |

- Las empresas que desaparecen **pierden su ticker en la SEC**. Se puede
  recuperar del texto de su último 10-K en ~70 % de los casos, pero después
  **solo un 23–37 % tiene serie de precios gratuita**. Yahoo no sirve valores
  deslistados; Tiingo y WIKI solo tienen una parte.
- **Tiingo gratuito limita a ~500 símbolos al mes.** Descargar ~2.000
  empresas por fecha durante 15 años llevaría muchos meses.
- La identidad acreditada (pruebas SEC de ticker por fecha, como en el #27 y el
  #34) para miles de empresas es posible con las mismas herramientas, pero
  costosa.

## Conclusión

**Con datos gratuitos no se puede alcanzar el estándar acreditado de las
pruebas anteriores**. Faltarían los precios de ~65–77 % de las empresas que
desaparecen, justo las que evita el sesgo de supervivencia.

Sí sería posible una **prueba con cotas de sensibilidad**, como en el #33:
calcular el IC suponiendo que las desaparecidas sin precio rinden como el peor
y como el mejor decil. La conclusión solo sería firme si se mantiene en ambos
extremos. Coste estimado:

- precios de supervivientes vía Yahoo (rápido);
- desaparecidas vía Tiingo y WIKI (varios meses por el límite de Tiingo);
- identidad por CIK y ticker de 10-K;
- un preregistro nuevo.

## Opciones para decidir

1. **Prueba con cotas**: viable, con sesgo acotado y explícito, y larga
   (meses, por Tiingo).
2. **Solo supervivientes y cohortes recientes**: más rápida, pero con sesgo de
   supervivencia que no se puede acotar bien. No recomendada.
3. **Cerrar como no viable** con datos gratuitos y apoyarse en la evidencia de
   factores (#45) y en las pruebas ciegas (#42, #43).
