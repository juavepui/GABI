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

with st.expander("📖 Cómo funciona y cómo probarlo (léelo si es la primera vez)"):
    st.markdown(
        """
**Qué hace, en orden**:
1. Filtra las empresas del universo que **no cumplen las reglas mínimas** de abajo (score, cobertura de
   datos, precio reciente, volatilidad, drawdown...) — quedan fuera como "descartes", con el motivo exacto.
2. De las que sí pasan, coge las mejores hasta el máximo de empresas que fijes.
3. Reparte el capital entre ellas usando **PyPortfolioOpt** (optimización de cartera de mínima
   volatilidad, con la técnica de contracción de covarianza Ledoit-Wolf) — no reparte a partes iguales,
   intenta combinar las posiciones de forma que la cartera conjunta tenga el menor riesgo posible dados
   sus históricos de precio.
4. Compara esos pesos objetivo con tus posiciones actuales (si las indicas) y decide: **comprar** (no la
   tenías o quieres más), **mantener** (ya está cerca del objetivo), **reducir** o **vender** (tienes más
   de lo que el plan recomienda, o ya no cumple las reglas).

**Para probarlo tú mismo**:
1. Si quieres partir de una cartera real, escribe tus posiciones actuales abajo (ticker y % que
   representan sobre tu patrimonio total en acciones) — si lo dejas vacío, GABI construye la cartera
   desde cero.
2. Ajusta las reglas del expander de abajo si quieres (los valores por defecto son razonables para
   empezar) y pulsa **"Generar decisiones"**.
3. Mira primero la tabla de descartes (al final) si el resultado te sorprende — casi siempre la
   respuesta a "¿por qué no eligió esta empresa que tiene buen score?" está ahí (ej. sin histórico de
   precio suficiente, o por debajo de su SMA200 aunque el score fundamental sea bueno).
4. El plan queda guardado automáticamente — puedes volver más tarde y revisarlo en "Planes anteriores".

**Importante**: esto no es una recomendación de compra real ni una predicción — son reglas mecánicas
aplicadas a los datos que ya tiene GABI. Trátalo como un punto de partida para tu propio análisis, no
como una orden a ejecutar sin más.
        """
    )

with st.expander("Reglas y límites", expanded=True):
    c1, c2, c3 = st.columns(3)
    min_score = c1.slider("Score mínimo", 0, 100, 65,
                          help="Composite Score mínimo (0-100) para que una empresa sea candidata. Más "
                               "alto = más exigente = menos candidatas, pero de más calidad según el score.")
    min_coverage = c2.slider("Cobertura mínima (%)", 50, 100, 70,
                             help="Qué porcentaje de las métricas del score deben tener dato real (no "
                                  "vacío) para confiar en el score de esa empresa. Evita elegir empresas "
                                  "cuyo score se basa en pocos datos.")
    max_positions = c3.number_input("Máximo de empresas", 1, 30, 10,
                                    help="Cuántas posiciones distintas puede tener la cartera como máximo.")
    c4, c5, c6 = st.columns(3)
    max_position = c4.slider("Máximo por empresa (%)", 1, 20, 5,
                             help="Ninguna empresa individual puede pesar más de esto sobre el patrimonio "
                                  "total — límite de concentración/riesgo por posición.")
    max_sector = c5.slider("Máximo por sector (%)", 5, 50, 20,
                           help="Todas las empresas de un mismo sector juntas no pueden pesar más de "
                                "esto — evita que la cartera dependa demasiado de un solo sector.")
    max_invested = c6.slider("Máximo invertido en acciones (%)", 10, 100, 50,
                             help="Qué porcentaje del patrimonio total puede estar invertido en acciones "
                                  "en total — el resto queda como 'efectivo objetivo'.")
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
        score_bar = st.progress(0.0, text="Calculando scores del universo...")

        def score_progress(done, total):
            score_bar.progress(done / total if total else 1.0, text=f"Calculando scores: {done}/{total}")

        table = screener.build_screener_table(universe, progress_cb=score_progress)
        score_bar.empty()
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
    st.caption(
        f"Asignación: {plan['method']} · Efectivo objetivo: {plan['cash_target_pct']:.1f} %",
        help="El 'método' indica cómo se repartió el capital entre las candidatas elegidas — normalmente "
             "optimización de mínima volatilidad de PyPortfolioOpt; si eso falla (poco histórico común "
             "entre las empresas, por ejemplo), cae a un reparto inverso a la volatilidad de cada una. "
             "El 'efectivo objetivo' es el % que el plan deja sin invertir, según el límite máximo de "
             "capital invertido que fijaste arriba.",
    )
    if plan["decisions"].empty:
        st.info("Ninguna empresa cumple las reglas con los datos disponibles.")
    else:
        st.caption(
            "**Comprar/Vender/Reducir/Mantener** compara tu posición actual con el % objetivo del plan. "
            "**Cambio %** es la diferencia a ejecutar (objetivo − actual). El cambio solo se marca como "
            "acción si supera un umbral mínimo — diferencias muy pequeñas se tratan como 'mantener' para "
            "no generar operaciones innecesarias por ruido."
        )
        st.dataframe(plan["decisions"].rename(columns={
            "symbol": "Ticker", "action": "Decisión", "current_pct": "Actual %",
            "target_pct": "Objetivo %", "change_pct": "Cambio %", "reason": "Motivo", "score": "Score",
        }), hide_index=True, width="stretch")
        st.download_button("Descargar decisiones CSV", plan["decisions"].to_csv(index=False).encode("utf-8-sig"),
                           file_name="gabi_decisiones.csv", mime="text/csv")
    if plan["risk"] and plan["risk"]["historical_sharpe"] is not None:
        st.caption(
            f"Riesgo de la combinación propuesta en {plan['risk']['sessions']} sesiones pasadas: "
            f"Sharpe {plan['risk']['historical_sharpe']:.2f} · "
            f"drawdown máximo {plan['risk']['historical_max_drawdown']:.1%}. "
            "Es retrospectivo, no una previsión.",
            help="Cómo se habría comportado ESTA combinación exacta de pesos en su propio histórico de "
                 "precios reciente (hasta 252 sesiones ≈ 1 año) — no es una garantía de que se comporte "
                 "igual en el futuro, solo contexto de qué tan volátil ha sido la mezcla hasta ahora.",
        )
    rejected = [(s, "; ".join(r)) for s, r in plan["rejections"].items() if r]
    with st.expander(f"Ver {len(rejected)} descartes y motivos"):
        st.caption("Por qué una empresa no entró en el plan — mira aquí antes de sorprenderte de que falte alguna.")
        st.dataframe([{"Ticker": s, "Motivo": r} for s, r in rejected], hide_index=True, width="stretch")

saved = decision_engine.list_saved_plans()
if not saved.empty:
    with st.expander("Planes anteriores"):
        labels = {int(row["id"]): f"{row['name']} · {row['created_at'][:16]} (#{row['id']})"
                  for _, row in saved.iterrows()}
        selected = st.selectbox("Plan guardado", saved["id"].tolist(), format_func=lambda run_id: labels[run_id])

        old_decisions = decision_engine.load_saved_plan(selected)
        if not old_decisions.empty:
            display_old = old_decisions.rename(columns={
                "symbol": "Ticker", "action": "Decisión", "current_pct": "Actual %",
                "target_pct": "Objetivo %", "change_pct": "Cambio %", "reason": "Motivo", "score": "Score",
            })
            st.dataframe(
                display_old, hide_index=True, width="stretch",
                column_config={
                    "Ticker": st.column_config.TextColumn(help="Símbolo bursátil de la empresa."),
                    "Decisión": st.column_config.TextColumn(
                        help="COMPRAR/VENDER/REDUCIR/MANTENER según la diferencia entre el % actual y el "
                             "objetivo; REVISAR cuando no hay datos fiables para decidir con seguridad."),
                    "Actual %": st.column_config.NumberColumn(
                        format="%.2f", help="% de tu patrimonio que ya tenías en esta empresa al generar el plan."),
                    "Objetivo %": st.column_config.NumberColumn(
                        format="%.2f", help="% que el plan recomienda tener, según la optimización de cartera."),
                    "Cambio %": st.column_config.NumberColumn(
                        format="%.2f", help="Objetivo menos Actual — cuánto habría que comprar (+) o vender (−)."),
                    "Motivo": st.column_config.TextColumn(help="Por qué esa decisión: regla de la política o motivo del descarte."),
                    "Score": st.column_config.NumberColumn(format="%.1f", help="Composite Score de la empresa en el momento del plan."),
                },
            )
        else:
            st.info("Este plan no tiene posiciones guardadas.")

        current_name = saved.loc[saved["id"] == selected, "name"].iloc[0]
        with st.form(f"rename_plan_{selected}"):
            new_name = st.text_input("Cambiar nombre", value=current_name)
            if st.form_submit_button("Guardar nombre"):
                try:
                    decision_engine.rename_saved_plan(selected, new_name)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

        progress = decision_engine.plan_progress(int(selected))
        if progress:
            st.markdown(f"#### Progreso desde {progress['as_of_date']} hasta hoy")
            if progress.get("stale"):
                if progress["data_as_of"]:
                    st.info(
                        f"ℹ️ Los precios en caché solo llegan hasta el **{progress['data_as_of']}** — la misma "
                        "fecha (o anterior) en que se generó este plan, así que todavía no hay ningún día "
                        "nuevo que comparar. Actualiza los datos en ⚙️ Configuración y vuelve a mirarlo."
                    )
                else:
                    st.info("ℹ️ Todavía no hay precios cacheados para estas empresas.")
            if progress["portfolio_return"] is not None:
                dc1, dc2, dc3 = st.columns(3)
                dc1.metric(
                    "Cartera del plan", f"{progress['portfolio_return']:+.1%}",
                    help="Retorno ponderado por el % OBJETIVO real de cada posición (no a partes iguales) "
                         "desde que se generó el plan hasta hoy.",
                )
                if progress["benchmark_return"] is not None:
                    dc2.metric("SPY (mismo periodo)", f"{progress['benchmark_return']:+.1%}",
                              help="Qué habría rentado el SPY desde la misma fecha del plan hasta hoy.")
                    dc3.metric("Diferencia", f"{progress['excess_return']:+.1%}",
                              help="Cartera menos SPY — positivo significa que el plan bate al índice hasta ahora.")
                else:
                    dc2.metric("SPY (mismo periodo)", "—")
                if progress["available"] < progress["requested"]:
                    st.caption(
                        f"⚠️ Cobertura {progress['available']}/{progress['requested']} — sin precio hasta hoy "
                        "para: " + ", ".join(progress["missing"]) + " (no cuentan como 0%, se excluyen del cálculo)."
                    )

                curve = decision_engine.plan_price_curve(int(selected))
                if not curve.empty:
                    st.line_chart(curve, y_label="Valor (100 = fecha del plan)")

                st.caption("Detalle por posición (solo las que tienen peso objetivo > 0):")
                detail = progress["detail"].copy()
                detail["return"] = detail["return"] * 100
                detail = detail.rename(columns={
                    "symbol": "Ticker", "weight_pct": "Peso objetivo %",
                    "price_start": f"Precio {progress['as_of_date']}", "price_now": "Precio hoy", "return": "Retorno %",
                })
                st.dataframe(
                    detail, hide_index=True, width="stretch",
                    column_config={
                        "Peso objetivo %": st.column_config.NumberColumn(format="%.2f"),
                        "Retorno %": st.column_config.NumberColumn("Retorno %", format="%.1f%%"),
                        f"Precio {progress['as_of_date']}": st.column_config.NumberColumn(format="%.2f"),
                        "Precio hoy": st.column_config.NumberColumn(format="%.2f"),
                    },
                )
            else:
                st.info("Sin precios suficientes todavía para calcular el progreso de este plan.")

        if st.button("Borrar este plan", key=f"delete_plan_{selected}"):
            decision_engine.delete_saved_plan(selected)
            if st.session_state.get("decision_run_id") == selected:
                st.session_state.pop("decision_plan", None)
                st.session_state.pop("decision_run_id", None)
            st.rerun()
