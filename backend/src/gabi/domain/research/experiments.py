"""Research Lab stages, shared by the legacy logger and the new readers."""

STAGES = ["RESEARCH", "IN_SAMPLE", "OUT_OF_SAMPLE", "LIVE_FORWARD"]

STAGE_INFO = {
    "RESEARCH": {"emoji": "🔬", "label": "Research", "help": "Fase de exploración: se prueban ideas y configuraciones. Un buen resultado aquí es solo un candidato."},
    "IN_SAMPLE": {"emoji": "📊", "label": "In-sample", "help": "Resultado con los mismos datos que se usaron para diseñar la idea: es normal que salga bien, así que no demuestra nada."},
    "OUT_OF_SAMPLE": {"emoji": "🧪", "label": "Out-of-sample", "help": "Resultado con datos que NO se miraron al diseñar la idea: si sale bien aquí, es un indicio serio."},
    "LIVE_FORWARD": {"emoji": "🚀", "label": "Live forward", "help": "Seguimiento real con datos nuevos, desde que se fijaron las reglas: la prueba más fiable, porque no se pudo ajustar nada."},
}

# Better is higher for all three: max_drawdown is stored as a negative fraction, so closer to zero is better.
RANKED_METRICS = {"sharpe": "higher", "sortino": "higher", "max_drawdown": "higher"}
