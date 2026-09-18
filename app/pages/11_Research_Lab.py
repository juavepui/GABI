import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import research_lab, stats_rigor

st.title("🔬 Research Lab")
st.caption(
    "Registro de experimentos de backtesting con su metodología, el commit exacto de código y el "
    "resultado — para poder aplicar rigor estadístico (Probabilistic/Deflated Sharpe Ratio, PBO/CSCV, "
    "bootstrap) sin depender de la memoria ni de re-ejecutar nada. Nace porque esta sesión probó 10+ "
    "configuraciones sobre el mismo histórico documentándolo a mano — esto lo formaliza."
)

with st.expander("ℹ️ Las cuatro fases, y por qué importa no confundirlas"):
    st.markdown(
        "\n".join(
            f"- **{info['emoji']} {info['label']}** (`{stage}`): {info['help']}"
            for stage, info in research_lab.STAGE_INFO.items()
        )
        + "\n\nUn resultado en fase RESEARCH que parece bueno **no es evidencia** — es un candidato. "
        "La única forma honesta de saber si una estrategia funciona es verla sobrevivir en datos que no "
        "se usaron para elegirla (OUT_OF_SAMPLE) o, mejor aún, en el futuro real (LIVE_FORWARD). Ver "
        "🎓 Aprender → 'Cómo piensa GABI' para el contexto completo."
    )

experiments = research_lab.list_experiments()

st.subheader("Experimentos registrados")
if experiments.empty:
    st.info("Todavía no hay experimentos registrados. Regístralos desde 🕰️ Ranking histórico tras "
            "ejecutar un backtest, o manualmente más abajo.")
else:
    families = ["(todas)"] + research_lab.list_families()
    stages = ["(todas)"] + research_lab.STAGES
    fc1, fc2 = st.columns(2)
    family_filter = fc1.selectbox("Familia", families)
    stage_filter = fc2.selectbox("Fase", stages)
    filtered = experiments.copy()
    if family_filter != "(todas)":
        filtered = filtered[filtered["family"] == family_filter]
    if stage_filter != "(todas)":
        filtered = filtered[filtered["stage"] == stage_filter]
    display = filtered.copy()
    display["fase"] = display["stage"].map(
        lambda s: f"{research_lab.STAGE_INFO[s]['emoji']} {research_lab.STAGE_INFO[s]['label']}")
    display["tiene retornos"] = display["returns_json"].notna().map({True: "✅", False: "—"})
    cols = ["id", "model_id", "fase", "family", "n_positions", "rebalance", "sharpe", "sortino",
           "max_drawdown", "hypothesis_registered", "git_commit", "tiene retornos", "notes"]
    st.dataframe(display[[c for c in cols if c in display.columns]], hide_index=True, width="stretch")

    del1, del2 = st.columns([3, 1])
    del_id = del1.number_input("Eliminar experimento por id", min_value=0, value=0, step=1, key="del_id")
    if del2.button("Eliminar", key="del_button") and del_id:
        if research_lab.delete_experiment(int(del_id)):
            st.success(f"Experimento #{int(del_id)} eliminado.")
            st.rerun()
        else:
            st.error(f"No existe el experimento #{int(del_id)}.")

with st.expander("➕ Registrar experimento manualmente"):
    st.caption("Para experimentos que no vienen de 🕰️ Ranking histórico (ej. resultados calculados fuera de la app).")
    with st.form("manual_experiment"):
        m1, m2, m3 = st.columns(3)
        model_id = m1.text_input("Model ID", value="GABI-MF-v1.0")
        n_positions = m2.number_input("Nº posiciones", min_value=1, max_value=100, value=20)
        rebalance = m3.selectbox("Rebalanceo", ["Quarterly", "Semiannual", "Annual", "Monthly"])
        m4, m5 = st.columns(2)
        universe = m4.text_input("Universo", value="S&P 500 histórico, muestra de 200")
        cost_model = m5.text_input("Modelo de costes", value="10pb por lado")
        m6, m7 = st.columns(2)
        family = m6.text_input("Familia (agrupa intentos comparables)", value="")
        data_cutoff = m7.date_input("Corte de datos", value=date.today())
        m8, m9 = st.columns(2)
        is_start = m8.date_input("Inicio periodo IS", value=date(2016, 7, 2))
        is_end = m9.date_input("Fin periodo IS", value=date(2025, 4, 1))
        s1, s2, s3 = st.columns(3)
        sharpe = s1.number_input("Sharpe", value=0.0, format="%.3f")
        sortino = s2.number_input("Sortino", value=0.0, format="%.3f")
        max_drawdown = s3.number_input("Máx. drawdown", value=0.0, format="%.3f",
                                       help="Como fracción negativa, ej. -0.25 = -25%.")
        s4, s5 = st.columns(2)
        n_periods = s4.number_input("Nº de periodos", min_value=1, value=36)
        periods_per_year = s5.number_input("Periodos por año", min_value=1.0, value=4.0)
        stage = st.selectbox(
            "Fase", research_lab.STAGES,
            format_func=lambda s: f"{research_lab.STAGE_INFO[s]['emoji']} {research_lab.STAGE_INFO[s]['label']}")
        hypothesis_registered = st.checkbox("¿Hipótesis registrada formalmente antes de ver el resultado?")
        notes = st.text_area("Notas")
        if st.form_submit_button("Registrar"):
            try:
                exp_id = research_lab.log_experiment(
                    model_id, stage, hypothesis_registered, data_cutoff=data_cutoff.isoformat(),
                    universe=universe, factors="Value/Quality/Momentum/Risk", n_positions=int(n_positions),
                    rebalance=rebalance, cost_model=cost_model, is_start=is_start.isoformat(),
                    is_end=is_end.isoformat(), family=family or None, sharpe=sharpe or None,
                    sortino=sortino or None, max_drawdown=max_drawdown or None,
                    n_periods=int(n_periods), periods_per_year=float(periods_per_year), notes=notes or None,
                )
                st.success(f"Experimento #{exp_id} registrado.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

st.divider()
st.subheader("📐 Probabilistic / Deflated Sharpe Ratio")
st.caption(
    "PSR: probabilidad de que el Sharpe observado sea genuinamente positivo (no ruido de muestreo). "
    "DSR: lo mismo, pero comparando contra el Sharpe máximo que cabría esperar por puro azar entre TODOS "
    "los intentos de la familia elegida — corrige por haber probado varias configuraciones."
)
if experiments.empty:
    st.info("Registra al menos 2 experimentos con Sharpe para poder calcular esto.")
else:
    with_sharpe = experiments[experiments["sharpe"].notna()]
    dc1, dc2 = st.columns(2)
    dsr_family = dc1.selectbox("Familia de intentos (define N)", research_lab.list_families(), key="dsr_family")
    family_rows = with_sharpe[with_sharpe["family"] == dsr_family] if dsr_family else with_sharpe
    if len(family_rows) < 2:
        st.warning("Esta familia tiene menos de 2 experimentos con Sharpe — no se puede calcular DSR (haría "
                   "falta al menos 2 intentos para estimar cuánto varía el Sharpe entre ellos por azar).")
    else:
        options = {f"#{row.id} · {row.model_id} · {row.n_positions}pos · {row.rebalance} · Sharpe {row.sharpe:.2f}": row.id
                  for row in family_rows.itertuples()}
        selected_label = dc2.selectbox("Experimento a evaluar", list(options))
        selected_id = options[selected_label]
        selected = research_lab.get_experiment(selected_id)
        trial_sharpes = family_rows["sharpe"].tolist()

        if selected["returns"] is not None:
            exact = stats_rigor.probabilistic_sharpe_ratio_from_returns(
                selected["returns"], selected["periods_per_year"] or 4)
            skew, kurtosis = exact["skew"], exact["kurtosis"]
            st.caption("✅ Serie de retornos real disponible — PSR/DSR exactos (no aproximación normal).")
        else:
            skew, kurtosis = 0.0, 3.0
            st.caption("⚠️ Sin serie de retornos guardada para este experimento — PSR/DSR con aproximación "
                      "normal (skew=0, kurtosis=3), igual que `sharpe_standard_error`.")

        result = stats_rigor.deflated_sharpe_ratio(
            selected["sharpe"], trial_sharpes,
            n_obs=int(selected["n_periods"] or 36), periods_per_year=float(selected["periods_per_year"] or 4),
            skew=skew, kurtosis=kurtosis,
        )
        raw_psr = stats_rigor.probabilistic_sharpe_ratio_annualized(
            selected["sharpe"], int(selected["n_periods"] or 36), float(selected["periods_per_year"] or 4),
            skew=skew, kurtosis=kurtosis, benchmark_sharpe=0.0,
        )
        r1, r2, r3 = st.columns(3)
        r1.metric("PSR (vs Sharpe=0)", f"{raw_psr:.1%}",
                  help="Probabilidad de que el Sharpe sea genuinamente positivo, sin corregir por nº de intentos.")
        r2.metric("SR*₀ (máximo esperado por azar)", f"{result['sr0_benchmark']:.2f}",
                  help=f"Con N={result['n_trials']} intentos en esta familia, este es el Sharpe que cabría "
                       "esperar por pura casualidad, sin ninguna ventaja real.")
        r3.metric("DSR (deflactado)", f"{result['dsr']:.1%}",
                  help="Probabilidad de que el Sharpe sea genuinamente positivo, YA corregida por haber "
                       "probado N configuraciones distintas — el número honesto.")
        st.caption(
            f"Con N={result['n_trials']} intentos probados en la familia \"{dsr_family}\", el Sharpe de "
            f"{selected['sharpe']:.2f} del experimento #{selected_id} tiene un DSR de {result['dsr']:.1%} "
            f"— {'sigue pareciendo genuino incluso corrigiendo por multiple testing' if result['dsr'] > 0.95 else 'convendría más evidencia (out-of-sample o más historia) antes de confiar en él'}."
        )

st.divider()
st.subheader("🔄 PBO / CSCV (Probability of Backtest Overfitting)")
st.caption(
    "Elige la mejor variante dentro de una muestra y comprueba si esa elección se sostiene fuera de "
    "ella. Requiere la serie de retornos DIARIA real de al menos 2 experimentos — solo disponible para "
    "los que se registraron desde 🕰️ Ranking histórico (no para los sembrados con cifras históricas del "
    "README, que solo tienen el Sharpe resumen)."
)
with_returns = experiments[experiments["returns_json"].notna()] if not experiments.empty else experiments
if len(with_returns) < 2:
    st.info("Hacen falta al menos 2 experimentos con serie de retornos guardada. Registra backtests desde "
            "🕰️ Ranking histórico para generarlos.")
else:
    options = {f"#{row.id} · {row.model_id} · Sharpe {row.sharpe:.2f}" if pd.notna(row.sharpe)
              else f"#{row.id} · {row.model_id}": row.id for row in with_returns.itertuples()}
    picked_labels = st.multiselect("Variantes a comparar (mínimo 2)", list(options), key="pbo_picks")
    if len(picked_labels) >= 2:
        series = {}
        for label in picked_labels:
            exp = research_lab.get_experiment(options[label])
            series[label] = exp["returns"]
        matrix = pd.concat(series, axis=1).dropna()
        if len(matrix) < 16:
            st.warning("Muy pocas fechas comunes entre las variantes elegidas para dividir en bloques.")
        else:
            pbo_result = stats_rigor.pbo_cscv(matrix, n_splits=min(16, (len(matrix) // 10) * 2 or 2))
            st.metric("PBO", f"{pbo_result['pbo']:.1%}",
                      help="Fracción de particiones in-sample/out-of-sample en las que la mejor variante "
                           "dentro de muestra queda por DEBAJO de la mediana fuera de muestra. Cerca de 0% "
                           "= la elección se sostiene; cerca de 50% = elegir 'la mejor' no aporta nada, es "
                           "ruido.")
            st.caption(f"{pbo_result['n_combinations']} combinaciones IS/OOS evaluadas.")

st.divider()
st.subheader("🎲 Bootstrap del Sharpe")
st.caption("Intervalo de confianza del Sharpe por remuestreo por bloques (preserva autocorrelación) — más "
          "robusto que la aproximación normal, a costa de no dar una fórmula cerrada. Requiere serie de "
          "retornos real.")
if with_returns.empty:
    st.info("Hacen falta experimentos con serie de retornos guardada.")
else:
    boot_options = {f"#{row.id} · {row.model_id}": row.id for row in with_returns.itertuples()}
    boot_label = st.selectbox("Experimento", list(boot_options), key="boot_pick")
    boot_exp = research_lab.get_experiment(boot_options[boot_label])
    if len(boot_exp["returns"].dropna()) < 30:
        st.warning("Esta serie tiene menos de 30 observaciones — no es suficiente para un bootstrap razonable.")
    elif st.button("Calcular intervalo de confianza"):
        boot_result = stats_rigor.bootstrap_sharpe_ci(
            boot_exp["returns"], periods_per_year=float(boot_exp["periods_per_year"] or 252))
        b1, b2, b3 = st.columns(3)
        b1.metric("Estimación (bootstrap)", f"{boot_result['point_estimate']:.2f}")
        b2.metric("Límite inferior (95%)", f"{boot_result['lower']:.2f}")
        b3.metric("Límite superior (95%)", f"{boot_result['upper']:.2f}")
