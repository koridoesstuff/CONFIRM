"""Count baseline tables laid out as side-by-side panels, and what they cost.

Some papers save vertical space by running two label/value pairs across one
physical row:

    Parameter (unit)  | Value          | Parameter (unit)      | Value
    Hb (g/dl)         | 13.96 +- 1.46  | Total Bilirubin (mg/dL) | 0.41 +- 0.19

The extractor treats every row as one label followed by one value per group, so
the first panel's label is matched against the second panel's number: Hb is
stored as 0.41. Unlike the comma and dash faults, nothing downstream protects
against this, because the value attached to the wrong label is a plausible
number of the right kind.

Detection has two levels, reported separately because they differ sharply in
confidence:

  header-repeat  A non-empty header text appears more than once in the header
                 row. Suggestive, but "n (%)" repeated across arms is benign
                 when the arm names live in a row above.
  row-shape      A row has a non-numeric cell at an interior position with
                 numeric cells on both sides -- a second label mid-row. This
                 is the layout itself rather than a hint of it, so it is the
                 figure to trust.

For every row-shape hit the script prints what the extractor stores and what
the row actually contains, so the mis-pairing is visible rather than inferred.

Usage:
    python audit/panel_census.py
    python audit/panel_census.py --limit 800 --show 10
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HAS_DIGIT = re.compile(r"\d")
MOSTLY_WORDS = re.compile(r"[A-Za-z]{3}")


def load_extractor(root: Path):
    path = root / "extract_tables.py"
    if not path.exists():
        sys.exit(f"{path} not found; run this from the repository root")
    spec = importlib.util.spec_from_file_location("_et", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def looks_like_label(text: str) -> bool:
    """Words and no number worth speaking of -- i.e. a label, not a value."""
    t = (text or "").strip()
    return bool(t) and bool(MOSTLY_WORDS.search(t)) and not HAS_DIGIT.search(t[:4])


def looks_like_value(et, text: str) -> bool:
    t = (text or "").strip()
    return bool(t) and bool(HAS_DIGIT.search(t)) and (
        et.parse_mean_sd(t) is not None or bool(re.fullmatch(r"[\d.,%()\s+-]+", t)))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw", type=Path, default=Path("raw_papers"))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--show", type=int, default=8)
    args = p.parse_args()

    et = load_extractor(Path.cwd())
    files = sorted(args.raw.glob("*.xml"))
    if args.limit:
        files = files[:args.limit]
    if not files:
        sys.exit(f"no XML files under {args.raw}")

    with_baseline = 0
    header_repeat: set[str] = set()
    row_shape: set[str] = set()
    row_shape_rows = 0
    loose_only: set[str] = set()
    loose_examples: list[tuple[str, list[str], list[str]]] = []
    examples: list[tuple[str, list[str], list[str]]] = []

    for i, path in enumerate(files, 1):
        if i % 1000 == 0:
            print(f"  ...{i}/{len(files)}", file=sys.stderr)
        try:
            art = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        found = et.find_baseline_table(art)
        if not found:
            continue
        table, _caption = found
        if table is None:
            continue
        rows = [r for r in table.iter() if et.local(r.tag) == "tr"]
        if len(rows) < 2:
            continue
        with_baseline += 1

        heads = [et.cell_text(c) for c in et.row_cells(rows[0])]
        seen = [h.strip() for h in heads if h and h.strip()]
        if len(seen) != len(set(seen)):
            header_repeat.add(path.stem)

        # The discriminating test: an interior label cell sitting under a
        # REPEAT of the first column's own header. Without that anchor the
        # shape test alone picks up test-statistic columns ("U = 811.0
        # (Mann-Whitney)") and verdict columns ("Dominant"), which are
        # wordy interior cells but not second labels. Requiring
        # heads[k] == heads[0] takes precision over recall, which is what a
        # census meant to justify a code change needs.
        first_head = (heads[0] or "").strip()
        panel_cols = {k for k, h in enumerate(heads)
                      if k > 0 and first_head and (h or "").strip() == first_head}
        hit_rows = []
        for tr in rows[1:]:
            cells = [et.cell_text(c) for c in et.row_cells(tr)]
            if len(cells) < 4:
                continue
            for k in range(1, len(cells) - 1):
                if (looks_like_label(cells[k])
                        and looks_like_value(et, cells[k - 1])
                        and looks_like_value(et, cells[k + 1])):
                    hit_rows.append((cells, k, k in panel_cols))
                    break
        anchored = [h for h in hit_rows if h[2]]
        if anchored:
            row_shape.add(path.stem)
            row_shape_rows += len(anchored)
            if len(examples) < args.show:
                examples.append((path.stem, heads, anchored[0][0]))
        elif hit_rows:
            loose_only.add(path.stem)
            if len(loose_examples) < 4:
                loose_examples.append((path.stem, heads, hit_rows[0][0]))

    print()
    print(f"papers scanned: {len(files)}")
    print(f"papers with a selected baseline table: {with_baseline}")
    print()
    print(f"header-repeat (suggestive): {len(header_repeat)} papers"
          f"  ({100.0 * len(header_repeat) / max(with_baseline, 1):.1f}% of those)")
    print(f"PANEL, anchored (interior label under a repeat of column 1's"
          f" header): {len(row_shape)} papers, {row_shape_rows} rows"
          f"  ({100.0 * len(row_shape) / max(with_baseline, 1):.1f}% of those)")
    print(f"shape-only, no header anchor (mostly test-statistic and verdict"
          f" columns; inspect before trusting): {len(loose_only)} papers")
    print(f"both signatures: {len(header_repeat & row_shape)} papers")
    print(f"row-shape without header-repeat: {len(row_shape - header_repeat)} papers")
    print()
    for pmcid, heads, cells in examples:
        print(f"-- {pmcid}")
        print(f"   header: {heads}")
        print(f"   row:    {cells}")
        print(f"   stored: label {cells[0]!r} gets {cells[1]!r}"
              f"  (its own panel's value)")
        print()
    if loose_examples:
        print("-- shape-only examples, for inspection")
        for pmcid, heads, cells in loose_examples:
            print(f"   {pmcid}: header {heads}")
            print(f"       row {cells}")
        print()
    print("The anchored count is the one to act on. Compare it against the "
          "coverage you would lose by skipping such tables before choosing "
          "between skipping them and splitting the panels properly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
