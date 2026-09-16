import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import streamlit as st

from gabi import journal, storage

st.set_page_config(page_title="Diario de inversión — GABI", page_icon="📓", layout="wide")
st.title("📓 Diario de inversión")
st.markdown(
    "Antes de invertir, escribe tu tesis: por qué compras, a qué precio, qué esperas que pase "
    "y qué demostraría que te equivocaste. Revísala pasados unos meses — se aprende mucho más "
    "entendiendo **por qué** salió bien o mal que acumulando indicadores. Echa un vistazo también "
    "al [🌐 Panel Macro](/Panel_Macro) — el contexto de tipos, inflación y crédito suele ser tan "
    "relevante para el resultado como la propia empresa."
)

journal.init_db()

prefill_symbol = st.session_state.pop("journal_prefill_symbol", None)

with st.expander("➕ Nueva entrada", expanded=prefill_symbol is not None):
    with st.form("new_journal_entry", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        symbol = col1.text_input("Ticker", value=(prefill_symbol or "")).upper().strip()
        horizon = col2.selectbox(
            "Horizonte temporal",
            ["Corto (<6 meses)", "Medio (6-12 meses)", "Largo (>12 meses)"], index=1,
        )
        default_price = 0.0
        if prefill_symbol:
            p = storage.get_prices(prefill_symbol)
            if not p.empty:
                default_price = float(p["close"].iloc[-1])
        entry_price = col3.number_input("Precio de entrada ($)", min_value=0.0, value=default_price, step=0.5)

        thesis = st.text_area(
            "Tesis — ¿por qué gana dinero esta empresa? ¿qué la protege de la competencia "
            "(moat, pricing power, switching costs)? ¿qué parece estar descontando ya el precio?",
            height=110,
        )

        st.markdown("**Escenarios de valoración** — piensa en rangos, no en un número exacto")
        c1, c2, c3 = st.columns(3)
        bear_price = c1.number_input("Precio bajista ($)", min_value=0.0, value=0.0, step=0.5)
        base_price = c2.number_input("Precio base ($)", min_value=0.0, value=0.0, step=0.5)
        bull_price = c3.number_input("Precio alcista ($)", min_value=0.0, value=0.0, step=0.5)

        c4, c5, c6 = st.columns(3)
        bear_prob = c4.slider("Prob. bajista (%)", 0, 100, 20)
        base_prob = c5.slider("Prob. base (%)", 0, 100, 50)
        bull_prob = c6.slider("Prob. alcista (%)", 0, 100, 30)
        total_prob = bear_prob + base_prob + bull_prob
        if total_prob != 100:
            st.caption(
                f"⚠️ Las probabilidades suman {total_prob}%, no 100% "
                "(se normalizan automáticamente al calcular el valor esperado)."
            )

        catalysts = st.text_area(
            "Catalizadores esperados — ¿qué puede hacer que el mercado revalúe la empresa? "
            "(resultados, márgenes, recortes de tipos, productos, recompras, reducción de deuda...)",
            height=80,
        )
        risks = st.text_area("Riesgos / qué demostraría que estabas equivocado", height=80)
        position_size_pct = st.slider("Tamaño de la posición (% de tu cartera)", 0, 100, 0)
        notes = st.text_area("Notas adicionales", height=60)

        if st.form_submit_button("💾 Guardar entrada"):
            if not symbol:
                st.error("Indica un ticker.")
            else:
                journal.add_entry({
                    "symbol": symbol,
                    "created_at": date.today().isoformat(),
                    "horizon": horizon,
                    "entry_price": entry_price or None,
                    "thesis": thesis,
                    "bear_price": bear_price or None,
                    "base_price": base_price or None,
                    "bull_price": bull_price or None,
                    "bear_prob": bear_prob,
                    "base_prob": base_prob,
                    "bull_prob": bull_prob,
                    "catalysts": catalysts,
                    "risks": risks,
                    "position_size_pct": position_size_pct,
                    "notes": notes,
                })
                st.success(f"Entrada guardada para {symbol}.")
                st.rerun()

st.divider()
st.subheader("📋 Tus entradas")

entries = journal.list_entries()
if entries.empty:
    st.info(
        "Todavía no has escrito ninguna tesis. Usa '➕ Nueva entrada' arriba, o el botón "
        "'📝 Escribir tesis' desde la Ficha de una empresa."
    )
else:
    only_open = st.checkbox("Mostrar solo entradas abiertas (sin revisar)", value=False)
    view = entries[entries["status"] == "abierta"] if only_open else entries

    for _, e in view.iterrows():
        ev = journal.compute_expected_value(
            e["entry_price"], e["bear_price"], e["base_price"], e["bull_price"],
            e["bear_prob"], e["base_prob"], e["bull_prob"],
        )
        ev_txt = f" · Retorno esperado: {ev['expected_return_pct']:+.1f}%" if ev else ""
        status_icon = "🟢" if e["status"] == "abierta" else "✅"

        with st.expander(f"{status_icon} {e['symbol']} — {e['created_at']} ({e['horizon']}){ev_txt}"):
            colx, coly = st.columns(2)
            colx.markdown(f"**Precio de entrada:** {e['entry_price']}")
            coly.markdown(f"**Tamaño de posición:** {e['position_size_pct']}%")

            st.markdown(f"**Tesis:** {e['thesis'] or '—'}")
            st.markdown(
                f"**Escenarios:** bajista {e['bear_price']} ({e['bear_prob']}%) · "
                f"base {e['base_price']} ({e['base_prob']}%) · alcista {e['bull_price']} ({e['bull_prob']}%)"
            )
            if ev:
                st.markdown(
                    f"**Precio esperado (ponderado):** {ev['expected_price']:.2f} → "
                    f"retorno esperado **{ev['expected_return_pct']:+.1f}%**"
                )
            st.markdown(f"**Catalizadores:** {e['catalysts'] or '—'}")
            st.markdown(f"**Riesgos / invalidación:** {e['risks'] or '—'}")
            if e["notes"]:
                st.markdown(f"**Notas:** {e['notes']}")

            st.divider()
            if e["status"] == "abierta":
                st.markdown("**Revisar esta tesis**")
                with st.form(f"review_{e['id']}"):
                    latest_price = None
                    p = storage.get_prices(e["symbol"])
                    if not p.empty:
                        latest_price = float(p["close"].iloc[-1])
                    review_price = st.number_input(
                        "Precio actual", min_value=0.0, value=latest_price or 0.0, step=0.5, key=f"rp_{e['id']}",
                    )
                    review_notes = st.text_area("¿Qué ha pasado? ¿Qué has aprendido?", key=f"rn_{e['id']}")
                    if st.form_submit_button("✅ Marcar como revisada"):
                        journal.update_review(e["id"], date.today().isoformat(), review_price, review_notes)
                        st.success("Revisión guardada.")
                        st.rerun()
            else:
                real_return = None
                if e["entry_price"] and e["review_price"]:
                    real_return = (e["review_price"] / e["entry_price"] - 1) * 100
                st.markdown(f"**Revisada el:** {e['review_date']}")
                if real_return is not None:
                    st.markdown(f"**Retorno real:** {real_return:+.1f}% (precio de revisión: {e['review_price']})")
                st.markdown(f"**Aprendizaje:** {e['review_notes'] or '—'}")

            if st.button("🗑️ Eliminar entrada", key=f"del_{e['id']}"):
                journal.delete_entry(e["id"])
                st.rerun()
