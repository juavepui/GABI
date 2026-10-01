"""Research Lab stages, shared by the legacy logger and the new readers."""

STAGES = ["RESEARCH", "IN_SAMPLE", "OUT_OF_SAMPLE", "LIVE_FORWARD"]

STAGE_INFO = {
    "RESEARCH": {"emoji": "🔬", "label": "Research", "help": "Explorando/probando configuraciones -- la mayoría del trabajo de investigación."},
    "IN_SAMPLE": {"emoji": "📊", "label": "In-sample", "help": "Resultado sobre el rango de datos usado para diseñar la hipótesis."},
    "OUT_OF_SAMPLE": {"emoji": "🧪", "label": "Out-of-sample", "help": "Resultado sobre datos que NO se miraron al diseñar la hipótesis."},
    "LIVE_FORWARD": {"emoji": "🚀", "label": "Live forward", "help": "Seguimiento real desde hoy, sin margen para haber influido en el diseño."},
}
