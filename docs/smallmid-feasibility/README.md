# Viabilidad de probar GABI fuera del S&P 500 con datos gratuitos (#44)

Código: `gabi.smallmid_feasibility`. Datos en esta carpeta.

> **Corrección del 2026-10-03:** este piloto ya se realizó en septiembre. La
> [auditoría posterior](AUDITORIA-2026-10-03.md) reproduce los CSV y separa
> candidatos del catálogo Tiingo de series realmente descargadas y verificadas.
> El universo aún no tiene acreditada la disponibilidad *point-in-time* del
> float; la cobertura de fundamentales tampoco se midió. La conclusión inicial
> de inviabilidad no era una medida de cobertura efectiva y no decide la prueba
> preregistrada posterior.

## Regla de universo (fijada antes de mirar resultados)

En cada fecha (30 de junio de 2012, 2017 y 2022), las empresas con *public
float* SEC (XBRL) fechado en los 15 meses anteriores, entre 300 millones y
20.000 millones de USD, sin los emisores del S&P 500 de esa fecha. Sale de
datos SEC y no selecciona solo emisores que sigan reportando hoy.

## 1. Tamaño del universo: muy bueno

| Fecha | Empresas | Sin float ni acciones de portada SEC en los 18 meses siguientes | Float mediano |
| --- | ---: | ---: | ---: |
| 2012-06-30 | 1.785 | 47 (2,6 %) | 1.024 M USD |
| 2017-06-30 | 2.102 | 71 (3,4 %) | 1.322 M USD |
| 2022-06-30 | 2.400 | 200 (8,3 %) | 1.243 M USD |

Es entre 3,5 y 5 veces el S&P 500 como universo candidato. Solo aumentaría la
potencia de la prueba de sección cruzada (#39, #40) si se acreditan los inputs y
retornos de una fracción suficiente sin selección sesgada.

La SEC ofrece datos XBRL desde 2009–2010, pero **este piloto no midió** qué
fracción de estas empresas tiene los fundamentales necesarios para GABI en cada
fecha. «Sin float ni acciones de portada posteriores» es un proxy de cese de
información, no una deslistación acreditada.

## 2. Precios de las empresas sin reportes posteriores: el obstáculo

Muestra de 60 empresas por fecha, la mitad sin facts posteriores de float o
acciones de portada en la ventana definida:

| Cohorte | Ticker SEC actual | Ticker recuperado del último 10-K | Candidato en el catálogo Tiingo, no precio verificado |
| --- | ---: | ---: | ---: |
| 2012, sin reportes posteriores | 7 % | 67 % | **23 %** |
| 2012, sigue reportando | 50 % | 30 % | 73 % |
| 2017, sin reportes posteriores | 3 % | 67 % | **23 %** |
| 2017, sigue reportando | 80 % | 17 % | 93 % |
| 2022, sin reportes posteriores | 0 % | 73 % | **37 %** |
| 2022, sigue reportando | 80 % | 20 % | 83 % |

- La cohorte sin reportes posteriores suele perder el ticker SEC actual. Se
  recuperó uno del último 10-K en aproximadamente el 70 % de sus casos, pero
  el **23–37 % solo es presencia en el catálogo Tiingo para la ventana**. No
  prueba descarga, atribución al CIK ni disponibilidad de retorno. El cálculo
  original no comprobó WIKI para esta tabla.
- **Tiingo gratuito limita a ~500 símbolos al mes.** Descargar ~2.000
  empresas por fecha durante 15 años llevaría muchos meses.
- La identidad acreditada (pruebas SEC de ticker por fecha, como en el #27 y el
  #34) para miles de empresas es posible con las mismas herramientas, pero
  costosa.

## Conclusión

El informe original juzgó inviable alcanzar el estándar acreditado con datos
gratuitos a partir del catálogo Tiingo. Esa inferencia era demasiado fuerte:
no medía series verificadas y después se añadió Kaggle mediante la ampliación
A2 del preregistro. La [auditoría de las series recogidas](AUDITORIA-2026-10-03.md)
muestra una brecha grave de cobertura en esta muestra, pero la recogida #44
sigue abierta hasta su congelación fijada en A3. No se ha medido aún la cobertura
PIT de fundamentales ni se han acreditado todas las salidas terminales.

Se preregistró una **sensibilidad a retornos ausentes**, como en el #33:
calcular el IC suponiendo que los emisores sin precio rinden como los percentiles
10 y 90 observados, con la dirección adversa o favorable según su score. Son
escenarios de imputación, **no cotas matemáticas**: un retorno faltante puede
quedar por debajo del P10 o por encima del P90. Coste estimado originalmente:

- precios de supervivientes vía Yahoo (rápido);
- desaparecidas vía Tiingo y WIKI (varios meses por el límite de Tiingo);
- identidad por CIK y ticker de 10-K;
- un preregistro nuevo (ya registrado en septiembre).

## Opciones para decidir

1. **Prueba con cotas**: el propietario la eligió y preregistró el 2026-09-27;
   los rankings y resultados esperan a la congelación A3. Las cotas no
   sustituyen la acreditación de identidad y fechas.
2. **Solo supervivientes y cohortes recientes**: más rápida, pero con sesgo de
   supervivencia que no se puede acotar bien. No recomendada.
3. **Cerrar como no viable** con datos gratuitos y apoyarse en la evidencia de
   factores (#45) y en las pruebas ciegas (#42, #43).
