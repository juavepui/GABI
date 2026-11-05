**GABI sí aplica un enfoque cuantitativo**, con reglas, pruebas históricas, riesgo y seguimiento programado.
Eso todavía no demuestra que el modelo activo obtenga una ventaja al invertir: **GABI-MF-v3 necesita evidencia propia**.
Las mejoras de cartera, análisis contable y determinismo ya están implementadas; sus issues #290–#296 están cerradas.
La auditoría paraguas #297 sigue abierta y su diagnóstico inicial necesita actualizarse.
He reproducido un defecto importante: un desdoblamiento de acciones puede producir una pérdida ficticia en cartera.
Hay controles de datos y rigor estadístico, pero persisten límites históricos de cobertura y del registro de pruebas.
Las comprobaciones ejecutadas pasan; no certifican los datos reales actuales ni la continuidad del equipo del propietario.
Propongo **una sola issue nueva**, más un comentario de actualización en #297. No he creado ni comentado ninguna.

Auditoría del código local `6433486d9bf061f0a97107d4a13e00c75bbdc11a`, rama `feat/296-determinismo`. Consulté código, documentación, ledger y todas las issues abiertas y cerradas. `gh issue list --state all` falló con HTTP 401; el conector GitHub permitió recuperar 161 issues, excluyendo PR, y los comentarios relacionados. Algunas frases del encargo están cortadas: el alcance verificable de capacidades es cartera y 10-K.

**1. Gestión cuantitativa: existe el proceso, falta acreditar su resultado**

✅ implementado y comprobado; ⚠️ parcial o sin verificar operativamente; ❌ defecto reproducido.

| Pieza | Estado y significado | Evidencia | Issue relacionada |
|---|---|---|---|
| Universo y datos conocidos en cada fecha | ⚠️ Membresía e identidad históricas explícitas; cobertura incompleta | `backend/src/gabi/application/research/backtest_v2.py:150`, `:154`, `:169` | [#44](https://github.com/juavepui/GABI/issues/44), [#251](https://github.com/juavepui/GABI/issues/251) |
| Criterios medibles | ✅ Percentiles, pesos y requisitos de cobertura explícitos | `backend/src/gabi/domain/market/scoring.py:123`, `:136`, `:172` | [#291](https://github.com/juavepui/GABI/issues/291), cerrada |
| Construcción y riesgo | ✅ Límites por emisor/sector, caja, liquidez y escenarios adversos | `backend/src/gabi/domain/portfolio/risk_policy.py:24`, `:76`, `:213` | [#292](https://github.com/juavepui/GABI/issues/292), cerrada |
| Ejecución simulada | ✅ V3 ejecuta a siguiente apertura, reserva costes y limita participación; contempla eventos corporativos | `backend/src/gabi/domain/portfolio/backtest_v3.py:87`, `:112`, `:198`; `test_backtest_v3.py` | [#249](https://github.com/juavepui/GABI/issues/249), cerrada |
| Seguimiento y registro | ⚠️ Implementados; no comprobé primera noche ni continuidad actual del programador | [Comentario operativo #290](https://github.com/juavepui/GABI/issues/290#issuecomment-6630558829) | [#290](https://github.com/juavepui/GABI/issues/290), cerrada; [#297](https://github.com/juavepui/GABI/issues/297) |
| Validación con datos nuevos | ⚠️ Protocolos y reservas existen; superioridad del modelo activo sin demostrar | `backend/src/gabi/infrastructure/model_versions.py:31`; `docs/search-ledger/ledger.json:40`; `docs/ensemble-prospective/README.md:11` | [#60](https://github.com/juavepui/GABI/issues/60), [#43](https://github.com/juavepui/GABI/issues/43) |

Para completar el proceso faltan **evidencia nueva por versión, cobertura acreditada y comprobación operativa real**. No faltan todos los motores desde cero. El primer registro ENS está previsto para 2026-12-21; sus primeras revisiones, y las de VALUE, para 2029-12-21. Antes se comprueba integridad y continuidad, sin mirar resultados reservados. Los motores publicados V1/V2 conservan limitaciones conocidas: corregirlas exige una versión nueva, sin cambiar silenciosamente estudios activos (`docs/architecture/backtest-v3.md:6`).

**2. Cartera y 10-K: capacidades conectadas, con límites concretos**

| Capacidad | Estado | Evidencia | Issue |
|---|---|---|---|
| Rentabilidad y evolución diaria | ✅ Compras, ventas y dividendos; TWR elimina efecto de aportaciones y XIRR considera sus fechas | `backend/src/gabi/domain/portfolio/holdings_performance.py:114`; `backend/tests/test_holdings_performance.py:53`, `:72` | [#294](https://github.com/juavepui/GABI/issues/294), cerrada |
| Riesgo, concentración y diversificación | ✅ Volatilidad, caída máxima, exposiciones y límites; no garantizan protección | `backend/src/gabi/domain/portfolio/risk_policy.py:76`; `holdings_performance.py:114` | [#292](https://github.com/juavepui/GABI/issues/292), [#294](https://github.com/juavepui/GABI/issues/294) |
| Comparación con índice | ✅ SPY en euros con los mismos flujos; declara datos insuficientes | `backend/src/gabi/domain/portfolio/holdings_performance.py:143` | [#294](https://github.com/juavepui/GABI/issues/294) |
| Atribución: origen de la ganancia | ✅ Por posición y sector, conciliada; no es descomposición de TWR | `backend/src/gabi/domain/portfolio/holdings_performance.py:166`; `backend/tests/test_holdings_performance.py:82`; `docs/mi-cartera.md:30` | [#294](https://github.com/juavepui/GABI/issues/294) |
| Splits y contrasplits en cartera real | ❌ Cantidades y precios pueden quedar en bases incompatibles | `backend/src/gabi/application/portfolio/holdings.py:182`; reproducción abajo | **Nueva propuesta** |
| Cuentas y señales del 10-K | ✅ Comparación de cifras, reexpresiones, retrasos, auditor, devengos, cobros y dilución | `backend/src/gabi/domain/market/tenk_flags.py:108`, `:128`, `:146`, `:196`; `backend/tests/test_tenk_flags.py:37` | [#293](https://github.com/juavepui/GABI/issues/293), cerrada |
| Lectura narrativa integral del 10-K | ⚠️ No analiza automáticamente Risk Factors, MD&A ni anexos narrativos | `backend/src/gabi/domain/market/filings.py:3`; `docs/tenk-flags.md:3` | [#250](https://github.com/juavepui/GABI/issues/250), descartada |
| Recorrido actual con datos reales propios | ⚠️ API, aplicación y React conectados; no certifiqué cartera real ni nueva descarga SEC | `backend/src/gabi_api/routes/holdings.py:32`; `frontend/src/features/portfolio/holdings-page.tsx:550` | Actualizar [#297](https://github.com/juavepui/GABI/issues/297) |

**Defecto ejecutado:** compra de 10 acciones a 100 €, seguida de split 2:1 sin cambio económico. Con cierres Yahoo en base actual `[50, 50]`, el código devuelve estado `ok`, valor final **500 €** y ganancia **−500 €**. Deben ser **20 acciones × 50 € = 1.000 €**, ganancia cero. El cálculo toma cierres sin transformar cantidades ni reconstruir precios nominales; V3 sí tiene reglas para esas bases (`backend/src/gabi/domain/portfolio/backtest_v3_inputs.py:42`). La reproducción y sus `assert` quedan en las notas de auditoría. No atribuyo un error TWR adicional: no se demostró.

**3. Los números salen del código o de fuentes identificadas**

Inventario por familias localizadas; **no garantiza cobertura de cada campo numérico de cada pantalla**. Prefijo de rutas: `backend/src/gabi/`; los tests citados están en `backend/tests/`. **D**: mismos datos, parámetros, fechas y versiones producen el mismo cálculo. **S**: aleatorio con semilla. En todas las filas se inspeccionó el uso de IA: **no existe importación automática de cifras de un LLM**.

| Familia visible | Cálculo o fuente | D/S | Prueba conocida / límite | Issue |
|---|---|---|---|---|
| PER, EV/EBITDA, capitalización, PEG, P/VC, márgenes, deuda, liquidez, ROE/ROA, dividendo | `domain/market/fundamentals.py:47` | D | `test_metrics.py:9`, `:68`; muchos valores vienen de Yahoo, no se recalculan | #296 |
| Crecimientos, márgenes y ROIC SEC antiguo | `domain/market/sec_facts.py:164` | D | `test_fundamental_metrics_pit.py`; fechas y límites legacy | #291 |
| ROIC V2.1, NOPAT, impuestos, deuda, caja y EV | `domain/market/sec_metrics_v2.py:165` | D | `test_sec_metrics_v2.py:37`: cuenta independiente; reexpresiones `:145` | #291 |
| Medias, RSI, momentum y fuerza relativa | `domain/market/technicals.py:17` | D | `test_technicals.py:27`: RSI plano 50; otras pruebas de propiedades | #296 |
| Rentabilidad, volatilidad, caída, Sharpe/Sortino, beta/alpha | `domain/market/risk.py:30` | D | `test_risk.py:56`, `:67`, `:80`: caída y betas conocidas | #296 |
| Puntuaciones, percentiles, cobertura y aportaciones | `domain/market/scoring.py:123` | D | `test_scoring.py:203`: confianza conocida; huellas de regresión | #296 |
| Checklist, ratios y medianas sectoriales | `domain/market/checklist.py:656` | D | `test_checklist.py:79`, `:127`: referencias Excel; no cada alarma | #291 |
| DCF, FCFF, WACC y crecimiento implícito | `domain/market/valuation_v2.py:57`; `valuation_expectations.py:24` | D | `test_valuation_v2.py:40`, `:59`: cuentas; puente equity parcialmente consistencia | #291 |
| Cambios contables y alertas 10-K | `domain/market/tenk_flags.py:108` | D | `test_tenk_flags.py:37`, `:54`: cifras conocidas y ausencias | #293 |
| Recompras, emisión, dividendos y financiación | `domain/portfolio/capital_allocation.py:71` | D | `test_capital_allocation.py:15`, `:34`: ratios y ausente≠cero | #296 |
| Lotes, divisas, valor, coste y pesos | `domain/portfolio/holdings.py:181` | D | `test_holdings*`; defecto de splits reproducido | Nueva |
| Evolución, TWR/XIRR, riesgo, índice y atribución | `domain/portfolio/holdings_performance.py:114` | D | `test_holdings_performance.py:53`, `:72`, `:82` | #294 |
| Aportaciones, unidades, valor liquidativo y escenarios | `domain/portfolio/contributions.py:131` | D | `test_investor_benchmark.py`, `test_contributions.py`; hipótesis explícitas | #294 |
| Costes, impuestos, rotación y ejecución | `domain/portfolio/broker_costs.py:47`; `backtest_v3.py:112` | D | Tests de costes y V3 con casos conocidos | #249 |
| Calmar, recuperación, error frente al índice y capturas | `domain/portfolio/metrics.py:144` | D | `test_portfolio_metrics.py:8`, `:37`, `:71`: valores conocidos | #296 |
| Pérdida extrema VaR/ES, asimetría y curtosis | `domain/portfolio/metrics.py:27` | D | `test_portfolio_metrics.py:101`, `:111`, `:142`; histórico, no Monte Carlo | #296 |
| Pesos optimizados, concentración HHI y estrés | `domain/research/portfolio_lab.py:53` | D¹ | `test_portfolio_lab.py:149`, `:171`; optimización principalmente propiedades | #292 |
| Escenarios y retorno esperado | `domain/portfolio/journal.py:6`; `investment_card.py:201` | D | `test_journal_expected_value.py:4`: suma ponderada manual | #296 |
| Correlación de señales, quintiles y estabilidad | `domain/research/factors.py:47` | D | Tests de factores; no oráculo manual de cada resumen | #60 |
| Regresiones, alpha/betas e intervalos robustos | `domain/research/academic_factors.py:45` | D | `test_academic_factors.py:45`, `:120`, `:131`: casos independientes | #60 |
| Consenso, revisiones y sorpresa de beneficios | `domain/research/estimates.py:55` | D | `test_estimates.py`; consenso externo | #296 |
| Sharpe probabilístico/deflactado y sobreajuste PBO | `domain/research/statistics.py:32` | D | `test_stats_rigor.py:29`, `:78`, `:213`: casos conocidos y plausibilidad | #60 |
| Intervalos por remuestreo y placebos | `domain/research/statistics.py:147`; `block_bootstrap.py:162`; `placebo_engine.py:140` | S | Tests de semilla/bloques; metadatos de entrada y código | #296 |
| Integración Monte Carlo y límites secuenciales | `infrastructure/statistics/prospective.py:17` | S² | `test_determinism.py:23`: instancias nuevas iguales | #296 |

¹ Depende también de versiones y del optimizador. ² La semilla fija reproduce una secuencia; repetir llamadas sobre el mismo generador consume estado. La reproducción legacy conserva deliberadamente `rng=None`, sin modificar planes publicados. No se comprobó igualdad bit a bit entre sistemas operativos o versiones de librerías.

| Control transversal | Estado y evidencia | Issue |
|---|---|---|
| IA limitada a explicación | ✅ Se exporta un prompt para copiar; no hay llamada ni lectura automática de respuesta (`backend/src/gabi/application/market/prompt_text.py:1`) | [#296](https://github.com/juavepui/GABI/issues/296) |
| Comprobación numérica del prompt | ⚠️ `backend/tests/test_prompt_numbers.py:45` valida salida, no respuesta externa ni correspondencia semántica completa | [#296](https://github.com/juavepui/GABI/issues/296) |
| Versiones y reproducción | ⚠️ Modelos/versiones y huellas verificables; revisión de caché no equivale a snapshot inmutable de datos (`backend/src/gabi/infrastructure/storage/market.py:1`) | [#296](https://github.com/juavepui/GABI/issues/296), [#60](https://github.com/juavepui/GABI/issues/60) |

Si se incorpora una respuesta IA en el futuro, cada cifra debería llevar identificador de métrica, valor, unidad, periodo y fuente; el código debe rechazar discrepancias o cifras sin origen. Hoy un asistente externo puede inventar números y el usuario puede transcribirlos: GABI no ofrece garantía sobre ese recorrido manual.

**4. Calidad de datos y rigor: hay controles, no una garantía absoluta**

| Aspecto | Estado y evidencia | Issue |
|---|---|---|
| Precios imposibles, duplicados y OHLC | ✅ Rechaza ventana inválida: finitos, precios positivos, volumen y coherencia (`backend/src/gabi/domain/market/price_sync.py:47`) | [#295](https://github.com/juavepui/GABI/issues/295) |
| Plausibilidad y saltos | ✅ V3 convierte métricas inválidas en ausencia; saltos eliminan métricas de precio; cruce capitalización solo avisa (`backend/src/gabi/domain/market/input_checks.py:29`, `:89`, `:103`) | [#295](https://github.com/juavepui/GABI/issues/295) |
| Huecos, frescura y procedencia | ⚠️ Diagnósticos y exclusión por identidad; no certificado integral (`backend/src/gabi/domain/market/data_quality.py:107`, `:347`) | [#295](https://github.com/juavepui/GABI/issues/295) |
| Unidades, divisas y publicación | ✅ Filtra unidades SEC y no finitos; solo hechos publicados a fecha consultada (`backend/src/gabi/domain/research/sec_bulk.py:21`; `backend/src/gabi/infrastructure/storage/sec_reads.py:95`) | [#291](https://github.com/juavepui/GABI/issues/291) |
| Reexpresiones contables | ✅ Conserva publicación/procedencia y selecciona versión conocida entonces (`backend/src/gabi/domain/market/sec_facts.py:130`; `sec_metrics_v2.py:96`) | [#291](https://github.com/juavepui/GABI/issues/291) |
| Splits, dividendos y desaparecidas | ⚠️ Acreditación histórica exige evidencia; quedan terminales/cobertura incompletos (`backend/src/gabi/domain/research/price_accreditation.py:108`, `:146`) | [#60](https://github.com/juavepui/GABI/issues/60), [#44](https://github.com/juavepui/GABI/issues/44) |
| Sobreajuste, costes e intervalos | ⚠️ Hay métodos y pruebas; historial incompleto impide afirmar control global del error (`docs/search-ledger/ledger.json:40`, `:50`) | [#60](https://github.com/juavepui/GABI/issues/60), [#43](https://github.com/juavepui/GABI/issues/43) |

El ledger verifica sus huellas, pero reconoce un mínimo de 38 configuraciones y búsquedas irrecuperables. La revalidación publicada deja PBO/DSR acreditados sin calcular por el evento RAI y cinco posiciones sin terminal confirmado (`docs/historical-revalidation-2011-2025/README.md:52`, `:82`). No puede concluirse ausencia de sesgo de supervivencia ni ventaja neta demostrada.

**Verificación ejecutada y límites**

Pasaron tandas de **154 y 107 tests numéricos**, **79 de cartera/10-K/V3**, **136 de datos/estadística/ledger**, y **9 guardas frontend**. No los sumo: hay solapamiento. Arquitectura backend/frontend, tipos frontend, hashes congelados y `ledger --verify` pasaron. Ruff devolvió éxito, con avisos de directorios inaccesibles: no lo presento como cobertura completa de cada archivo. No se ejecutó la suite completa.

No cambié código ni usé la base real para validar; tampoco descargué fuentes, ejecuté estudios ni abrí datos reservados. Quedan expresamente pendientes comprobaciones reales de seguimiento ([#290](https://github.com/juavepui/GABI/issues/290)), comparación de rankings ([#291](https://github.com/juavepui/GABI/issues/291)) y reporte de entrada ([#295](https://github.com/juavepui/GABI/issues/295)); sus comentarios ya lo documentan. No requieren issues duplicadas.

**Lista propuesta antes de crear nada**

**Una issue nueva: «[Cartera] Conciliar cantidades y precios tras splits y contrasplits»**.

| Campo | Propuesta |
|---|---|
| Problema e impacto | Cantidades originales y precios ajustados pueden producir valor y ganancia falsos con estado `ok`; el usuario puede interpretar una pérdida inexistente |
| Prioridad y etiquetas | **Alta**; etiqueta existente `bug` |
| Dependencias | Integración sobre #294; reutilizar o adaptar las reglas de base de precios de #249; enlazar bajo #297. Ambas dependencias están cerradas |
| Aceptación verificable | Tests sintéticos de split 2:1 y contrasplit, antes/después de compras y ventas; valor y rendimiento neutrales a valor económico constante; conciliación cantidades×precio, coste y atribución; distinguir cantidades originales de ya reajustadas sin doble ajuste; dato de evento ausente/ambiguo advertido o bloqueado; prueba del recorrido API con fuentes temporales |
| Duplicados descartados | Búsqueda en issues abiertas/cerradas por split, contrasplit, desdoblamiento y eventos corporativos. #249 cubre backtest; #294 no cubre ajuste de cantidades de cartera real |

Propongo además **comentar #297**, sin abrir otro paraguas, para enlazar esta evidencia, las entregas cerradas y las comprobaciones operativas pendientes. Esperaré tu confirmación de esta lista antes de crear la issue o publicar el comentario. Para crearla mediante `gh issue create` también tendrá que funcionar su autenticación, que hoy devolvió 401.
