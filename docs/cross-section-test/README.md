# Capacidad predictiva en sección cruzada: resultado (#40)

**Seguimiento (#47):** la [prueba de cola preregistrada](../tail-effect-test/README.md)
encuentra un patrón retrospectivo concentrado en el Top 5 %, aunque la
ventaja previa del Top-20 impide tratarlo como confirmación independiente.
Las conclusiones de abajo corresponden a la prueba global de #40.

Preregistro: [PREREGISTRO.md](PREREGISTRO.md) (sha256
`07df8d57fcd1c30f651331a70514e9567184a3641d3a602fba14ab9ff78aee1f`, commit
`44c0e2e`), escrito antes de calcular ningún retorno. Resultados en
[resultado.json](resultado.json) y [por-trimestre.csv](por-trimestre.csv), y
en la tabla `experiments`.

## Decisión preregistrada: **indicio no concluyente**

Se usan 57 trimestres (2011-07 → 2025-07), con una media de 321 empresas
elegibles por trimestre.

| Prueba | Media | t Newey-West | p unilateral | p Holm |
| --- | ---: | ---: | ---: | ---: |
| **Principal**: IC de Spearman trimestral | **0,009** | **0,66** | 0,26 | — |
| Fama-MacBeth (pendiente del percentil, con sector y tamaño) | 0,0018 | 0,29 | 0,39 | 0,78 |
| Quintil superior − quintil inferior | +0,15 pp | 0,28 | 0,39 | 0,78 |

**El Composite no ordena de forma distinguible del azar a las empresas del
S&P 500** según su rentabilidad del trimestre siguiente. El IC es positivo en
34 de los 57 trimestres, pero muy pequeño.

## Descriptivas (no deciden nada)

- **Quintiles planos.** Media trimestral del quintil peor al mejor: 3,59 %,
  3,49 %, 3,17 %, 3,37 % y 3,73 %. No hay gradiente.
- **Top-20 frente al universo: +1,36 pp por trimestre (t NW 3,93).** Ya se
  había visto en el #39, así que no es confirmatorio. La ventaja aparece solo
  en el extremo superior (las 20 primeras) y no en el resto de la
  clasificación. Y el Top-20 fue la configuración elegida al diseñar GABI
  (#12), lo que añade sesgo de selección.
- **Inestable en el tiempo.** IC por ventana:
  - 2011–2015: −0,002 (t −0,08);
  - 2016–2020: −0,014 (t −0,64);
  - 2021–2025: +0,045 (t 2,16).
- **Por bloques**, solo valor apunta algo: IC 0,026 (t 1,32). Calidad (−0,001),
  momentum (−0,011) y riesgo (0,000) dan prácticamente cero.

## Qué significa para GABI

- Con toda la potencia disponible (57 trimestres × ~320 empresas), **no hay
  evidencia de que la puntuación de GABI contenga información sobre la
  rentabilidad futura**.
- La ventaja del Top-20 frente al SPY y frente al universo (#35, #39) se
  concentra en unas pocas empresas y no se refleja en la ordenación general.
  Eso es compatible con la suerte y con la selección de la configuración
  durante el diseño, y no con un factor que funcione de forma sistemática.
- Por tanto, **no se puede afirmar que GABI supere al S&P 500 por algo más que
  la suerte**, ni con cartera (#35) ni con sección cruzada (#40).
- Lo que no cabe hacer es probar variantes hasta que una salga significativa.
  Cada prueba sube el listón (29 configuraciones documentadas hasta ahora), y
  el resultado sería de nuevo suerte.
- Si se quiere un modelo con evidencia, el camino es formular una hipótesis
  nueva y concreta (por ejemplo, centrada en valor, el único bloque con
  señal), preregistrarla y validarla **fuera de muestra**: prospectivamente
  (#42) o con datos anteriores a 2010, si llegan a existir (#41).

## Límites

- **Retrospectivo**: incluye la muestra de diseño.
- **IC ≠ rentabilidad de cartera**: un Top-20 puede batir al universo aunque el
  IC global sea bajo. Pero sin gradiente, esa ventaja no tiene explicación
  sistemática.
- **Sectores aproximados**: los de las empresas que ya no existen.
