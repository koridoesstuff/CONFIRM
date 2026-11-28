"""Count cells where a space is acting as a thousands separator.

Some journals write twelve thousand and ninety as "12 090". The number pattern
does not cross the space, so it matches from after it and stores 090 -- the
same failure as the decimal comma, and just as quiet, because 090 is a number
a reader could believe.

A space is a weaker signal than a comma, though. "5 10 (2)" is plausibly two
values in one cell, not 510, and no amount of staring at the digits settles it.
So this reports three things rather than one: how many cells look like a
separated thousand, what the pipeline stores for them now, and what it would
store if the space were treated as a separator. Read the examples before
writing any rule.

Classes, by what follows the space:
  separator  - exactly three digits, then no digit ("12 090", "18 241")
  twonums    - one or two digits, or four and more ("5 10", "7 1234")

Only `separator` is a candidate for repair. `twonums` is listed so the size of
the ambiguity is visible.

Usage:
    python audit/space_census.py
    python audit/space_census.py --limit 500 --show 15
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DIGIT_SPACE = re.compile(r"\d \d")
SEPARATOR = re.compile(r"(?<!\d)(\d{1,3}) (\d{3})(?!\d)")
TWONUMS = re.compile(r"\d (?:\d{1,2}(?!\d)|\d{4,})")


def load_extractor(root: Path):
    path = root / "extract_tables.py"
    if not path.exists():
        sys.exit(f"{path} not found; run this from the repository root")
    spec = importlib.util.spec_from_file_location("_et", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repaired(text: str) -> str:
    """The cell as it would read if a space before three digits joined them."""
    return SEPARATOR.sub(lambda m: m.group(1) + m.group(2), text)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw", type=Path, default=Path("raw_papers"))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--show", type=int, default=12)
    args = p.parse_args()

    et = load_extractor(Path.cwd())

    files = sorted(args.raw.glob("*.xml"))
    if args.limit:
        files = files[:args.limit]
    if not files:
        sys.exit(f"no XML files under {args.raw}")

    kept = collections.Counter()
    refused = collections.Counter()
    papers = collections.defaultdict(set)
    examples = collections.defaultdict(list)
    changes_value = 0
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
                now = et.parse_mean_sd(text)
                if now:
                    parsed_cells += 1
                if not DIGIT_SPACE.search(text):
                    continue
                kind = "separator" if SEPARATOR.search(text) else (
                    "twonums" if TWONUMS.search(text) else None)
                if kind is None:
                    continue
                if not now:
                    refused[kind] += 1
                    continue
                kept[kind] += 1
                papers[kind].add(path.stem)
                after = et.parse_mean_sd(repaired(text))
                if kind == "separator" and after != now:
                    changes_value += 1
                if len(examples[kind]) < args.show:
                    examples[kind].append((path.stem, text, now, after))

    print()
    print(f"papers scanned: {len(files)}")
    print(f"cells parsing as mean/SD: {parsed_cells}")
    print()
    print("Cells that PARSE as mean/SD and contain a digit-space-digit run:")
    for kind in ("separator", "twonums"):
        print(f"  {kept[kind]:>6}  {kind:<10} across {len(papers[kind])} papers")
    print(f"  {changes_value:>6}  of the 'separator' cells would store a "
          f"different value if repaired")
    print()
    print("Cells with such a run that are already refused (no change either way):")
    for kind in ("separator", "twonums"):
        print(f"  {refused[kind]:>6}  {kind}")
    print()
    for kind in ("separator", "twonums"):
        if not examples[kind]:
            continue
        print(f"-- examples, {kind}")
        for pmcid, text, now, after in examples[kind]:
            mark = "  <-- CHANGES" if (kind == "separator" and after != now) else ""
            print(f"   {pmcid:<13} {text[:34]!r:<36}")
            print(f"                 now -> {now}")
            print(f"              repaired -> {after}{mark}")
        print()
    print("Decide from the examples, not the totals. A rule is worth writing "
          "only if the 'separator' cells really are single numbers; every one "
          "that is actually two values would be corrupted by joining them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
