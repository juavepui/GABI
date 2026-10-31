# Mapa de ventajas económicas y selección de hipótesis (#268)

**Estado:** propuesta del 2026-10-31, pendiente de aprobación del propietario.
Ni este documento ni su elaboración incluyen código de trading, cálculo de
rentabilidades ni consulta de muestras reservadas (#43, #44 y #237).

**Relación:** concreta el primer paso de #252 y alimenta #60, que conserva el
objetivo y el registro de intentos (`docs/search-ledger/ledger.json`). Aquí no
se abre un segundo registro. Prerrequisitos técnicos de la evaluación: #243,
#245 y #249.

## 1. Punto de partida: qué ha visto ya GABI

Una hipótesis solo es «nueva» si su familia no se ha medido antes sobre el mismo
histórico. Según el registro de #60 y los diagnósticos publicados:

| Familia | ¿Observada en S&P 500 2011–2025? | Dónde |
|---|---|---|
| Valor (PER, EV/EBITDA, P/B) | Sí | Factor Zoo (#48), QV y QVM; además está en seguimiento prospectivo en ENS-VQE (#237) |
| Calidad (ROIC, margen operativo, crecimientos, «calidad persistente») | Sí | Factor Zoo, R3 E6a, QV y QE |
| Momentum 12m / 6m / SMA200 | Sí, con IC medio negativo | Factor Zoo y QVM |
| Recompras y generación de caja | Sí, descartada | RCF v1 |
| Brecha de crecimiento implícito (expectativas) | Sí | QE; ENS (prospectivo) |
| Riesgo (deuda, volatilidad, drawdown) | Sí | Factor Zoo, R3 E6b |
| Accruals / devengos | **No** | — |
| Rentabilidad operativa de caja o bruta sobre activos | **No** (correlacionada con ROIC/margen, que sí se vieron) | — |
| Crecimiento de activos / inversión | **No** | — |
| Emisión neta de acciones | **No** (la dilución no pudo acreditarse: 0/57 fechas) | Auditoría de capital de #60 |
| Sorpresa de beneficios y deriva posterior (PEAD) | **No** | — |
| Revisiones de analistas | **No** (no hay historia point-in-time) | `docs/estimates-data.md` |

Consecuencia: elegir otra vez valor, calidad clásica o momentum supondría
reutilizar resultados ya vistos. Este informe solo considera como candidatas
nuevas las familias de la mitad inferior de la tabla.

## 2. Evidencia general: las primas se degradan

Cualquier decisión debe partir de que una prima publicada probablemente valga
menos de lo que dice su artículo original:

- **McLean y Pontiff (2016).** En 97 predictores, los rendimientos de cartera
  son un 26 % menores fuera de muestra y un 58 % menores tras la publicación.
  *Journal of Finance* 71(1), 5–32.
- **Hou, Xue y Zhang (2020).** Al mitigar el peso de las microcaps (cortes del
  NYSE y ponderación por capitalización), el 65 % de 452 anomalías no supera
  |t| = 1,96. *Review of Financial Studies* 33(5), 2019–2133.
- **Jensen, Kelly y Pedersen (2023).** Contrapunto: la mayoría de los factores
  replica y se agrupa en 13 temas. La conclusión de «crisis» depende del criterio
  de replicación. *Journal of Finance* 78(5), 2465–2518.
- **Harvey, Liu y Zhu (2016).** Proponen exigir t > 3 a un factor nuevo, dado el
  volumen de búsquedas. *RFS* 29(1), 5–68.
- **Linnainmaa y Roberts (2018).** La mayoría de las anomalías contables,
  incluida la inversión, no aparece antes de 1963. Entre 1918 y 1962 tampoco
  encuentran primas significativas de rentabilidad ni de inversión. *RFS*
  31(7), 2606–2649.
- **Chen y Velikov (2023).** Descontando spreads efectivos, efectos de
  publicación y la era de negociación moderna, la anomalía media espera unos
  4 pb/mes, y las más fuertes como mucho 10 pb. *JFQA* 58(3).
- **Novy-Marx y Velikov (2016).** Las anomalías con rotación inferior al
  50 %/mes sobreviven a los costes si se diseñan para ello, sobre todo mediante
  una banda de compra/mantenimiento. Pocas de alta rotación sobreviven. Tamaño,
  valor y rentabilidad tienen la mayor capacidad. *RFS* 29(1), 104–147.

Lectura para GABI: el objetivo de +2 pp anuales netos frente al S&P 500 (#60)
supera el rendimiento esperado de casi cualquier anomalía publicada en
grandes compañías. Lo honesto es fijar como alternativa por defecto un ETF del
índice o un ETF factorial barato. La estrategia propia tiene que demostrar que
añade algo a esa alternativa.

## 3. Mecanismos candidatos

### 3.1 Sorpresas de beneficios y deriva posterior (PEAD), y revisiones

- **Mecanismo:** infrarreacción a la información de resultados. El precio
  sigue moviéndose en la dirección de la sorpresa durante semanas (Ball y Brown,
  1968; Bernard y Thomas, 1989).
- **Contraevidencia fuerte para el S&P 500:**
  - Chordia, Goyal, Sadka, Sadka y Shivakumar (2009) encuentran que la deriva se
    concentra en acciones ilíquidas: unos 0,04 %/mes ponderado por capitalización
    en las más líquidas, frente a 2,43 % en las menos líquidas. Los costes
    absorben entre el 70 % y el 100 % del beneficio en papel.
    *Financial Analysts Journal* 65(4), 18–32.
  - Martineau (2022), «Rest in Peace Post-Earnings Announcement Drift», sostiene
    que la deriva desaparece en las no microcaps desde 2001 y del todo hacia
    2006. *Critical Finance Review* 11(3–4), 613–646.
  - Subrahmanyam (documento de trabajo de 2025, datos de 2001 a 2024) la vuelve
    a encontrar con todas las acciones (t = 2,18), pero no al excluir microcaps
    (t = 1,43).
- **Revisiones de analistas:** no existe historia point-in-time gratuita.
  Yahoo solo da la foto actual. El archivo propio de GABI empieza en su primera
  captura y hoy devuelve `insufficient_data` (`docs/estimates-data.md`).
- **Veredicto:** descartar la PEAD para el universo S&P 500. Aparcar las
  revisiones hasta que el archivo propio acumule suficientes capturas: solo
  sirven para seguimiento prospectivo.

### 3.2 Calidad del beneficio: accruals y rentabilidad operativa de caja

- **Mecanismo:** el mercado sobrevalora la persistencia del componente devengado
  del beneficio frente al componente de caja (Sloan, 1996, *The Accounting
  Review* 71(3), 289–315).
- **Contraevidencia:** Green, Hand y Soliman (2011) documentan que la prima del
  accrual de Sloan ha decaído en EE. UU. hasta no ser fiablemente positiva, en
  parte por el capital de los hedge funds que la explotan. *Management Science*
  57(5), 797–816.
- **Reformulación que sobrevive:** Ball, Gerakos, Linnainmaa y Nikolaev (2016).
  - Definen la rentabilidad operativa de caja (CbOP) como ventas − coste de
    ventas − gastos generales y de administración, menos los cambios en cuentas
    a cobrar, inventario y gastos anticipados, más los cambios en ingresos
    diferidos, cuentas a pagar y gastos devengados; todo escalado por los
    activos totales.
  - La CbOP subsume a los accruals y a la rentabilidad operativa con devengos.
  - En la muestra sin microcaps, con regresiones Fama-MacBeth entre 1963 y 2013,
    la CbOP alcanza t = 5,83, mientras que la rentabilidad operativa cae a
    t = 1,19.
  - Excluye las financieras. *Journal of Financial Economics* 121(1), 28–45.
- **Encaje con grandes compañías:**
  - Fama y French (2008) encuentran la anomalía de accruals en todos los grupos
    de tamaño. *Journal of Finance* 63(4), 1653–1678.
  - Novy-Marx (2013) muestra que la rentabilidad bruta funciona especialmente
    bien entre las mayores y más líquidas al combinarla con valor. *JFE*
    108(1), 1–28.
- **Riesgos:**
  - La prima puede ser la de RMW (Fama y French, 2015, *JFE* 116(1), 1–22)
    y no una ventaja de selección. En ese caso un ETF de calidad la captura más
    barato.
  - Correlación con ROIC y margen operativo, que en GABI dieron IC +0,013 y
    −0,007 (Factor Zoo). Es contaminación parcial y se declara.
  - Linnainmaa y Roberts no hallan prima de rentabilidad antes de 1963.

### 3.3 Inversión y crecimiento de activos

- **Mecanismo:** las empresas que crecen mucho en activos rinden menos después,
  por sobreextrapolación o por el menor coste de capital que lleva a invertir
  (Cooper, Gulen y Schill, 2008, *Journal of Finance* 63(4); factor CMA de
  Fama y French, 2015; q-factor de Hou, Xue y Zhang, 2015, *RFS* 28(3)).
- **Contraevidencia decisiva para el S&P 500:** Fama y French (2008) no
  encuentran anomalía de crecimiento de activos en las grandes compañías, que
  suman más del 90 % de la capitalización. Linnainmaa y Roberts la clasifican
  como probable artefacto de minería de datos.
- **Veredicto:** descartar para el universo actual. Reconsiderar solo con
  small/mid caps acreditadas (#251/#44).

### 3.4 Emisión neta de acciones

- **Mecanismo:** las empresas emiten cuando sus acciones están caras y
  recompran cuando están baratas. Pontiff y Woodgate (2008), «Share Issuance
  and Cross-sectional Returns», *Journal of Finance* 63(2), 921–945.
- **A favor:** Fama y French (2008) la consideran generalizada en todos los
  tamaños, igual que los accruals y el momentum.
- **Bloqueo de datos:** GABI no ha podido acreditar el número de acciones
  ajustado por splits. La auditoría de capital de #60 dio 0 de 57 fechas.
- **Solape:** RCF v1, que usaba recompras brutas sobre FCF, ya se vio y se
  descartó. El solape es parcial, porque la emisión neta mide el cambio en las
  acciones en circulación.
- **Veredicto:** candidata de reserva, condicionada a superar una puerta de
  datos de splits y clases antes de mirar cualquier rendimiento.

### 3.5 Momentum 12–2

- **A favor:** es una de las anomalías más extendidas y replicadas
  (Jegadeesh y Titman, 1993, *JF* 48(1); Asness, Moskowitz y Pedersen, 2013,
  *JF* 68(3)).
- **En contra:**
  - Daniel y Moskowitz (2016) documentan caídas severas en los rebotes tras
    mercados bajistas. *JFE* 122(2), 221–247.
  - La rotación es alta.
  - En GABI ya se ha visto con IC negativo.
- **Veredicto:** aparcar como hipótesis. Usarlo solo como exposición de
  control en las regresiones.

### 3.6 Eventos especiales (escisiones, salidas de índice, recompras anunciadas)

No hay un universo histórico de eventos verificable y gratuito. El protocolo de
#252 prefiere seguimiento prospectivo manual a un backtest falso. **Veredicto:**
aparcar.

### 3.7 Valor frente a expectativas

Ya se ha observado (QE) y está en seguimiento prospectivo (ENS-VQE, primer
registro el 2026-12-21). Abrir otra variante ahora sería elegir con resultados
vistos y competir con un estudio activo (ADR 0008). **Veredicto:** fuera de
esta selección.

## 4. Matriz de viabilidad

Puntuación cualitativa del 1 (malo) al 5 (bueno). **No es una probabilidad de
batir al índice.**

| | PEAD | Revisiones | CbOP / accruals | Crecimiento de activos | Emisión neta | Momentum 12–2 |
|---|---|---|---|---|---|---|
| Plausibilidad económica | 4 | 4 | 4 | 3 | 4 | 4 |
| Replicación independiente | 2 (desaparece fuera de microcaps) | 3 | 4 (CbOP), 2 (accrual de Sloan) | 2 en grandes | 4 | 5 |
| Vigencia en grandes compañías | 1 | 3 | 4 | 1 | 3 | 3 |
| Inputs point-in-time | Fecha del 8-K Item 2.02 en `submissions` de EDGAR (gratis); BPA trimestral XBRL con el Q4 derivado | No existen gratis; solo el archivo propio desde su inicio | Company Facts con fecha `filed`; faltan etiquetas de SG&A, I+D y variaciones de circulante | `Assets` ya sincronizado | Acciones en circulación: el ajuste por splits no está acreditado | Precios Yahoo; universo histórico acreditado 2010–2026 |
| Cobertura histórica y deslistados | XBRL desde 2009–2011 | Ninguna | XBRL desde 2009–2011; deslistados según identidad 2010–2015 | Igual | Igual, más clases de acciones | Precios atribuidos por emisor; huecos declarados |
| Licencia y cuotas | SEC pública, 10 peticiones/s | Yahoo sin licencia formal | SEC pública | SEC pública | SEC pública | Yahoo sin licencia formal |
| Dificultad de construcción | Alta: motor de eventos diario | — | Media: nuevas etiquetas y fórmula | Baja | Media-alta: splits y clases | Baja |
| Riesgo de sesgo | Medio (fecha del anuncio frente al filing) | Alto | Medio (heterogeneidad de etiquetas; financieras excluidas) | Bajo | Alto (clases, splits) | Bajo |
| Rotación y costes | Alta | Media | Baja (señal anual) | Baja | Baja | Alta |
| Diferenciación frente a un ETF | Alta | Alta | Baja-media (solape con RMW / ETF de calidad) | Media | Media | Baja (ETF de momentum) |
| Contaminación en GABI | Ninguna | Ninguna | Parcial (ROIC y margen vistos) | Ninguna | Parcial (RCF) | Total |
| Horas estimadas hasta la evaluación | 25–40 | Bloqueada | 15–25 | 8–12 | 20–30 más la puerta de datos | 6–10 |
| Comparador nulo | Cartera equiponderada con las mismas fechas de anuncio | — | ETF de calidad y regresión sobre RMW | CMA | Cartera equiponderada del universo | UMD |

## 5. Decisión propuesta

1. **Candidata principal: rentabilidad operativa de caja (CbOP) en el S&P 500,
   excluidas financieras.**
   - Es la única familia nueva con evidencia replicada en grandes compañías,
     una reformulación que ya incorpora el decaimiento del accrual de Sloan,
     baja rotación y datos gratuitos con fecha de presentación.
   - Riesgo principal: que solo sea la prima de rentabilidad que ya vende un ETF
     de calidad. El protocolo lo contrasta explícitamente; si se confirma, la
     conclusión útil es «comprar el ETF», no «GABI tiene ventaja».
2. **Reserva: emisión neta de acciones.** Solo si antes se acredita el número de
   acciones ajustado por splits y clases (puerta de datos, sin rendimientos).
3. **Descartadas para el S&P 500:**
   - PEAD: desaparece en las acciones líquidas.
   - Crecimiento de activos: no aparece en las grandes compañías.
4. **Aparcadas:**
   - Revisiones: hasta que haya un archivo propio suficiente; solo prospectivo.
   - Momentum: ya visto; queda como control.
   - Eventos especiales: sin datos de eventos.
   - Valor frente a expectativas: lo cubre ENS.

**Qué falsaría cada una**, fijado antes de mirar ningún rendimiento:

- **CbOP**, cualquiera de estas condiciones:
  - Cobertura de etiquetas inferior al 70 % del universo elegible en algún año.
    Se cierra por inviable sin evaluar.
  - En la evaluación exploratoria, IC medio ≤ 0, o exceso neto BASE ≤ 0 frente
    al S&P 500 TR en EUR con flujos idénticos.
  - Alfa frente a FF5 con intervalo centrado en ≈ 0 y sin ventaja frente al ETF
    de calidad. En ese caso se reclasifica como «exposición factorial» y no se
    promociona.
- **Emisión neta:**
  - Puerta de acreditación de splits/clases inferior al 70 % de emisores-fecha.
    Se cierra por inviable.
  - Después, mismas condiciones económicas que la CbOP.

## 6. Propuesta de preregistro de la CbOP (sin ejecutar)

Se someterá a #252 cuando #243, #245 y #249 permitan una evaluación fiable. Las
cifras son propuestas y se congelarán en el preregistro definitivo, con el hash
del commit, antes de cualquier cálculo de rendimiento.

**Universo, señal y datos**

| Elemento | Propuesta |
|---|---|
| Identificador | `CBOP-v1` |
| Universo | Miembros del S&P 500 en cada fecha de señal según la composición histórica acreditada; excluidos SIC 6000–6999. |
| Datos | Company Facts de la SEC. Añadir a la sincronización: SG&A, I+D (para seguir la definición de Ball et al., 2014, que la excluye de los gastos operativos), `IncreaseDecreaseInAccountsReceivable`, `IncreaseDecreaseInInventories`, `IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets`, `IncreaseDecreaseInContractWithCustomerLiability` / `IncreaseDecreaseInDeferredRevenue`, `IncreaseDecreaseInAccountsPayable` e `IncreaseDecreaseInAccruedLiabilities`. Solo hechos del 10-K anual con `filed` anterior a la señal. Sin imputar ausencias como cero, salvo una partida de circulante que el emisor no presente en ningún periodo; esa regla se fija y audita antes. |
| Señal | CbOP del último ejercicio / activos totales al cierre de ese ejercicio. Percentil dentro del universo elegible; sin pesos ni combinación con otros factores. |
| Retardo | Utilizable desde la sesión siguiente a la aceptación del 10-K. Ejecución en la apertura siguiente a la señal (motor V3). |

**Cartera y flujos**

| Elemento | Propuesta |
|---|---|
| Cartera | 20 posiciones equiponderadas, máximo 6 por división SIC. |
| Banda de mantenimiento | Entra el quintil superior; se mantiene mientras siga en el 40 % superior (Novy-Marx y Velikov). |
| Rebalanceo | Anual tras la temporada de 10-K (primera sesión de julio). |
| Aportaciones | Mensuales: 11.000 € iniciales y 700 €/mes, invertidos en las posiciones más infraponderadas. |
| Deslistados | Eventos del motor V3 (fusión en efectivo o en acciones, exclusión, quiebra con su recuperación). Sin rellenar precios hacia atrás. |
| Costes | Escenarios BASE y STRESS de V3, más conversión EUR/USD y retención del 15 % sobre dividendos (W-8BEN). |

**Comparadores y riesgo**

| Elemento | Propuesta |
|---|---|
| Benchmark primario | S&P 500 total return en EUR (#244) con el mismo calendario, flujos y contabilidad. |
| Comparadores baratos | Equiponderado del universo elegible, ETF de calidad UCITS con flujos idénticos y regresión sobre FF5 + UMD (Ken French, gratis). |
| Límites de riesgo | Volatilidad diaria ≤ 110 % de la del índice; drawdown no más de 5 pp peor (#60); presupuesto de pérdida del 20 % (#242). |

**Evaluación**

| Elemento | Propuesta |
|---|---|
| Fases | (1) Puerta de datos: cobertura por año, sin rendimientos. (2) Exploratoria en 2011–2025, que ya es historia observada del universo y nunca se citará como independiente. (3) Seguimiento prospectivo desde la fecha de registro. |
| Ventanas | 2011–15, 2016–20 y 2021–25, informadas por separado; ninguna se elige a posteriori. |
| Test | Exceso neto mensual frente al benchmark. Cota inferior unilateral por bootstrap circular de bloques de 12 meses, 5.000 réplicas, α = 0,05/3. IC medio con t HAC. |
| Presupuesto de intentos | 3 configuraciones como máximo: primaria, STRESS y Top-30 como sensibilidad. Todas se registran en el ledger de #60. |
| Criterio de abandono | Cualquiera de los falsadores de la sección 5. |

**Potencia.** Con un tracking error del 6 % anual, una ventaja real de +2 pp
daría t ≈ 2/6·√14 ≈ 1,2 en 14 años. La fase exploratoria no puede «demostrar»
el objetivo de #60, y 1–2 años de seguimiento prospectivo todavía menos. La
decisión de usarla con dinero real exige aceptar esa incertidumbre o quedarse
con el índice.

Horas estimadas hasta la primera decisión go/no-go, sin contar los
prerrequisitos:

| Tarea | Horas |
|---|---|
| Etiquetas y sincronización | 6–10 |
| Auditoría de cobertura | 3–5 |
| Señal en el dominio con pruebas | 4–6 |
| Evaluación con V3 | 4–8 |

## 7. Enlaces y tiempo

- Cuando el propietario apruebe la decisión, se anotará en #60 (familia nueva
  `cbop_v1`, todavía sin resultados) y en #242.
- Tiempo invertido en esta entrega: unas 2 h de trabajo asistido el 2026-10-31,
  entre revisión del registro de #60, búsqueda y verificación de fuentes y
  redacción. El propietario añade aquí su tiempo de revisión.

## Referencias

- Asness, Moskowitz y Pedersen (2013). Value and Momentum Everywhere. *JF* 68(3), 929–985.
- Ball y Brown (1968). An Empirical Evaluation of Accounting Income Numbers. *JAR* 6(2), 159–178.
- Ball, Gerakos, Linnainmaa y Nikolaev (2016). Accruals, Cash Flows, and Operating Profitability in the Cross Section of Stock Returns. *JFE* 121(1), 28–45.
- Bernard y Thomas (1989). Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium? *JAR* 27, 1–36.
- Chen y Velikov (2023). Zeroing In on the Expected Returns of Anomalies. *JFQA* 58(3).
- Chordia, Goyal, Sadka, Sadka y Shivakumar (2009). Liquidity and the Post-Earnings-Announcement Drift. *FAJ* 65(4), 18–32.
- Cooper, Gulen y Schill (2008). Asset Growth and the Cross-Section of Stock Returns. *JF* 63(4), 1609–1651.
- Daniel y Moskowitz (2016). Momentum Crashes. *JFE* 122(2), 221–247.
- Fama y French (2008). Dissecting Anomalies. *JF* 63(4), 1653–1678.
- Fama y French (2015). A Five-Factor Asset Pricing Model. *JFE* 116(1), 1–22.
- Green, Hand y Soliman (2011). Going, Going, Gone? The Apparent Demise of the Accruals Anomaly. *Management Science* 57(5), 797–816.
- Harvey, Liu y Zhu (2016). … and the Cross-Section of Expected Returns. *RFS* 29(1), 5–68.
- Hou, Xue y Zhang (2015). Digesting Anomalies: An Investment Approach. *RFS* 28(3), 650–705.
- Hou, Xue y Zhang (2020). Replicating Anomalies. *RFS* 33(5), 2019–2133.
- Jegadeesh y Titman (1993). Returns to Buying Winners and Selling Losers. *JF* 48(1), 65–91.
- Jensen, Kelly y Pedersen (2023). Is There a Replication Crisis in Finance? *JF* 78(5), 2465–2518.
- Linnainmaa y Roberts (2018). The History of the Cross-Section of Stock Returns. *RFS* 31(7), 2606–2649.
- Martineau (2022). Rest in Peace Post-Earnings Announcement Drift. *Critical Finance Review* 11(3–4), 613–646.
- McLean y Pontiff (2016). Does Academic Research Destroy Stock Return Predictability? *JF* 71(1), 5–32.
- Novy-Marx (2013). The Other Side of Value: The Gross Profitability Premium. *JFE* 108(1), 1–28.
- Novy-Marx y Velikov (2016). A Taxonomy of Anomalies and Their Trading Costs. *RFS* 29(1), 104–147.
- Pontiff y Woodgate (2008). Share Issuance and Cross-sectional Returns. *JF* 63(2), 921–945.
- Sloan (1996). Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings? *The Accounting Review* 71(3), 289–315.
- Subrahmanyam (2025). Keeping it Simple: How Can Post-Earnings Return Drift Exist and Not Exist Simultaneously? Documento de trabajo, SSRN 5930255.
