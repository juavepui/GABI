import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import (
    academic_factors,
    broker_costs,
    data_fetch,
    data_quality,
    edgar,
    evaluation,
    factor_benchmark,
    factor_benchmark_ui,
    factor_stability,
    factor_stability_ui,
    multifactor_backtest,
    portfolio_backtest,
    portfolio_metrics,
    research_lab,
    screener_asof,
    tail_risk_ui,
    tax_drag,
    universe,
)
from gabi.ui_helpers import METRIC_INFO, build_color_basis, gradient_style, translate_sector

st.title("🕰️ Ranking histórico")
st.warning(
    "⚠️ **Experimental.** Reconstruye lo que el screener habría mostrado en una fecha pasada, usando "
    "solo datos que ya se conocían ese día (sin mirar al futuro). No sustituye a un backtest real — "
    "sirve para explorar, no para sacar conclusiones estadísticas de una sola fecha.",
    icon="⚠️",
)

with st.expander("ℹ️ Cómo funciona y sus límites (léelo antes de usarlo)"):
    st.markdown(
        """
- **Universo**: se reconstruye qué empresas formaban realmente el S&P 500 ese día (evita el sesgo de
  supervivencia de usar la lista actual) con datos de la comunidad
  ([`hanshof/sp500_constituents`](https://github.com/hanshof/sp500_constituents), sin garantías,
  cobertura hasta 2025-08-23 — para fechas más recientes se usa el universo actual como aproximación).
- **Fundamentales y múltiplos** (ROIC, márgenes, deuda neta/EBITDA, PER, P/VC, P/Ventas, EV/EBITDA):
  100% desde SEC EDGAR con la fecha real de presentación de cada dato — nunca desde Yahoo Finance, que
  no guarda histórico.
- **Precio y capitalización**: el histórico de precios normal solo cubre ~2 años. Para fechas más
  antiguas hace falta pedir el histórico completo (botón de abajo) — puede no estar disponible para
  empresas muy antiguas o ya deslistadas.
- ⚠️ **Los tickers se reciclan.** Cuando una empresa desaparece, la bolsa puede reasignar su símbolo a
  otra empresa completamente distinta años después (comprobado: "APC" era Anadarko Petroleum en 2019 y
  hoy en la SEC es "ARKO Petroleum Corp"). Por eso cada fila muestra el **nombre registrado en la SEC**
  junto al ticker — si no coincide con lo que esperabas, no te fíes de esos datos.
        """
    )

col1, col2 = st.columns([1, 2])
with col1:
    as_of = st.date_input(
        "Fecha a reconstruir", value=date(2019, 6, 3),
        min_value=date(1996, 1, 2), max_value=date.today() - timedelta(days=1),
        help="El screener se reconstruye tal y como se habría visto al cierre de este día.",
    )
with col2:
    size_choice = st.radio(
        "Tamaño del universo", ["Prueba rápida (15 empresas)", "Medio (50 empresas)", "Completo"],
        index=0, horizontal=True,
        help="El universo completo de una fecha antigua puede tener ~500 símbolos, muchos ya "
             "deslistados — prepararlos todos tarda bastante.",
    )
limit_map = {"Prueba rápida (15 empresas)": 15, "Medio (50 empresas)": 50, "Completo": None}
limit = limit_map[size_choice]
as_of_str = as_of.isoformat()

universe_info = universe.get_sp500_constituents_asof(as_of_str)
symbols = universe_info["symbols"]
if limit:
    symbols = symbols[:limit]

if universe_info["is_exact"]:
    st.caption(f"✅ {universe_info['note']}")
else:
    st.caption(f"⚠️ {universe_info['note']}")

st.caption(f"{len(symbols)} empresas en el universo a preparar/mostrar para esta fecha.")

if st.button("🔄 Preparar datos que falten para esta fecha", type="primary"):
    edgar_bar = st.progress(0.0, text="SEC EDGAR: preparando...")

    def edgar_progress_cb(done, total, sym):
        edgar_bar.progress(min(done / total, 1.0) if total else 1.0, text=f"SEC EDGAR: {done}/{total} ({sym})")

    with st.spinner("Descargando fundamentales SEC EDGAR..."):
        edgar_result = edgar.ensure_edgar_data(symbols, progress_cb=edgar_progress_cb, as_of=as_of_str)
    edgar_bar.progress(1.0, text="SEC EDGAR: completado")

    price_bar = st.progress(0.0, text="Precios: comprobando cobertura...")

    def price_progress_cb(done, total, sym):
        price_bar.progress(min(done / total, 1.0) if total else 1.0, text=f"Precios (histórico completo): {done}/{total}")

    with st.spinner("Ampliando histórico de precios donde haga falta..."):
        price_result = data_fetch.ensure_price_history_asof(symbols, as_of_str, progress_cb=price_progress_cb)
    price_bar.progress(1.0, text="Precios: completado")

    st.success(
        f"SEC EDGAR actualizado: {edgar_result['edgar_refreshed']} · fallos: {len(edgar_result['failed'])} · "
        f"Precios ampliados: {price_result['deep_fetched']} (ya cubrían la fecha: {price_result['already_covered']}) "
        f"· fallos de precio: {len(price_result['failed'])}"
    )
    all_failed = {}
    for sym, reason in edgar_result["failed"].items():
        all_failed.setdefault(sym, {})["edgar"] = reason
    for sym, reason in price_result["failed"].items():
        all_failed.setdefault(sym, {})["precio"] = reason
    if all_failed:
        with st.expander(f"Ver los {len(all_failed)} símbolos con algún fallo"):
            rows = [{"symbol": s, "etapa": k, "motivo": v} for s, stages in all_failed.items() for k, v in stages.items()]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

st.divider()

result = screener_asof.build_ranking_as_of(as_of_str, symbols=symbols)
df = result["table"]
if "identity_status" in df:
    ambiguous_identity = df["identity_status"].eq("ambiguous")
    unresolved_identity = df["identity_status"].eq("unresolved")
    if ambiguous_identity.any():
        st.warning(f"{ambiguous_identity.sum()}/{len(df)} empresas con identidad ambigua (varios alias en "
                   "conflicto para esta fecha). No se usan sus datos por ticker para calcular el score. "
                   "Consulta el diagnóstico de identidad en 🩺 Calidad de los datos.")
    if unresolved_identity.any():
        st.caption(f"{unresolved_identity.sum()}/{len(df)} empresas sin identidad histórica acreditada todavía "
                   "(migración no completada) -- siguen usando la caché por ticker de siempre, sin cambios.")

if df.empty:
    st.info("Sin datos todavía para este universo. Pulsa 'Preparar datos' arriba.")
    st.stop()

has_price = df["market_cap"].notna()
n_with_price = int(has_price.sum())
n_with_fundamentals = int(df["roic"].notna().sum())
n_no_sector = int(df["sector"].isna().sum()) if "sector" in df.columns else 0
n_sector_approx = int(df["sector_is_approximate"].sum()) if "sector_is_approximate" in df.columns else 0
st.caption(
    f"{len(df)} empresas en la tabla · {n_with_fundamentals} con fundamentales reconstruidos · "
    f"{n_with_price} con precio/capitalización de esa fecha (requiere histórico de precios profundo) · "
    f"{n_sector_approx} con sector aproximado (sin foto point-in-time anterior a esta fecha) · "
    f"{n_no_sector} sin ningún sector conocido (típicamente deslistadas antes de existir este registro)."
)

quality_threshold = st.sidebar.slider("Cobertura completa mínima (%)", 0, 100, 70) / 100
_degradation_msgs = []
_sector_bad_frac = float((df["sector"].isna() | df.get("sector_is_approximate", False)).mean()) if len(df) else 0
if _sector_bad_frac > (1 - quality_threshold):
    _degradation_msgs.append(
        f"**Sector**: {_sector_bad_frac:.0%} de las empresas de esta tabla tienen sector aproximado o "
        "desconocido para esta fecha -- el color por sector y los percentiles sectoriales de una buena "
        "parte de la tabla no son point-in-time reales."
    )
_degradation_msgs += data_quality.block_coverage_warnings(data_quality.score_block_coverage(df), quality_threshold)
if _degradation_msgs:
    st.warning(
        "**Cobertura de datos degradada en esta reconstrucción** (ver 🩺 Calidad de los datos):\n\n"
        + "\n".join(f"- {m}" for m in _degradation_msgs),
        icon="⚠️",
    )

hide_no_data = st.checkbox("Ocultar empresas sin ningún dato reconstruido", value=True)
filtered = df[df["roic"].notna() | df["market_cap"].notna()] if hide_no_data else df

DISPLAY_KEYS = [
    "resolved_title", "sector", "market_cap", "price", "pe", "pb", "roic",
    "gross_margin", "operating_margin", "debt_to_equity", "net_debt_to_ebitda",
    "revenue_growth_yoy", "revenue_cagr_3y", "fcf_cagr_3y", "fundamentals_period_end",
    "quality_persistence_score", "roic_persistence_mean", "roic_persistence_std", "roic_years",
    "operating_margin_persistence_mean", "operating_margin_persistence_std", "operating_margin_years",
    "fcf_conversion_mean", "fcf_years", "revenue_per_share_cagr",
    "implied_fcf_growth", "historical_fcf_cagr", "expectations_gap",
    "metrics_available", "metrics_possible", "score_coverage",
    "value_score", "quality_score", "momentum_score", "risk_score", "composite_score",
]

table_source = filtered.copy()
table_source["resolved_title"] = [edgar.get_resolved_title(s) or filtered.loc[s, "name"] or s for s in filtered.index]

present_keys = [k for k in DISPLAY_KEYS if k in table_source.columns]
color_basis = build_color_basis(table_source, [k for k in present_keys if k != "resolved_title"])


def _format_cell(col, value):
    if col in ("resolved_title", "sector"):
        if col == "sector":
            return translate_sector(value) or "—"
        return value or "—"
    from gabi.ui_helpers import format_metric_value
    return format_metric_value(col, value)


table = pd.DataFrame(
    {col: table_source[col].map(lambda v, c=col: _format_cell(c, v)) for col in present_keys},
    index=table_source.index,
)
label_map = {k: METRIC_INFO.get(k, {}).get("label", k) for k in present_keys}
label_map["resolved_title"] = "Empresa (nombre SEC)"
table.rename(columns=label_map, inplace=True)
color_basis.rename(columns=label_map, inplace=True)
color_basis = color_basis.reindex(index=table.index, columns=table.columns)


def _apply_colors(_data):
    return color_basis.map(gradient_style)


styled = table.style.apply(_apply_colors, axis=None)
st.dataframe(styled, width="stretch", height=500)
st.caption(
    "🟩 mejor · 🟨 medio · 🟥 peor, comparado con el resto de empresas de su sector (sector aproximado "
    "salvo que ya exista una foto point-in-time anterior a esta fecha — ver aviso arriba; sin sector "
    "conocido, se compara contra todo el universo en su lugar). Las columnas sin color no se usan para puntuar."
)
st.caption(
    "Las métricas de persistencia de calidad son descriptivas y point-in-time; se muestran para investigar "
    "la hipótesis del roadmap #18, pero todavía no cambian el Composite ni el orden del ranking. "
    "El reverse DCF usa descuento fijo del 9%, crecimiento terminal del 2,5% y horizonte de 5 años; "
    "sus supuestos tampoco se optimizan con esta tabla."
)

st.subheader("Resultado posterior de las primeras candidatas")
st.caption("Reconstrucción exploratoria; usa rentabilidad total ajustada por dividendos, cartera equiponderada y SPY. Los símbolos sin precio completo se excluyen y se indican.")
eval_n = st.number_input("Primeras candidatas", min_value=1, max_value=50, value=10)
cost_bps = st.number_input("Coste por operación (puntos básicos)", min_value=0.0, max_value=100.0, value=0.0)
eligible = df[df["composite_score"].notna()].head(int(eval_n))
if len(eligible) < eval_n:
    st.caption(f"Solo {len(eligible)} candidatas superan la cobertura mínima.")
for months in (6, 12):
    outcome = evaluation.evaluate(eligible.index.tolist(), as_of_str, months, cost_bps)
    if outcome["status"] == "pending":
        st.write(f"{months} meses: pendiente hasta {outcome['end_date']}")
    else:
        pf = f"{outcome['portfolio_return']:+.1%}" if outcome["portfolio_return"] is not None else "—"
        spy = f"{outcome['benchmark_return']:+.1%}" if outcome["benchmark_return"] is not None else "—"
        st.write(f"{months} meses: candidatas {pf} · SPY {spy} · cobertura {outcome['available']}/{outcome['requested']}")
        if outcome["status"] == "incomplete":
            st.caption("Resultado parcial; faltan: " + ", ".join(outcome["missing"]))

st.divider()
st.subheader("Backtest multifactor por rebalanceos")
st.caption("Reconstruye el ranking en cada fecha con SEC EDGAR y la composición histórica del índice. "
           "Un periodo sin cobertura suficiente se salta (no aborta todo el rango); se listan los saltados. "
           "El universo histórico gratuito termina en 2025 y puede contener símbolos reutilizados. "
           "Los tamaños de 50/100 empresas son pruebas parciales, no resultados representativos del S&P 500.")

tab_v1, tab_v2 = st.tabs(["Motor V1 (clásico)", "🆕 Motor V2 (contabilidad real)"])

with tab_v1:
    with st.expander("📖 Cómo probarlo (léelo si es la primera vez)"):
        st.markdown(
            """
**Qué hace**: en cada fecha de rebalanceo, reconstruye el ranking tal y como se habría visto ese día
(sin usar datos futuros), elige las N mejores candidatas, y mide cuánto habría rentado esa cesta hasta
el siguiente rebalanceo — comparándolo con comprar y mantener el SPY, y con repartir el dinero a partes
iguales entre **todas** las empresas elegibles de ese periodo (el "universo equiponderado": sirve para
saber si elegir bien aporta algo por encima de simplemente estar invertido).

**Pasos para probarlo tú mismo**:
1. Deja fechas por defecto o elige un rango — **empieza en 2016-07-02 o después**: antes de eso apenas
   hay empresas con fundamentales SEC EDGAR completos y la mayoría de periodos se saltarán.
2. Pulsa **"Preparar datos de todos los rebalanceos"** primero — descarga SEC EDGAR y precios para
   todas las empresas que hagan falta en ese rango. Con rangos largos (varios años) puede tardar varios
   minutos; con pocos meses es casi instantáneo si ya tienes datos cacheados.
3. Pulsa **"Ejecutar backtest multifactor"**.
4. Mira primero **Sharpe y Sortino** (abajo), no solo el retorno — un retorno más alto con mucho más
   riesgo no es necesariamente mejor. Compara los tres: tu estrategia, el universo equiponderado y el SPY.

**⚠️ Este motor cobra el coste como un % plano de compra+venta sobre cada posición nueva** (no a las
que ya se tenían en el periodo anterior, ni al SPY, que se trata como referencia pasiva) — pero sigue
siendo una simulación por periodos de rebalanceo, no una cartera real con acciones + caja. Ver la
pestaña "Motor V2" para la versión con contabilidad real de cartera, y 🎓 Aprender → "Cómo piensa
GABI" para el porqué importa la diferencia.

**Qué probar**: sube "Empresas por periodo" a 20 y compara — en nuestras pruebas, 20 posiciones bajó el
drawdown máximo sin apenas perder Sharpe/Sortino frente a 10 (ver README, sección de backtesting). Prueba
también a subir "Coste por lado" a 25-50 puntos básicos — el margen de la estrategia frente al SPY se
estrecha mucho más de lo que parece a primera vista con solo 10pb.
            """
        )

    with st.expander("🧮 Calculadora: coste real de eToro para tu cartera"):
        st.caption(
            "eToro cobra un importe FIJO por apertura/cierre (1$ en acciones/ETF), no un %, así que pesa "
            "más cuanto menor sea la posición. Este cálculo es solo del coste de **operar** (abrir/cerrar "
            "dentro de la cuenta) — el coste de **depositar** dinero nuevo desde el banco (conversión de "
            "divisa) es un coste distinto, de una sola vez por aportación, que no se aplica en cada "
            "rebalanceo del backtest (ver README, sección \"Costes reales del bróker\")."
        )
        cc1, cc2 = st.columns(2)
        calc_capital = cc1.number_input("Capital total (€ o $)", min_value=0.0, value=10000.0, step=500.0,
                                        key="calc_capital")
        calc_n = cc2.number_input("Nº de posiciones", min_value=1, max_value=50, value=10, key="calc_n")
        calc_position = broker_costs.position_size_usd(calc_capital, int(calc_n))
        calc_bps = broker_costs.effective_trade_cost_bps(calc_position)
        st.write(f"Posición media: **{calc_position:,.0f}** · coste real por lado: **{calc_bps:.1f} puntos "
                 f"básicos** — cópialo en \"Coste por lado (pb)\" más abajo si quieres usarlo.")

    with st.form("multifactor_test"):
        a, b, c = st.columns(3)
        bt_start = a.date_input("Inicio", value=date(2019, 1, 2), key="bt_start",
                                 help="Recomendado: 2016-07-02 o después. Antes de eso, la mayoría de "
                                      "periodos se saltarán por falta de cobertura SEC EDGAR.")
        bt_end = b.date_input("Fin", value=date(2020, 1, 2), max_value=date.today(), key="bt_end")
        interval = c.selectbox("Rebalanceo", [1, 3, 6, 12], index=1, format_func=lambda n: f"Cada {n} meses",
                               help="Cada cuánto se recalcula el ranking y se cambia de cesta de empresas.")
        d, e, f = st.columns(3)
        n_picks = d.number_input("Empresas por periodo", 1, 50, 10,
                                 help="Cuántas de las mejores candidatas se compran cada rebalanceo, a partes "
                                      "iguales. Más posiciones suele bajar el riesgo (drawdown) a costa de "
                                      "diluir algo el retorno — no hay un número 'correcto' único.")
        universe_size = e.selectbox("Universo", [50, 100, 500], index=0,
                                    help="Cuántas empresas del S&P 500 de esa fecha se consideran como "
                                         "candidatas (muestreo aleatorio si hay más de las indicadas, no "
                                         "las primeras alfabéticamente). 500 ≈ el índice completo.")
        bt_cost = f.number_input("Coste por lado (pb)", min_value=0.0, value=10.0,
                                 help="Fricción de comprar/vender (spread, comisión, slippage) en puntos "
                                      "básicos (100pb = 1%). Se aplica en cada rebalanceo a cada posición. "
                                      "10pb es razonable para grandes capitalizadas líquidas; con empresas "
                                      "menos líquidas o peor ejecución, 25-50pb es más realista.")
        rotation_hurdle = st.number_input(
            "Umbral de rotacion (puntos Composite)", min_value=0.0, value=0.0, step=1.0,
            help="Solo sustituye una posicion si la candidata mejora a la mas debil por mas puntos. "
                 "Fijalo antes de mirar el resultado; 0 mantiene el top-N estricto.")
        if st.form_submit_button("Ejecutar backtest multifactor"):
            try:
                test = multifactor_backtest.run(bt_start.isoformat(), bt_end.isoformat(), interval,
                                                n_picks, bt_cost, max_symbols=universe_size,
                                                rotation_hurdle_points=float(rotation_hurdle))
                test["data_fingerprint"] = data_quality.compute_data_fingerprint()
                st.session_state["multifactor_result"] = test
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))
    if st.button("Preparar datos de todos los rebalanceos"):
        try:
            all_symbols = multifactor_backtest.required_symbols(bt_start.isoformat(), bt_end.isoformat(),
                                                                 interval, universe_size)
            st.info(f"Preparando {len(all_symbols)} símbolos históricos y SPY. Puede tardar varios minutos.")
            with st.spinner("Descargando SEC EDGAR y precios históricos..."):
                edgar_result = edgar.ensure_edgar_data(all_symbols)
                price_failures = {}
                for offset in range(0, len(all_symbols), 25):
                    batch = all_symbols[offset:offset + 25]
                    price_failures.update(data_fetch.fetch_prices_batch(batch, period="max"))
                price_failures.update(data_fetch.fetch_prices_batch(["SPY"], period="max"))
            st.success(f"Preparación terminada. Fallos SEC: {len(edgar_result['failed'])}; "
                       f"fallos de precios: {len(price_failures)}.")
            if price_failures:
                st.dataframe(pd.DataFrame([{"Ticker": s, "Motivo": reason}
                                           for s, reason in price_failures.items()]), hide_index=True)
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
    if "multifactor_result" in st.session_state:
        test = st.session_state["multifactor_result"]
        st.caption(f"Política de rotación: umbral {test.get('rotation_hurdle_points', 0):.1f} puntos Composite; "
                   "las comisiones/spread se aplican solo al ejecutar cambios.")
        st.warning("Limitaciones estructurales de datos históricos: sector aproximado y cobertura SEC incompleta. Consulta Calidad de los datos.")
        for period_date, quality in test.get("data_quality", {}).items():
            messages = data_quality.ranking_quality_warnings(quality, quality_threshold)
            if messages:
                st.warning(f"{period_date}: " + " · ".join(messages))
        if test["skipped"]:
            with st.expander(f"⚠️ {len(test['skipped'])} periodo(s) saltado(s) por falta de cobertura"):
                st.dataframe(pd.DataFrame(test["skipped"]), hide_index=True, width="stretch")

        st.caption(
            "**Sharpe**: retorno por encima de la tasa libre de riesgo, dividido entre la volatilidad total — "
            "más alto es mejor (más retorno por unidad de riesgo asumido). **Sortino**: lo mismo pero solo "
            "penaliza la volatilidad a la baja (caídas), no la al alza — más informativo que Sharpe si lo que "
            "te preocupa es perder dinero, no que suba mucho. **Drawdown**: la mayor caída desde un máximo "
            "hasta un mínimo posterior — cuánto habrías llegado a perder en el peor momento."
        )
        strat_m, universo_m, spy_m = test["metrics"]["estrategia"], test["metrics"]["universo_ew"], test["metrics"]["spy"]

        def _metric_row(label, ret, m, help_extra=""):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(f"{label} · acumulado", f"{ret:+.1%}")
            c2.metric("Sharpe", f"{m['sharpe']:.2f}" if m["sharpe"] is not None else "—",
                      help="Retorno anualizado (sobre el 4% libre de riesgo) dividido entre la volatilidad. " + help_extra)
            c3.metric("Sortino", f"{m['sortino']:.2f}" if m["sortino"] is not None else "—",
                      help="Como Sharpe, pero solo cuenta la volatilidad a la baja.")
            c4.metric("Máx. drawdown", f"{m['max_drawdown']:.1%}" if m["max_drawdown"] is not None else "—",
                      help="Mayor caída desde un máximo hasta un mínimo posterior, entre rebalanceos.")

        st.markdown("**Tu estrategia (top-N del ranking)**")
        _metric_row("Estrategia", test["return"], strat_m)
        st.markdown("**Universo equiponderado** — todas las candidatas elegibles de cada periodo, a partes iguales")
        _metric_row("Universo", test["universo_ew_return"], universo_m,
                    "Compáralo con la estrategia: si Sharpe aquí es parecido o mejor, elegir las top-N no está "
                    "aportando tanto como parece por el retorno bruto.")
        st.markdown("**SPY** — comprar y mantener el índice, sin rebalanceos")
        _metric_row("SPY", test["spy_return"], spy_m)

        st.line_chart(test["periods"].set_index("hasta")[["capital", "universo_capital", "spy_capital"]])
        st.caption("Capital acumulado (partiendo de 1) de la estrategia, el universo equiponderado y el SPY.")
        st.dataframe(test["periods"], hide_index=True, width="stretch")

        with st.expander("Riesgo de cola · retornos por rebalanceo"):
            period_starts = pd.PeriodIndex(test["periods"]["fecha"], freq="M").asi8
            period_ends = pd.PeriodIndex(test["periods"]["hasta"], freq="M").asi8
            durations = set(period_ends - period_starts)
            if len(durations) == 1 and next(iter(durations)) > 0:
                tail_risk_ui.render_returns(
                    {"Estrategia": test["periods"]["retorno"], "Universo EW": test["periods"]["universo_ew"],
                     "SPY": test["periods"]["spy"]}, horizon=f"{next(iter(durations))} meses (rebalanceo V1)", key="v1_tail")
                st.caption("Solo periodos disponibles del backtest; no mide caídas dentro de cada periodo. "
                           "Los periodos saltados no se imputan como retornos cero.")
            else:
                st.info("No se mezclan retornos de distinta duración en una distribución de cola.")

        with st.expander("📋 Registrar este experimento en el Research Lab"):
            rl1, rl2 = st.columns(2)
            rl_stage = rl1.selectbox(
                "Fase", research_lab.STAGES, key="v1_rl_stage",
                format_func=lambda s: f"{research_lab.STAGE_INFO[s]['emoji']} {research_lab.STAGE_INFO[s]['label']}")
            rl_family = rl2.text_input("Familia (agrupa intentos comparables)", value="", key="v1_rl_family")
            rl_hypothesis = st.checkbox("¿Hipótesis registrada formalmente antes de ver el resultado?", key="v1_rl_hyp")
            rl_notes = st.text_area("Notas", key="v1_rl_notes")
            if st.button("Registrar en el Research Lab", key="v1_rl_button"):
                returns_series = test["periods"].set_index(pd.to_datetime(test["periods"]["hasta"]))["retorno"]
                exp_id = research_lab.log_experiment(
                    "GABI-MF-v1", rl_stage, rl_hypothesis, universe=f"S&P 500 histórico, muestra de {universe_size}",
                    factors="Value/Quality/Momentum/Risk", n_positions=int(n_picks),
                    rebalance={1: "Monthly", 3: "Quarterly", 6: "Semiannual", 12: "Annual"}[interval],
                    cost_model=f"V1: {bt_cost:.0f}pb round-trip sobre el 100% de cada posición cada periodo",
                    is_start=bt_start.isoformat(), is_end=bt_end.isoformat(), family=rl_family or None,
                    sharpe=strat_m["sharpe"], sortino=strat_m["sortino"], max_drawdown=strat_m["max_drawdown"],
                    total_return=test["return"], n_periods=len(test["periods"]), periods_per_year=12 / interval,
                    returns=returns_series, notes=rl_notes or None,
                    result={"data_quality": test.get("data_quality", {})},
                    data_fingerprint=test.get("data_fingerprint"),
                )
                st.success(f"Experimento #{exp_id} registrado — consúltalo en 🔬 Research Lab.")

        st.markdown("#### Contraste con factores académicos (Fama-French)")
        st.caption(
            "¿Lo que hace la estrategia es distinto de las primas de factor ya documentadas en la literatura "
            "académica (mercado, tamaño, value, calidad/rentabilidad, inversión, momentum — Kenneth French Data "
            "Library, Dartmouth), o es la misma exposición con otro nombre? Se regresiona el retorno de la "
            "estrategia contra esos 6 factores; 'alfa' es lo que queda sin explicar por ellos.",
            help="Fuente: mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html — gratis, sin API key. "
                 "Se descarga y cachea la primera vez que se usa esta sección.",
        )
        try:
            with st.expander("Inferencia HAC/Newey-West"):
                automatic_lags = st.checkbox("Elegir retardos automáticamente", value=True, key="ff_hac_auto")
                hac_lags = None if automatic_lags else int(st.number_input(
                    "Máximo retardo (periodos del backtest)", min_value=0,
                    max_value=max(len(test["periods"]) - 1, 0),
                    value=min(3, max(len(test["periods"]) - 1, 0)), key="ff_hac_lags",
                    help="0 corrige heterocedasticidad; los valores mayores también autocorrelación. "
                         "Elige el criterio antes de mirar qué t-stat produce.",
                ))
            with st.spinner("Descargando series de Kenneth French (Fama-French 5 factores + Momentum)..."):
                ff_factors = academic_factors.fetch_ff_factors()
            reg = academic_factors.regress_returns_on_factors(test["periods"], ff_factors, hac_lags=hac_lags)
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric(
                "Alfa anualizado", f"{reg['alpha_anualizado']:+.2%}",
                help="Retorno anualizado que NO explican los 6 factores académicos — la parte 'propia' de la "
                     "estrategia, si es que existe alguna.",
            )
            rc2.metric(
                "t-stat del alfa (HAC)", f"{reg['t_stat']['alpha']:+.2f}",
                help="Errores estándar Newey-West robustos a heterocedasticidad y autocorrelación. "
                     "|t| ≈ 2 es solo una referencia asintótica, poco precisa con muestras pequeñas. "
                     "Harvey, Liu y Zhu proponen exigir >3.0 precisamente porque se prueban muchas configuraciones "
                     "en este tipo de investigación (ver HIPOTESIS_CONGELADA.md).",
            )
            rc3.metric("R² de la regresión", f"{reg['r2']:.2f}",
                      help="Qué % de la varianza del retorno de la estrategia explican los 6 factores conocidos — "
                           "más alto significa que la estrategia se parece más a una combinación de exposiciones ya "
                           "documentadas y menos a algo genuinamente distinto.")
            st.caption(f"Regresión con {reg['periodos_alineados']}/{reg['periodos_totales']} periodos alineados "
                      f"({reg['dof']} grados de libertad tras 6 factores + alfa). "
                      f"HAC/Newey-West: Bartlett, {reg['hac_lags']} retardos, corrección n/(n−k). "
                      f"t-stat del alfa OLS convencional: {reg['t_stat_ols']['alpha']:+.2f}. "
                      "Con pocos periodos, la inferencia sigue siendo aproximada; HAC no corrige el multiple testing.")
            betas_df = pd.DataFrame([
                {"Factor": f, "Qué mide": label, "Beta": reg["coef"][f],
                 "SE (HAC)": reg["se"][f], "t-stat (HAC)": reg["t_stat"][f]}
                for f, label in [
                    ("Mkt-RF", "Exposición al mercado (~1 = se mueve como la bolsa en general)"),
                    ("SMB", "Tamaño (small minus big) — tilt hacia empresas más pequeñas"),
                    ("HML", "Value (high minus low book-to-market)"),
                    ("RMW", "Calidad/rentabilidad (robust minus weak)"),
                    ("CMA", "Inversión (conservative minus aggressive)"),
                    ("Mom", "Momentum"),
                ]
            ])
            st.dataframe(
                betas_df, hide_index=True, width="stretch",
                column_config={
                    "Beta": st.column_config.NumberColumn(format="%.3f"),
                    "SE (HAC)": st.column_config.NumberColumn(format="%.3f"),
                    "t-stat (HAC)": st.column_config.NumberColumn(format="%.2f"),
                },
            )
            with st.expander("Estabilidad temporal de alfa y betas"):
                try:
                    stability_inputs = factor_stability.aligned_quarters(test["periods"], ff_factors)
                    factor_stability_ui.render(factor_stability.analyze(stability_inputs), key="ff_stability_live")
                except (ValueError, KeyError) as exc:
                    st.info(f"Diagnóstico temporal no disponible: {exc}")
            with st.expander("Benchmark ajustado por beta y factores"):
                try:
                    benchmark_inputs = factor_benchmark.aligned_inputs(test["periods"], ff_factors)
                    factor_benchmark_ui.render(factor_benchmark.analyze(benchmark_inputs), key="factor_benchmark_live")
                except (ValueError, KeyError) as exc:
                    st.info(f"Benchmark trimestral no disponible: {exc}")
        except (ValueError, RuntimeError, ImportError) as exc:
            st.warning(f"No se pudo calcular el contraste con factores académicos: {exc}")

        with st.expander("💶 Drag fiscal español (aproximado, IRPF base del ahorro)"):
            st.caption(
                "El retorno del backtest de arriba es bruto — no paga impuestos. Con rebalanceo trimestral "
                "y turnover alto, las plusvalías se realizan constantemente, perdiendo el diferimiento "
                "fiscal que sí tendría un comprar-y-mantener. Simulación aparte con coste medio por "
                "cartera (no FIFO lote a lote) y los tramos 2024 de la base del ahorro — ver limitaciones "
                "abajo antes de tomarlo como una cifra exacta."
            )
            try:
                tax_capital = st.number_input(
                    "Capital inicial de la simulación (€)", min_value=1_000.0, value=100_000.0,
                    step=10_000.0, key="tax_drag_capital",
                )
                strategy_tax = tax_drag.simulate_tax_drag(test["periods"], initial_capital=tax_capital)
                benchmark_tax = tax_drag.simulate_tax_drag(
                    tax_drag.zero_turnover_periods(test["periods"], "spy"), initial_capital=tax_capital,
                )
                st.dataframe(
                    pd.DataFrame([
                        {"": "Retorno bruto", "Estrategia": strategy_tax["pretax_return"],
                         "SPY comprado y mantenido": benchmark_tax["pretax_return"]},
                        {"": "Retorno neto (con IRPF)", "Estrategia": strategy_tax["aftertax_return"],
                         "SPY comprado y mantenido": benchmark_tax["aftertax_return"]},
                    ]),
                    hide_index=True, width="stretch",
                    column_config={
                        "Estrategia": st.column_config.NumberColumn(format="percent"),
                        "SPY comprado y mantenido": st.column_config.NumberColumn(format="percent"),
                    },
                )
                tc1, tc2 = st.columns(2)
                tc1.metric("Impuesto pagado — estrategia", f"{strategy_tax['total_tax_paid']:,.0f} €")
                tc2.metric("Impuesto pagado — SPY buy & hold", f"{benchmark_tax['total_tax_paid']:,.0f} €",
                          help="Con turnover 0, casi toda la plusvalía queda sin realizar (sin vender, no "
                               "tributa) — la comparación directa de cuánto cuesta rotar la cartera cada "
                               "trimestre frente a no venderla nunca durante el mismo periodo.")
                st.caption(
                    f"Ganancia patrimonial no realizada que queda sin tributar al final del periodo: "
                    f"{strategy_tax['unrealized_gain_remaining']:,.0f} € en la estrategia."
                )
                with st.expander("Detalle año a año"):
                    year_rows = [
                        {"Año": year, "Ganancia/pérdida neta compensada": v["realized_net"],
                         "Base imponible": v["taxable"], "Impuesto": v["tax"]}
                        for year, v in strategy_tax["tax_by_year"].items()
                    ]
                    st.dataframe(
                        pd.DataFrame(year_rows), hide_index=True, width="stretch",
                        column_config={c: st.column_config.NumberColumn(format="%.0f €")
                                      for c in ("Ganancia/pérdida neta compensada", "Base imponible", "Impuesto")},
                    )
                st.caption("Limitaciones de esta simulación: " + " · ".join(tax_drag.LIMITATIONS))
            except (ValueError, KeyError) as exc:
                st.info(f"Simulación fiscal no disponible: {exc}")

with tab_v2:
    st.caption(
        "Contabilidad real de cartera: acciones + caja, comisión fija + spread real (no un % plano sobre "
        "el 100% de cada posición cada periodo), SPY comprado y mantenido (no rotado), y una curva de "
        "capital DIARIA real en vez de una reconstrucción por periodos. Ver 🎓 Aprender → \"Cómo piensa "
        "GABI\" → \"V1 vs V2\" para el porqué, y README.md para el detalle técnico."
    )
    with st.expander("📖 Cómo probarlo"):
        st.markdown(
            """
**Diferencia clave con el motor clásico (V1)**: aquí cada rebalanceo es una operación real sobre
acciones y caja — lo que se mantiene solo paga comisión sobre el ajuste de peso frente al objetivo, no
sobre el 100% de la posición; el SPY se compra una vez y se mantiene; y la curva de capital es un
cálculo día a día real, no una reconstrucción escalada.

**Modo de universo**:
- **Validación**: usa el universo histórico COMPLETO, sin muestrear — es el único modo cuyo resultado
  debería citarse como evidencia de la estrategia real. En un rango de varios años puede tardar
  **20-30 minutos** (medido: ~26 min para 2016-2025 completo) — no se ha colgado, espera.
- **Desarrollo rápido**: muestrea a un tamaño fijo (50/100/200) — útil para probar rápido, sus
  resultados no deben citarse como evidencia.

**Pasos**: pulsa "Preparar datos" primero (reutiliza lo que ya hayas descargado para el mismo rango,
aunque sea desde la pestaña V1), elige el modo, y pulsa "Ejecutar backtest V2".
            """
        )

    with st.form("portfolio_v2_form"):
        va, vb, vc = st.columns(3)
        v2_start = va.date_input("Inicio", value=date(2019, 1, 2), key="v2_start",
                                 help="Recomendado: 2016-07-02 o después.")
        v2_end = vb.date_input("Fin", value=date(2020, 1, 2), max_value=date.today(), key="v2_end")
        v2_interval = vc.selectbox("Rebalanceo", [1, 3, 6, 12], index=1, format_func=lambda n: f"Cada {n} meses",
                                   key="v2_interval")
        vd, ve = st.columns(2)
        v2_n_picks = vd.number_input("Empresas por periodo", 1, 50, 20, key="v2_n_picks")
        v2_capital = ve.number_input("Capital inicial ($)", min_value=1000.0, value=100_000.0, step=10_000.0,
                                     key="v2_capital")
        vf, vg = st.columns(2)
        v2_commission = vf.number_input("Comisión fija por operación ($)", min_value=0.0,
                                        value=broker_costs.STOCK_FEE_USD, step=0.5, key="v2_commission",
                                        help="Por defecto, la comisión real de eToro calibrada esta sesión.")
        v2_spread = vg.number_input("Spread (pb)", min_value=0.0, value=10.0, key="v2_spread")
        v2_rotation_hurdle = st.number_input(
            "Umbral de rotacion (puntos Composite)", min_value=0.0, value=0.0, step=1.0,
            key="v2_rotation_hurdle",
            help="Regla fijada ex ante: una nueva posicion debe superar a la mas debil por este margen. "
                 "Las comisiones y el spread se aplican despues sobre las operaciones reales.")
        v2_mode = st.radio(
            "Modo", ["Validación (universo completo — lento)", "Desarrollo rápido (muestra)"],
            index=1, horizontal=True, key="v2_mode",
            help="Validación no admite tamaño de muestra: usa el universo histórico completo de cada fecha.",
        )
        v2_max_symbols = None
        if v2_mode == "Desarrollo rápido (muestra)":
            v2_max_symbols = st.selectbox("Tamaño de la muestra", [50, 100, 200], index=2, key="v2_max_symbols")
        else:
            st.caption("⏱️ Puede tardar 20-30 minutos en un rango de varios años — no se ha colgado.")
        if st.form_submit_button("Ejecutar backtest V2"):
            try:
                v2_mode_value = "validation" if v2_mode.startswith("Validación") else "fast_dev"
                v2_test = portfolio_backtest.run(
                    v2_start.isoformat(), v2_end.isoformat(), months=v2_interval, top_n=int(v2_n_picks),
                    max_symbols=v2_max_symbols, mode=v2_mode_value, initial_capital=float(v2_capital),
                    commission_usd=float(v2_commission), spread_bps=float(v2_spread),
                    rotation_hurdle_points=float(v2_rotation_hurdle),
                )
                v2_test["data_fingerprint"] = data_quality.compute_data_fingerprint()
                st.session_state["portfolio_v2_result"] = v2_test
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))

    if st.button("Preparar datos de todos los rebalanceos", key="v2_prepare"):
        try:
            all_symbols = multifactor_backtest.required_symbols(
                v2_start.isoformat(), v2_end.isoformat(), v2_interval, v2_max_symbols)
            st.info(f"Preparando {len(all_symbols)} símbolos históricos y SPY. Puede tardar varios minutos.")
            with st.spinner("Descargando SEC EDGAR y precios históricos..."):
                edgar_result = edgar.ensure_edgar_data(all_symbols)
                price_failures = {}
                for offset in range(0, len(all_symbols), 25):
                    batch = all_symbols[offset:offset + 25]
                    price_failures.update(data_fetch.fetch_prices_batch(batch, period="max"))
                price_failures.update(data_fetch.fetch_prices_batch(["SPY"], period="max"))
            st.success(f"Preparación terminada. Fallos SEC: {len(edgar_result['failed'])}; "
                       f"fallos de precios: {len(price_failures)}.")
            if price_failures:
                st.dataframe(pd.DataFrame([{"Ticker": s, "Motivo": reason}
                                           for s, reason in price_failures.items()]), hide_index=True)
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))

    if "portfolio_v2_result" in st.session_state:
        v2_test = st.session_state["portfolio_v2_result"]
        st.caption(f"Política de rotación: umbral {v2_test.get('rotation_hurdle_points', 0):.1f} puntos Composite; "
                   "las comisiones y el spread se cargan sobre las operaciones reales.")
        st.warning("Limitaciones estructurales de datos históricos: sector aproximado y cobertura SEC incompleta. Consulta Calidad de los datos.")
        for period_date, quality in v2_test.get("data_quality", {}).items():
            messages = data_quality.ranking_quality_warnings(quality, quality_threshold)
            if messages:
                st.warning(f"{period_date}: " + " · ".join(messages))
        if v2_test["skipped"]:
            with st.expander(f"⚠️ {len(v2_test['skipped'])} periodo(s) saltado(s) por falta de cobertura"):
                st.dataframe(pd.DataFrame(v2_test["skipped"]), hide_index=True, width="stretch")

        nav = v2_test["nav_curve"]
        nav_spy = v2_test["nav_curve_spy"]
        daily = multifactor_backtest.daily_risk_metrics(nav)
        daily_spy = multifactor_backtest.daily_risk_metrics(nav_spy)
        returns = nav.pct_change().dropna()
        returns_spy = nav_spy.pct_change().dropna()

        mode_label = ("Validación — sujeta a las limitaciones de calidad indicadas" if v2_test["mode"] == "validation"
                      else "🧪 Desarrollo rápido — no citar como evidencia")
        st.markdown(f"**Modo usado: {mode_label}**")

        g1, g2, g3 = st.columns(3)
        g1.metric("Turnover medio", f"{v2_test['turnover_medio']:.1f}%",
                  help="Importe realmente negociado cada periodo (los 2 lados + reequilibrio de lo mantenido) "
                       "como % del valor de la cartera — no solo qué fracción de nombres cambia.")
        g2.metric("Comisión total pagada", f"{v2_test['comision_total']:,.0f} $",
                  help=f"Partiendo de {v2_capital:,.0f} $ iniciales.")
        g3.metric("Capital final", f"{v2_test['capital_final']:,.0f} $")

        st.caption(
            "**Sharpe**: retorno por encima de la tasa libre de riesgo, dividido entre la volatilidad total. "
            "**Sortino**: lo mismo pero solo penaliza la volatilidad a la baja. **Drawdown**: la mayor caída "
            "desde un máximo hasta un mínimo posterior — aquí calculado sobre la curva DIARIA real, no solo "
            "en fechas de rebalanceo."
        )

        def _metric_row_v2(label, m):
            d1, d2, d3, d4 = st.columns(4)
            d1.metric(f"{label} · anualizado", f"{m['anualizado']:+.1%}" if m["anualizado"] is not None else "—")
            d2.metric("Sharpe", f"{m['sharpe']:.2f}" if m["sharpe"] is not None else "—")
            d3.metric("Sortino", f"{m['sortino']:.2f}" if m["sortino"] is not None else "—")
            d4.metric("Máx. drawdown", f"{m['max_drawdown']:.1%}" if m["max_drawdown"] is not None else "—")

        st.markdown("**Tu estrategia**")
        _metric_row_v2("Estrategia", daily)
        st.markdown("**SPY** — comprado una vez y mantenido")
        _metric_row_v2("SPY", daily_spy)

        with st.expander("Riesgo de cola · retornos diarios"):
            tail_risk_ui.render_nav({"Estrategia": nav, "SPY": nav_spy}, key="v2_tail")

        h1, h2, h3, h4 = st.columns(4)
        calmar = portfolio_metrics.calmar_ratio(daily["anualizado"], daily["max_drawdown"])
        h1.metric("Calmar", f"{calmar:.2f}" if calmar is not None else "—",
                  help="Retorno anualizado / |máximo drawdown| — retorno obtenido por unidad de la peor caída.")
        recovery = portfolio_metrics.recovery_time(nav)
        h2.metric("Días de recuperación", f"{recovery}" if recovery is not None else "—",
                  help="Días de calendario desde el pico previo al máximo drawdown hasta volver a superarlo.")
        beta = portfolio_metrics.beta_vs_benchmark(returns, returns_spy)
        h3.metric("Beta vs SPY", f"{beta:.2f}" if beta is not None else "—",
                  help="Sensibilidad al SPY — 1.0 = se mueve igual que el mercado.")
        ir = portfolio_metrics.information_ratio(returns, returns_spy)
        h4.metric("Information Ratio", f"{ir:.2f}" if ir is not None else "—",
                  help="Exceso de retorno anualizado frente al SPY, dividido entre el tracking error.")

        capture = portfolio_metrics.capture_ratios(returns, returns_spy)
        i1, i2 = st.columns(2)
        i1.metric("Capture al alza", f"{capture['upside'] * 100:.0f}%" if capture["upside"] is not None else "—",
                  help="Cuánto se mueve la estrategia, de media, en los meses en que el SPY sube.")
        i2.metric("Capture a la baja", f"{capture['downside'] * 100:.0f}%" if capture["downside"] is not None else "—",
                  help="Cuánto se mueve la estrategia, de media, en los meses en que el SPY baja — menos de 100% es deseable.")

        curve_df = pd.DataFrame({"Estrategia": nav / nav.iloc[0] * 100, "SPY": nav_spy / nav_spy.iloc[0] * 100})
        st.line_chart(curve_df)
        st.caption("Curva de capital DIARIA real (base 100), no una reconstrucción por periodos de rebalanceo.")
        st.dataframe(v2_test["periods"], hide_index=True, width="stretch")

        with st.expander("📋 Registrar este experimento en el Research Lab"):
            st.caption("Se guarda la curva de retornos DIARIA real — habilita PBO/CSCV y bootstrap para "
                      "este experimento, a diferencia de los sembrados con cifras resumen del README.")
            rv1, rv2 = st.columns(2)
            rv_stage = rv1.selectbox(
                "Fase", research_lab.STAGES, key="v2_rl_stage",
                format_func=lambda s: f"{research_lab.STAGE_INFO[s]['emoji']} {research_lab.STAGE_INFO[s]['label']}")
            rv_family = rv2.text_input("Familia (agrupa intentos comparables)", value="", key="v2_rl_family")
            rv_hypothesis = st.checkbox("¿Hipótesis registrada formalmente antes de ver el resultado?", key="v2_rl_hyp")
            rv_notes = st.text_area("Notas", key="v2_rl_notes")
            if st.button("Registrar en el Research Lab", key="v2_rl_button"):
                exp_id = research_lab.log_experiment(
                    "GABI-MF-v2", rv_stage, rv_hypothesis,
                    universe=("S&P 500 histórico completo, sin muestreo" if v2_test["mode"] == "validation"
                             else f"S&P 500 histórico, muestra de {v2_max_symbols}"),
                    factors="Value/Quality/Momentum/Risk", n_positions=int(v2_n_picks),
                    rebalance={1: "Monthly", 3: "Quarterly", 6: "Semiannual", 12: "Annual"}[v2_interval],
                    cost_model=f"V2: {v2_commission:.2f}$ fijo + {v2_spread:.0f}pb spread, solo sobre variación de peso real",
                    is_start=v2_start.isoformat(), is_end=v2_end.isoformat(), family=rv_family or None,
                    sharpe=daily["sharpe"], sortino=daily["sortino"], max_drawdown=daily["max_drawdown"],
                    total_return=float(nav.iloc[-1] / nav.iloc[0] - 1), n_periods=len(returns),
                    periods_per_year=252, returns=returns, notes=rv_notes or None,
                    data_fingerprint=v2_test.get("data_fingerprint"),
                    result={"data_quality": v2_test.get("data_quality", {}),
                           "mode": v2_test["mode"], "turnover_medio": v2_test["turnover_medio"],
                           "comision_total": v2_test["comision_total"], "capital_inicial": v2_capital},
                )
                st.success(f"Experimento #{exp_id} registrado — consúltalo en 🔬 Research Lab.")

with st.expander("Comparar qué bloque aporta más en esta fecha"):
    st.caption("Comparación exploratoria de una sola fecha. Para ajustar pesos hacen falta varias fechas y validación posterior independiente.")
    factor_rows = []
    for label, column in (("Value", "value_score"), ("Quality", "quality_score"),
                          ("Momentum", "momentum_score"), ("Risk", "risk_score")):
        leaders = df[df[column].notna() & (df["score_coverage"] >= .5)].nlargest(int(eval_n), column)
        outcome = evaluation.evaluate(leaders.index.tolist(), as_of_str, 12, cost_bps)
        factor_rows.append({
            "Bloque": label,
            "Retorno 12 meses": outcome["portfolio_return"] * 100 if outcome.get("portfolio_return") is not None else None,
            "SPY": outcome["benchmark_return"] * 100 if outcome.get("benchmark_return") is not None else None,
            "Cobertura": f"{outcome.get('available', 0)}/{outcome.get('requested', len(leaders))}",
        })
    st.dataframe(pd.DataFrame(factor_rows), hide_index=True, width="stretch",
                 column_config={"Retorno 12 meses": st.column_config.NumberColumn(format="%.1f%%"),
                                "SPY": st.column_config.NumberColumn(format="%.1f%%")})
