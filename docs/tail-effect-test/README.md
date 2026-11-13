# STAT-4 (#47): señal en la cola superior

Preregistro: [PREREGISTRO.md](PREREGISTRO.md) y
[preregistro.json](preregistro.json), SHA-256
`423016a5919ba9bd2e0065f1687fb8ce0cb3167658d9274af116ab10eb9c234b`,
sellado en el commit `9b7acfb` **antes de calcular estos resultados**.
Resultados completos: [resultado.json](resultado.json) y
[por-trimestre.csv](por-trimestre.csv).

## Resultado

**Los dos contrastes fijados detectan un patrón histórico compatible con una
señal de cola, sin confirmación independiente.** Se usaron los 57 trimestres
de #40 (2011-07 a 2025-07), con 321 elegibles medios. Hay 18.287 retornos
observados de 18.289 elegibles; todas las bandas tienen retorno en todos los
trimestres. Los retornos son brutos, sin costes.

| Contraste trimestral | Media | IC 95 % HAC | t HAC(3) | p unilateral Holm |
| --- | ---: | ---: | ---: | ---: |
| Top 5 % − 5–20 % | +1,73 pp | [+0,71, +2,75] pp | 3,39 | 0,0013 |
| (Top 5 % − 5–20 %) − (5–20 % − 20–100 %) | +1,84 pp | [+0,18, +3,51] pp | 2,22 | 0,0153 |

Medias trimestrales de los grupos agregados: Top 5 % **5,02 %**,
5–20 % **3,29 %**, 20–100 % **3,41 %**. El universo elegible obtuvo
**3,47 %** y SPY **3,71 %**. La primera banda (0–1 %) no tiene por sí sola
un exceso significativo; la banda 1–5 % sí, con **+1,68 pp** frente al
universo y `p Holm < 0,001` entre las ocho bandas. Es una descomposición
secundaria: no se eligió después como nuevo corte decisorio.

| Banda | Retorno trimestral | Exceso vs universo | Exceso vs SPY |
| --- | ---: | ---: | ---: |
| 0–1 % | 4,48 % | +1,01 pp | +0,77 pp |
| 1–5 % | 5,15 % | +1,68 pp | +1,44 pp |
| 5–10 % | 3,46 % | −0,02 pp | −0,26 pp |
| 10–20 % | 3,21 % | −0,26 pp | −0,50 pp |
| 20–40 % | 3,38 % | −0,09 pp | −0,34 pp |
| 40–60 % | 3,16 % | −0,31 pp | −0,55 pp |
| 60–80 % | 3,51 % | +0,04 pp | −0,20 pp |
| 80–100 % | 3,58 % | +0,11 pp | −0,14 pp |

Las tres ventanas **descriptivas** muestran que el salto Top 5 % frente a
5–20 % se reduce: +2,01 pp (2011–15), +2,55 pp (2016–20) y +0,60 pp
(2021–25). La convexidad correspondiente es +2,35, +3,51 y −0,40 pp.
No se realizaron pruebas por ventana ni se eligió el periodo ganador.

## Interpretación y límites

El Top-20 ya se había observado como ventaja en #40 y se había elegido durante
el diseño de GABI. El nuevo patrón es compatible con una relación no lineal,
pero **también con selección previa, ruido o un efecto que se haya debilitado**.
Esta muestra no permite distinguir esas explicaciones con evidencia
independiente. Los quintiles planos y el IC global casi nulo de #40 siguen
siendo compatibles con una ventaja concentrada en pocas posiciones.

Los retornos observados no descuentan rotación ni otros costes de cartera;
comparar una banda de acciones con SPY tampoco controla riesgo o exposiciones.
RSP no está en los datos congelados de esta serie. No se cambian pesos ni el
modelo Investor: se necesitaría una muestra futura o independiente.

## Reproducción

Con el caché histórico y los `forward-*.csv` de #40 presentes:

```powershell
.venv/Scripts/python.exe -m gabi.tail_effect_test --analyze
.venv/Scripts/python.exe -m pytest tests/test_tail_effect_test.py tests/test_cross_section_test.py -q
```

El analizador exige el preregistro intacto, comprueba el calendario y el
universo del #40, y deja en `resultado.json` SHA-256 del código, del manifiesto,
de los 57 rankings, de los 57 ficheros de retornos y del benchmark. La salida trimestral
incluye tamaños y cobertura por banda para auditar cada media.
