# Small/mid caps y Europa con datos gratuitos: matriz de fuentes y protocolo de piloto (#251)

**Estado:** matriz y protocolo redactados el 2026-11-02, **sin descargar datos** y sin
medir rentabilidades. Las condiciones de cada fuente se comprobaron ese día en su
documentación pública. Lo que no se pudo comprobar en la fuente oficial queda marcado
como **no verificado** y no se da por bueno.

## 1. Alcance y relación con #44

- **EE. UU. fuera del S&P 500:** lo estudia #44.
  - Su auditoría pública ([`docs/smallmid-feasibility`](../smallmid-feasibility/README.md))
    ya mide el tamaño del universo PIT (1.785–2.400 emisores por fecha) y la brecha de
    precios de los emisores que dejaron de reportar.
  - También mide el límite gratuito de Tiingo, de unos 500 símbolos al mes.
  - Su recogida se congela como tarde el **2027-01-15**. Esta issue no abre sus
    rankings ni sus retornos reservados, y su piloto de EE. UU. espera a esas
    conclusiones públicas.
- **Europa:** es lo nuevo de esta issue y es lo que desarrolla este documento.
- **Cambiar de geografía no es evidencia independiente** si el régimen de mercado es el
  mismo. Un resultado europeo de 2021–2025 sería historia observada en el mismo periodo
  que ya vio GABI.

## 2. Matriz de fuentes

Estado: **V** = verificado en la fuente oficial el 2026-11-02; **NV** = no verificado
(fuentes secundarias o sin términos encontrados); **L** = comprobado localmente.

### Fundamentales

| Región | Fuente | Cobertura | Acceso y licencia | Continuidad | Estado |
|---|---|---|---|---|---|
| EE. UU. | SEC Company Facts / FSDS | Todos los emisores SEC, con XBRL desde 2009–2011 | Pública, 10 peticiones/s y User-Agent identificable | Oficial | V (en uso) |
| Europa | **ESEF** (iXBRL obligatorio) | Estados primarios con etiquetado detallado para ejercicios desde el **1-1-2020**; notas solo con *block tagging* desde 2022; el detalle de las notas es voluntario | Publicado por cada OAM nacional; no hay repositorio oficial central | Obligatorio por norma | V |
| Europa | **filings.xbrl.org** (XBRL International) | Agrega ESEF de los OAM. **No es completo: no incluye Alemania ni Irlanda**, y excluye los filings sin LEI o fecha determinables | API JSON gratuita, con posibles límites o retirada; pide User-Agent con contacto; índices anuales para descargas masivas; «sin restricciones» de reutilización | Servicio voluntario y sin compromiso de permanencia | V |
| Europa | **ESAP** (ESMA) | Punto de acceso único: recogida desde el 10-7-2026 y **apertura pública el 10-7-2027** | ESMA lo anuncia como acceso gratuito y centralizado; **API no confirmada** | Oficial | V (fechas) / NV (API) |
| Europa | Antes de 2020 | Sin XBRL obligatorio: solo informes en PDF/HTML | — | — | V |

### Precios, eventos corporativos, identidad, divisas y calendario

| Elemento | Fuente | Condiciones | Estado |
|---|---|---|---|
| Precios EE. UU. | Yahoo (en uso) y Tiingo (500 símbolos al mes en el plan gratuito, según #44) | Yahoo **sin licencia formal**; Tiingo con cuota limitada | NV (Yahoo) / según #44 |
| Precios Europa | Yahoo (sufijos .DE, .PA, .AS…) | Sin licencia formal; cobertura de deslistados no medida | NV |
| Precios Europa | Stooq | Datos diarios gratuitos. Fuentes secundarias de 2026 indican clave por CAPTCHA, cuota diaria baja y bloqueos por IP; **términos oficiales no encontrados** | NV |
| Eventos corporativos | Splits y dividendos de Yahoo; fusiones y exclusiones sin fuente gratuita fiable | Igual que la #249: lo que no se confirma no se rellena | NV |
| Identidad | **OpenFIGI** (Bloomberg) | API gratuita: *mapping* de 25 peticiones/min sin clave o 25 cada 6 s con clave gratuita, con 10 o 100 trabajos por petición; ISIN o ticker → FIGI y mercado | V (límites) / NV (términos completos) |
| Identidad | LEI (GLEIF) en cada filing ESEF | Identifica al emisor, no a la línea de cotización. Clases de acciones y cotizaciones múltiples, vía OpenFIGI | V (ESEF exige LEI) |
| Divisas | **Banco Central Europeo** (`data-api.ecb.europa.eu`) | Tipos de referencia diarios. Reutilización **gratuita, también comercial**, citando «Source: ECB statistics» y sin modificar los datos | V |
| Calendario | `exchange_calendars` 4.13.2 (en uso) | Incluye XETR, XFRA, XPAR, XAMS, XBRU, XLIS, XMIL, XMAD, XSWX, XLON, XSTO, XHEL, XCSE, XOSL, XWBO, XDUB y XWAR | L |
| Composición histórica | Índices europeos (STOXX, MSCI…) | **Sin fuente gratuita de miembros históricos.** Las carteras de los ETF solo dan la composición actual | V (ausencia) |

## 3. Qué permite y qué no

1. **Un histórico europeo sin sesgo de supervivencia no es viable gratis.**
   - No hay XBRL antes de los ejercicios de 2020.
   - No hay composición histórica gratuita de ningún índice.
   - La cobertura de precios de deslistados no se puede acreditar.
   - Un universo construido con los emisores de hoy no acredita miembros históricos.
2. **Un histórico europeo de 2021 a 2025 sería corto (unos 4 años) y estaría
   contaminado.** Es el mismo periodo observado y sin composición PIT. Como mucho,
   serviría de diagnóstico de cobertura, nunca de evidencia.
3. **El seguimiento prospectivo en Europa puede ser viable**, porque cada ejercicio
   nuevo deja un ESEF fechado. Pero:
   - sin Alemania ni Irlanda en filings.xbrl.org, hoy faltaría el mayor mercado de la
     región;
   - ESAP (julio de 2027) puede resolverlo con una fuente oficial central, aunque falta
     confirmar que tenga API.
4. **Las métricas no son comparables directamente.** IFRS no es US GAAP: la taxonomía,
   las extensiones de cada emisor y las monedas de presentación cambian. Habría que
   hacer un mapeo propio de conceptos IFRS a las métricas de GABI, con su propia versión
   de métricas y sin heredar evidencia (ADR 0008).

## 4. Protocolo del piloto (fijado antes de ejecutarlo)

El piloto **no se ejecuta ahora**. Se autoriza explícitamente cuando se cumplan las
condiciones de la sección 5. Mide cobertura y sesgos; **nunca rentabilidad**, ni para
elegir proveedor.

**Universo**
- Emisores con al menos un informe anual ESEF en el país y el año del piloto, con su
  LEI.
- La muestra se estratifica por país, tamaño (capitalización en EUR al cierre del
  ejercicio, con los tipos del BCE) y sector, con un máximo de 300 emisores.
- Incluye a los emisores que dejaron de presentar, para medir ausencias y no ocultarlas.

**Medidas por emisor y año**
1. **Identidad:** del LEI al ISIN, al FIGI y a la cotización principal (OpenFIGI). Se
   registran las clases de acciones y las cotizaciones múltiples.
2. **Fundamentales:** cobertura de los conceptos IFRS necesarios para las métricas de
   valor y calidad (ingresos, resultado operativo, resultado neto, flujo de explotación,
   capex, deuda, caja y patrimonio) en los estados primarios, con la fecha de
   publicación.
3. **Precios:** serie diaria con la base declarada (nominal o ajustada), en la moneda de
   cotización y convertida a EUR, y presencia de splits y dividendos.
4. **Ausencias:** cada hueco se clasifica (fuente sin el país, filing excluido, concepto
   no etiquetado, ticker sin precio…). Nada se imputa.

**Umbrales go/no-go por región**, fijados hoy. Deben cumplirse todos:

| Medida | Umbral |
|---|---|
| Emisores con identidad única LEI → cotización | ≥ 95 % |
| Emisores con todos los conceptos de los estados primarios del año | ≥ 80 % |
| Emisores con precio diario verificado del año completo | ≥ 90 % |
| Países con OAM accesible de forma automatizable | todos los incluidos; un país sin acceso queda fuera y se declara |
| Cuota y licencia | coste monetario cero y términos oficiales verificados por escrito para cada fuente usada |

Si alguna región no cumple, **queda fuera de la selección** y se explica la causa. No
se relajan los umbrales después de medir.

**Validación del software del piloto:** fixtures temporales para el mapeo
LEI/ISIN/FIGI, clases de acciones, monedas de presentación y de cotización, y
conceptos IFRS. Sin descargas en los tests.

## 5. Decisión go/no-go actual

| Región | Histórico sin supervivencia | Prospectivo |
|---|---|---|
| EE. UU. fuera del S&P 500 | Pendiente de las conclusiones públicas de #44 (congelación como tarde el 2027-01-15) | Se decide con #44 |
| Europa | **No-go** con datos gratuitos: sin XBRL antes de 2020, sin composición histórica y sin deslistados acreditables | **Aplazado**: piloto cuando ESAP abra (julio de 2027) y se confirme su acceso automatizado, o antes solo con los países que cubre filings.xbrl.org, declarando las ausencias de Alemania e Irlanda |

Hasta entonces, la selección de GABI sigue limitada al S&P 500. Ninguna ampliación se
presenta como evidencia fuera de muestra por el mero cambio de geografía.

## Fuentes consultadas (2026-11-02)

- [filings.xbrl.org: Acerca de](https://filings.xbrl.org/about.html) y [documentación de la API](https://filings.xbrl.org/docs/api).
- [XBRL International: origen y acceso de los filings ESEF](https://www.xbrl.org/news/well-over-3000-esef-filings-at-filings-xbrl-org-where-are-they-coming-from-and-how-can-we-improve-access/).
- [ESMA: European Single Access Point](https://www.esma.europa.eu/node/223341), [Société Générale: apertura el 10-7-2027](https://www.securities-services.societegenerale.com/en/insights/views/news/esap-the-platform-will-open-on-10-july-2027/) y [CONSOB, 9-7-2026](https://www.consob.it/web/consob-and-its-activities/w/press-release-of-9-july-2026).
- ESEF, alcance y fases: [CNMV/ESMA](https://cnmv.es/DocPortal/OtrosDocumentos/ESEF_ESMA.pdf), [AFM](https://www.afm.nl/en/sector/effectenuitgevende-ondernemingen/financiele-en-duurzaamheidsverslaggeving/jaarlijkse-verslaggeving-in-esef) y [Forvis Mazars](https://www.forvismazars.com/ro/en/insights/blog/business-insights/fresh-2022-news-on-esef-reporting).
- [OpenFIGI: documentación de la API](https://www.openfigi.com/api/documentation).
- [BCE: política de reutilización de estadísticas](https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html), [aviso legal](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html) y [API de datos](https://data.ecb.europa.eu/help/api/data).
- Stooq, solo fuentes secundarias: [Wealth-Lab](https://www2.wealth-lab.com/WL5Wiki/StooqProvider.ashx) y [foro de Fund Manager, abril de 2026](https://fundmanagersoftware.com/forum/viewtopic.php?p=28752).
