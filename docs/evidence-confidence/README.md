# Evidencia por candidata (#52)

Screener, Mi cartera y Ficha de Empresa separan tres dimensiones: Composite Score, disponibilidad ponderada de datos y confianza de evidencia. La API numérica `confidence` se conserva por compatibilidad; en pantalla se llama **Cobertura ponderada**. La nueva categoría BAJA/MEDIA/ALTA procede de `evidence_confidence`, no cambia scores, pesos, elegibilidad ni asignación de capital.

Las [reglas](preregistro.json) y su [explicación](PREREGISTRO.md) se fijaron en `ecf5085`, antes de implementar niveles. Su SHA-256 canónico es `2a0776de996c8044e4997da925e0b603da03c0721a883810bfd9cdfe541064ab`. Los umbrales de 80 % de cobertura, 90 % de persistencia y 50 % de peso con apoyo estadístico son reglas conservadoras de comunicación; no están calibrados como probabilidades ni elegidos para maximizar CAGR.

| Nivel | Regla |
|---|---|
| BAJA | Falla cualquier componente: catálogo íntegro/completo, modelo coincidente, datos actuales, cobertura, estabilidad, atribución del score, factores tras Holm, contraste predictivo, placebos o incertidumbre emparejada. |
| MEDIA | Todos esos filtros pasan con evidencia retrospectiva trazable. Sigue sin acreditar independencia. |
| ALTA | Además, dos confirmaciones preregistradas independientes del modelo exacto, datasets distintos, efecto positivo, p corregida < 0,05, integridad comprobada y sin revelación anticipada. |

La implementación de producción **no carga confirmaciones independientes automáticamente**. Los ejemplos MEDIA/ALTA de las pruebas usan datos sintéticos declarados. Ni la etiqueta LIVE_FORWARD ni una rentabilidad acumulada favorable elevan la confianza.

El [catálogo](sources.json) fija los seis resultados originales (#40, #47, #48, #49, #50, #51) y el [suplemento SIC fechado de #48](../factor-zoo-sector/README.md), sus huellas y el alcance del modelo congelado. Se verifica JSON canónico, independiente de CRLF/LF; para el suplemento también se comprueban código/reglas/CSV. El catálogo tiene SHA-256 `2d1f928a2bc87f5ce77c051fbc1885f57507f028d8b313d903c3354e3c55e684`. El catálogo inicial de seis resultados permanece en el historial Git (`d41779b`, SHA `312e51e6d6cb90291b90c28ab4ff48f775c6b4d78e35055fde607651529db1a2`). Si falta o cambia un archivo, su componente no se interpreta como evidencia positiva y el nivel baja. Actualizar resultados/reglas exige revisar y publicar sus huellas; no hay recálculo automático ni lectura de la prueba ciega o de #44 sin finalizar.

La evidencia actual da **BAJA**, incluso con score alto y datos completos: ninguno de los 13 factores supera Holm al 5 %, el contraste principal del Composite es inconcluyente y los placebos favorables son condicionales. SIC fechado aporta un diagnóstico retrospectivo por industrias amplias, sin sustituir GICS ni reestimar scores, regresiones o placebos. El bootstrap neto V1 no es estimable con sus huecos; el intervalo principal de diferencia de CAGR de V2 incluye cero. Se muestran esas diferencias de alcance, la sensibilidad temporal y #44 pendiente, sin reunir p-valores de estudios distintos.

Cada objeto conserva las señales descriptivas (percentil ≥ 50), familia, IC/p Holm, ventanas, sectores/tamaños disponibles, contribuciones de score, estabilidad local de #51, calidad/frescura, placebos/bootstrap y razones a favor/en contra. Los pesos efectivos reproducen la media del score: se renormalizan solo los bloques disponibles y cada bloque reparte su peso entre sus métricas disponibles. Los puntos procedentes de factores con apoyo tras Holm permiten calcular qué fracción del score tiene ese respaldo retrospectivo. Si la atribución no reproduce el score, se declara no atribuible y se degrada.

El análisis se hace sobre el universo completo antes de filtros de pantalla. Investor muestra el Top-20 y el detalle de una candidata; Research añade componentes y procedencia completos. La descarga JSON incluye modelo, versión/config, commit, fingerprint de entradas y referencias/huellas de experimentos. Los pesos distintos o universos distintos del alcance declarado se identifican como experimentales. El histórico del S&P 500 superviviente no acredita el universo actual point-in-time; el nuevo SIC tampoco elimina ese sesgo.

El ledger #57 congela los objetos de las candidatas propuestas junto a la decisión. Consultarlos después no recalcula ni reemplaza su confianza original. El informe prospectivo permanece separado de la evidencia estadística del modelo.
