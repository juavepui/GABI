# Puerta de datos de TACT-v1: consenso de modelos de asignación táctica (#312)

**Estado:** puerta **no pasada**. Faltan casi todos los datos que necesitan los
modelos. No se ha calculado ningún rendimiento ni se ha mirado ningún precio: solo
se han contado filas y fechas en `data/gabi.db` (2026-11-05, solo lectura).

## Qué se quiere probar

Si un **consenso de modelos tácticos publicados** («cuánto poner en bolsa y cuánto
en refugio») ayuda a un inversor a largo plazo de GABI frente a mantener la
inversión siempre. Idea sacada de QuantForge (#313), que publica un «pulso» de 10
modelos sin decir cuáles ni sus reglas.

## Qué datos hay hoy

| Dato | Para qué | En `data/gabi.db` |
|---|---|---|
| SPY (S&P 500) | bolsa de EE. UU. | **Sí**, 8.500 sesiones desde 1993-01-29 |
| EFA / VEA (bolsa desarrollada fuera de EE. UU.) | bolsa internacional | No |
| EEM / VWO (emergentes) | bolsa emergente y «canario» de Keller | No |
| AGG / BND (bonos agregados) | refugio y «canario» | No |
| IEF, SHY, LQD, TLT, TIP (bonos por plazo y tipo) | refugios | No |
| VNQ (inmobiliario), GLD (oro) | activos de los modelos de Faber | No |
| DBC (materias primas) | activo de Faber | Solo en el archivo histórico (4.399 filas) |
| Letra del Tesoro (FRED `DTB3`) o BIL | rentabilidad del efectivo | No |
| EUR/USD (FRED `DEXUSEU`) | resultado en euros | No |

Las series de FRED guardadas son las del panel macro (#309); ninguna da la
rentabilidad del efectivo ni el tipo de cambio.

## Qué haría falta para pasar la puerta

1. **Descargar** (acción explícita, nunca en una consulta) los precios ajustados de
   unos 12 fondos de Yahoo y 2 series de FRED. Todo es gratis. Todos los fondos
   existen antes de 2009, así que hay los 12 meses previos que necesitan las
   señales desde 2010.
2. **Auditar** cada serie como en #295: huecos, saltos imposibles, ajuste por
   dividendos coherente entre `close` y `adj_close`, y una muestra contrastada con
   otra fuente.
3. **Comprobar el periodo**: toda la evaluación entre 2010-01-01 y 2025-07-02
   (`require_observed_period`). Lo descargado posterior a esa fecha no se usa en
   ningún análisis.

## Cautelas que la puerta ya deja claras

- **Muestra corta y con pocas caídas.** En 2010–2025 la bolsa de EE. UU. tuvo un
  mercado alcista largo y pocas caídas fuertes: 2011, finales de 2018, la caída
  rápida de 2020 y 2022. Estos modelos ganan sobre todo en caídas lentas y largas
  (2000–2002, 2008), que quedan fuera del periodo permitido.
- **Contaminación.** Ya sabemos a grandes rasgos cómo fueron esos años, y varios de
  estos modelos se publicaron con datos que incluyen parte del periodo.
- **Impuestos.** En España, vender un fondo cotizado para pasar a bonos tributa por
  la ganancia (no es un traspaso entre fondos). Un modelo que cambia varias veces
  al año genera impuestos que mantener la inversión aplaza. GABI ya tiene el cálculo
  (`domain/portfolio/tax_drag.py`).

Decisión sobre si seguir: en [tact-v1-preregistro-propuesta.md](tact-v1-preregistro-propuesta.md).
