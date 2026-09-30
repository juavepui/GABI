"""Streamlit adapter for the shared published Factor Zoo/SIC use case."""

import hashlib
import threading

import pandas as pd
import streamlit as st

from gabi.application.errors import QueryError
from gabi.application.research.published_factors import PublishedFactorQueries

from . import evidence_catalog, factor_sector_stability
from .ui_helpers import METRIC_INFO


class LegacyPublishedFactorSource:
    """Adapt the already published Streamlit verifier without changing its seals."""

    def __init__(self):
        root = evidence_catalog.config.BASE_DIR
        output = factor_sector_stability.OUTPUT
        artifacts = ("cross-section-test", "factor-zoo", "tail-effect-test", "placebo-engine",
                     "block-bootstrap", "rank-stability", "factor-zoo-sector")
        self.paths = (root / "docs/evidence-confidence/preregistro.json",
                      root / "docs/evidence-confidence/sources.json",
                      *(root / "docs" / name / "resultado.json" for name in artifacts),
                      output / "preregistro.json",
                      factor_sector_stability.Path(factor_sector_stability.__file__),
                      *(output / name for name in ("filings.csv", "assignments.csv", "sector_ic.csv",
                                                   "coverage.csv", "factor_coverage.csv")))
        self.lock = threading.Lock()
        self.version = None
        self.result = None
        self.exports = {}

    def _stamp(self):
        stamps = []
        total = 0
        for path in self.paths:
            stat = path.stat()
            if stat.st_size > 6_000_000:
                raise ValueError("Published artifact exceeds size limit")
            total += stat.st_size
            stamps.append((stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        if total > 16_000_000:
            raise ValueError("Published artifacts exceed total size limit")
        return tuple(stamps)

    def read(self) -> dict:
        with self.lock:
            try:
                before = self._stamp()
                if self.result is not None and before == self.version:
                    return self.result
                self.result, self.exports = None, {}
                catalogue = evidence_catalog.load()
                if not catalogue["available"] or not catalogue["factors"]:
                    raise ValueError("Published catalogue unavailable")
                sector_source = catalogue["sources"]["factor-zoo-sector"]
                zoo_source = catalogue["sources"]["factor-zoo"]
                sector = factor_sector_stability.load_saved(sector_source["sha256"])
                if before != self._stamp():
                    raise ValueError("Published artifacts changed during verification")
                self.result = {"zoo": {"factors": catalogue["factors"], "n_dates": sector["n_dates"]},
                               "sector": sector, "zoo_sha256": zoo_source["sha256"],
                               "sector_sha256": sector_source["sha256"]}
                self.version = before
                return self.result
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.result, self.version = None, None
                raise QueryError("published_factors_unavailable", "No se puede verificar el mapa publicado.") from exc

    def download(self, name: str) -> str:
        if name not in {"sector_ic.csv", "coverage.csv", "factor_coverage.csv"}:
            raise QueryError("published_export_not_found", "La exportación publicada no existe.", 404)
        result = self.read()
        with self.lock:
            if name not in self.exports:
                try:
                    contents = (factor_sector_stability.OUTPUT / name).read_text(encoding="utf-8")
                    if hashlib.sha256(contents.encode()).hexdigest() != result["sector"]["artifacts_sha256"][name]:
                        raise ValueError("Published export seal differs")
                    self.exports[name] = contents
                except (OSError, ValueError, KeyError) as exc:
                    raise QueryError("published_factors_unavailable", "No se puede verificar la exportación.") from exc
            return self.exports[name]


@st.cache_resource
def _source(root: str) -> LegacyPublishedFactorSource:
    return LegacyPublishedFactorSource()


def render() -> None:
    st.subheader("Mapa de evidencia por factor · #48")
    query = PublishedFactorQueries(_source(str(evidence_catalog.config.BASE_DIR)))
    try:
        result = query.overview()
    except QueryError as exc:
        st.warning(exc.message)
        return
    st.caption(f"{len(result['factors'])} señales declaradas y {result['n_dates']} trimestres congelados "
               "de 2011–2025. Evidencia retrospectiva; los diagnósticos por industria no seleccionan "
               "pesos ni aportan validación independiente.")

    primary = pd.DataFrame([{"Factor": METRIC_INFO.get(row["metric"], {}).get("label", row["metric"]),
                             "IC medio": row["ic_mean"], "ICIR": row["icir"],
                             "p Holm": row["p_holm"], "Clasificación": row["classification"],
                             "Trimestres": row["n_periods"], "Spread Q5−Q1": row["q_spread"]}
                            for row in result["factors"]])
    st.dataframe(primary, hide_index=True, width="stretch")
    st.caption("El contraste principal conserva HAC y Holm de las 13 señales. "
               f"{result['holm_significant_count']} superan Holm al 5 %.")
    st.write("**Estabilidad por industria SIC fechada**")
    st.caption("Clasificación SEC conocida antes de cada señal, en divisiones SIC amplias. SIC y GICS son "
               f"clasificaciones distintas. IC descriptivo con ≥{result['minimum_pairs']} pares por trimestre; "
               f"el resumen necesita ≥{result['minimum_summary_periods']} trimestres. "
               "No se calculan nuevos p-valores ni se cambia la confianza de evidencia.")
    st.metric("Cobertura de industria · empresa/fecha",
              f"{result['classified_fraction']:.1%}" if result["classified_fraction"] is not None else "No estimable")
    st.caption(f"{result['n_classified']:,} de {result['n_eligible']:,} observaciones elegibles, "
               "incluidas las que no tienen retorno futuro.")
    by_metric = {row["metric"]: row for row in result["factors"]}
    metric = st.selectbox("Señal · estabilidad por industria", list(by_metric), key="sic_factor",
                          format_func=lambda name: METRIC_INFO.get(name, {}).get("label", name))
    rows = []
    for detail in by_metric[metric]["sic_divisions"]:
        rows.append({"División SIC": detail["division"], "Industria": detail["name"],
                     "IC medio": detail["ic_mean"], "ICIR": detail["icir"],
                     "Trimestres estimables": detail["n_periods"],
                     "% IC positivo": detail["positive_fraction"],
                     "Soporte temporal": "Suficiente" if detail["status"] == "sufficient_periods" else "Insuficiente",
                     **{f"IC {window['period']}": window["ic_mean"] for window in detail["windows"]}})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.expander("Cobertura y periodos no estimables · SIC"):
        coverage = pd.DataFrame(result["coverage"])
        st.dataframe(coverage.rename(columns={"date": "fecha"}), hide_index=True, width="stretch")
        st.caption("Las categorías sin muestra y las fechas sin IC se conservan en el artefacto, "
                   "sin agruparlas ni imputarlas.")
        for name, label in (("sector_ic.csv", "IC por industria y trimestre"),
                            ("coverage.csv", "Cobertura y exclusiones"),
                            ("factor_coverage.csv", "Cobertura por señal")):
            st.download_button(f"Descargar {label}", query.export(name), name, "text/csv", key="sic_" + name)
