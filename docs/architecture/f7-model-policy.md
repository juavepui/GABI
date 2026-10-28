# F7.4: identidad y estado del modelo

`domain/market/model_policy.py` conserva pesos, tolerancia, identidad y etiqueta
de la hipótesis congelada, comparación de pesos, estado y mensaje experimental.
Las entradas son explícitas; el dominio no consulta configuración, archivos,
estudios ni SQLite. Los pesos de referencia del dominio son inmutables.

La composición de Mercado y la evidencia usan estas reglas directamente. La
fachada `app_mode.py` mantiene las firmas públicas y captura sus constantes
legacy al delegar, para conservar consumidores y personalizaciones existentes.
Su persistencia de modo y búsqueda de seguimiento permanecen pendientes de los
almacenes de compatibilidad; la API ya utiliza lectores y escritores propios.

Se conserva que coincidir en pesos da FROZEN, el seguimiento da LIVE_FORWARD
y desviarse da EXPERIMENTAL, incluso con seguimiento. VALIDATED permanece
reservado para acreditación independiente; ninguna refactorización la otorga.
La API mantiene bloqueo de pesos en Investor y validación en Research.

Diez casos de referencia capturados del original cubren pesos exactos, tolerancia,
ausentes y desviación, con/sin seguimiento y texto completo del mensaje. Otras
pruebas comprueban independencia de archivos/configuración y compatibilidad de
la fachada. Las rutas nuevas se registran solo para futuros metadatos del ledger.
No cambian acceso a datos, cachés, resultados ni motores congelados.

## Versiones del modelo operativo (ADR 0008, fase 2)

`domain/market/model_version.py` define `ModelVersion`: identidad, etiqueta, pesos,
parámetros técnicos, benchmark y tipo libre de riesgo, validados e inmutables.
`infrastructure/model_versions.py` declara GABI-MF-v1 con sus valores literales y
el modelo activo (`ACTIVE_MODEL_ID`); cambiarlo es un commit. El bootstrap de la
API y los jobs de decisiones y filings componen mercado, cálculos y política desde
esa versión y ya no leen `config.py`, que queda como snapshot sellado.

La hipótesis sellada conserva sus reglas FROZEN/LIVE_FORWARD/EXPERIMENTAL. Una
versión nueva tiene su propio id y se muestra EXPERIMENTAL aunque haya seguimiento:
no hereda evidencia. El id entra en la clave de caché del ranking. `ModelPolicy`
pasa a `weights`/`model_id`; el campo HTTP `basis: "frozen_weights"` de señales no
cambia. Los tests comparan v1 con `config.py`, `FROZEN_WEIGHTS` y los casos de
referencia de la política, y comprueban que este camino no importa `config`.
