import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import blind_validation as bv

st.title("🔒 Blind Forward Validation")
st.caption(
    "Convierte una promesa de \"no tocar la estrategia hasta tal fecha\" en algo real: cada rebalanceo "
    "queda registrado de forma inmutable (picks, precios, hash encadenado, commit de código), y el "
    "rendimiento frente al SPY queda **oculto hasta la fecha de desbloqueo**. Sigue descargando y "
    "registrando datos con normalidad — solo el resultado se esconde."
)
st.warning(
    "⚠️ Ver el resultado a medias es la forma más humana de arruinar una prueba prospectiva: "
    "\"llevamos seis meses perdiendo, quizá Momentum debería pasar de 25 a 35%...\" — en cuanto se hace "
    "eso, la prueba ha muerto, sin que nadie necesite hacer trampa conscientemente. Por eso esta página "
    "no muestra ningún número de rendimiento mientras una validación sigue bloqueada.",
    icon="⚠️",
)

with st.expander("➕ Crear nueva validación ciega"):
    st.caption(
        "Por defecto, los mismos parámetros de HIPOTESIS_CONGELADA.md: 20 posiciones equiponderadas, "
        "pesos 30/35/25/10, rebalanceo trimestral — para poder retomar literalmente la promesa original "
        "(2026-Q4 → 2027-09-17) si no cambias nada."
    )
    with st.form("create_validation"):
        name = st.text_input("Nombre", value="Hipótesis congelada — prueba prospectiva")
        c1, c2, c3, c4 = st.columns(4)
        w_value = c1.number_input("Peso Value (%)", 0, 100, 30)
        w_quality = c2.number_input("Peso Quality (%)", 0, 100, 35)
        w_momentum = c3.number_input("Peso Momentum (%)", 0, 100, 25)
        w_risk = c4.number_input("Peso Risk (%)", 0, 100, 10)
        c5, c6 = st.columns(2)
        n_positions = c5.number_input("Nº de posiciones", 1, 50, 20)
        rebalance_months = c6.selectbox("Rebalanceo", [1, 3, 6, 12], index=1,
                                        format_func=lambda n: f"Cada {n} meses")
        c7, c8 = st.columns(2)
        start_date = c7.date_input("Fecha de inicio", value=date.today())
        unlock_date = c8.date_input(
            "Fecha de desbloqueo", value=date(2027, 9, 17),
            help="Hasta esta fecha no se mostrará ningún rendimiento. HIPOTESIS_CONGELADA.md proponía "
                 "4 rebalanceos trimestrales reales, ~1 año natural.",
        )
        if st.form_submit_button("Crear validación"):
            try:
                weights = {"value": w_value / 100, "quality": w_quality / 100,
                          "momentum": w_momentum / 100, "risk": w_risk / 100}
                vid = bv.create_validation(name, weights, int(n_positions), int(rebalance_months),
                                           start_date.isoformat(), unlock_date.isoformat())
                st.success(f"Validación #{vid} creada — bloqueada hasta {unlock_date.isoformat()}.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

validations = bv.list_validations()
if validations.empty:
    st.info("Todavía no hay ninguna validación ciega creada.")
    st.stop()


def _status_badge(row) -> str:
    if row["status"] == "broken_early":
        return "⚠️ Sello roto antes de tiempo"
    if date.today().isoformat() >= row["unlock_date"]:
        return "🔓 Desbloqueada"
    return "🔒 Bloqueada"


st.subheader("Validaciones registradas")
display = validations.copy()
display["estado"] = display.apply(_status_badge, axis=1)
st.dataframe(display[["id", "name", "estado", "start_date", "unlock_date", "rebalance_months", "n_positions"]],
            hide_index=True, width="stretch")

options = {f"#{row.id} · {row.name}": row.id for row in validations.itertuples()}
selected_label = st.selectbox("Ver detalle de", list(options))
vid = options[selected_label]
status = bv.get_status(vid)

st.divider()
st.subheader(f"Detalle: {selected_label}")
d1, d2, d3, d4 = st.columns(4)
d1.metric("Estado", "🔓 Desbloqueada" if status["revealed"] else "🔒 Bloqueada")
d2.metric("Rebalanceos registrados", status["n_periods"])
d3.metric("Próximo rebalanceo", status["next_rebalance_due"] or "—")
d4.metric("Días para desbloqueo", status["days_to_unlock"] if not status["revealed"] else 0)

integrity = status["integrity"]
if integrity["ok"]:
    st.success(f"✅ Integridad verificada — cadena de hashes intacta ({integrity['n_periods']} periodo(s)).")
else:
    st.error(f"🚨 La cadena de hashes se rompe en {integrity['broken_at']} — algún registro se modificó "
            "después de crearse.")

can_record = status["next_rebalance_due"] is not None and date.today().isoformat() >= status["next_rebalance_due"]
if st.button("📋 Registrar rebalanceo de hoy", disabled=not can_record,
            help=None if can_record else "Todavía no toca el siguiente rebalanceo."):
    try:
        with st.spinner("Reconstruyendo el ranking de hoy y fijando precios de entrada..."):
            result = bv.record_rebalance(vid)
        st.success(f"Rebalanceo del {result['rebalance_date']} registrado e inmutable — "
                  f"{len(result['symbols'])} posiciones, hash {result['record_hash'][:12]}...")
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))

if not status["revealed"]:
    st.info("🔒 Esta validación sigue bloqueada — no se muestra ningún dato de rendimiento, ni siquiera "
            "si vas ganando o perdiendo frente al SPY. Solo se confirma que los datos se están "
            "registrando correctamente (arriba).")
    with st.expander("Romper el sello antes de tiempo (no recomendado)"):
        st.caption(
            "Esta app no puede impedirte de verdad mirar tus propios datos — pero si lo haces, queda "
            "constancia permanente de que la prueba se rompió antes de tiempo y por qué, igual que se "
            "documentó la ruptura de HIPOTESIS_CONGELADA.md en esta misma sesión."
        )
        reason = st.text_area("Motivo (obligatorio)", key="break_reason")
        if st.button("Romper el sello", type="secondary"):
            try:
                bv.break_seal_early(vid, reason)
                st.warning("Sello roto — a partir de ahora esta validación muestra su rendimiento.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
else:
    perf = status.get("performance")
    if not perf or not perf["periods"]:
        st.info("Desbloqueada, pero todavía no hay ningún rebalanceo registrado.")
    else:
        rows = perf["periods"]
        df = pd.DataFrame(rows)
        df["capital"] = (1 + df["retorno"].fillna(0)).cumprod()
        df["capital_spy"] = (1 + df["retorno_spy"].fillna(0)).cumprod()
        total_return = float(df["capital"].iloc[-1] - 1)
        total_spy = float(df["capital_spy"].iloc[-1] - 1)
        e1, e2 = st.columns(2)
        e1.metric("Retorno acumulado (estrategia)", f"{total_return:+.1%}")
        e2.metric("Retorno acumulado (SPY)", f"{total_spy:+.1%}")
        st.line_chart(df.set_index("rebalance_date")[["capital", "capital_spy"]])
        st.dataframe(df, hide_index=True, width="stretch")
        if st.button("Exportar al Research Lab"):
            try:
                exp_id = bv.export_to_research_lab(vid)
                st.success(f"Exportado como experimento #{exp_id} (fase LIVE_FORWARD) en 🔬 Research Lab.")
            except ValueError as exc:
                st.error(str(exc))
