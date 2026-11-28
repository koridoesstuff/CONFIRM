"""Count what refusing every comma-bearing numeric cell would cost.

A comma between digits in a table cell has three incompatible readings:

    1,234.5     thousands separator
    53,8        decimal separator (European convention)
    134 (131,135)   a median with its interquartile range

v1.4.2 narrowed the thousands rule to require exactly three following digits,
which resolved cells like "69(67,71)" but cannot touch the other two: "53,8"
now matches *after* the comma and yields 8, and "131,135" is a valid thousands
group by any syntactic test.

The principled repair is to refuse any cell with a comma between digits, which
is how the rest of the pipeline treats ambiguity. Before doing that, this
counts the loss: how many cells currently parse as a mean and an SD while
carrying such a comma, split by which reading the comma most likely has.

A cell is classed by what follows the comma:
  thousands  - exactly three digits, then no digit ("1,234", "131,135")
  decimal    - one or two digits, then no digit ("53,8", "164,14")
  listish    - anything else, or more than one comma
Note that "thousands" is syntactic only. "131,135" lands there and is really
an interquartile range, which is the whole difficulty.

Usage:
    python audit/comma_census.py
    python audit/comma_census.py --limit 500 --show 12
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DIGIT_COMMA = re.compile(r"\d,\d")
THOUSANDS = re.compile(r"\d,\d{3}(?!\d)")
DECIMALISH = re.compile(r"\d,\d{1,2}(?!\d)")


def load_extractor(root: Path):
    """Import extract_tables.py from the repo root as a module."""
    path = root / "extract_tables.py"
    if not path.exists():
        sys.exit(f"{path} not found; run this from the repository root")
    spec = importlib.util.spec_from_file_location("_et", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classify(text: str) -> str:
    if len(DIGIT_COMMA.findall(text)) > 1:
        return "listish"
    if THOUSANDS.search(text):
        return "thousands"
    if DECIMALISH.search(text):
        return "decimal"
    return "listish"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw", type=Path, default=Path("raw_papers"))
    p.add_argument("--limit", type=int, default=0,
                   help="scan only the first N papers (0 = all)")
    p.add_argument("--show", type=int, default=10,
                   help="example cells to print per class")
    args = p.parse_args()

    root = Path.cwd()
    et = load_extractor(root)

    files = sorted(args.raw.glob("*.xml"))
    if args.limit:
        files = files[:args.limit]
    if not files:
        sys.exit(f"no XML files under {args.raw}")

    kept = collections.Counter()          # parses as mean/SD, has a comma
    refused = collections.Counter()       # has a comma, already refused
    papers = collections.defaultdict(set)
    examples = collections.defaultdict(list)
    total_cells = 0
    parsed_cells = 0

    for i, path in enumerate(files, 1):
        if i % 1000 == 0:
            print(f"  ...{i}/{len(files)}", file=sys.stderr)
        try:
            tree = ET.parse(path)
        except ET.ParseError:
            continue
        for row in tree.iter():
            if et.local(row.tag) != "tr":
                continue
            for cell in row:
                if et.local(cell.tag) not in ("td", "th"):
                    continue
                text = et.cell_text(cell)
                if not text:
                    continue
                total_cells += 1
                parsed = et.parse_mean_sd(text)
                if parsed:
                    parsed_cells += 1
                if not DIGIT_COMMA.search(text):
                    continue
                kind = classify(text)
                if parsed:
                    kept[kind] += 1
                    papers[kind].add(path.stem)
                    if len(examples[kind]) < args.show:
                        examples[kind].append((path.stem, text, parsed))
                else:
                    refused[kind] += 1

    print()
    print(f"papers scanned: {len(files)}")
    print(f"cells with text: {total_cells}")
    print(f"cells parsing as mean/SD: {parsed_cells}")
    print()
    print("Cells that PARSE as mean/SD and carry a comma between digits.")
    print("These are exactly what a refuse-all-commas rule would discard:")
    for kind in ("thousands", "decimal", "listish"):
        print(f"  {kept[kind]:>6}  {kind:<10} across {len(papers[kind])} papers")
    print(f"  {sum(kept.values()):>6}  TOTAL  "
          f"({100.0 * sum(kept.values()) / max(parsed_cells, 1):.2f}% of parsed cells)")
    print()
    print("Cells with such a comma that are already refused (no change):")
    for kind in ("thousands", "decimal", "listish"):
        print(f"  {refused[kind]:>6}  {kind}")
    print()
    for kind in ("thousands", "decimal", "listish"):
        if not examples[kind]:
            continue
        print(f"-- examples, {kind}")
        for pmcid, text, parsed in examples[kind]:
            print(f"   {pmcid:<13} {text[:40]!r:<42} -> mean {parsed[0]}, SD {parsed[1]}")
        print()
    print("Read the 'thousands' examples before deciding. A genuine "
          "thousands-separated mean is a real loss; an interquartile range "
          "sitting in that class is a value the pipeline currently gets wrong.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
