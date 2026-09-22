# Drag fiscal español (IRPF, base del ahorro)

Implementación del [issue #14](https://github.com/juavepui/GABI/issues/14).
`src/gabi/tax_drag.py` simula cuánto del retorno bruto de un backtest V1 se
pierde por pagar IRPF sobre plusvalías realizadas trimestre a trimestre, en
vez de diferirlas como haría un comprar-y-mantener.

## Por qué hace falta esto aparte del motor V1/V2

Ni `multifactor_backtest.py` ni `portfolio_backtest.py` rastrean coste de
adquisición por posición — no hay forma de calcular una plusvalía realizada
exacta desde dentro sin tocar el motor ya validado. `tax_drag.py` hace su
propia contabilidad, fuera de esos motores, aproximando el coste de
adquisición como repartido uniformemente sobre toda la cartera (coste
medio) — razonable para una cartera equiponderada y diversificada, pero
**no** una réplica FIFO lote a lote de cada posición individual.

## Cómo funciona

`simulate_tax_drag(periods, ...)` reutiliza `periods["retorno"]` y
`periods["turnover_pct"]`, ya calculados por `multifactor_backtest.run()`
— no reconstruye picks ni precios por símbolo. Cada periodo:

1. La cartera crece con `retorno` (ya neto de costes de fricción).
2. La fracción `turnover_pct` se vende y recompra de inmediato en las
   nuevas candidatas — realiza su parte proporcional de la plusvalía no
   realizada acumulada hasta ese momento. La fracción restante sigue
   diferida, con su coste de adquisición antiguo intacto.
3. Al cierre de cada año natural se liquida: se compensan ganancias y
   pérdidas realizadas ESE año más el arrastre de años anteriores, se
   aplican los tramos progresivos de la base del ahorro sobre el neto
   positivo, y el impuesto se resta del valor de la cartera — compone
   sobre menos capital a partir de ahí. Una pérdida neta anual se arrastra,
   sin tributar, al año siguiente.

`zero_turnover_periods(periods, "spy")` construye la misma estructura con
turnover 0 en todos los periodos, para comparar contra un comprar-y-mantener
puro del mismo benchmark durante el mismo tramo temporal — su drag fiscal
es prácticamente nulo por construcción (nada se vende, nada tributa).

## Tramos usados (`SPANISH_SAVINGS_BRACKETS_2024`)

Base imponible del ahorro, vigente desde el ejercicio 2023 (Ley 31/2022):

| Hasta | Tipo |
|---:|---:|
| 6.000 € | 19% |
| 50.000 € | 21% |
| 200.000 € | 23% |
| 300.000 € | 27% |
| Resto | 28% |

**Revisar cada año** — cambian con la ley de presupuestos, no hay garantía
de que sigan siendo estos cuando se lea este código.

## Verificado con datos reales

Backtest V1 real (Top-10, muestra de 30, 2019-01-02 a 2021-01-02, incluye
el crash de COVID): retorno bruto +32,44% → neto +27,37% tras IRPF
(impuesto total 4.757 € sobre 100.000 € iniciales). El mismo periodo en SPY
comprado y mantenido: +52,35% bruto = +52,35% neto, impuesto 0 € — toda la
plusvalía queda diferida porque nunca se vende. La comparación no pretende
decir "SPY gana siempre" (aquí gana porque tuvo mejor retorno bruto en esta
ventana concreta) — aísla específicamente el coste fiscal de rotar la
cartera, no el resultado de la estrategia.

22 tests: tramos exactos verificados a mano, diferimiento total con
turnover cero, realización completa con turnover 100%, compensación de
pérdidas dentro del mismo año, arrastre de pérdidas entre años, y
validaciones (columnas requeridas, capital positivo, turnover en rango).

## Limitaciones (no ocultas, expuestas también en el resultado y en la UI)

- Coste de adquisición medio repartido uniformemente, no FIFO lote a lote
  por posición (la ley exige FIFO en ventas parciales del mismo valor).
- No modela la regla de los 2 meses (pérdida no deducible si se recompra el
  mismo valor, u otro sustancialmente idéntico, dentro de los 2 meses
  siguientes a la venta).
- El arrastre de pérdidas no aplica el límite legal de 4 años — se arrastra
  sin límite.
- Un solo tramo estatal — no distingue tramo autonómico ni deducciones
  personales.
- Liquida el impuesto de todo el año de golpe al cierre de ese año — en la
  práctica se paga en la declaración del año siguiente (aprox. junio).
- No incluye dividendos ni su retención, solo plusvalías por compraventa.

No sustituye asesoramiento fiscal real — es una aproximación para entender
el ORDEN DE MAGNITUD del drag, no una liquidación de IRPF.
