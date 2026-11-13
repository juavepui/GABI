# Piloto de extracción de fundamentales de 10-K sin XBRL (#41)

Pregunta: ¿se pueden obtener los fundamentales anteriores a 2009 (sin XBRL)
extrayéndolos del texto de los 10-K con suficiente precisión como para ampliar
la historia de GABI?

## Método

- **Muestra**: 30 miembros del S&P 500 a 2008-12-31 con 10-K del ejercicio 2008
  presentado entre enero y abril de 2009 (sin XBRL) y ese ejercicio disponible
  como comparativo en un 10-K XBRL posterior. Se elige una de cada *k* en orden
  alfabético.
- **Documentos**: el principal del 10-K y el anexo EX-13, donde muchas empresas
  publicaban los estados financieros.
- **Extractor** (`gabi.tenk_extraction` en el commit 1283bf5; desde ADR 0002
  `gabi.domain.research.tenk_extraction`, ejecutable con
  `python -m gabi_cli research tenk-extraction [--subset ajuste|reserva]`): tablas HTML de resultados, balance y
  flujos de caja; etiquetas normalizadas; columna del ejercicio más reciente;
  escala («in millions» / «in thousands») de la tabla, del texto que la
  precede o la dominante del documento.
- **Referencia**: el valor XBRL del mismo ejercicio en la **primera**
  presentación que lo incluye (Company Facts de SEC). Una discrepancia puede
  ser un error de extracción o una reexpresión posterior.
- **Protocolo contra el sobreajuste**: la división se fijó antes de mirar
  ningún fallo. Las posiciones pares (15 empresas) sirven para ajustar el
  extractor y las impares (15) se miden **una sola vez** al final. Se hicieron
  dos rondas de ajuste. La segunda empeoraba el ajuste (56 frente a 59
  aciertos) y se descartó.

## Resultados (8 partidas por empresa)

| | Ajuste | Reserva |
| --- | ---: | ---: |
| Valores comparables | 98 | 110 |
| Exactos (±0,5 %) | 60 % | **65 %** |
| Discrepancia del 0,9–1,12× (probable reexpresión: operaciones discontinuadas, SFAS 160) | 9 % | 10 % |
| Erróneos | 21 % | **8 %** (4 de ellos, escala ×1000) |
| No extraídos | 9 % | **17 %** |

Por partida, exactitud en la reserva:

| Partida | Exactitud |
| --- | ---: |
| Deuda a largo plazo | 85 % |
| Resultado operativo | 70 % |
| Amortizaciones | 69 % |
| Beneficio neto | 67 % |
| Capex | 64 % |
| Ingresos | 60 % |
| Patrimonio | 53 % |
| Flujo operativo | 53 % |

## Conclusión

**Con este extractor, la extracción no alcanza la calidad necesaria para
ampliar GABI.**

- El Composite necesita unas ocho partidas por empresa y año. Con un 8 % de
  valores erróneos por partida, **cerca de la mitad de las empresas tendría al
  menos un dato mal**, a veces por un factor de 1.000. Con un 17 % de no
  extraídos, la cobertura de métricas caería por debajo del 70 % exigido en
  muchas empresas.
- Las discrepancias pequeñas no son errores del extractor: el texto da el dato
  original, que es el correcto en fecha. Pero confirman que los comparativos
  XBRL no sirven como sustituto (#41).
- Además, el piloto solo cubre documentos de 2009, los más fáciles. Los 10-K de
  2000–2005 tienen formatos más heterogéneos, incluido texto plano sin
  tablas HTML.

## Opciones

1. **Extractor robusto con comprobaciones contables**: activo = pasivo +
   patrimonio, beneficio ≈ BPA × acciones, y rechazo de valores con escala
   ambigua. Convierte errores en ausencias, pero exige varios días de trabajo y
   una nueva medición con 30 empresas nuevas. No hay garantía de llegar a una
   precisión de investigación (> 95 %).
2. **Fuente de pago con fundamentales point-in-time «as reported» y empresas
   deslistadas**, por ejemplo Sharadar SF1 en Nasdaq Data Link, desde 1998, o
   Compustat. Resolvería el problema, pero tiene coste.
3. **Descartar la ampliación**: GABI completo solo es evaluable desde 2010, y
   la nueva evidencia vendrá de pruebas prospectivas (#43, #42).
