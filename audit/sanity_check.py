"""Check extracted rows for values that cannot be right, whatever the paper says.

Most of the audit suite asks whether CONFIRM agrees with a source or with an
independent re-derivation. This asks a cheaper question: does the extracted
dataset contain values that are impossible on their face? A standard deviation
cannot be negative, a sample size cannot be below one, and a cell parsed as a
mean and an SD must hold two numbers.

Those cost nothing to test and they catch parser faults that agreement tests
miss, because a wrong value can be re-derived wrongly in the same way twice. The
negative-SD test is what exposed the comma-without-space median/IQR fault in
v1.4.1, where "69(67,71)" was read as mean 69, SD 6771: the two negative SDs it
produced were visible, and the 210 positive ones were not.

Hard failures are things that cannot occur. Warnings are shapes that are merely
suspect -- an SD enormously larger than its mean is the signature of two numbers
concatenated -- and are reported separately so a real finding is never buried.

Usage:
    python audit/sanity_check.py --data results/extracted_data_v16.csv
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

# An SD this many times its mean is almost certainly two values run together,
# as "67,71" becoming 6771. Set high enough that genuinely dispersed measures
# -- counts of rare events, costs, durations -- do not trip it.
CONCAT_RATIO = 20.0
CONCAT_MIN_SD_DIGITS = 3

# Collapse the specifics out of a description so like faults group together.
KIND_RE = re.compile(r"\s*(\(.*\)|--.*|\d+x the mean.*)$")


def numeric(value: str) -> float | None:
    try:
        return float((value or "").strip())
    except (TypeError, ValueError):
        return None


def digits(value: str) -> int:
    return sum(ch.isdigit() for ch in (value or "").split(".")[0])


def check(rows: list[dict]) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]]]:
    """Return (failures, warnings) as (description, row) pairs.

    Only genuine impossibilities count as failures. A tempting extra test --
    the same variable, group and n carrying two different values -- was tried
    and removed: a paper legitimately repeats a label across tables and
    timepoints, so it produced 735 false failures and no true ones.
    """
    failures: list[tuple[str, dict]] = []
    warnings: list[tuple[str, dict]] = []

    for row in rows:
        mean_text, sd_text, n_text = row.get("mean"), row.get("sd"), row.get("n")
        mean, sd, n = numeric(mean_text), numeric(sd_text), numeric(n_text)

        if sd is not None and sd < 0:
            failures.append(("negative SD", row))
        if n is not None and n < 1:
            failures.append((f"sample size below 1 (n={n_text})", row))
        if n is not None and n != int(n):
            failures.append((f"non-integer sample size (n={n_text})", row))
        if mean_text and mean is None:
            failures.append((f"mean is not numeric ({mean_text!r})", row))
        if sd_text and sd is None:
            failures.append((f"SD is not numeric ({sd_text!r})", row))

        if mean is not None and sd is not None and mean != 0:
            if (abs(sd / mean) > CONCAT_RATIO
                    and digits(sd_text) >= CONCAT_MIN_SD_DIGITS
                    and digits(sd_text) > digits(mean_text)):
                warnings.append(
                    (f"SD {abs(sd / mean):.0f}x the mean -- possible concatenation", row))

    return failures, warnings


def show(title: str, items: list[tuple[str, dict]], limit: int) -> None:
    print(f"{title}: {len(items)}")
    by_kind = collections.Counter(KIND_RE.sub("", desc) for desc, _ in items)
    for kind, count in by_kind.most_common():
        print(f"    {count:>6}  {kind}")
    for desc, row in items[:limit]:
        print(f"      {row.get('pmcid',''):<13} {(row.get('variable') or '')[:40]:<40} "
              f"mean={row.get('mean',''):<9} sd={row.get('sd',''):<9} {desc}")
    if len(items) > limit:
        print(f"      ... {len(items) - limit} more")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=Path("results/extracted_data.csv"))
    p.add_argument("--show", type=int, default=15)
    args = p.parse_args()

    if not args.data.exists():
        print(f"{args.data} not found", file=sys.stderr)
        return 1

    with args.data.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    failures, warnings = check(rows)
    print(f"rows checked: {len(rows)}  ({args.data})\n")
    show("impossible values", failures, args.show)
    print()
    show("suspicious shapes", warnings, args.show)
    print()
    if failures:
        print("FAIL - the dataset contains values that cannot be correct.")
        return 1
    print("PASS - no impossible values.")
    if warnings:
        print("      Warnings are not failures, but each is worth reading once.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
