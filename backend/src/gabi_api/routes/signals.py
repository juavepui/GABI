from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request

from gabi.application.market.signals import SignalMonitor
from gabi.application.market.snapshots import SnapshotTracking
from gabi_api.schemas.signals import (
    CompareSignals,
    EarningsEvent,
    EarningsList,
    FilingCheckSaved,
    SaveFilingCheck,
    SaveSnapshot,
    SignalEvent,
    SignalEventList,
    Snapshot,
    SnapshotList,
    SnapshotProgress,
    SnapshotRename,
    SnapshotRenamed,
)

router = APIRouter(prefix="/api/v1/market", tags=["market"])


def service(request: Request) -> SignalMonitor:
    return request.app.state.signals


def tracking(request: Request) -> SnapshotTracking:
    return request.app.state.snapshot_tracking


Tracking = Annotated[SnapshotTracking, Depends(tracking)]


@router.get("/snapshots/{snapshot_id}/progress", response_model=SnapshotProgress)
def snapshot_progress(snapshot_id: Annotated[int, Path(ge=1, le=1_000_000)], query: Tracking) -> dict:
    return query.progress(snapshot_id)


@router.post("/snapshots/{snapshot_id}/rename", response_model=SnapshotRenamed)
def rename_snapshot(snapshot_id: Annotated[int, Path(ge=1, le=1_000_000)], body: SnapshotRename,
                    query: Tracking) -> dict:
    return query.rename(snapshot_id, body.name)


@router.get("/snapshots", response_model=SnapshotList)
def snapshots(monitor: Annotated[SignalMonitor, Depends(service)]) -> SnapshotList:
    return SnapshotList(items=[Snapshot.model_validate(item) for item in monitor.snapshots()])


@router.post("/snapshots", response_model=Snapshot, status_code=201)
def save_snapshot(body: SaveSnapshot, monitor: Annotated[SignalMonitor, Depends(service)]) -> Snapshot:
    snapshot_id = monitor.save(body.name, body.top_n)
    return next(Snapshot.model_validate(item) for item in monitor.snapshots() if item["id"] == snapshot_id)


@router.get("/signals", response_model=SignalEventList)
def events(monitor: Annotated[SignalMonitor, Depends(service)],
           severity: Literal["INFO", "WATCH", "MATERIAL"] | None = None,
           limit: Annotated[int, Query(ge=1, le=200)] = 100,
           since_hours: Annotated[int | None, Query(ge=1, le=720)] = None) -> SignalEventList:
    return SignalEventList(items=[SignalEvent.model_validate(item)
                                  for item in monitor.events(severity, limit, since_hours)])


@router.post("/signals/compare", response_model=SignalEventList)
def compare(body: CompareSignals, monitor: Annotated[SignalMonitor, Depends(service)]) -> SignalEventList:
    events = monitor.run(body.snapshot_id, body.rank_change, body.score_change, body.confidence_drop)
    status: Literal["DIAGNOSTIC", "EXPERIMENTAL"] = "DIAGNOSTIC" if (body.rank_change, body.score_change, body.confidence_drop) == (5, 10, 20) \
        else "EXPERIMENTAL"
    return SignalEventList(items=[SignalEvent.model_validate(item) for item in events], status=status)


@router.get("/snapshots/{snapshot_id}/earnings", response_model=EarningsList)
def earnings(snapshot_id: Annotated[int, Path(ge=1)],
             monitor: Annotated[SignalMonitor, Depends(service)]) -> EarningsList:
    return EarningsList(items=[EarningsEvent.model_validate(item) for item in monitor.earnings(snapshot_id)])


@router.post("/signals/filings/record", response_model=FilingCheckSaved)
def record_filings(body: SaveFilingCheck, monitor: Annotated[SignalMonitor, Depends(service)]) -> FilingCheckSaved:
    return FilingCheckSaved.model_validate(monitor.save_filings_job(body.job_id))
