"""Detecta cambios relevantes entre el ranking en vivo y el último snapshot
guardado (evaluation.ranking_snapshots), sin confundir ruido diario con una
señal nueva -- convierte GABI de herramienta que se consulta a mano en una
que también puede avisar de qué cambió.

Ningún evento de este módulo es una recomendación de compra/venta: es un
diagnóstico de qué se movió desde la última foto guardada, nada más -- la
decisión sigue siendo de 🧭 Decisiones de cartera (o del propio usuario).

`compare_snapshots` es una función pura (sin red, sin base de datos) para
que sea trivialmente determinista y testeable; `record_events`/`list_events`
son la capa de persistencia; `run_comparison` orquesta ambas para la UI."""
import json
from datetime import UTC, datetime

import pandas as pd

from . import evaluation, scoring, storage

SEVERITIES = ("INFO", "WATCH", "MATERIAL")

# Configurables: se pueden sobrescribir por llamada (compare_snapshots) o
# desde la UI -- pensados para evitar avisos por ruido normal día a día.
DEFAULT_THRESHOLDS = {
    "rank_change": 5,         # posiciones de diferencia en el ranking
    "score_change": 10.0,     # puntos de composite_score (escala 0-100)
    "confidence_drop": 20.0,  # puntos de caída de confidence (escala 0-100)
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at TEXT NOT NULL,
    from_snapshot_id INTEGER,
    to_snapshot_id INTEGER,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    previous_value TEXT,
    new_value TEXT,
    cause TEXT NOT NULL,
    UNIQUE(from_snapshot_id, to_snapshot_id, symbol, event_type)
);
CREATE INDEX IF NOT EXISTS idx_signal_events_detected ON signal_events (detected_at);
"""


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


_NO_SNAPSHOT = 0  # sentinel para from/to_snapshot_id=None: SQLite trata NULL != NULL en UNIQUE, así que NULL rompería la deduplicación


def record_events(events: list[dict], from_snapshot_id: int | None, to_snapshot_id: int | None):
    """Persiste eventos ya calculados por compare_snapshots. Idempotente:
    repetir la misma comparación (mismo from/to/symbol/event_type) no
    duplica filas -- lo garantiza el UNIQUE de signal_events, no lógica de
    aplicación, así que es correcto aunque se llame varias veces seguidas."""
    if not events:
        return
    detected_at = datetime.now(UTC).isoformat()
    from_id = from_snapshot_id if from_snapshot_id is not None else _NO_SNAPSHOT
    to_id = to_snapshot_id if to_snapshot_id is not None else _NO_SNAPSHOT
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR IGNORE INTO signal_events (detected_at, from_snapshot_id, to_snapshot_id, symbol, "
            "event_type, severity, previous_value, new_value, cause) VALUES (?,?,?,?,?,?,?,?,?)",
            [(detected_at, from_id, to_id, e["symbol"], e["event_type"], e["severity"],
              json.dumps(e["previous_value"]), json.dumps(e["new_value"]), e["cause"])
             for e in events],
        )
        conn.commit()


def list_events(severity: str = None, since_hours: float = None, limit: int = 200) -> pd.DataFrame:
    query = "SELECT * FROM signal_events"
    conditions: list[str] = []
    params: list = []
    if severity:
        conditions.append("severity = ?")
        params.append(severity)
    if since_hours is not None:
        cutoff = (datetime.now(UTC) - pd.Timedelta(hours=since_hours)).isoformat()
        conditions.append("detected_at >= ?")
        params.append(cutoff)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY detected_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        df = pd.read_sql_query(query, conn, params=params)
    if not df.empty:
        df["previous_value"] = df["previous_value"].map(lambda v: json.loads(v) if v is not None else None)
        df["new_value"] = df["new_value"].map(lambda v: json.loads(v) if v is not None else None)
        for col in ("from_snapshot_id", "to_snapshot_id"):
            df[col] = df[col].replace(_NO_SNAPSHOT, None)
    return df


class Notifier:
    """Interfaz desacoplada del motor de señales: cualquier notificador
    (in-app, email, Telegram...) implementa notify(event) y no necesita
    tocar compare_snapshots/run_comparison. Solo existe InAppNotifier por
    ahora, pero añadir otro no requiere cambiar el motor de detección."""

    def notify(self, event: dict) -> None:
        raise NotImplementedError


class InAppNotifier(Notifier):
    """La UI (📡 Signal Monitor) lee signal_events directamente -- "notificar
    en la propia app" es simplemente que el evento ya quedó persistido, así
    que este notificador no tiene nada más que hacer. Existe para que
    run_comparison siempre tenga al menos un notificador por defecto y para
    dejar explícito el punto de extensión del objetivo (email/Telegram/etc.)."""

    def notify(self, event: dict) -> None:
        pass


def run_comparison(*, snapshot_id: int | None = None, top_n: int | None = None,
                   weights: dict | None = None, thresholds: dict | None = None,
                   notifiers: list[Notifier] | None = None) -> dict:
    """Calcula el ranking en vivo (solo datos ya cacheados, sin red -- igual
    que 📊 Screener), lo compara contra el snapshot indicado (o el más
    reciente guardado si no se indica ninguno), persiste los eventos y
    notifica a `notifiers` (por defecto, [InAppNotifier()]).

    Devuelve {"events": [...], "snapshot_id": int|None, "reason": str|None}
    -- `reason` explica por qué no hay comparación posible (sin snapshot
    guardado todavía, por ejemplo) en vez de fallar."""
    from . import (
        screener,  # import diferido: evita acoplar el motor de señales al pipeline completo del screener en import time
    )

    snapshot_id = snapshot_id if snapshot_id is not None else evaluation.latest_snapshot_id()
    if snapshot_id is None:
        return {"events": [], "snapshot_id": None, "reason": "No hay ningún snapshot guardado todavía en 📊 Screener."}
    previous = evaluation.get_snapshot_table(snapshot_id)
    if previous.empty:
        return {"events": [], "snapshot_id": snapshot_id, "reason": "El snapshot elegido está vacío."}

    top_n = top_n or len(previous)
    uni = screener.get_universe(limit=None)
    current_full = screener.build_screener_table(uni, weights=weights or scoring.DEFAULT_WEIGHTS)
    current = current_full[current_full["composite_score"].notna()].copy()
    current["rank"] = range(1, len(current) + 1)

    events = compare_snapshots(previous, current, top_n, thresholds)
    record_events(events, snapshot_id, None)
    for notifier in notifiers or [InAppNotifier()]:
        for event in events:
            notifier.notify(event)
    return {"events": events, "snapshot_id": snapshot_id, "reason": None,
            "compared_at": datetime.now(UTC).isoformat()}
