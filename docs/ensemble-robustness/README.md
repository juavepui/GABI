# #53: robustez del ensemble Valor + Calidad + Expectativas, sin retornos

## Trazabilidad

| Paso | Commit | Huella |
| --- | --- | --- |
| [Preregistro](PREREGISTRO.md) | `9f6d5e8` | especificación `8609a0770a49d00c72bf5bb507d55551eba88b895543b305ca66715292555bca`; texto `75fa9e40f319c405780a800a4d3c9871793d1c43b729e24a7c99d8d66b9565c8` |
| Motor | `4813b4e` | — |
| [Corrección](CORRECCION.md): emisores con dos símbolos | `26dad7d` | — |
| [Resultado](resultado.json) | — | canónica `f595c1bfa251a69caba403fcc2153250e499985d67e10ff42577b75cb988ca05` |

Los tres primeros pasos se guardaron antes de ejecutar el análisis. La primera
ejecución se detuvo en la validación de entrada sin calcular nada.

**No se ha leído ningún retorno.** El resultado lista los 61 ficheros
abiertos: el preregistro, `scores.csv` de #60, los dos resultados que acreditan
sus huellas y los 57 rankings congelados, de los que solo se leen volatilidad,
drawdown, beta y capitalización pasados. No se abrió `gabi.db`, ningún
`forward-*` ni nada de #43 o #44.

## Decisión preregistrada: **parcial**

| Criterio | Resultado |
| --- | --- |
| Redundancia: Spearman medio entre componentes < 0,80 | Sí: V–Q −0,13; V–E +0,33; Q–E −0,03 |
| Dominancia por un componente < 0,75 | Sí: 0,59 |
| P1, rotación menor que la de cada componente | Solo frente a Expectativas |
| P2, persistencia ante ruido mayor que la de cada componente | Frente a Calidad y Expectativas, no frente a Valor |

El ensemble queda **entre sus componentes**, no por encima de todos:

- **Frente a Valor** no se distingue en ninguno de los dos endpoints.
- **Frente a Calidad** rota bastante más, aunque resiste mejor el ruido.
- **Frente a Expectativas** es mejor en ambos.

Promediar no compra más estabilidad que la del componente más estable. El
preregistro anticipaba que superar P2 era esperable; no superarlo frente a
Valor es la parte informativa.

## Endpoints

Diferencias ENS − componente con bootstrap circular de 4 trimestres e
intervalos al nivel 1 − 0,05/6. Las 57 fechas son evaluables; U_t tiene entre
117 y 198 empresas (mediana 167).

| Señal | P1: rotación trimestral del Top-20 | P2: persistencia con ruido ±5 pp |
| --- | ---: | ---: |
| **ENS** | **22,1 %** | **94,2 %** |
| Valor | 22,0 % | 94,3 % |
| Calidad | 11,5 % | 87,8 % |
| Expectativas | 26,0 % | 90,6 % |

| ENS − componente | P1 (puntos) | Intervalo | P2 (puntos) | Intervalo |
| --- | ---: | ---: | ---: | ---: |
| Valor | +0,2 | −3,6 a +3,9 | −0,1 | −1,4 a +1,0 |
| Calidad | +10,6 | +8,0 a +13,0 | +6,3 | +5,2 a +7,6 |
| Expectativas | −3,8 | −7,4 a −0,5 | +3,6 | +2,1 a +5,1 |

En P1 menos es mejor; en P2, más. La sensibilidad con ruido ±2 y ±10 pp
mantiene el orden: Valor ≈ ENS > Expectativas > Calidad. La rotación por
ventanas (2011–15 / 2016–20 / 2021–25) es, para ENS, 25,6 / 21,5 / 19,7 %; los
demás valores están en `resultado.json`.

## Descriptivos

- **Diversificación real.** Los Top-20 de los componentes apenas coinciden
  (Jaccard 0,07–0,19). El de ENS se parece más al de Valor (0,40) y al de
  Expectativas (0,34) que al de Calidad (0,15).
- **Autocorrelación del score** entre trimestres: ENS 0,90; Valor 0,94;
  Calidad 0,99; Expectativas 0,86.
- **Coste de cobertura.** Exigir los tres bloques deja U_t en el 52 % de las
  empresas elegibles de #60, sobre todo por la cobertura de Expectativas.
- **Concentración.** Ninguna señal deja plazas en efectivo, y todas ocupan unas
  5,6–5,9 divisiones SIC (HHI ≈ 0,21–0,22).
- **Riesgo ex ante del Top-20, medias.** Volatilidad, drawdown y beta son
  métricas pasadas y no predicen nada.

| Señal | Volatilidad | Drawdown | Beta | Capitalización mediana |
| --- | ---: | ---: | ---: | ---: |
| ENS | 0,302 | −0,393 | 1,06 | 13,9 mm USD |
| Valor | 0,307 | −0,416 | 1,07 | 11,0 mm USD |
| Calidad | 0,269 | −0,331 | 0,96 | 37,8 mm USD |
| Expectativas | 0,328 | −0,398 | 1,11 | 16,9 mm USD |
| Universo U_t | 0,286 | −0,363 | 1,02 | 21,9 mm USD |

- **Emisores con dos símbolos.** Aparecen en 42 fechas y se tratan como indica
  la corrección. La autocorrelación excluye 16 casos emisor-transición.

## Qué permite y qué no

- No es evidencia de rentabilidad ni de capacidad predictiva, y no sustituye
  al modelo de Investor. No se cambian componentes, pesos, ruido ni umbrales.
- Como no hay redundancia, la regla permite activar el **plan prospectivo v1**.
  Activarlo es una acción explícita aparte: requiere implementar la puntuación
  en vivo con SIC fechado antes del primer rebalanceo elegible (2026-12-21 o el
  siguiente). Sus revisiones nunca se adelantan a las de #43.
- Queda **pendiente** añadir ENS-VQE-v1 al registro de búsquedas: una
  configuración candidata nueva y tres comparadores de diagnóstico.
  `ledger.json` es un artefacto publicado y verificado por la CI, así que se
  regenera en un cambio propio.

## Reproducción

```powershell
uv run --project backend python -m gabi_cli research ensemble-robustness --verify
uv run --project backend python -m pytest backend/tests/test_ensemble_robustness.py -q
```

`--verify` comprueba las huellas de los artefactos publicados, recalcula en una
carpeta temporal y exige la misma huella canónica. `--analyze` nunca
sobrescribe un resultado existente.

Validación: 14 pruebas con datos sintéticos temporales. Cubren:

- la especificación sellada;
- desempates y tope por división;
- multiconjuntos de emisor;
- la equivalencia exacta entre las rutas numpy y pandas del ruido;
- el bootstrap con huecos;
- la regla de decisión;
- el rechazo de `forward-*`, fechas no acreditadas y fuentes alteradas;
- la reproducción completa.

Ruff, el control de tipos del proyecto, la guarda de arquitectura y las
verificaciones del registro y de los motores congelados pasan.
