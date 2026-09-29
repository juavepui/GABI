"""Genera un prompt estructurado para pegar en el asistente de IA que
prefiera el usuario (Claude, ChatGPT...). GABI no llama a ninguna API de IA
por sí misma — solo construye el texto.

Regla de diseño explícita (pedida por el usuario): la IA nunca calcula
métricas financieras. Los números que aparecen en el prompt salen siempre de
código determinista (metrics.py, technicals.py, edgar.py, scoring.py) sobre
datos ya descargados; a la IA se le pide interpretar esos números y los
documentos fuente, no recalcularlos ni inventar otros nuevos. Esto reduce
mucho el riesgo de alucinaciones frente a pedirle directamente una predicción
de precio."""
import pandas as pd

from .ui_helpers import METRIC_INFO, format_metric_value

EXTRACTION_POINTS = [
    "Cambios en el guidance (frente al trimestre/año anterior)",
    "Cambios en márgenes (bruto, operativo) y su causa",
    "Principales riesgos mencionados por la propia empresa",
    "Catalizadores concretos a 6-12 meses",
    "Comentarios de la dirección sobre demanda",
    "CAPEX: nivel, tendencia y hacia qué se dirige",
    "Competencia: cómo describen su posición relativa",
    "Pricing power: ¿pueden subir precios sin perder clientes?",
    "Problemas regulatorios abiertos o potenciales",
    "Cambios de estrategia recientes",
]


def _scores_block(row: pd.Series) -> str:
    if "composite_score" not in row.index or pd.isna(row.get("composite_score")):
        return "(scores no disponibles todavía — actualiza datos en ⚙️ Configuración)"
    return (
        f"- Composite: {row['composite_score']:.1f}/100\n"
        f"- Value: {row['value_score']:.1f}/100\n"
        f"- Quality: {row['quality_score']:.1f}/100\n"
        f"- Momentum: {row['momentum_score']:.1f}/100"
    )


def _metrics_table(breakdown: pd.DataFrame) -> str:
    if breakdown is None or breakdown.empty:
        return "(sin métricas calculadas todavía — actualiza datos en ⚙️ Configuración)"
    lines = ["| Métrica | Valor | Percentil (vs. sector) |", "|---|---|---|"]
    for _, r in breakdown.iterrows():
        if pd.isna(r.get("value")):
            continue
        label = METRIC_INFO.get(r["metric"], {}).get("label", r["metric"])
        value = format_metric_value(r["metric"], r["value"])
        pct = f"{r['percentile']:.0f}/100" if pd.notna(r.get("percentile")) else "—"
        lines.append(f"| {label} | {value} | {pct} |")
    if len(lines) == 2:
        return "(sin métricas calculadas todavía — actualiza datos en ⚙️ Configuración)"
    return "\n".join(lines)


def _filings_block(row: pd.Series) -> str:
    lines = []
    if pd.notna(row.get("latest_10k_url")):
        lines.append(f"- Último 10-K ({row.get('latest_10k_date')}): {row['latest_10k_url']}")
    if pd.notna(row.get("latest_10q_url")):
        lines.append(f"- Último 10-Q ({row.get('latest_10q_date')}): {row['latest_10q_url']}")
    if not lines:
        lines.append("- (sin enlaces todavía — actualiza datos en ⚙️ Configuración)")
    return "\n".join(lines)


def build_analysis_prompt(row: pd.Series, breakdown: pd.DataFrame, symbol: str) -> str:
    """row: fila de screener.build_screener_table() para `symbol`.
    breakdown: scoring.explain_row(df, symbol) (columnas metric/value/percentile)."""
    name = row.get("name") or symbol
    sector = row.get("sector") or "desconocido"
    extraction_list = "\n".join(f"{i + 1}. {point}" for i, point in enumerate(EXTRACTION_POINTS))

    return f"""Eres un analista financiero. Te doy el contexto cuantitativo de {name} ({symbol}, sector {sector}) que YA HE CALCULADO con código determinista (percentiles frente a otras empresas del mismo sector). No recalcules estos números ni inventes otros nuevos: si te falta un dato para razonar, dilo explícitamente en vez de estimarlo. Tu trabajo es interpretar estos números y los documentos fuente que te paso, no calcular métricas financieras.

NO me digas simplemente si crees que la acción "va a subir". Ayúdame a construir un marco de decisión.

## Scores ya calculados (0-100, percentil frente a su sector)
{_scores_block(row)}

## Métricas detalladas ya calculadas
{_metrics_table(breakdown)}

## Documentos fuente
{_filings_block(row)}
- [ ] Transcripción de la última earnings call (pégala aquí si la tienes)
- [ ] Guidance / rueda de prensa de resultados más reciente (pégala aquí)
- [ ] Noticias relevantes de las últimas semanas (pégalas aquí)

## Qué quiero que extraigas de esos documentos
{extraction_list}

## Qué quiero que generes al final

**Tesis alcista** — qué tendría que ser cierto para que esta inversión funcione (ej. margen FCF en expansión + revisiones de EPS al alza + crecimiento de demanda + valoración razonable frente al sector).

**Tesis bajista** — qué tendría que ser cierto para que NO funcione (ej. expansión de múltiplos excesiva + desaceleración del crecimiento + CAPEX elevado sin retorno claro).

**Qué invalidaría la inversión** — condiciones concretas y medibles (ej. "margen bruto por debajo de X%" o "crecimiento de ingresos por debajo de Y%"). Usa las métricas de arriba como referencia para fijar X e Y de forma razonada, explicando tu razonamiento.

Regla importante: cualquier cifra financiera que cites debe ser una de las que te he dado arriba, o una que saques literalmente de los documentos fuente que te pegue — nunca una cifra inventada o estimada de memoria."""
