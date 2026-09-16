import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import streamlit as st

from gabi import data_fetch, decision_engine, screener, storage

st.title("🧭 Decisiones de cartera")
st.markdown(
    "GABI elige candidatas, calcula pesos objetivo y decide **comprar, mantener, reducir o vender** "
    "según reglas explícitas. Usa los datos descargados en Configuración. Las decisiones quedan "
    "registradas; esta página no envía órdenes al bróker."
)

with st.expander("Reglas y límites", expanded=True):
    c1, c2, c3 = st.columns(3)
    min_score = c1.slider("Score mínimo", 0, 100, 65)
    min_coverage = c2.slider("Cobertura mínima (%)", 50, 100, 70)
    max_positions = c3.number_input("Máximo de empresas", 1, 30, 10)
    c4, c5, c6 = st.columns(3)
    max_position = c4.slider("Máximo por empresa (%)", 1, 20, 5)
    max_sector = c5.slider("Máximo por sector (%)", 5, 50, 20)
    max_invested = c6.slider("Máximo invertido en acciones (%)", 10, 100, 50)
    st.caption("También exige precio reciente sobre SMA200, volatilidad ≤60 %, drawdown ≥−50 % y 126 sesiones de retornos.")

holdings_text = st.text_area(
    "Posiciones actuales (ticker, porcentaje de la cartera; una por línea)",
    placeholder="AAPL,3\nMSFT,4", height=100,
)
plan_name = st.text_input("Nombre del nuevo plan (opcional)", placeholder="Revisión de septiembre")


def parse_holdings(raw: str) -> dict[str, float]:
    result = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2 or not parts[0]:
            raise ValueError(f"Formato inválido: {line!r}. Usa TICKER,porcentaje.")
        symbol = parts[0].upper()
        if symbol in result:
            raise ValueError(f"Ticker repetido: {symbol}")
        result[symbol] = float(parts[1])
    return result


if st.button("Generar decisiones", type="primary"):
    try:
        holdings = parse_holdings(holdings_text)
        if plan_name and (not plan_name.strip() or len(plan_name.strip()) > 80):
            raise ValueError("El nombre del plan debe tener entre 1 y 80 caracteres.")
        policy = decision_engine.Policy(
            min_score=float(min_score), min_coverage=min_coverage / 100,
            max_positions=int(max_positions), max_position_pct=float(max_position),
            max_sector_pct=float(max_sector), max_invested_pct=float(max_invested),
        )
        universe = screener.get_universe()
        progress = st.progress(0.0, text="Comprobando histórico de precios...")

        def price_progress(done, total):
            progress.progress(done / total if total else 1.0,
                              text=f"Preparando precios ajustados: {done}/{total}")

        price_result = data_fetch.ensure_decision_prices(
            universe["symbol"].tolist() + ["SPY"], progress_cb=price_progress,
        )
        progress.progress(1.0, text="Histórico de precios preparado")
        if price_result["requested"]:
            st.caption(f"Históricos actualizados: {price_result['requested'] - len(price_result['failed'])}; "
                       f"ya preparados: {price_result['already_ready']}.")
        if price_result["failed"]:
            st.warning(f"No se pudieron actualizar {len(price_result['failed'])} símbolos. "
                       "Se mostrarán como datos insuficientes si siguen sin cobertura.")
            with st.expander("Ver fallos de descarga"):
                st.dataframe([{"Ticker": s, "Motivo": r} for s, r in price_result["failed"].items()],
                             hide_index=True, width="stretch")
        table = screener.build_screener_table(universe)
        histories = storage.get_prices_multi(table.index.tolist())
        plan = decision_engine.build_plan(table, histories, holdings, policy)
        run_id = decision_engine.save_plan(plan, policy, holdings, plan_name or None)
        st.session_state["decision_plan"] = plan
        st.session_state["decision_run_id"] = run_id
        st.session_state["decision_inputs"] = (holdings_text, min_score, min_coverage,
                                                 max_positions, max_position, max_sector, max_invested)
        st.success(f"Plan #{run_id} guardado.")
    except (ValueError, ImportError) as exc:
        st.error(str(exc))

if "decision_plan" in st.session_state:
    if st.session_state.get("decision_inputs") != (holdings_text, min_score, min_coverage,
                                                    max_positions, max_position, max_sector, max_invested):
        st.warning("Has cambiado las entradas. Pulsa «Generar decisiones» para actualizar el plan mostrado.")
    plan = st.session_state["decision_plan"]
    st.caption(f"Asignación: {plan['method']} · Efectivo objetivo: {plan['cash_target_pct']:.1f} %")
    if plan["decisions"].empty:
        st.info("Ninguna empresa cumple las reglas con los datos disponibles.")
    else:
        st.dataframe(plan["decisions"].rename(columns={
            "symbol": "Ticker", "action": "Decisión", "current_pct": "Actual %",
            "target_pct": "Objetivo %", "change_pct": "Cambio %", "reason": "Motivo", "score": "Score",
        }), hide_index=True, width="stretch")
        st.download_button("Descargar decisiones CSV", plan["decisions"].to_csv(index=False).encode("utf-8-sig"),
                           file_name="gabi_decisiones.csv", mime="text/csv")
    if plan["risk"] and plan["risk"]["historical_sharpe"] is not None:
        st.caption(f"Riesgo de la combinación propuesta en {plan['risk']['sessions']} sesiones pasadas: "
                   f"Sharpe {plan['risk']['historical_sharpe']:.2f} · "
                   f"drawdown máximo {plan['risk']['historical_max_drawdown']:.1%}. "
                   "Es retrospectivo, no una previsión.")
    rejected = [(s, "; ".join(r)) for s, r in plan["rejections"].items() if r]
    with st.expander(f"Ver {len(rejected)} descartes y motivos"):
        st.dataframe([{"Ticker": s, "Motivo": r} for s, r in rejected], hide_index=True, width="stretch")

saved = decision_engine.list_saved_plans()
if not saved.empty:
    with st.expander("Planes anteriores"):
        labels = {int(row["id"]): f"{row['name']} · {row['created_at'][:16]} (#{row['id']})"
                  for _, row in saved.iterrows()}
        selected = st.selectbox("Plan guardado", saved["id"].tolist(), format_func=lambda run_id: labels[run_id])
        st.dataframe(decision_engine.load_saved_plan(selected), hide_index=True, width="stretch")
        current_name = saved.loc[saved["id"] == selected, "name"].iloc[0]
        with st.form(f"rename_plan_{selected}"):
            new_name = st.text_input("Cambiar nombre", value=current_name)
            if st.form_submit_button("Guardar nombre"):
                try:
                    decision_engine.rename_saved_plan(selected, new_name)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        if st.button("Borrar este plan", key=f"delete_plan_{selected}"):
            decision_engine.delete_saved_plan(selected)
            if st.session_state.get("decision_run_id") == selected:
                st.session_state.pop("decision_plan", None)
                st.session_state.pop("decision_run_id", None)
            st.rerun()
