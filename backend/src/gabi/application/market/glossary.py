"""The Aprender metric glossary: each block's metrics, whether they score, and their plain-language help."""

from gabi.domain.market.metric_info import METRIC_INFO

BLOCK_LABELS = {"value": "Value", "quality": "Quality", "momentum": "Momentum", "risk": "Risk"}


def metric_glossary(blocks: dict[str, list[str]], scored: dict[str, list[str]]) -> list[dict]:
    """The old page listed every metric of each block; marking the 13 that score keeps the Composite honest."""
    return [{"block": block, "label": BLOCK_LABELS[block],
             "metrics": [{"key": key, "label": METRIC_INFO[key]["label"], "help": METRIC_INFO[key]["help"],
                          "scored": key in scored.get(block, [])} for key in keys if key in METRIC_INFO]}
            for block, keys in blocks.items()]


def terms(keys: tuple[str, ...] = ("pe", "ev_ebitda", "volatility", "max_drawdown")) -> dict[str, str]:
    """Glossary terms whose definition is the metric help itself (PER, EV/EBITDA, volatility, drawdown)."""
    return {key: METRIC_INFO[key]["help"] for key in keys}
