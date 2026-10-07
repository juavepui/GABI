"""Original event/checkpoint policy with explicit time and previous state."""

import re


def validate_status(status: str) -> None:
    if status not in {"new", "revised", "unchanged", "failed"}:
        raise ValueError("Estado de sincronización desconocido.")


def event_checkpoint(source: str, entity: str, dataset: str, previous: dict, now: str, *,
                     status: str, calls: int, payload_bytes: int, seconds: float, cpu_seconds: float,
                     state: dict | None = None, new: int = 0, revised: int = 0, unchanged: int = 0,
                     reason: str = "", skipped: bool = False) -> tuple[dict, dict]:
    validate_status(status)
    reason = re.sub(r"(?i)(api_key|token)=([^&\s]+)", r"\1=<redacted>", reason)
    event = {"source": source, "entity": entity, "dataset": dataset, "at": now,
             "status": status, "new": new, "revised": revised, "unchanged": unchanged,
             "calls": calls, "payload_bytes": payload_bytes,
             "seconds": seconds, "cpu_seconds": cpu_seconds,
             "reason": reason, "skipped": skipped}
    checkpoint = {**previous, **(state or {}), "status": status, "checked_at": now}
    if previous.get("watermark") and checkpoint.get("watermark"):
        checkpoint["watermark"] = max(previous["watermark"], checkpoint["watermark"])
    if status != "failed" and not skipped:
        checkpoint["last_success"] = now
    if status == "failed":
        # An error must never advance the successful watermark or validation token.
        checkpoint = {**previous, "status": status, "checked_at": now, "error": reason}
    return event, checkpoint
