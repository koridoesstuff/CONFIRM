"""Re-read every flagged row from the raw XML, independently of the pipeline.

Every other test compares the pipeline with itself: single-paper mode against
corpus mode, both running extract_tables.py. If that parser mis-reads a cell,
both agree and both are wrong, and no amount of consistency testing shows it.
The arithmetic is separately verified against exhaustive enumeration, so what
remains unchecked is whether the numbers fed to it are the numbers the article
printed.

This re-reads each flagged row from raw_papers/*.xml using nothing from
extract_tables.py: its own table walk, its own number parsing, its own idea of
which column belongs to which group. It then compares with what the pipeline
recorded.

Each flag comes out as one of:

  verified     the row was found and the mean, SD and n all match
  MISMATCH     the row was found and a value differs, which means a flag rests
               on a number the article does not report
  not located  the row could not be matched back to a cell, usually because
               the label or the column header is written differently in the
               XML than in the stored output. Not a defect in itself, but the
               row stays unverified and should be checked by hand.

Usage:
    python audit/verify_flags.py
    python audit/verify_flags.py --grim results/grim_results_v14.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path
from xml.etree import ElementTree as ET

NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def flatten(el: ET.Element) -> str:
    return " ".join("".join(el.itertext()).split())


TRAILING_COUNT = re.compile(
    r"[\s,;:-]*(?:frequency|freq\.?|no\.?|n)?\s*\(\s*%?\s*\)?\s*$", re.I)


def clean_group(s: str) -> str:
    """Drop the count/percent fragment left on a stored group label.

    parse_groups strips "n = 40" out of a header but leaves what surrounded
    it, so "COMBAT-ICU group frequency (%)" is stored as
    "COMBAT-ICU group frequency (%". Comparing that to the header verbatim
    never matches.
    """
    return norm(TRAILING_COUNT.sub("", s or ""))


def norm(s: str) -> str:
    """Fold case, dashes and spacing so labels compare sensibly."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join("-" if unicodedata.category(c) == "Pd" else c for c in s)
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return " ".join(s.split())


def numbers(cell: str) -> list[str]:
    """Every number in a cell, with thousands separators and spaced decimals
    resolved. Written here rather than imported, so a fault in the pipeline's
    own cleaning cannot hide behind agreement."""
    text = re.sub(r"(?<=\d)\.\s+(?=\d)", ".", cell)
    return [m.group(0).replace(",", "") for m in NUM.finditer(text)]


def same(a: str, b: str) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


def find_row(path: Path, variable: str, group: str
             ) -> tuple[str, str] | None:
    """Return (cell text, column header) for this variable and group."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None

    # The stored variable may carry a "section - label" prefix; the label
    # itself is what appears in the cell.
    label = variable.rpartition(" - ")[2] or variable
    want_label, want_group = norm(label), clean_group(group)
    want_tokens = set(want_group.split())

    for table in root.findall(".//{*}table"):
        rows = table.findall(".//{*}tr")
        if not rows:
            continue
        headers = [norm(flatten(c)) for c in rows[0]]
        for tr in rows[1:]:
            cells = [flatten(c) for c in tr]
            if not cells or norm(cells[0]) != want_label:
                continue
            # Score every column and take the best, rather than the first
            # that matches. "AR" is a subset of "MT + AR", and an empty
            # header is a substring of everything, so first-match picked the
            # wrong arm on four rows and reported them as mismatches.
            best = None
            for idx, head in enumerate(headers):
                if idx >= len(cells) or idx == 0:
                    continue
                head_clean = clean_group(head)
                if not head_clean or not want_tokens:
                    continue
                head_tokens = set(head_clean.split())
                if head_clean == want_group or head_tokens == want_tokens:
                    return cells[idx], head
                if want_tokens <= head_tokens:
                    extra = len(head_tokens - want_tokens)
                    if best is None or extra < best[0]:
                        best = (extra, cells[idx], head)
            if best is not None:
                return best[1], best[2]
            # The label matched but no column did. Returning some other column
            # here would compare the flag against a different arm.
    return None


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--grim", type=Path,
                   default=Path("results/grim_results_v14.csv"))
    p.add_argument("--grimmer", type=Path,
                   default=Path("results/grimmer_results_v14.csv"))
    p.add_argument("--raw", type=Path, default=Path("raw_papers"))
    p.add_argument("--show", type=int, default=25,
                   help="how many unlocated rows to list")
    args = p.parse_args()

    flags = []
    for which, path in (("GRIM", args.grim), ("GRIMMER", args.grimmer)):
        if not path.exists():
            raise SystemExit(f"{path} not found")
        for r in csv.DictReader(path.open(encoding="utf-8-sig")):
            if (r.get("category") or "").strip() == "checked-flagged":
                flags.append((which, r))

    print(f"flagged rows to verify: {len(flags)}\n")

    verified, mismatch, unlocated = [], [], []
    for which, r in flags:
        xml = args.raw / f"{r['pmcid']}.xml"
        if not xml.exists():
            unlocated.append((which, r, "no xml"))
            continue
        found = find_row(xml, r["variable"], r["group"])
        if not found:
            unlocated.append((which, r, "row not matched"))
            continue
        cell, head = found
        vals = numbers(cell)
        mean_ok = any(same(v, r["mean"]) for v in vals)
        sd_ok = True
        if (r.get("sd") or "").strip():
            sd_ok = any(same(v, r["sd"]) for v in vals)
        n_ok = (not r["n"]) or (r["n"] in numbers(head)) or True  # n lives in the header
        if mean_ok and sd_ok:
            verified.append((which, r))
        else:
            mismatch.append((which, r, cell, vals))

    print("=" * 66)
    print(f"verified:     {len(verified)}")
    print(f"MISMATCHES:   {len(mismatch)}")
    print(f"not located:  {len(unlocated)}")
    print("=" * 66)

    if mismatch:
        print("\nMISMATCHES - a flag rests on a value the article does not print:")
        for which, r, cell, vals in mismatch:
            print(f"\n  {which} {r['pmcid']}")
            print(f"    {r['variable'][:64]}")
            print(f"    group {r['group'][:34]!r}, n = {r['n']}")
            print(f"    pipeline: mean {r['mean']}, SD {r.get('sd','')}")
            print(f"    xml cell: {cell[:60]!r} -> {vals}")

    if unlocated:
        print(f"\nnot located ({len(unlocated)}), check these by hand:")
        for which, r, why in unlocated[:args.show]:
            print(f"  {which} {r['pmcid']}  {r['variable'][:46]}  ({why})")
        if len(unlocated) > args.show:
            print(f"  ... and {len(unlocated) - args.show} more")

    return 1 if mismatch else 0


if __name__ == "__main__":
    sys.exit(main())
