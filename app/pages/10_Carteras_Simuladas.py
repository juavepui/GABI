import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import data_fetch, sim_portfolios, storage

st.title("🧪 Carteras simuladas")
st.caption("Crea varias carteras, registra operaciones en fechas pasadas y compara resultados. "
           "Solo se descargan precios públicos; no se conecta ninguna cuenta ni se envían órdenes.")
st.info("Los precios son cierres de Yahoo Finance en la divisa de cada ticker, no cotizaciones ejecutables de eToro. "
        "El spread es una hipótesis editable; eToro no publica un histórico fijo por símbolo.")

create_tab, trade_tab, results_tab, strategy_tab = st.tabs(
    ["Crear cartera", "Operaciones", "Resultados", "Probar estrategia"]
)

with create_tab:
    with st.form("create_sim_portfolio"):
        name = st.text_input("Nombre de la cartera", placeholder="Calidad y momentum")
        base_currency = st.selectbox("Divisa base de la cartera", ["USD", "EUR"])
        initial_cash = st.number_input(f"Capital inicial ({base_currency})", min_value=1.0, value=10000.0,
                                       step=1000.0)
        c1, c2, c3 = st.columns(3)
        stock_fee = c1.number_input("Comisión inicial: acción (divisa del ticker)", min_value=0.0, value=1.0, step=.5)
        etf_fee = c2.number_input("Comisión inicial: ETF (divisa del ticker)", min_value=0.0, value=0.0, step=.5)
        spread_bps = c3.number_input("Spread total supuesto (puntos básicos)", min_value=0.0,
                                     value=10.0, step=1.0)
        if st.form_submit_button("Crear cartera"):
            try:
                portfolio_id = sim_portfolios.create_portfolio(name, initial_cash, stock_fee, etf_fee, spread_bps,
                                                               base_currency)
                st.success(f"Cartera #{portfolio_id} creada.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.markdown(
        "[eToro publica las tarifas vigentes](https://www.etoro.com/es/trading/fees/): "
        "algunas acciones tienen 1 o 2 USD por apertura y cierre según país y bolsa; "
        "los ETF no tienen comisión de operación. El diferencial de mercado varía. "
        "Comprueba el coste estimado de tu instrumento en eToro y ajusta esta cartera antes de simular. "
        "El cambio y su coste se pueden introducir por operación. No se modelan impuestos, CFD ni financiación."
    )

portfolios = sim_portfolios.list_portfolios()
if portfolios.empty:
    with trade_tab:
        st.info("Crea una cartera para registrar operaciones simuladas.")
    with results_tab:
        st.info("Todavía no hay carteras que comparar.")
    with strategy_tab:
        st.info("Crea una cartera para definir sus hipótesis de costes.")
    st.stop()

options = {f"{row['name']} (#{row['id']})": int(row["id"]) for _, row in portfolios.iterrows()}
selection = st.selectbox("Cartera activa", list(options))
portfolio_id = options[selection]
portfolio = sim_portfolios.get_portfolio(portfolio_id)

with trade_tab:
    st.write(f"Capital inicial: **{portfolio['initial_cash']:,.2f} {portfolio['base_currency']}** · "
             f"comisión inicial acción: **{portfolio['stock_commission']:.2f} en divisa del ticker** · "
             f"ETF: **{portfolio['etf_commission']:.2f} en divisa del ticker** · "
             f"spread supuesto: **{portfolio['spread_bps']:.0f} pb**")
    symbol = st.text_input("Ticker para consultar", placeholder="AAPL").strip().upper()
    if symbol:
        prices = storage.get_prices(symbol)
        if not prices.empty:
            latest = prices.dropna(subset=["close"])
            if not latest.empty:
                st.caption(f"Último cierre cacheado de {symbol}: {latest['close'].iloc[-1]:.2f} en divisa del ticker "
                           f"({latest.index[-1].date()}). Puede estar retrasado.")
        if st.button("Actualizar precios públicos de este ticker"):
            pairs = [sim_portfolios.fx_symbol(c, portfolio["base_currency"])
                     for c in ("USD", "EUR", "GBP") if c != portfolio["base_currency"]]
            failed = data_fetch.fetch_prices_batch([symbol, "SPY"] + pairs, period="max")
            if failed:
                st.error(str(failed))
            else:
                st.success("Histórico descargado.")
                st.rerun()

    with st.form("add_sim_trade"):
        c1, c2, c3 = st.columns(3)
        trade_symbol = c1.text_input("Ticker", value=symbol).strip().upper()
        asset_type = c2.selectbox("Instrumento", ["Acción", "ETF"])
        side = c3.selectbox("Operación simulada", ["Comprar", "Vender"])
        c4, c5 = st.columns(2)
        requested_date = c4.date_input("Fecha solicitada", value=date.today(), max_value=date.today())
        notional = c5.number_input("Importe a precio medio (divisa de cotización)", min_value=0.01,
                                   value=100.0, step=10.0)
        c6, c7, c8 = st.columns(3)
        market = c6.selectbox("Mercado", list(sim_portfolios.MARKETS),
                              format_func=lambda code: sim_portfolios.MARKETS[code])
        quote_currency = c7.selectbox("Divisa de cotización", ["USD", "EUR", "GBP"])
        manual_fx = c8.number_input(f"Cambio: {portfolio['base_currency']} por 1 {quote_currency} (0 = caché)",
                                    min_value=0.0, value=0.0, format="%.6f")
        c9, c10, c11 = st.columns(3)
        trade_fee = c9.number_input("Comisión equivalente en divisa de cotización",
                                    min_value=0.0, value=float(portfolio["stock_commission"]), step=.5)
        trade_spread = c10.number_input("Spread de esta operación (pb)", min_value=0.0,
                                        value=float(portfolio["spread_bps"]))
        fx_fee = c11.number_input("Coste de conversión (pb)", min_value=0.0, value=0.0)
        if st.form_submit_button("Registrar operación simulada"):
            try:
                trade = sim_portfolios.add_trade(
                    portfolio_id, trade_symbol, "STOCK" if asset_type == "Acción" else "ETF",
                    "BUY" if side == "Comprar" else "SELL", requested_date.isoformat(), notional,
                    market=market, quote_currency=quote_currency, commission=trade_fee,
                    spread_bps=trade_spread, fx_rate=manual_fx or None, fx_fee_bps=fx_fee,
                )
                st.success(f"Operación simulada registrada al cierre del {trade['execution_date']} "
                           f"({trade['reference_close']:.2f} {quote_currency}); "
                           f"comisión {trade['commission']:.2f} {quote_currency}.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.caption("Se utiliza la primera sesión del mercado elegido desde la fecha. Si falta su precio "
               "en el caché, actualiza el histórico. Se permiten fracciones de título. Las compras deben tener efectivo "
               "y las ventas posición suficiente. eToro expresa algunas comisiones en USD: introduce aquí su "
               "equivalente en la divisa del ticker. Para valorar una cartera con cambio se necesita su "
               "histórico, aunque escribas manualmente el cambio de la operación.")
    trades = sim_portfolios.list_trades(portfolio_id)
    if not trades.empty:
        st.dataframe(trades[["execution_date", "symbol", "market", "asset_type", "side", "reference_close",
                             "notional", "quote_currency", "commission", "spread_bps", "fx_rate", "fx_fee_bps"]],
                     hide_index=True, width="stretch")
        if st.button("Deshacer la última operación introducida"):
            try:
                sim_portfolios.undo_last_trade(portfolio_id)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

with results_tab:
    trades = sim_portfolios.list_trades(portfolio_id)
    if not trades.empty and st.button("Actualizar precios de esta cartera y SPY"):
        symbols = trades["symbol"].unique().tolist() + ["SPY"]
        symbols += [p for p in {sim_portfolios.fx_symbol(c, portfolio["base_currency"])
                                 for c in trades["quote_currency"].unique().tolist() + ["USD"]} if p]
        failed = data_fetch.fetch_prices_batch(symbols, period="max")
        st.success(f"Actualizados {len(symbols) - len(failed)} símbolos; fallos: {len(failed)}")
        if failed:
            st.dataframe([{"Ticker": s, "Motivo": r} for s, r in failed.items()])
        st.rerun()
    if trades.empty:
        st.info("Añade una operación simulada para ver la evolución.")
    else:
        try:
            result = sim_portfolios.portfolio_history(portfolio_id)
            summary = sim_portfolios.summarize(result)
            if summary.get("status") == "complete":
                c1, c2, c3 = st.columns(3)
                c1.metric("Valor", f"{summary['value']:,.2f} {portfolio['base_currency']}", f"{summary['return']:+.1%}")
                c2.metric("SPY (misma fecha)", f"{summary['benchmark_return']:+.1%}"
                          if summary["benchmark_return"] is not None else "Sin datos")
                c3.metric("Efectivo", f"{result['cash']:,.2f} {portfolio['base_currency']}")
                st.caption(f"Valoración al {summary['as_of']}; SPY es una compra inicial con "
                           "medio spread supuesto y sin ventas posteriores.")
                st.line_chart(result["curve"]["value"], y_label=f"Valor en {portfolio['base_currency']}")
                if summary["max_drawdown"] is not None:
                    sharpe_text = (f"Sharpe histórico: {summary['sharpe']:.2f} · "
                                   if summary["sharpe"] is not None else "")
                    st.caption(f"{sharpe_text}drawdown máximo: {summary['max_drawdown']:.1%}")
            else:
                st.warning("Faltan precios recientes de alguna posición; actualiza el histórico antes de valorar.")
        except ValueError as exc:
            st.error(str(exc))

    st.subheader("Comparar carteras")
    comparisons = []
    for _, row in portfolios.iterrows():
        try:
            summary = sim_portfolios.summarize(sim_portfolios.portfolio_history(int(row["id"])))
            if summary.get("status") == "complete":
                comparisons.append({"Cartera": row["name"], "Desde": sim_portfolios.list_trades(int(row["id"]))["execution_date"].min(),
                                    "Hasta": summary["as_of"], "Retorno %": summary["return"] * 100,
                                    "SPY %": summary["benchmark_return"] * 100 if summary["benchmark_return"] is not None else None,
                                    "Drawdown %": summary["max_drawdown"] * 100 if summary["max_drawdown"] is not None else None})
        except ValueError:
            continue
    if comparisons:
        st.dataframe(pd.DataFrame(comparisons), hide_index=True, width="stretch")
        st.caption("Compara rentabilidades frente a SPY para cada periodo; carteras con fechas distintas "
                   "no son directamente equivalentes. Los resultados pasados no validan una estrategia futura.")

with strategy_tab:
    st.markdown("Prueba un **cruce de medias** con [Backtesting.py](https://github.com/kernc/backtesting.py). "
                "La señal usa el cierre y se ejecuta en la sesión siguiente; incluye la comisión y "
                "el spread supuestos de la cartera activa.")
    st.caption("El test técnico usa la divisa en la que cotiza el ticker y un capital nominal de 10.000 "
               "unidades. No convierte a la divisa base de la cartera.")
    with st.form("sma_backtest"):
        symbol_bt = st.text_input("Ticker de la estrategia", value="SPY").strip().upper()
        asset_bt = st.selectbox("Instrumento del test", ["ETF", "Acción"])
        c1, c2 = st.columns(2)
        start_bt = c1.date_input("Inicio del test", value=date(2023, 1, 1))
        end_bt = c2.date_input("Fin del test", value=date.today(), max_value=date.today())
        c3, c4 = st.columns(2)
        fast = c3.number_input("Media rápida (sesiones)", min_value=2, value=50)
        slow = c4.number_input("Media lenta (sesiones)", min_value=3, value=200)
        if st.form_submit_button("Ejecutar backtest"):
            try:
                test = sim_portfolios.sma_backtest(
                    symbol_bt, start_bt.isoformat(), end_bt.isoformat(), int(fast), int(slow),
                    10000, portfolio["etf_commission"] if asset_bt == "ETF" else portfolio["stock_commission"],
                    portfolio["spread_bps"],
                )
                st.metric("Estrategia", f"{test['strategy_return']:+.1%}")
                st.metric("Comprar y mantener", f"{test['buy_hold_return']:+.1%}")
                st.caption(f"Operaciones cerradas: {test['trades']} · Drawdown máximo: {test['max_drawdown']:.1%}")
                st.line_chart(test["equity_curve"], y_label="Valor en divisa del ticker")
            except (ValueError, ImportError) as exc:
                st.error(f"No se pudo probar la estrategia: {exc}. Descarga el histórico del ticker en Operaciones.")
    st.caption("La comparación 'comprar y mantener' de Backtesting.py es bruta, sin los costes de la estrategia. "
               "Este backtest usa cierres ajustados por splits, pero no incorpora dividendos. "
               "Los resultados de carteras manuales sí usan rentabilidad total ajustada por dividendos. "
               "Este test técnico no modela impuestos, conversión de divisa ni deslizamiento adicional.")
