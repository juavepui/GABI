"""Read-only, whitelisted view of the published Factor Zoo and SIC diagnostic."""

from typing import Protocol

from gabi.application.errors import QueryError


class PublishedFactorSource(Protocol):
    def read(self) -> dict: ...

    def download(self, name: str) -> str: ...


class PublishedFactorQueries:
    def __init__(self, source: PublishedFactorSource):
        self.source = source

    def overview(self) -> dict:
        verified = self.source.read()
        zoo, sector = verified["zoo"], verified["sector"]
        try:
            if not zoo["factors"] or set(zoo["factors"]) != set(sector["factors"]) or zoo["n_dates"] != sector["n_dates"]:
                raise ValueError("Published factor sets differ")
            all_dates = [row for row in sector["coverage"] if row["stratum"] == "all"]
            eligible = sum(int(row["n_eligible"]) for row in all_dates)
            classified = sum(int(row["n_classified"]) for row in all_dates)
            if not all_dates or classified > eligible:
                raise ValueError("Invalid published coverage")
            factors = []
            for metric, data in zoo["factors"].items():
                divisions = []
                for division, detail in sector["factors"][metric].items():
                    divisions.append({
                        "division": division, "name": detail["name"], "ic_mean": detail["ic_mean"],
                        "icir": detail["icir"], "n_periods": detail["n_periods"],
                        "positive_fraction": detail["positive_fraction"], "status": detail["status"],
                        "windows": [{"period": period, "ic_mean": window["ic_mean"],
                                     "n_periods": window["n_periods"]}
                                    for period, window in detail["windows"].items()],
                    })
                factors.append({
                    "metric": metric, "ic_mean": data["media"], "icir": data["icir"],
                    "p_holm": data["p_holm"], "classification": data["classification"],
                    "n_periods": data["n_periods"], "q_spread": data["q_spread"],
                    "sic_divisions": divisions,
                })
            return {
                "status": "RETROSPECTIVE_DESCRIPTIVE", "independent_advantage_demonstrated": False,
                "holm_significant_count": sum(row["p_holm"] is not None and row["p_holm"] < .05
                                              for row in factors),
                "factor_zoo_sha256": verified["zoo_sha256"], "sic_sha256": verified["sector_sha256"],
                "n_dates": zoo["n_dates"], "minimum_pairs": sector["minimum_pairs"],
                "minimum_summary_periods": sector["minimum_summary_periods"],
                "n_eligible": eligible, "n_classified": classified,
                "classified_fraction": classified / eligible if eligible else None,
                "factors": factors,
                "coverage": [{"date": row["fecha"], "stratum": row["stratum"],
                              "n_eligible": row["n_eligible"], "n_identity": row["n_identity"],
                              "n_selected_filing": row["n_selected_filing"],
                              "n_classified": row["n_classified"],
                              "classified_fraction": row["classified_fraction"]}
                             for row in sector["coverage"]],
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise QueryError("published_factors_unavailable",
                             "El mapa de factores publicado tiene una estructura inesperada.", 503) from exc

    def export(self, name: str) -> str:
        return self.source.download(name)
