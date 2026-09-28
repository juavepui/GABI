"""Execute the charts and the real Research Lab interaction without network or real DB."""

from pathlib import Path

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from gabi import block_bootstrap as bb
from gabi import config, research_lab


def test_render_distributions_and_switch_to_paired_excess():
    app = AppTest.from_string('''
import numpy as np
import pandas as pd
from gabi import block_bootstrap as bb, block_bootstrap_ui as ui
values = np.random.default_rng(5).normal(.01, .05, 57)
frame = pd.DataFrame({"strategy": values, "benchmark": values * .7})
audit, draws = bb.analyze_sensitivity(frame, periods_per_year=4, strategy="strategy", n_boot=128)
ui.render(audit, draws, key="test")
''').run(timeout=20)
    assert not app.exception
    assert len(app.get("plotly_chart")) == 1
    assert len(app.dataframe) == 4
    assert "evidencia OOS" in app.warning[0].value
    app.selectbox(key="test_metric").set_value("vs_benchmark/excess_mean").run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 1


def test_nonestimable_sharpe_displays_message_instead_of_histogram():
    app = AppTest.from_string('''
import numpy as np
import pandas as pd
from gabi import block_bootstrap as bb, block_bootstrap_ui as ui
audit, draws = bb.analyze_sensitivity(pd.DataFrame({"strategy": np.full(40, .01)}), periods_per_year=4, n_boot=128)
ui.render(audit, draws, key="constant")
''').run(timeout=20)
    app.selectbox(key="constant_metric").set_value("strategy/sharpe").run()
    assert not app.exception
    assert not app.get("plotly_chart")
    assert "no es estimable" in app.info[0].value


def test_render_temporal_ic_and_spread_without_annualizing_them():
    app = AppTest.from_string('''
import numpy as np
import pandas as pd
from gabi import block_bootstrap as bb, block_bootstrap_ui as ui
frame = pd.DataFrame({"ic": np.linspace(-.1, .15, 57), "q5_menos_q1": np.linspace(-.03, .04, 57)})
audit, draws = bb.analyze_sensitivity(frame, periods_per_year=4, means=True, n_boot=128)
ui.render(audit, draws, key="means")
''').run(timeout=20)
    assert not app.exception
    assert len(app.get("plotly_chart")) == 1
    assert not set(app.dataframe[0].value["Métrica"]) - {"Media temporal"}
    app.selectbox(key="means_metric").set_value("q5_menos_q1").run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 1


def test_research_lab_runs_paired_diagnostic_and_rejects_misaligned_benchmark(tmp_path, monkeypatch):
    # Keep all saved audit panels out of this integration test.
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(bb, "OUTPUT", tmp_path / "bootstrap")
    values = np.random.default_rng(8).normal(.01, .05, 40)
    dates = pd.date_range("2010-01-01", periods=40, freq="QS")
    ids = []
    for name, index in (("bad_benchmark", dates + pd.DateOffset(months=3)), ("benchmark", dates), ("strategy", dates)):
        ids.append(research_lab.log_experiment(name, "RESEARCH", False, git_commit="test", family="test",
                                               returns=pd.Series(values, index=index), periods_per_year=4))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/pages/11_Research_Lab.py"))
    app.run(timeout=30)
    assert not app.exception
    app.selectbox(key="bb_benchmark").set_value(f"#{ids[1]} · benchmark").run()
    app.button(key="bb_calculate").click().run(timeout=30)
    assert not app.exception
    assert len(app.get("plotly_chart")) == 1
    app.selectbox(key="bb_benchmark").set_value(f"#{ids[0]} · bad_benchmark").run()
    app.button(key="bb_calculate").click().run(timeout=30)
    assert not app.exception
    assert any("no está alineado" in item.value for item in app.warning)
    assert not app.get("plotly_chart")
