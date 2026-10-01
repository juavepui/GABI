"""Aprender in React: metric definitions come from the backend, the single source of their meaning."""

from fastapi.testclient import TestClient

from gabi import config, scoring
from gabi.domain.market.metric_info import METRIC_INFO
from gabi.infrastructure.settings import Settings
from gabi.ui_helpers import METRIC_INFO as STREAMLIT_METRIC_INFO
from gabi_api.bootstrap import create_app


def test_glossary_lists_every_block_metric_and_marks_the_13_that_score():
    with TestClient(create_app(Settings(config.DATA_DIR))) as client:
        response = client.get("/api/v1/learn/metrics")
    assert response.status_code == 200
    body = response.json()
    blocks = {block["block"]: block["metrics"] for block in body["blocks"]}
    assert [block["label"] for block in body["blocks"]] == ["Value", "Quality", "Momentum", "Risk"]
    assert [metric["key"] for metric in blocks["value"]] == scoring.VALUE_METRICS_LOWER_BETTER
    scored = {metric["key"] for metrics in blocks.values() for metric in metrics if metric["scored"]}
    assert scored == {key for keys in scoring.SCORE_METRICS.values() for key in keys} and len(scored) == 13
    assert blocks["value"][0] == {"key": "pe", "label": "PER", "help": METRIC_INFO["pe"]["help"], "scored": True}
    assert body["terms"]["max_drawdown"] == METRIC_INFO["max_drawdown"]["help"]


def test_streamlit_keeps_the_same_metric_info_object():
    assert STREAMLIT_METRIC_INFO is METRIC_INFO
