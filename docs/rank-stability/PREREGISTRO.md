# Estabilidad del ranking (#51)

Esta especificación se publica antes de calcular el diagnóstico. Se usan las 24 transferencias dirigidas de 1 y 2 puntos porcentuales entre pares de los cuatro bloques. Se conservan el universo elegible y los percentiles de cada fecha. No se leen retornos ni se buscan los pesos de mayor rentabilidad.

El score de estabilidad es el porcentaje medio de integrantes del Top-20 original que permanece en él. Por empresa se muestra la fracción de perturbaciones en que pertenece al Top-20 y el rango de posiciones. Una candidata es persistente si aparece en todas y frágil si alguna la excluye. Las fracciones son descriptivas de esta vecindad finita, no probabilidades de éxito futuro.

Se informan también Spearman/Kendall, Top-10/20/30, entradas/salidas, dispersión individual y, cuando existe cobertura sectorial completa, concentración y cambios sectoriales. Las medias agregadas ponderan las fechas por igual. Un Top-N que contiene todo el universo no recibe un diagnóstico artificialmente perfecto. No se rellenan sectores históricos con sectores actuales.

La definición completa está en `preregistro.json`. La ejecución verifica su huella y registra las huellas de todos los rankings y artefactos generados. No altera el modelo congelado ni las pruebas prospectivas.
