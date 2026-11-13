# F7.4: reglas conservadoras de evidencia

`domain/market/evidence.py` concentra descomposición del score, frescura y
clasificación BAJA/MEDIA/ALTA. Recibe fechas, catálogo revisado, estabilidad,
traza y configuración inmutable (`EvidenceRules`): métricas, TTL y huella de
reglas. No lee reloj, SQLite, configuración global, estudios ni reservas.
Las contribuciones y condiciones de confirmación independiente se conservan.

`application/market/evidence_assessment.py` comparte la evaluación del ranking
completo. Recibe el catálogo cargado, concordancia del modelo, metadatos, reloj,
sesión y el puerto del análisis congelado de estabilidad. Conserva el fingerprint
de entradas, las fases, los mensajes y el manejo de estabilidad no estimable.

La API usa el caso de uso mediante `legacy/evidence.py`, que solo reúne fuentes
antiguas y admite reloj/configuración por instancia. El ledger sigue usando
`evidence_confidence.py`, fachada compatible que delega al mismo flujo; por eso
conserva su nombre. Sus lecturas de estudios/metadatos siguen pendientes de la
migración de `evidence_catalog` y `live_ledger`. Se eliminan las dependencias
NumPy/pandas de la fachada en el inventario: permanecen 79 módulos planos y las
excepciones no crecen.

El ledger incluye las rutas nuevas de dominio/aplicación en metadatos futuros.
No cambia el preregistro, la huella de reglas publicada ni registros anteriores.
La caché de API mantiene su clave de revisión y pesos y reemplazo por capacidad;
no se introduce una caché de estudios ni un camino adicional de datos.

## Evidencia

`fixtures/evidence_rules_migration.json` conserva seis clasificaciones, frescura
y un ranking completo sintético de 35 símbolos del original `486942a`, con SHA
normalizado a LF. Solo se tolera el redondeo numérico; estados, fechas, mensajes,
huellas y procedencia se comparan exactamente. Las pruebas cubren TTL explícito,
independencia de configuración legacy, conservación de entradas, ausencia de
SQLite/red y reloj/configuración del adaptador. API y ledger conservan sus
pruebas anteriores, incluida una evaluación por revisión de ranking.

Arquitectura, Ruff, tipos, contratos y motores congelados se comprueban por
separado. No se atribuye una mejora de rendimiento a esta extracción.
