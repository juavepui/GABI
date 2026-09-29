"""Published Factor Zoo evidence and its dated SIC diagnostic; read-only UI."""

import pandas as pd
import streamlit as st

from . import evidence_catalog, factor_sector_stability
from .ui_helpers import METRIC_INFO


def render() -> None:
    st.subheader("Mapa de evidencia por factor · #48")
    st.caption("13 señales declaradas y 57 trimestres congelados de 2011–2025. Evidencia retrospectiva; "
               "los diagnósticos por industria no seleccionan pesos ni aportan validación independiente.")
    catalogue = evidence_catalog.load()
    factors = catalogue.get("factors", {})
    if not catalogue["available"] or not factors:
        st.warning("No se puede verificar el mapa de evidencia publicado.")
        for error in catalogue["errors"]:
            st.write(error)
        return
    primary = pd.DataFrame([{"Factor": METRIC_INFO.get(metric, {}).get("label", metric),
                             "IC medio": data.get("media"), "ICIR": data.get("icir"),
                             "p Holm": data.get("p_holm"), "Clasificación": data.get("classification"),
                             "Trimestres": data.get("n_periods"), "Spread Q5−Q1": data.get("q_spread")}
                            for metric, data in factors.items()])
    st.dataframe(primary, hide_index=True, width="stretch")
    st.caption("El contraste principal conserva HAC y Holm de las 13 señales. Ninguna supera Holm al 5 %.")
    source = catalogue.get("sources", {}).get("factor-zoo-sector")
    if source is None:
        st.info("Diagnóstico SIC fechado aún no publicado.")
        return
    try:
        result = factor_sector_stability.load_saved(source["sha256"])
    except (OSError, ValueError, KeyError) as exc:
        st.warning(f"Diagnóstico SIC no verificable: {exc}")
        return
    st.write("**Estabilidad por industria SIC fechada**")
    st.caption("Clasificación SEC conocida antes de cada señal, en divisiones SIC amplias. SIC y GICS son "
               "clasificaciones distintas. IC descriptivo con ≥30 pares por trimestre; el resumen necesita "
               "≥30 trimestres. No se calculan nuevos p-valores ni se cambia la confianza de evidencia.")
    coverage = pd.DataFrame(result["coverage"])
    all_dates = coverage.loc[coverage.stratum == "all"]
    eligible = int(all_dates.n_eligible.sum())
    classified = int(all_dates.n_classified.sum())
    st.metric("Cobertura de industria · empresa/fecha", f"{classified / eligible:.1%}" if eligible else "No estimable")
    st.caption(f"{classified:,} de {eligible:,} observaciones elegibles, incluidas las que no tienen retorno futuro.")
    metric = st.selectbox("Señal · estabilidad por industria", list(result["factors"]), key="sic_factor",
                          format_func=lambda m: METRIC_INFO.get(m, {}).get("label", m))
    rows = []
    for division, data in result["factors"][metric].items():
        rows.append({"División SIC": division, "Industria": data["name"], "IC medio": data["ic_mean"],
                     "ICIR": data["icir"], "Trimestres estimables": data["n_periods"],
                     "% IC positivo": data["positive_fraction"],
                     "Soporte temporal": "Suficiente" if data["status"] == "sufficient_periods" else "Insuficiente",
                     **{f"IC {name}": values["ic_mean"] for name, values in data["windows"].items()}})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.expander("Cobertura y periodos no estimables · SIC"):
        st.dataframe(coverage.drop(columns="reasons"), hide_index=True, width="stretch")
        st.caption("Las categorías sin muestra y las fechas sin IC se conservan en el artefacto, sin agruparlas ni imputarlas.")
        for name, label in (("sector_ic.csv", "IC por industria y trimestre"),
                            ("coverage.csv", "Cobertura y exclusiones"), ("factor_coverage.csv", "Cobertura por señal")):
            st.download_button(f"Descargar {label}", (factor_sector_stability.OUTPUT / name).read_text(encoding="utf-8"),
                               name, "text/csv", key="sic_" + name)
