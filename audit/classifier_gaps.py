"""Look at what the classifier gave up on, and what that costs.

Every other check tests rows the tool decided. The larger population is the
rows it declined: 17,000-odd classified "measure type unknown" and excluded
from the denominator. A row excluded there is not a wrong answer, it is a
question never asked, and a named instrument sitting in that pile is a
checkable row being thrown away.

This does two things.

First it scans the unknown labels for instruments and count phrasings that
classify_measure does not currently recognise, and reports how many rows each
would recover. That is a direct list of what to add, ordered by what it buys.

Second it prints the most common unknown labels outright, recognised or not,
since the frequent ones are where the coverage actually is.

Nothing here changes a verdict. It measures what is being left on the table.

Usage:
    python audit/classifier_gaps.py
    python audit/classifier_gaps.py --top 40
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

# Instruments and count phrasings that are integer-valued by construction.
# Deliberately a different list from the one in grim_check.py: the point is
# to find what that one misses, so reusing it would find nothing.
KNOWN = {
    "MMSE": r"\bMMSE\b|mini[- ]mental",
    "MoCA": r"\bMoCA\b|montreal cognitive",
    "PHQ": r"\bPHQ[- ]?\d*\b|patient health questionnaire",
    "GAD-7": r"\bGAD[- ]?7\b",
    "HADS": r"\bHADS\b|hospital anxiety",
    "PSQI": r"\bPSQI\b|pittsburgh sleep",
    "BDI/BAI": r"\bBDI\b|\bBAI\b|beck (depression|anxiety)",
    "MADRS": r"\bMADRS\b",
    "Barthel": r"\bbarthel\b|\bMBI\b",
    "Berg balance": r"\bberg\b|\bBBS\b",
    "Fugl-Meyer": r"fugl[- ]?meyer|\bFMA\b",
    "SPPB": r"\bSPPB\b|short physical performance",
    "NIHSS": r"\bNIHSS\b",
    "APACHE": r"\bAPACHE\b",
    "Charlson": r"\bcharlson\b|\bCCI\b",
    "SOFA": r"\bSOFA\b",
    "ASA class": r"\bASA\b.{0,12}(class|status|score)",
    "ODI/Oswestry": r"\boswestry\b|\bODI\b",
    "AUDIT": r"\bAUDIT(-C)?\b",
    "ESS/Epworth": r"\bESS\b|epworth",
    "ISI/insomnia": r"\bISI\b|insomnia severity",
    "UPDRS": r"\bUPDRS\b",
    "FIM": r"\bFIM\b|functional independence",
    "mRS": r"\bmRS\b|modified rankin",
    "Katz/Lawton": r"\bkatz\b|\blawton\b|\bIADL\b|\bADL\b",
    "CES-D": r"\bCES[- ]?D\b",
    "STAI": r"\bSTAI\b|state[- ]trait anxiety",
    "WOMAC": r"\bWOMAC\b",
    "GDS": r"\bGDS\b|geriatric depression",
    "PCL/IES": r"\bPCL[- ]?5?\b|\bIES[- ]?R\b",
    "count phrasing": r"\bnumber of\b|\bno\.? of\b|\bcount of\b|\btotal number\b",
    "score (generic)": r"\bscore\b|\bscale\b|\bindex\b|\binventory\b",
}


def own_label(variable: str) -> str:
    """The row's own label, without any section prefix."""
    return (variable or "").rpartition(" - ")[2] or (variable or "")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--grim", type=Path,
                   default=Path("results/grim_results_v14.csv"))
    p.add_argument("--top", type=int, default=30)
    args = p.parse_args()

    if not args.grim.exists():
        raise SystemExit(f"{args.grim} not found")

    unknown_labels: Counter[str] = Counter()
    unknown_papers: dict[str, set[str]] = {}
    total = unknown = 0

    for r in csv.DictReader(args.grim.open(encoding="utf-8-sig")):
        total += 1
        if (r.get("reason") or "").strip() != "not applicable - measure type unknown":
            continue
        unknown += 1
        label = " ".join(own_label(r["variable"]).split())[:64]
        unknown_labels[label] += 1
        unknown_papers.setdefault(label, set()).add(r["pmcid"])

    print(f"rows in the results file:           {total}")
    print(f"classified measure type unknown:    {unknown}"
          f"  ({unknown / total:.1%})")
    print(f"distinct labels among them:         {len(unknown_labels)}\n")

    print("=" * 66)
    print("RECOVERABLE: unknown rows whose label names a known instrument")
    print("=" * 66)
    hits: list[tuple[int, str, int]] = []
    for name, pattern in KNOWN.items():
        rx = re.compile(pattern, re.I)
        rows = sum(c for lab, c in unknown_labels.items() if rx.search(lab))
        labs = sum(1 for lab in unknown_labels if rx.search(lab))
        if rows:
            hits.append((rows, name, labs))
    for rows, name, labs in sorted(hits, reverse=True):
        print(f"  {rows:6} rows  {labs:4} distinct labels   {name}")
    if not hits:
        print("  none")

    print()
    print("=" * 66)
    print(f"MOST COMMON unknown labels (top {args.top})")
    print("=" * 66)
    for label, count in unknown_labels.most_common(args.top):
        papers = len(unknown_papers[label])
        print(f"  {count:5} rows  {papers:4} papers   {label}")

    print()
    print("A label naming an instrument is a checkable row being dropped.")
    print("A label that is a unit, a date or a free-text phrase is correctly")
    print("excluded. Read the list and decide which is which.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
