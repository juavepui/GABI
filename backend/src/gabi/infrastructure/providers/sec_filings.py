"""Text tables of a pinned SEC filing, for the reviewed pre-XBRL extraction."""
import hashlib
import html as html_std
import re

from lxml import html

from gabi.domain.research.legacy_filings import reviewed_rows

TABLES = re.compile(r"<table\b[^>]*>.*?</table\s*>", re.I | re.S)


def table_lines(source: str) -> list[list[str]]:
    tables = []
    for match in TABLES.finditer(source):
        markup = match.group()
        if re.search(r"<tr\b", markup, re.I):
            node = html.fromstring(markup)
            lines = [" ".join(row.text_content().split()) for row in node.xpath(".//tr")]
        else:
            text = html_std.unescape(re.sub(r"<[^>]+>", " ", markup))
            lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
        tables.append(lines)
    return tables


def extract_reviewed(content: bytes, contract: dict) -> list[dict]:
    if hashlib.sha256(content).hexdigest() != contract["sha256"]:
        raise ValueError("Filing differs from the reviewed document")
    return reviewed_rows(table_lines(content.decode(contract.get("encoding", "cp1252"), errors="replace")), contract)
