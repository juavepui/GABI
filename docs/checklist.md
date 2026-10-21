# Checklist fundamental descriptivo (#167)

La ficha de empresa (`/mercado/empresas/{símbolo}`) muestra la sección
**Checklist fundamental**. Evalúa la empresa frente a los criterios del checklist
del usuario, extraídos de vídeos de análisis fundamental (Javier DV, Memorias de
Tiburón, Pedro Gutiérrez y La Pizarra de Andrés), con veredicto ✔/✘/sin dato,
fórmula, fuente y ejercicio usado. Además muestra las señales de alarma, un DCF
inverso y los criterios cualitativos.

Es **informativo**. No entra en el Composite Score, no filtra ni selecciona en el
ranking ni en backtests, y no modifica `scoring.py` ni los 18 motores congelados.
Usar cualquiera de sus criterios como señal requiere un experimento preregistrado.

## Código

| Capa | Archivo |
| --- | --- |
| Dominio (fórmulas, umbrales, alarmas, DCF) | `backend/src/gabi/domain/market/checklist.py` |
| Caso de uso | `backend/src/gabi/application/market/checklist.py` |
| Umbrales editados | `backend/src/gabi/infrastructure/storage/checklist_thresholds.py` → `data/checklist_thresholds.json` |
| API | `GET /api/v1/companies/{symbol}/checklist`, `GET/POST /api/v1/checklist/thresholds`, `POST /api/v1/checklist/thresholds/reset` |
| Interfaz | `frontend/src/features/market/company-checklist.tsx` |

## Reglas de datos

- **Fuente**: hechos SEC de 10-K/10-K/A ya guardados, con `filed_date ≤ hoy`.
  Las excepciones se declaran por criterio:
  - precio: último cierre de la caché;
  - acciones: último hecho SEC presentado, ajustado por splits posteriores;
  - PER forward y beta: registro de Yahoo ya descargado;
  - % de directivos: Yahoo `heldPercentInsiders`, todavía no capturado (F3).
- **Un solo ejercicio**: todos los componentes de un ratio se leen en el último
  cierre anual de ingresos (o de beneficio), con una tolerancia de 45 días. Si un
  componente es de otro ejercicio, el criterio queda «sin dato» (`stale_*`).
- **Ausencia ≠ cero**: una partida no declarada nunca se rellena con cero.
  - Sin deuda declarada, la deuda neta queda sin dato (`no_debt_reported`).
  - Si faltan componentes a corto plazo (deuda a corto, inversiones a corto), se
    listan en `components_not_reported`.
  - La cobertura de intereses cumple solo si la deuda declarada es 0.
- **Sector financiero** (`Financials`/`Financial Services`): los criterios basados
  en margen bruto, CFO, CAPEX, EBITDA o EV se marcan «no aplica».
- **Consultar no descarga ni escribe**: el GET solo lee. Editar umbrales es un
  POST explícito.

## Diferencias con las métricas del Composite

| Concepto | Checklist (vídeos) | Composite / Research |
| --- | --- | --- |
| ROIC | EBIT × (1 − tipo efectivo) / (deuda total + patrimonio − caja e inversiones c/p) | Beneficio neto / (patrimonio + deuda LP) |
| Deuda neta y EV | Deuda LP + deuda a corto − caja − inversiones a corto | Deuda LP − caja |
| Crecimiento | CAGR a 10 años (o 5) de ingresos y CFO | CAGR a 3 años de ingresos y FCF |
| Conversión de caja | CFO / beneficio neto | `fcf_conversion_mean` es FCF / ingresos (margen de FCF, pese al nombre) |
| DCF inverso | 10 años, 9 % de descuento, 3 % a perpetuidad, sobre la capitalización (hoja del Excel) | `reverse_dcf_growth`: 5 años, 2,5 %, sobre el EV (sin cambios) |
| Método | Umbrales absolutos | Percentiles sectoriales ponderados; momentum pesa un 25 % |

En el factor zoo, ningún factor individual sobrevive a la corrección de Holm. Los
umbrales del Checklist son reglas generales que dependen del sector, no señales
validadas.

## Umbrales

- **Valores por defecto**: los del Excel (`RULES` y `DCF_DEFAULTS` en el dominio,
  versión `THRESHOLDS_VERSION = 1`), con el vídeo de origen de cada uno.
- **Edición**: se hace desde «Editar umbrales» en la ficha y solo se guardan los
  valores que difieren de los del Excel. El backend valida el criterio, el rango,
  que sea un número finito, que los años sean enteros y que el crecimiento a
  perpetuidad sea menor que la tasa de descuento.
- **Fichero no válido**: si `checklist_thresholds.json` está corrupto o tiene otra
  versión, se usan los valores del Excel y la respuesta lo avisa
  (`invalid_saved_thresholds`).
- **Alcance**: los umbrales editados solo cambian el ✔/✘ del Checklist. Los
  parámetros de las alarmas son constantes documentadas del dominio.

## Pendiente (fases de #167)

- **F2**: las fórmulas que dependen de etiquetas aún no sincronizadas
  (`CHECKLIST_TAGS`: intereses, SBC, impuestos, deuda e inversiones a corto,
  goodwill, deterioros, emisión de deuda, dividendos, coste de ventas, activos)
  ya están implementadas y devuelven «sin dato» hasta que una sincronización
  explícita guarde esas etiquetas. Deben ir en una lista separada de
  `TRACKED_TAGS`, y la sincronización debe forzar el reproceso, porque hoy un
  companyfacts sin cambios no se reprocesa.
- **F3**: capturar `heldPercentInsiders` en una lista de campos Yahoo propia de
  infraestructura (`config.py` está congelado).
- **F4**: comparación de múltiplos con la mediana histórica propia y la sectorial.
