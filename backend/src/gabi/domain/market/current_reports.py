"""8-K current reports classified by the SEC «Item» codes, without AI (#292). Version ``8k-items-v1``.

The SEC submissions index lists each 8-K with the Items the company ticked
(field ``items``, e.g. ``"2.02,9.01"``). This table translates every code of
the current Form 8-K into a plain-language category. A code outside the table
(old pre-2004 numbering, a typo, a future Item) is «sin clasificar», never
guessed. Nothing here reads the text of the filing.
"""

import re

VERSION = "8k-items-v1"
FORMS = ("8-K", "8-K/A")

# category: plain-language label shown to the investor.
CATEGORIES: dict[str, str] = {
    "contratos": "Contrato importante (firma o fin)",
    "quiebra": "Quiebra o administración judicial",
    "minas": "Seguridad en minas",
    "ciberseguridad": "Incidente de ciberseguridad importante",
    "adquisicion": "Compra o venta de activos completada",
    "resultados": "Resultados",
    "deuda": "Deuda nueva o que vence antes de tiempo",
    "reestructuracion": "Reestructuración o deterioro (pérdida de valor de activos)",
    "exclusion_bolsa": "Aviso de exclusión de bolsa",
    "acciones": "Emisión de acciones o cambio de derechos de los accionistas",
    "auditor": "Cambio de auditor",
    "reexpresion": "Las cuentas anteriores ya no son fiables (reexpresión)",
    "control": "Cambio de control de la empresa",
    "directivos": "Cambio de directivos o consejeros",
    "gobierno": "Estatutos, código ético u otros cambios de gobierno",
    "votaciones": "Votaciones de accionistas",
    "titulizacion": "Valores respaldados por activos",
    "comunicacion": "Comunicación al mercado",
    "otros": "Otros hechos",
    "anexos": "Estados financieros y anexos",
    "sin_clasificar": "Sin clasificar",
}

# Item code of the current Form 8-K → category.
ITEMS: dict[str, str] = {
    "1.01": "contratos", "1.02": "contratos", "1.03": "quiebra", "1.04": "minas", "1.05": "ciberseguridad",
    "2.01": "adquisicion", "2.02": "resultados", "2.03": "deuda", "2.04": "deuda",
    "2.05": "reestructuracion", "2.06": "reestructuracion",
    "3.01": "exclusion_bolsa", "3.02": "acciones", "3.03": "acciones",
    "4.01": "auditor", "4.02": "reexpresion",
    "5.01": "control", "5.02": "directivos", "5.03": "gobierno", "5.04": "gobierno", "5.05": "gobierno",
    "5.06": "gobierno", "5.07": "votaciones", "5.08": "votaciones",
    "6.01": "titulizacion", "6.02": "titulizacion", "6.03": "titulizacion", "6.04": "titulizacion",
    "6.05": "titulizacion",
    "7.01": "comunicacion", "8.01": "otros", "9.01": "anexos",
}

# Items that ask the investor to review an open idea (#247): bankruptcy, delisting notice,
# change of auditor and financial statements that can no longer be relied on.
REVIEW_ITEMS = ("1.03", "3.01", "4.01", "4.02")

_CODE = re.compile(r"\d+\.\d{2}")


def parse_items(text: str | None) -> list[str]:
    """Codes as the SEC lists them, in order and without repeats; blanks dropped."""
    seen: list[str] = []
    for part in (text or "").split(","):
        code = part.strip()
        if code and code not in seen:
            seen.append(code)
    return seen


def classify(code: str) -> dict:
    """One Item: its category and label; an unknown code is «sin clasificar», never guessed."""
    category = ITEMS.get(code) if _CODE.fullmatch(code) else None
    if category is None:
        return {"code": code, "category": "sin_clasificar", "label": f"{CATEGORIES['sin_clasificar']} (Item {code})",
                "review": False}
    return {"code": code, "category": category, "label": CATEGORIES[category], "review": code in REVIEW_ITEMS}


def filing_url(cik: str | int, accession: str, primary_document: str | None) -> str:
    """The SEC page of the filing: its main document, or the filing index when none is listed."""
    folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
    return f"{folder}/{primary_document}" if primary_document else f"{folder}/{accession}-index.htm"


def from_submissions(payload: dict) -> list[dict]:
    """The 8-K and 8-K/A rows of a submissions payload's ``recent`` block, as stored (newest first)."""
    recent = (payload.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []

    def column(name: str, index: int):
        values = recent.get(name) or []
        return values[index] if index < len(values) else None

    rows = []
    for index, form in enumerate(forms):
        accession = column("accessionNumber", index)
        if form not in FORMS or not accession:
            continue
        rows.append({"accession": accession, "form": form, "filed_date": column("filingDate", index),
                     "report_date": column("reportDate", index) or None, "items": column("items", index) or "",
                     "primary_document": column("primaryDocument", index) or None})
    return sorted(rows, key=lambda row: (row["filed_date"] or "", row["accession"]), reverse=True)


def describe(row: dict, cik: str | int) -> dict:
    """A stored row with its classified Items, the SEC link and whether it asks for a review."""
    items = [classify(code) for code in parse_items(row.get("items"))]
    return {"accession": row["accession"], "form": row["form"], "amendment": row["form"].endswith("/A"),
            "filed_date": row["filed_date"], "report_date": row.get("report_date"),
            "url": filing_url(cik, row["accession"], row.get("primary_document")),
            "items": items, "review": any(item["review"] for item in items)}
