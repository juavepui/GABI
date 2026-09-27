# Ampliación A1 del preregistro #44: ¿la señal de GABI está solo en la parte alta del ranking? (#47)

Escrita el 2026-09-27, **antes de calcular ningún ranking del #44** (la función se niega si existe alguno).
La especificación exacta está en [`preregistro-a1.json`](preregistro-a1.json):

| Campo | Valor |
| --- | --- |
| SHA-256 de la ampliación | `2608251cefe5d82cd822c14c726a97a9af5cd8d84b2b50c4a12712de925f5e3e` |
| Preregistro que amplía | `99d36edf…` ([PREREGISTRO.md](PREREGISTRO.md)), sin cambios |
| Código del análisis congelado | `smallmid_test.py`, SHA-256 `3e7848f8…` |
| Experimento | id 47, familia `stat_4` |

## Por qué

En el S&P 500 (#40), la puntuación de GABI no ordena bien el universo: la empresa 100 no rinde mejor que
la 300. Pero las 20 primeras superaron a la media en +1,36 puntos por trimestre (t 3,93). Una explicación
posible es que la señal exista solo en la parte más alta. Ese resultado ya lo vimos, así que no sirve como
prueba. Esta ampliación contrasta la idea con las empresas de fuera del S&P 500, que no se usaron para
diseñar GABI y cuyos resultados aún no se han calculado.

## Pruebas

- **T1**: rentabilidad media de las 20 elegibles con mejor puntuación menos la media de todas las elegibles,
  trimestre a trimestre. Media con t Newey-West unilateral.
- **T2**: lo mismo con el 5 % superior. En el S&P 500, 20 empresas son el 4,4 % de las elegibles, así que T2 es
  la versión proporcional de T1.
- **Corrección**: Holm sobre T1 y T2 (alfa conjunto del 5 %). La prueba principal del #44 no cambia.
- **Datos que faltan**: las mismas tres cotas del #44 (adversa, favorable y casos completos).

## Decisión

| Resultado | Condición |
| --- | --- |
| Cola robusta | T1 o T2 positivos con p de Holm < 0,05, también con la cota adversa |
| Cola condicionada a los datos | p de Holm < 0,05 con casos completos, pero no con la cota adversa |
| Cola no concluyente | T1 y T2 positivos sin significación |
| Sin efecto de cola | T1 o T2 ≤ 0 sin ninguna significativa |

## Solo descriptivo

- Exceso medio de las bandas 0–1 %, 1–5 %, 5–10 %, 10–20 %, 20–40 %, 40–60 %, 60–80 % y 80–100 %.
- Convexidad: banda 0–5 % menos banda 5–20 %.
- IC por ventana (2011–15, 2016–20 y 2021–25).
- Rotación del Top-20.

Los retornos son **brutos**: aunque la parte alta resulte significativa, eso no demuestra que se pueda
invertir en ella con beneficio. No se cambiarán pesos ni modelo por este resultado.
