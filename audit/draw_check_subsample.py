"""Carve a blind check subsample out of the tier-1 worksheet.

The 300-paper coverage sample is to be rated automatically, which is only
worth anything if the automated rating has a measured error rate. This draws
a random 30 of the same papers for the human to rate independently. Rate
these first: if the automated ratings do not exist yet, the human rating
cannot be influenced by them, which is a stronger guarantee than agreeing
not to look.

The two files are compared afterwards on pmcid. Agreement on
`integer_rows_present` is the figure that matters, since that is the
judgment the coverage claim rests on.

Usage:
    python audit/draw_check_subsample.py
    python audit/draw_check_subsample.py --n 30 --seed 20261117
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tier1", type=Path,
                        default=Path("audit/gold/tier1_coverage.csv"))
    parser.add_argument("--out", type=Path,
                        default=Path("audit/gold/tier1_human_check.csv"))
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261117,
                        help="use a DIFFERENT seed from the 300-paper draw")
    args = parser.parse_args()

    if not args.tier1.exists():
        print(f"{args.tier1} not found", file=sys.stderr)
        return 1

    with args.tier1.open(encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        rows = list(reader)

    if not rows:
        print(f"{args.tier1} has no rows", file=sys.stderr)
        return 1

    filled = sum(1 for r in rows if (r.get("baseline_table_exists") or "").strip())
    if filled:
        print(f"warning: {filled} rows in {args.tier1} already carry ratings. "
              "The subsample is drawn anyway, but a blank worksheet is the "
              "intended starting point.", file=sys.stderr)

    rng = random.Random(args.seed)
    picked = rng.sample(rows, min(args.n, len(rows)))
    picked.sort(key=lambda r: r["pmcid"])

    # Blank every rating column, in case the source had any.
    blanked = []
    for r in picked:
        out = {f: "" for f in fields}
        out["pmcid"] = r["pmcid"]
        out["url"] = r.get("url", "")
        blanked.append(out)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(blanked)

    print(f"drawn from:  {len(rows)} papers in {args.tier1}")
    print(f"subsample:   {len(blanked)} papers -> {args.out}")
    print(f"seed:        {args.seed}")
    print()
    print("Rate this file before any automated rating is produced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
