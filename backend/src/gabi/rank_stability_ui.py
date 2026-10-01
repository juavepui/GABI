"""Display fragility without changing a score, eligibility or portfolio."""

import pandas as pd
import streamlit as st

from . import rank_stability


def render(frame: pd.DataFrame, weights: dict, *, mode: str) -> None:
    with st.expander("Estabilidad del ranking · cambios de 1–2 puntos en los pesos"):
        try:
            summary, metrics, companies = rank_stability.analyze(frame, weights)
        except ValueError as exc:
            st.info(f"Estabilidad no disponible: {exc}")
            return
        score = summary["stability_score"]
        if score is not None:
            st.metric("Integrantes del Top-20 que permanecen (media)", f"{score:.1f}%")
        else:
            st.info("El universo elegible es demasiado pequeño para evaluar cambios del Top-20.")
        st.caption(f"{summary['eligible']} empresas elegibles antes de filtros · {summary['perturbations']} perturbaciones "
                   f"· {summary['omitted_infeasible']} omitidas por pesos en el límite.")
        st.caption("Persistencia = fracción de estos cambios que conserva la empresa en el Top-20. "
                   "Describe fragilidad del ranking; no es probabilidad de ganar ni evidencia de rentabilidad futura. "
                   "El score y la cobertura de datos se mantienen separados.")
        if not summary["sectors_complete"]:
            st.caption("Concentración sectorial incompleta: no se rellenan sectores desconocidos.")
        if mode == "INVESTOR":
            selected = companies[companies.base_rank <= 20].copy()
            cols = [c for c in ("base_rank", "rank_min", "rank_max", "top20_inclusion", "diagnosis") if c in selected]
            st.dataframe(selected[cols].rename(columns={"base_rank": "Posición", "rank_min": "Mejor posición",
                                                       "rank_max": "Peor posición", "top20_inclusion": "Persistencia Top-20",
                                                       "diagnosis": "Diagnóstico"}), width="stretch")
        else:
            st.caption("Research: diagnóstico de los pesos actuales, incluidos los experimentales; no se elige una variante por retorno.")
            st.dataframe(companies, width="stretch")
            st.dataframe(metrics, width="stretch")
            st.dataframe(rank_stability.perturbations(weights), width="stretch")
            st.download_button("Descargar dispersión por empresa", companies.to_csv(), "rank-stability.csv", "text/csv")

