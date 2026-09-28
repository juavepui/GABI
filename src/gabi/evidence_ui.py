"""Candidate confidence with visible components and reasons, in both app modes."""

import pandas as pd
import streamlit as st

from . import evidence_confidence
from .ui_helpers import METRIC_INFO


def render(frame: pd.DataFrame, weights: dict, *, mode="INVESTOR", symbol: str | None = None) -> None:
    evidence = evidence_confidence.build(frame, weights)
    if not evidence:
        st.info("Evidencia no disponible: aún no hay candidatas con datos.")
        return
    st.subheader("Evidencia del ranking")
    st.caption("Score = posición según las métricas. Cobertura ponderada = datos disponibles. "
               "Confianza de evidencia = BAJA/MEDIA/ALTA según reglas publicadas; no es probabilidad de subida.")
    ordered = sorted(evidence, key=lambda s: (-(evidence[s]["score"] if evidence[s]["score"] is not None else -1), s))
    selected_symbols = [symbol] if symbol in evidence else [s for s in ordered if evidence[s]["score"] is not None
                                                         and (evidence[s]["score_coverage"] or 0) >= .70][:20]
    if not selected_symbols:
        st.info("No hay empresas elegibles para el Top-20. El diagnóstico de evidencia sigue disponible por empresa.")
    else:
        rows = []
        for candidate in selected_symbols:
            e = evidence[candidate]
            persistence = e["stability"].get("top20_inclusion")
            fraction = e["validated_score_fraction"]
            rows.append({"Empresa": candidate, "Score": e["score"], "Cobertura ponderada": e["weighted_data_coverage"],
                         "Confianza de evidencia": e["confidence_level"],
                         "Persistencia Top-20": f"{persistence:.0%}" if persistence is not None else "No estimable",
                         "Score con apoyo tras Holm": f"{fraction:.1%}" if fraction is not None else "No atribuible"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.expander("Por qué se asigna este nivel de confianza", expanded=symbol is not None):
        candidate = symbol if symbol in evidence else st.selectbox("Candidata · evidencia", selected_symbols or ordered, key="evidence_candidate")
        e = evidence[candidate]
        st.metric("Confianza de evidencia", e["confidence_level"])
        st.write("**A favor**")
        for reason in e["reasons_for"]:
            st.write(f"• {reason}")
        st.write("**En contra y límites**")
        for reason in e["reasons_against"]:
            st.write(f"• {reason}")
        factors = pd.DataFrame([{ "Factor": METRIC_INFO.get(f["metric"], {}).get("label", f["metric"]),
                                  "Familia": f["family"], "Percentil": f["percentile"], "Apoya candidatura": f["supports_candidate"],
                                  "Peso efectivo": f["effective_weight"], "Puntos de score": f["contribution_points"],
                                  "Apoyo tras Holm": f["statistically_supported"], "IC medio": f["mean_ic"], "p Holm": f["p_holm"]}
                                 for f in e["factors"]])
        if not factors.empty:
            st.dataframe(factors, hide_index=True, width="stretch")
        st.caption("Un percentil alto apoya la puntuación descriptiva; la columna de Holm muestra su evidencia estadística. "
                   "La falta de confirmación no demuestra ausencia de efecto. La confianza no cambia el ranking ni sus pesos.")
        st.write(f"Fase del registro: {e['collection_stage']} · evidencia: {e['evidence_stage']} · reglas: {e['rules']['version']}")
        if mode == "RESEARCH":
            st.json({k: e[k] for k in ("predictive_test", "placebos", "bootstrap", "tail", "stability", "quality", "rules", "trace")})
        st.download_button("Descargar evidencia de la candidata", evidence_confidence.live_ledger.canonical(e),
                           f"evidence-{candidate}.json", "application/json", key="evidence_download")
