# Reglas de evidencia/confianza (#52)

Se fijan antes de implementar o asignar niveles. `Score` describe atractivo; la antigua columna numérica `confidence` mide cobertura ponderada de datos y se rotula como tal. La confianza de evidencia es una categoría separada, con componentes, razones y procedencia visibles.

BAJA es el estado por defecto ante resultados ausentes, modelo no coincidente, fragilidad, datos caducados, factores sin apoyo tras Holm o contraste de modelo/placebos/bootstrap inconcluyente. MEDIA requiere superar todos los filtros explícitos del JSON con evidencia retrospectiva trazable. ALTA requiere además dos confirmaciones independientes preregistradas del mismo modelo. Esta versión no acredita confirmaciones automáticamente: disponer de un ledger LIVE_FORWARD no convierte un seguimiento en una prueba positiva.

No se recalibran umbrales con rentabilidades, no se optimiza ningún peso y no se modifica el Composite ni la prueba ciega. Los resultados pendientes de #44 y los sectores históricos ausentes de #48 se muestran como límites. La aplicación puede completar esta funcionalidad aunque la evidencia actual siga siendo BAJA.
