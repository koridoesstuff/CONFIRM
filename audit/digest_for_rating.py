"""Condense each sampled paper into the few facts a tier-1 rating needs.

Reading 300 full papers is not practical, and not necessary: the rating
depends on whether the article is a randomised trial, what tables it has,
and - for each candidate characteristics table - the row labels, the column
headers and the statistic format of the cells. This writes that and nothing
else, as JSON Lines, one object per paper.

It deliberately does NOT read CONFIRM's output. The digest is built from the
same raw XML a human rater would be reading the rendered version of, so a
rating made from it is blind in the same way theirs is.

Cells are reduced to a shape rather than copied in full: "12.3 (4.5)" becomes
"num (num)", "12 (34.5%)" becomes "num (pct)". The shape is what decides
whether a row is a mean with a dispersion statistic, a count with a percent,
or a median with an interval - which is the question the rating turns on -
and it keeps the digest small enough to read in one pass.

Usage:
    python audit/digest_for_rating.py
    python audit/digest_for_rating.py --ids audit/gold/tier1_coverage.csv \
        --raw raw_papers --out audit/gold/digest.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

RANDOM_RE = re.compile(
    r"\brandomi[sz]ed\b|\brandomi[sz]ation\b|\brandomly (?:assigned|allocated)\b"
    r"|\brandomi[sz]ed controlled trial\b|\bRCT\b", re.I)
QUAL_RE = re.compile(
    r"\bqualitative\b|\bsemi-?structured interview|\bfocus group|\bthematic analysis\b",
    re.I)
SECONDARY_RE = re.compile(
    r"\bsecondary analysis\b|\bpost ?hoc analysis\b|\bexploratory analysis of\b"
    r"|\bancillary study\b|\bsub-?study\b", re.I)
CHARS_RE = re.compile(
    r"\bbaseline\b|\bcharacteristic|\bdemographic|\bparticipant|\bpatient"
    r"|\bsubject|\bclinical (?:profile|feature)", re.I)

NUM = r"-?\d[\d,]*(?:\.\d+)?"


def flat(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def shape(cell: str) -> str:
    """Reduce a cell to its statistic shape."""
    s = cell.strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    s = re.sub(NUM + r"\s*%", "pct", s)
    s = re.sub(r"\(\s*pct\s*\)", "(pct)", s)
    s = re.sub(NUM, "num", s)
    s = re.sub(r"\bnum\s*\(\s*num\s*\)", "num (num)", s)
    return s[:40]


def row_shapes(table) -> list[dict]:
    """Label plus the shape of the first non-empty data cell, per row."""
    out = []
    for tr in table.findall(".//tr"):
        cells = [flat(c) for c in tr]
        if not cells:
            continue
        label = cells[0]
        rest = [c for c in cells[1:] if c.strip()]
        out.append({"label": label[:70],
                    "shape": shape(rest[0]) if rest else ""})
    return out


def headers(table) -> list[str]:
    """Column headers, from the thead if there is one, else the first row."""
    thead = table.find(".//thead")
    rows = thead.findall(".//tr") if thead is not None else table.findall(".//tr")[:1]
    out = []
    for tr in rows:
        out.append(" | ".join(flat(c)[:40] for c in tr))
    return out


def digest(path: Path) -> dict:
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        return {"pmcid": path.stem, "error": f"unparseable: {exc}"}

    title_el = root.find(".//article-title")
    body = flat(root)

    rec = {
        "pmcid": path.stem,
        "title": flat(title_el)[:200] if title_el is not None else "",
        "mentions_randomisation": bool(RANDOM_RE.search(body)),
        "mentions_qualitative": bool(QUAL_RE.search(body)),
        "mentions_secondary": bool(SECONDARY_RE.search(body)),
        "tables": [],
    }

    for w in root.findall(".//table-wrap"):
        lab = w.find("label")
        cap = w.find("caption")
        label = flat(lab) if lab is not None else ""
        caption = flat(cap) if cap is not None else ""
        entry = {"label": label[:30], "caption": caption[:160]}
        # Only expand tables that look like characteristics tables; the rest
        # are listed by caption alone so the rater can see they exist.
        if CHARS_RE.search(caption) or CHARS_RE.search(label):
            tbl = w.find(".//table")
            if tbl is not None:
                entry["headers"] = headers(tbl)
                entry["rows"] = row_shapes(tbl)[:45]
        rec["tables"].append(entry)

    return rec


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", type=Path,
                        default=Path("audit/gold/tier1_coverage.csv"))
    parser.add_argument("--raw", type=Path, default=Path("raw_papers"))
    parser.add_argument("--out", type=Path,
                        default=Path("audit/gold/digest.jsonl"))
    args = parser.parse_args()

    if not args.ids.exists():
        print(f"{args.ids} not found", file=sys.stderr)
        return 1

    ids = [r["pmcid"].strip() for r in
           csv.DictReader(args.ids.open(encoding="utf-8-sig"))
           if r.get("pmcid", "").strip()]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    missing = 0
    with args.out.open("w", encoding="utf-8") as fh:
        for pmcid in ids:
            path = args.raw / f"{pmcid}.xml"
            if not path.exists():
                fh.write(json.dumps({"pmcid": pmcid, "error": "xml not found"}) + "\n")
                missing += 1
                continue
            fh.write(json.dumps(digest(path), ensure_ascii=False) + "\n")

    size = args.out.stat().st_size
    print(f"papers digested: {len(ids)}")
    if missing:
        print(f"  xml missing:   {missing}")
    print(f"written -> {args.out}  ({size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
