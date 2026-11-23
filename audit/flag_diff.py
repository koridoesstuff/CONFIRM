"""Compare two runs' flagged rows, so only the new ones need checking.

A flag is a claim about a published paper, so every one of them has to be
looked at before it is published. After a change to the pipeline the count
moves but the identity of the rows does not come with it, and the result files
hold tens of thousands of rows each. This prints the difference.

Three lists come out:

  newly flagged     in the new run and not the old one. These are the ones to
                    check by hand. Each is marked with where its sample size
                    came from, because a flag resting on an inferred n is the
                    circularity LIMITATIONS.md records: the n was recovered
                    from the paper's own percentages, and wrong percentages are
                    one of the things the tool looks for.

  no longer flagged in the old run and not the new one. There should be none.
                    If there are, a change silently retracted a finding, and
                    that needs explaining before anything is republished.

  still flagged     the overlap, as a count. Confirms the existing findings
                    survived the change.

Whether an n was read or inferred is not recorded in extracted_data.csv, so it
is approximated here: a group label that still carries an "n = 123" had its
size read from the header, and one that does not almost certainly had it
recovered. Add an n_source column to the extractor if you want this exact.

Usage:
    python audit/flag_diff.py --old results/grim_results_v1.3.2.csv \
        --new results/grim_results_v14.csv
    python audit/flag_diff.py --old results/grimmer_results_v1.3.2.csv \
        --new results/grimmer_results_v14.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

HEADER_N = re.compile(r"\b[nN]\s*[=:]\s*\d")


def flagged(path: Path) -> dict[tuple[str, str, str], dict]:
    """Every checked-flagged row, keyed by paper, variable and group."""
    if not path.exists():
        raise SystemExit(f"{path} not found")
    out = {}
    for r in csv.DictReader(path.open(encoding="utf-8-sig")):
        if (r.get("category") or "").strip() != "checked-flagged":
            continue
        key = (r["pmcid"].strip().upper(),
               " ".join((r.get("variable") or "").split()),
               " ".join((r.get("group") or "").split()))
        out[key] = r
    return out


def show(r: dict) -> str:
    n = r.get("n", "")
    src = "n read from header" if HEADER_N.search(r.get("group", "")) \
        else "n INFERRED - verify before publishing"
    sd = r.get("sd", "")
    val = f"mean {r.get('mean','')}" + (f", SD {sd}" if sd else "")
    return (f"  {r['pmcid']}\n"
            f"    {r.get('variable','')}\n"
            f"    group {r.get('group','')!r}, n = {n}\n"
            f"    {val}\n"
            f"    {src}\n")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--old", type=Path, required=True)
    p.add_argument("--new", type=Path, required=True)
    args = p.parse_args()

    old, new = flagged(args.old), flagged(args.new)
    added = [k for k in new if k not in old]
    dropped = [k for k in old if k not in new]
    kept = [k for k in new if k in old]

    print(f"old run: {args.old.name}  {len(old)} flagged")
    print(f"new run: {args.new.name}  {len(new)} flagged")
    print()
    print(f"still flagged:     {len(kept)}")
    print(f"newly flagged:     {len(added)}")
    print(f"no longer flagged: {len(dropped)}")
    print()

    if added:
        print("=" * 64)
        print("NEWLY FLAGGED - check each of these before publishing")
        print("=" * 64)
        inferred = 0
        for k in sorted(added):
            r = new[k]
            if not HEADER_N.search(r.get("group", "")):
                inferred += 1
            print(show(r))
        if inferred:
            print(f"{inferred} of {len(added)} rest on an inferred sample size.")
            print("Check the paper's own n before treating any of those as a")
            print("finding: the n came from its percentages, which may be wrong.")
            print()

    if dropped:
        print("=" * 64)
        print("NO LONGER FLAGGED - a change retracted these; explain why")
        print("=" * 64)
        for k in sorted(dropped):
            print(show(old[k]))

    if not added and not dropped:
        print("No change to the flagged set.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
