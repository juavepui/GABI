# Corrección de implementación de fechas EDGAR

El motor inicial, commit `16b9c23`, añadió una exclusión `accepted < filed_date` que **no estaba en el preregistro**. La primera ejecución dio 16.638/18.289 clasificaciones y excluyó por ese motivo 1.615 observaciones. Su huella JSON canónica fue `8c8d26b0dbc018d190afae6c32fcd43811528728ea87c90365bbb00ce2eb951f`.

La [SEC explica](https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/determine-status-my-filing) que las presentaciones fuera de horario pueden recibir fecha oficial del siguiente día hábil. Los ejemplos excluidos en SUB cumplen esa situación: aceptación 2011-04-26 21:40 y presentación 2011-04-27, o aceptación viernes 2011-04-29 21:14 y presentación lunes 2011-05-02. Ambas fechas siguen siendo anteriores a la señal de 2011-07-02.

Se elimina exclusivamente esa condición adicional. Permanecen el preregistro original, los archivos, el CIK histórico, el último filing, el límite de 400 días, ambas fechas estrictamente anteriores a la señal, los umbrales 30/30, las 13 señales, los 57 trimestres y las ventanas. No se seleccionan grupos ni reglas por los IC obtenidos.

La ejecución inicial y todos sus artefactos se conservan en [audit/initial-date-order-check](audit/initial-date-order-check/resultado.json). No fue publicada en el catálogo de evidencia ni usada en decisiones. El resultado corregido se calcula después de guardar la corrección en Git; no se altera ningún estudio anterior, ranking, retorno, score, Holm o prueba ciega.

## Exhaustividad del índice local

La comprobación independiente del SUB completo encontró **2.863 presentaciones adicionales en 66 archivos** para los mismos CIK. El índice SQLite era parcial. Verificar que sus filas coinciden con SUB no basta para asegurar que el último filing seleccionado sea el último realmente disponible.

La segunda ejecución (`32d0ed9dae3321d91f1c22407de73266a5b2fd573dd06cd47b11f5076478e35f`) se conserva en [audit/partial-index-check](audit/partial-index-check/resultado.json). Se reemplaza exclusivamente la lectura del índice por la extracción de **todos los SUB de los 68 trimestres de 2009–2025** para los CIK congelados y formularios declarados. La base se consulta solo para las huellas registradas de los ZIP, en modo lectura; no se reimporta ni modifica su índice.

Una prueba incluye un filing posterior ausente del índice y verifica que se recupera del SUB principal; también rechaza un trimestre ausente y la herencia a co-registrantes. La reproducción reconstruye el snapshot completo desde los ZIP y exige igualdad con `filings.csv`. Se conservan las reglas y umbrales originales; ambas ejecuciones previas son borradores de auditoría y no se usaron en decisiones.
