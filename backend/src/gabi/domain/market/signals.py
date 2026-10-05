"""Cambios relevantes entre dos rankings (el snapshot guardado y el actual), sin confundir
ruido diario con una señal nueva.

Ningún evento es una recomendación de compra/venta: es un diagnóstico de qué se movió
desde la última foto guardada. La persistencia está en ``infrastructure/storage/signals``.
"""
import pandas as pd

SEVERITIES = ("INFO", "WATCH", "MATERIAL")

# Configurables: se pueden sobrescribir por llamada (compare_snapshots) o
# desde la UI -- pensados para evitar avisos por ruido normal día a día.
DEFAULT_THRESHOLDS = {
    "rank_change": 5,         # posiciones de diferencia en el ranking
    "score_change": 10.0,     # puntos de composite_score (escala 0-100)
    "confidence_drop": 20.0,  # puntos de caída de confidence (escala 0-100)
}


def _event(symbol, event_type, severity, previous_value, new_value, cause) -> dict:
    return {"symbol": symbol, "event_type": event_type, "severity": severity,
            "previous_value": previous_value, "new_value": new_value, "cause": cause}


def compare_snapshots(previous: pd.DataFrame, current: pd.DataFrame, top_n: int,
                      thresholds: dict = None) -> list[dict]:
    """Compara dos tablas indexadas por symbol (columnas esperadas: rank,
    composite_score, confidence, sector -- lo que falte en cualquiera de las
    dos se trata como "sin dato", no como error) y devuelve una lista
    determinista de eventos, ordenada por (symbol, event_type) para que
    ejecutarla dos veces con el mismo input dé exactamente el mismo output.

    `top_n`: cuántas de las primeras filas de cada tabla cuentan como
    Top-N para detectar entrada/salida -- normalmente len(previous), ya que
    evaluation.save_snapshot ya solo guarda top_n filas.

    Eventos y severidad (fijos por tipo; el umbral decide si el evento
    aparece, no de qué severidad es):
    - top_n_entry / top_n_exit -> MATERIAL (cambia la composición del Top-N).
    - score_change -> MATERIAL (cambio material de Composite Score, tal cual
      lo pide el objetivo).
    - rank_change, confidence_drop, sector_change -> WATCH.
    - eligibility_change (deja de tener score calculable) -> INFO."""
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    events = []

    prev_top = set(previous.index[:top_n])
    curr_top = set(current.index[:top_n])

    for symbol in curr_top - prev_top:
        new_rank = None
        if "rank" in current.columns and pd.notna(current.loc[symbol, "rank"]):
            new_rank = int(current.loc[symbol, "rank"])
        events.append(_event(symbol, "top_n_entry", "MATERIAL", None, new_rank,
                             f"Entra en el Top-{top_n} (no estaba en el snapshot anterior)."))
    for symbol in prev_top - curr_top:
        prev_rank = None
        if "rank" in previous.columns and pd.notna(previous.loc[symbol, "rank"]):
            prev_rank = int(previous.loc[symbol, "rank"])
        events.append(_event(symbol, "top_n_exit", "MATERIAL", prev_rank, None,
                             f"Sale del Top-{top_n} (estaba en el snapshot anterior)."))

    for symbol in previous.index.intersection(current.index):
        prev_row, curr_row = previous.loc[symbol], current.loc[symbol]

        if "rank" in previous.columns and "rank" in current.columns:
            prev_rank, curr_rank = prev_row.get("rank"), curr_row.get("rank")
            if pd.notna(prev_rank) and pd.notna(curr_rank) and abs(curr_rank - prev_rank) >= thresholds["rank_change"]:
                events.append(_event(
                    symbol, "rank_change", "WATCH", int(prev_rank), int(curr_rank),
                    f"El rank cambió {int(curr_rank - prev_rank):+d} posiciones "
                    f"(umbral: {thresholds['rank_change']})."))

        if "composite_score" in previous.columns and "composite_score" in current.columns:
            prev_score, curr_score = prev_row.get("composite_score"), curr_row.get("composite_score")
            if pd.notna(prev_score) and pd.isna(curr_score):
                events.append(_event(
                    symbol, "eligibility_change", "INFO", round(float(prev_score), 1), None,
                    "Deja de tener Composite Score calculable (cobertura de datos insuficiente ahora)."))
            elif pd.notna(prev_score) and pd.notna(curr_score) and abs(curr_score - prev_score) >= thresholds["score_change"]:
                events.append(_event(
                    symbol, "score_change", "MATERIAL", round(float(prev_score), 1), round(float(curr_score), 1),
                    f"Composite Score cambió {curr_score - prev_score:+.1f} puntos "
                    f"(umbral: {thresholds['score_change']})."))

        if "confidence" in previous.columns and "confidence" in current.columns:
            prev_conf, curr_conf = prev_row.get("confidence"), curr_row.get("confidence")
            if pd.notna(prev_conf) and pd.notna(curr_conf) and (prev_conf - curr_conf) >= thresholds["confidence_drop"]:
                events.append(_event(
                    symbol, "confidence_drop", "WATCH", round(float(prev_conf), 1), round(float(curr_conf), 1),
                    f"Confidence cayó {curr_conf - prev_conf:+.1f} puntos "
                    f"(umbral: {thresholds['confidence_drop']})."))

        if "sector" in previous.columns and "sector" in current.columns:
            prev_sector, curr_sector = prev_row.get("sector"), curr_row.get("sector")
            if pd.notna(prev_sector) and pd.notna(curr_sector) and prev_sector != curr_sector:
                events.append(_event(
                    symbol, "sector_change", "WATCH", prev_sector, curr_sector,
                    "El sector detectado cambió respecto al snapshot anterior "
                    "(reclasificación GICS o identidad -- ver 🩺 Calidad de los datos)."))

    return sorted(events, key=lambda e: (e["symbol"], e["event_type"]))
