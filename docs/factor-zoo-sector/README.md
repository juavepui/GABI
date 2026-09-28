# #48: estabilidad descriptiva por industria SIC fechada

Se completa el criterio pendiente del [Factor Zoo](../factor-zoo/README.md) usando únicamente archivos SEC locales. La [documentación SUB de la SEC](https://www.sec.gov/files/financial-statement-data-sets.pdf) indica que el código SIC corresponde a la asignación en la fecha de presentación. Se une el registrante principal con el CIK del ranking histórico congelado, sin usar el ticker actual ni los sectores GICS de 2026.

Las reglas [PREREGISTRO.md](PREREGISTRO.md) y [preregistro.json](preregistro.json), huella canónica `6a417e8f9f31b69a7a8c201a7afe7700227a0898d5df0d29abeab9dc8b9d8097`, se publicaron en `0b88752` antes de medir cobertura o IC. El motor se guardó en `16b9c23`; las [correcciones documentadas](CORRECCION.md) de fechas EDGAR y exhaustividad quedaron en `3387ae4` y `4f4fa53` antes del cálculo definitivo. Las dos ejecuciones anteriores se conservan íntegras para auditoría y no se usaron en decisiones.

Esta ampliación es **retrospectiva y descriptiva**: los resultados originales ya se conocían. No es una confirmación independiente ni añade contrastes de significación. Las industrias SIC son más amplias que GICS y no reconstruyen sus 11 sectores.

## Cobertura y disponibilidad

Se verificaron los 68 ZIP trimestrales registrados de 2009–2025, sus hashes completos y los bytes de SUB. Se extrajeron íntegramente los metadatos de **35.991 presentaciones** para los CIK congelados; la fuente no depende del índice SQLite parcial. Se preservan los 57 rankings y retornos originales. La cobertura es **18.289 de 18.289 observaciones elegibles empresa/fecha (100 %)**, también 100 % por trimestre. Todas tienen CIK histórico, último filing previo conocido, SIC válido y antigüedad dentro de los 400 días declarados.

| División SIC | Industria | Observaciones clasificadas |
|---|---|---:|
| A | Agricultura, silvicultura y pesca | 0 |
| B | Minería | 693 |
| C | Construcción | 103 |
| D | Manufactura | 7.710 |
| E | Transporte, comunicaciones y servicios públicos | 2.342 |
| F | Comercio mayorista | 417 |
| G | Comercio minorista | 1.389 |
| H | Finanzas, seguros e inmobiliario | 2.951 |
| I | Servicios | 2.684 |
| J | Administración pública | 0 |

Los intervalos de división siguen el [manual SIC de OSHA](https://www.osha.gov/data/sic-manual), con los rangos fijados en el preregistro; códigos fuera de ellos quedan sin clasificar.

La cobertura incluye las empresas sin retorno futuro: **18.287/18.287** entre las que sí tienen retorno y **2/2** entre las que no. Esas dos observaciones permanecen en el denominador de cobertura, pero no se usan como pares de IC. [factor_coverage.csv](factor_coverage.csv) separa señal finita, retorno finito, pares con industria y pares sin industria, sobre todos los elegibles.

## Resultado descriptivo

Cada IC utiliza ≥30 pares finitos y variación en señal/retorno. Se publican **7.410 filas** (13 señales × 10 divisiones × 57 fechas): 2.636 estimables y 4.774 con pares insuficientes. No se omiten ni agrupan las divisiones sin muestra. A/B/C/F/G/J carecen de trimestres estimables a ese umbral; la cobertura de una etiqueta no implica suficiente muestra para medir estabilidad.

La tabla muestra **IC medio / trimestres estimables** en las cuatro divisiones que tienen alguna señal estimable. Con menos de 30 trimestres el resumen se marca con soporte temporal insuficiente. Todos los grupos, ICIR, proporción positiva, pares y ventanas 2011–15/2016–20/2021–25 están en [resultado.json](resultado.json).

| Señal | D: manufactura | E: transporte/utilities | H: finanzas/inmobiliario | I: servicios |
|---|---:|---:|---:|---:|
| `pe` | +0,029 / 57 | +0,072 / 57 | +0,059 / 57 | −0,022 / 55 |
| `pb` | +0,017 / 57 | +0,033 / 57 | +0,038 / 57 | +0,003 / 56 |
| `ev_ebitda` | +0,045 / 57 | +0,102 / 46 | No estimable / 0 | −0,023 / 32 |
| `roic` | +0,006 / 57 | +0,023 / 25 | +0,008 / 55 | +0,046 / 28 |
| `operating_margin` | −0,015 / 57 | −0,013 / 57 | −0,052 / 24 | +0,053 / 55 |
| `revenue_cagr_3y` | −0,012 / 57 | +0,029 / 50 | −0,004 / 54 | +0,018 / 54 |
| `fcf_cagr_3y` | −0,008 / 57 | No estimable / 0 | +0,019 / 38 | +0,023 / 51 |
| `momentum_12m` | −0,010 / 57 | −0,026 / 57 | −0,020 / 57 | −0,022 / 56 |
| `rel_strength_6m` | −0,002 / 57 | ≈0 / 57 | +0,003 / 57 | −0,038 / 56 |
| `price_vs_sma200` | −0,008 / 57 | −0,019 / 57 | −0,008 / 57 | −0,036 / 56 |
| `debt_to_equity` | −0,030 / 57 | −0,018 / 51 | −0,020 / 55 | −0,024 / 31 |
| `volatility` | +0,018 / 57 | −0,042 / 57 | +0,010 / 57 | −0,014 / 56 |
| `max_drawdown` | +0,017 / 57 | −0,031 / 57 | +0,005 / 57 | −0,011 / 56 |

Las medias positivas dependen de la industria: por ejemplo, PER y EV/EBITDA presentan IC negativo en servicios, y el margen operativo cambia de signo. Estos datos no autorizan elegir una industria favorable ni factores para el ensemble #53. **Ninguna de las 13 señales supera el Holm original al 5 %.** Scores, pesos, rankings, quintiles, inferencia principal y clasificaciones originales permanecen congelados; la confianza de evidencia sigue BAJA.

La estabilidad SIC no corrige la falta de GICS histórico, el sesgo de universo superviviente ni el control sectorial ausente en las regresiones/placebos originales. Los IC por industria usan los percentiles orientados originales, sin recalcular scores sector-neutral. Los resúmenes de ventanas también conservan fechas no estimables; son descriptivos y su soporte temporal se muestra explícitamente.

## Artefactos y aplicación

- [resultado.json](resultado.json): resúmenes, cobertura por fechas/retornos, especificación/código, versiones y hashes de fuentes/inputs/artefactos. SHA-256 canónico `1f48950f7215a23e4d3fe3a05ed051c5d203b480adb6a2857da96c17de69da2d`.
- [filings.csv](filings.csv): snapshot reproducible de metadatos de los registrantes principales, contrastados con SUB.
- [assignments.csv](assignments.csv): cada empresa/fecha, CIK, accession, SIC, división, fechas, motivo y disponibilidad de retorno.
- [sector_ic.csv](sector_ic.csv): todos los grupos/fechas/señales, pares y estados estimable/insuficiente.
- [coverage.csv](coverage.csv) y [factor_coverage.csv](factor_coverage.csv): denominadores y exclusiones sin eliminar resultados ausentes.

Factor Lab muestra el contraste original y el suplemento, permite elegir señal y descargar IC/cobertura. Los componentes de evidencia de Screener/Mi cartera/Ficha incluyen la estabilidad SIC y su referencia; no cambian los filtros BAJA/MEDIA/ALTA. El catálogo comprueba los hashes del resultado, código, reglas y CSV antes de mostrarlos. La aplicación solo consulta artefactos: no abre la base para este estudio, descarga ni recalcula resultados.

## Verificación y reproducción

```powershell
.venv/Scripts/python.exe -m gabi.factor_sector_stability --verify
.venv/Scripts/python.exe -m gabi.factor_sector_stability --reproduce data/research_reproductions/issue48-sic-new
.venv/Scripts/python.exe -m pytest tests/test_factor_sector_stability.py tests/test_factor_sector_ui.py tests/test_evidence_confidence.py tests/test_evidence_ui.py -q
```

La reproducción extrae otra vez todos los SUB y exige igualdad con `filings.csv` publicado; también utiliza los ZIP archivados y los inputs históricos con sus hashes. Escribe en una carpeta nueva y exige igualdad de la huella canónica final. La primera ejecución consulta las huellas de archivos registrados en una transacción SQLite **solo lectura**, sin usar el índice parcial de presentaciones. `--analyze` rechaza sobrescribir el suplemento congelado. No se modifica la base operativa ni se lee #44 o la prueba ciega #43.

La reproducción ejecutada en `data/research_reproductions/issue48-sic-complete-sub` devuelve exactamente la huella canónica `1f48950f7215a23e4d3fe3a05ed051c5d203b480adb6a2857da96c17de69da2d`, con igualdad del snapshot completo y los cinco CSV. Las carpetas de reproducción son caché local ignorada por Git; el suplemento publicado está en `docs`.

Validación: **69 pruebas** del suplemento/UI/evidencia/ledger y **996 pruebas** de la suite completa pasan. Ruff y mypy de los cinco módulos nuevos/modificados pasan; la sintaxis de las páginas se verifica. Los checks globales conservan únicamente la deuda anterior (3 avisos de imports de Ruff y 25 errores de mypy en los tres motores de estudios congelados `factor_zoo`, `placebo_engine` y `tail_effect_test`); no se cambian esos motores para alterar sus hashes. Los seis resultados originales mantienen sus huellas.
