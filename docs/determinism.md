# Determinismo de los números (#296)

Regla del proyecto: todo número que ve el usuario sale del código y se puede volver a
obtener exactamente igual.

- **Texto para la IA** (`application/market/prompt_text.py`).
  - Solo lleva números calculados por GABI, formateados por el código.
  - `tests/test_prompt_numbers.py` extrae cada número del texto y exige que sea un valor de entrada formateado o un número fijo de la plantilla.
  - El texto ya no pide a la IA que fije umbrales («X» e «Y»). Puede proponer condiciones (qué métrica y en qué dirección), pero los umbrales los calcula GABI o los fija el usuario.
- **Semillas.**
  - `bootstrap_sharpe_ci` exige una semilla entera explícita.
  - `ScipyNormalCDF` usa por defecto un generador fijo (`SEED = 20261104`).
  - Los dos comandos que regeneran planes ya publicados (`legacy/value_hypothesis.py` y `gabi_cli research … plan`) pasan `rng=None`. Así conservan la integración de SciPy con la que se publicaron, y el plan publicado no cambia.
- **Huella del ranking.**
  - `tests/test_determinism.py` calcula, sobre los datos de prueba fijos (`market_fixture`), la huella SHA-256 del ranking de cada versión del modelo: símbolos en orden y puntuación con 9 decimales.
  - Si un cambio altera el resultado, el test falla. Para aceptarlo hay que actualizar `RANKING_FINGERPRINTS` a propósito y explicar el motivo en el commit.
  - Una versión nueva del modelo necesita su propia huella.
