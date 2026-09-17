import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import academic_factors, config, data_fetch, edgar, evaluation, multifactor_backtest, screener_asof, universe
from gabi.ui_helpers import FRACTION_COLUMNS, METRIC_INFO, build_color_basis, gradient_style, translate_sector

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
        edgar_result = edgar.ensure_edgar_data(symbols, progress_cb=edgar_progress_cb)
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

if df.empty:
    st.info("Sin datos todavía para este universo. Pulsa 'Preparar datos' arriba.")
    st.stop()

has_price = df["market_cap"].notna()
n_with_price = int(has_price.sum())
n_with_fundamentals = int(df["roic"].notna().sum())
st.caption(
    f"{len(df)} empresas en la tabla · {n_with_fundamentals} con fundamentales reconstruidos · "
    f"{n_with_price} con precio/capitalización de esa fecha (requiere histórico de precios profundo)."
)

hide_no_data = st.checkbox("Ocultar empresas sin ningún dato reconstruido", value=True)
filtered = df[df["roic"].notna() | df["market_cap"].notna()] if hide_no_data else df

DISPLAY_KEYS = [
    "resolved_title", "sector", "market_cap", "price", "pe", "pb", "roic",
    "gross_margin", "operating_margin", "debt_to_equity", "net_debt_to_ebitda",
    "revenue_growth_yoy", "revenue_cagr_3y", "fcf_cagr_3y", "fundamentals_period_end",
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
    "🟩 mejor · 🟨 medio · 🟥 peor, comparado con el resto de empresas de su sector (sector actual — no "
    "hay fuente gratuita de sector histórico). Las columnas sin color no se usan para puntuar."
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

**Qué probar**: sube "Empresas por periodo" a 20 y compara — en nuestras pruebas, 20 posiciones bajó el
drawdown máximo sin apenas perder Sharpe/Sortino frente a 10 (ver README, sección de backtesting). Prueba
también a subir "Coste por lado" a 25-50 puntos básicos — el margen de la estrategia frente al SPY se
estrecha mucho más de lo que parece a primera vista con solo 10pb.
        """
    )

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
    if st.form_submit_button("Ejecutar backtest multifactor"):
        try:
            test = multifactor_backtest.run(bt_start.isoformat(), bt_end.isoformat(), interval,
                                            n_picks, bt_cost, max_symbols=universe_size)
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
        with st.spinner("Descargando series de Kenneth French (Fama-French 5 factores + Momentum)..."):
            ff_factors = academic_factors.fetch_ff_factors()
        reg = academic_factors.regress_returns_on_factors(test["periods"], ff_factors)
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric(
            "Alfa anualizado", f"{reg['alpha_anualizado']:+.2%}",
            help="Retorno anualizado que NO explican los 6 factores académicos — la parte 'propia' de la "
                 "estrategia, si es que existe alguna.",
        )
        rc2.metric(
            "t-stat del alfa", f"{reg['t_stat']['alpha']:+.2f}",
            help="Por debajo de ~2.0 no se puede distinguir de cero con confianza estadística habitual; "
                 "Harvey, Liu y Zhu proponen exigir >3.0 precisamente porque se prueban muchas configuraciones "
                 "en este tipo de investigación (ver HIPOTESIS_CONGELADA.md).",
        )
        rc3.metric("R² de la regresión", f"{reg['r2']:.2f}",
                  help="Qué % de la varianza del retorno de la estrategia explican los 6 factores conocidos — "
                       "más alto significa que la estrategia se parece más a una combinación de exposiciones ya "
                       "documentadas y menos a algo genuinamente distinto.")
        st.caption(f"Regresión con {reg['periodos_alineados']}/{reg['periodos_totales']} periodos alineados "
                  f"({reg['dof']} grados de libertad tras 6 factores + alfa).")
        betas_df = pd.DataFrame([
            {"Factor": f, "Qué mide": label, "Beta": reg["coef"][f], "t-stat": reg["t_stat"][f]}
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
                "t-stat": st.column_config.NumberColumn(format="%.2f"),
            },
        )
    except (ValueError, RuntimeError, ImportError) as exc:
        st.warning(f"No se pudo calcular el contraste con factores académicos: {exc}")
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
