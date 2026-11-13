"""Publish a supplied prospective plan only on an explicit command."""

from typing import Protocol

from gabi.domain.research.prospective_plan import plan_hash


class PlanWriter(Protocol):
    def save(self, name: str, payload: dict) -> None: ...


def publish_plan(record: dict, writer: PlanWriter, *, name: str) -> dict:
    payload = {"sha256": plan_hash(record), "plan": record}
    writer.save(name, payload)
    return payload
