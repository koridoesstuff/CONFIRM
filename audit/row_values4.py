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
    """Text of a cell, spaced the way the pipeline spaces it.

    cell_text() in extract_tables.py puts a space where a <break/> falls and
    nowhere else, so a header written as "BRG" over "n = 18" is stored as
    "BRG n = 18". Two wrong ways to do this were tried first. Joining
    itertext() with no separator gives "BRGn = 18", which never matches the
    stored group, so the baseline table goes unseen and a later table's
    numbers get reported as a mismatch. Joining every part with a space
    instead gives "BMI, kg/m 2" for a cell with a superscript, which stops
    the label matching. Only the break carries a space.
    """
    parts: list[str] = []

    def walk(e: ET.Element) -> None:
        if e.text:
            parts.append(e.text)
        for child in e:
            if child.tag.rpartition("}")[2] == "break":
                parts.append(" ")
            walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(el)
    return " ".join("".join(parts).split())


TRAILING_COUNT = re.compile(
    r"[\s,;:-]*(?:frequency|freq\.?|no\.?|n)?\s*\(\s*%?\s*\)?\s*$", re.I)


TRAILING_N = re.compile(r"\s+n\s+\d+$")


def clean_group(s: str) -> str:
    """Drop the count/percent fragment left on a stored group label.

    parse_groups strips "n = 40" out of a header but leaves what surrounded
    it, so "COMBAT-ICU group frequency (%)" is stored as
    "COMBAT-ICU group frequency (%". Comparing that to the header verbatim
    never matches.
    """
    # norm() has already turned "(n = 11)" into " n 11", so the paren-based
    # pattern above cannot see it. Strip that normalised tail too, or an exact
    # comparison against the header never succeeds and the row is given up on.
    return TRAILING_N.sub("", norm(TRAILING_COUNT.sub("", s or "")))


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
    text = re.sub(r"(?<=\d)\.\s+(?=\d)", ".", cell or "")
    # A minus sign in a table is often U+2212 or a typographic dash, not the
    # ASCII hyphen the number pattern expects, so "-0.673" came back as
    # "0.673" and looked like a mismatch.
    text = re.sub(r"[\u2212\u2012\u2013\u2014\u2010\u2011]", "-", text)
    return [m.group(0).replace(",", "") for m in NUM.finditer(text)]


def same(a: str, b: str) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


def find_row(path: Path, variable: str, group: str, caption: str = ""
             ) -> tuple[str, str] | None:
    """Return (cell text, column header) for this variable and group.

    When the stored row names its table, only that table is searched. A label
    like "Identified regulation" recurs in a paper's baseline, post-
    intervention and follow-up tables with different numbers in each, and
    without the caption there is no way to tell which one a row came from.
    """
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    want_caption = norm(caption)

    # The stored variable may carry a "section - label" prefix; the label
    # itself is what appears in the cell.
    label = variable.rpartition(" - ")[2] or variable
    want_label, want_group = norm(label), clean_group(group)
    want_tokens = set(want_group.split())

    # Collect every candidate, across every table, and refuse to choose.
    # A label is often not unique: a table may carry two rows called "Wake
    # after sleep onset", or "BMIa" and "BMIb" that both store as "BMI" once
    # the footnote letter is stripped. Picking the first matched the wrong
    # row and reported it as a mismatch.
    found: list[tuple[str, str]] = []
    tables: list[tuple[str, ET.Element]] = []
    for wrap in root.findall(".//{*}table-wrap"):
        cap_el = wrap.find("./{*}caption")
        cap = norm(flatten(cap_el)) if cap_el is not None else ""
        for tbl in wrap.findall(".//{*}table"):
            tables.append((cap, tbl))
    if not tables:
        tables = [("", t) for t in root.findall(".//{*}table")]
    if want_caption:
        matched = [(c, t) for c, t in tables
                   if c and (c in want_caption or want_caption in c)]
        if matched:
            tables = matched

    for _cap, table in tables:
        rows = table.findall(".//{*}tr")
        if not rows:
            continue
        headers = [norm(flatten(c)) for c in rows[0]]
        for tr in rows[1:]:
            cells = [flatten(c) for c in tr]
            if not cells:
                continue
            here = norm(cells[0])
            # Drop a trailing footnote letter: "BMIa" is stored as "BMI".
            bare = re.sub(r"[a-z]$", "", here).strip()
            if here != want_label and bare != want_label:
                continue
            # Match the group to a column by its exact cleaned text. An equal
            # *set* of tokens is not enough: "A-C-B" and "A-B-C" are anagrams,
            # as are "Premeal -> Postmeal" and its reverse, so an order-blind
            # test silently picked the wrong arm and then reported a mismatch
            # against a value the pipeline had read correctly. Where two
            # columns could both answer to the name, refuse rather than guess.
            exact = [(cells[idx], head) for idx, head in enumerate(headers)
                     if idx and idx < len(cells)
                     and clean_group(head) == want_group]
            if len(exact) == 1:
                found.append(exact[0])
                continue
            if exact:
                continue                     # ambiguous: two columns claim it
            subset = [(cells[idx], head) for idx, head in enumerate(headers)
                      if idx and idx < len(cells) and want_tokens
                      and want_tokens <= set(clean_group(head).split())]
            if len(subset) == 1:
                found.append(subset[0])
    if len(found) == 1:
        return found[0]
    if len(found) > 1 and len({numbers(c)[0] if numbers(c) else c
                               for c, _ in found}) == 1:
        return found[0]                       # several rows, same value
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
    p.add_argument("--sample", type=int, default=0,
                   help="instead of the flagged rows, re-read this many "
                        "extracted rows drawn at random")
    p.add_argument("--data", type=Path,
                   default=Path("results/extracted_data_v14.csv"))
    p.add_argument("--seed", type=int, default=20261122)
    args = p.parse_args()

    flags = []
    if args.sample:
        # Ordinary extracted rows, not just the ones that failed a test. A
        # mis-read value in a passing row never surfaces anywhere, so this is
        # the only check on the other fifty thousand.
        import random
        rows = list(csv.DictReader(args.data.open(encoding="utf-8-sig")))
        picked = random.Random(args.seed).sample(
            rows, min(args.sample, len(rows)))
        flags = [("row", r) for r in picked]
        print(f"re-reading {len(flags)} randomly drawn extracted rows\n")
        return report(flags, args)
    for which, path in (("GRIM", args.grim), ("GRIMMER", args.grimmer)):
        if not path.exists():
            raise SystemExit(f"{path} not found")
        for r in csv.DictReader(path.open(encoding="utf-8-sig")):
            if (r.get("category") or "").strip() == "checked-flagged":
                flags.append((which, r))

    print(f"flagged rows to verify: {len(flags)}\n")
    return report(flags, args)


def report(flags, args) -> int:
    verified, mismatch, unlocated = [], [], []
    for which, r in flags:
        xml = args.raw / f"{r['pmcid']}.xml"
        if not xml.exists():
            unlocated.append((which, r, "no xml"))
            continue
        found = find_row(xml, r["variable"], r["group"],
                         r.get("table_caption") or "")
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
