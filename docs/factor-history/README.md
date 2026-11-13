# La idea de GABI con 60 años y varios mercados: resultado (#45)

Preregistro: [PREREGISTRO.md](PREREGISTRO.md) (sha256
`d86e513845b9872c91f23caacfebbdf36e6bdca82eee1a335fde5ffb94779c99`, commit
`16bdca0`). Datos: Kenneth French Data Library, gratuitos, con su SHA-256 en
[resultado.json](resultado.json). Serie mensual en
[mezcla-mensual.csv](mezcla-mensual.csv).

## Decisión preregistrada: **idea respaldada**

La mezcla de GABI (valor 30 %, calidad/rentabilidad 35 %, momentum 25 % y bajo
riesgo 10 %) es una cartera que compra lo que esos criterios favorecen y vende
lo que desfavorecen:

| Muestra | Meses | Prima anual | Volatilidad | Sharpe | t Newey-West | p (Holm) | Peor racha |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **EE. UU. 1963–2015** (principal, antes del diseño) | 630 | **+4,9 %** | 6,9 % | 0,69 | **4,60** | < 0,0001 | −28 % |
| Europa 1990–2026 | 430 | +5,9 % | 4,3 % | 1,32 | 6,83 | < 0,0001 | −10 % |
| Japón 1990–2026 | 430 | +2,1 % | 5,2 % | 0,39 | 2,35 | 0,0095 | −15 % |
| Asia-Pacífico sin Japón 1990–2026 | 430 | +6,9 % | 4,8 % | 1,38 | 7,01 | < 0,0001 | −19 % |

La idea que hay detrás de GABI **tiene respaldo estadístico sólido**: 52 años
en EE. UU. y tres regiones independientes que no se usaron para diseñarla.

## Lo más importante: en EE. UU. la prima casi desapareció desde 2010

| EE. UU. por década | Prima anual | t |
| --- | ---: | ---: |
| 1970s | +4,9 % | 2,90 |
| 1980s | +7,4 % | 5,66 |
| 1990s | +3,7 % | 1,84 |
| 2000s | +6,5 % | 1,54 |
| **2010s** | **+1,0 %** | **0,82** |
| **2020–2026** | **+1,1 %** | **0,28** |
| **2016–2025** (muestra de diseño de GABI) | **+0,6 %** | **0,23** |

Esto **explica los resultados del #40**. En los años de los que GABI tiene
datos (2011–2025), la prima de su mezcla en EE. UU. fue casi nula. No es que
GABI haga algo mal: en ese periodo, ordenar el mercado estadounidense por
valor, calidad, momentum y bajo riesgo apenas se pagó. Es un fenómeno
documentado: las primas publicadas se reducen tras publicarse (McLean y
Pontiff, 2016), y el valor tuvo una década muy mala en EE. UU. (2007–2020).

## Cada ingrediente por separado (EE. UU. 1963–2015)

| Factor | Prima anual | t | Peor racha |
| --- | ---: | ---: | ---: |
| Momentum | +8,8 % | 4,06 | −58 % |
| Valor (HML) | +4,3 % | 2,65 | −40 % |
| Rentabilidad (RMW) | +3,2 % | 2,59 | −42 % |
| Bajo riesgo (varianza) | +3,0 % | 0,92 | −75 % |

**Mezclarlos reduce mucho el riesgo.** La peor racha de la mezcla (−28 %) es
menor que la de cualquier factor por separado, porque valor y momentum se
compensan (correlación −0,19).

## Qué significa para GABI

1. **La idea es buena** a largo plazo y en varios mercados. No es una
   casualidad de 14 años.
2. **En EE. UU. no se ha pagado desde 2010.** Por eso el backtest de GABI no
   puede demostrar una ventaja estadística con los datos de 2011–2025, aunque
   su idea sea correcta.
3. **Esto no garantiza el futuro.** Una prima que se debilita en EE. UU. puede
   volver (el valor se recuperó en parte en 2021–2022) o no volver. Las
   pruebas ciegas (#42, #43) lo irán diciendo.
4. **La implementación importa.** Estas cifras son de carteras largo-corto
   académicas con miles de acciones. GABI es un Top-20 solo comprador del
   S&P 500 y capta solo una parte. El #44 medirá si su implementación ordena
   bien acciones que no se usaron para diseñarla.
5. **Mercados fuera de EE. UU.** La prima siguió funcionando en Europa y
   Asia-Pacífico. Una versión de GABI para esos mercados sería una hipótesis
   razonable, pero no hay fundamentales gratuitos por acción para ellos.

## Límites

- Las primas de estos factores son conocidas en la literatura: la prueba no
  es ciega respecto a su existencia. Lo nuevo es la mezcla con los pesos de
  GABI y la regla fijada de antemano.
- **Bajo riesgo**: se usa el diferencial de carteras por varianza, solo en
  EE. UU. En las regiones, los pesos se reescalan sin él.
- **Costes**: rentabilidades brutas de carteras académicas, sin costes de
  transacción ni restricciones de venta en corto.
