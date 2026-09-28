"""Read-only ledger inspection and explicit append-only evaluation exports."""

import pandas as pd
import streamlit as st

from . import live_ledger, live_performance


def render() -> None:
    with st.expander("Registro prospectivo · decisiones congeladas y resultados posteriores"):
        try:
            integrity = live_ledger.verify_integrity()
            if not integrity["ok"]:
                st.error(f"Ledger no íntegro: {integrity['reason']}")
                return
            events = live_ledger.events()
            decisions = [e for e in events if e["payload"]["kind"] == "DECISION"]
            if not decisions:
                st.info("Aún no hay decisiones prospectivas. Las registrará la tarea periódica local.")
                return
            st.caption(f"Cadena y ancla verificadas · {integrity['seq']} eventos. "
                       "LIVE_FORWARD describe cuándo se guardó la señal; no acredita validación independiente.")
            st.dataframe(pd.DataFrame([{ "Evento": e["seq"], "Fase": e["payload"]["stage"],
                                        "Fecha": e["payload"]["market_date"], "Estado": e["payload"]["status"],
                                        "Candidatas": len(e["payload"]["top_n"]), "Commit": e["payload"].get("git_commit")}
                                       for e in decisions]), hide_index=True, width="stretch")
            selected = st.selectbox("Decisión guardada", [e["seq"] for e in decisions], key="ledger_event")
            frozen = next(e for e in decisions if e["seq"] == selected)
            st.json(frozen)
            if frozen["payload"].get("inputs"):
                replay = live_ledger.reproduce_decision(selected)
                if all(replay[k] for k in ("fingerprint_matches", "scores_match", "ranking_matches")):
                    st.caption("Entradas, scores y ranking reproducidos desde el registro congelado.")
                else:
                    st.error("La reproducción de las entradas guardadas no coincide; revisar el evento.")
            versions = sorted({e["payload"]["model_version"] for e in decisions if e["payload"]["stage"] == "LIVE_FORWARD"})
            if not versions:
                st.info("Los registros históricos/OOS no se incluyen en la performance LIVE_FORWARD.")
                return
            version = st.selectbox("Versión de modelo del reporte", versions, key="ledger_model", format_func=lambda v: v[:12])
            report = live_performance.report(model_version=version)
            if report["cumulative_return"] is not None:
                st.metric("Cartera ilustrativa prospectiva · retorno acumulado neto", f"{report['cumulative_return']:.2%}")
                if report["benchmark_return"] is not None:
                    st.metric("SPY · mismo intervalo y coste inicial", f"{report['benchmark_return']:.2%}")
                else:
                    st.info("SPY no disponible para comparar este intervalo.")
            else:
                st.info("Performance aún pendiente o incompleta; no se eliminan empresas sin precio.")
            st.caption("Primera decisión de cada sesión de entrada, incluso sin señal; apertura posterior al registro. "
                       "Cartera equiponderada con 10 pb/lado sobre lo negociado, separada de los backtests y de la prueba ciega.")
            st.dataframe(pd.DataFrame(report["intervals"]), hide_index=True, width="stretch")
            st.download_button("Descargar reporte prospectivo", live_ledger.canonical(report), "live-forward.json", "application/json")
            if st.button("Guardar evaluación como evento nuevo", key="ledger_save_evaluation"):
                saved = live_ledger.save_evaluation(report)
                st.success(f"Evaluación #{saved['seq']} añadida; señales originales conservadas.")
        except (OSError, ValueError, KeyError) as exc:
            st.warning(f"Registro prospectivo no disponible: {exc}")
