"""Compare the hand-rated gold worksheets against what CONFIRM produced.

Run this only after both worksheets are filled in. It opens CONFIRM's output
for the first time, joins on pmcid, and reports two things:

  Coverage (tier 1). Of the papers a human says have a baseline table with
  integer-valued rows, how many did CONFIRM extract anything from? The
  papers where the human says yes and CONFIRM produced nothing are the
  false negatives - the number that decides whether the tool is usable as a
  screen or only as a convenience on papers it happens to parse.

  Extraction accuracy (tier 2). For papers rated row by row, how do the
  hand-transcribed rows line up with CONFIRM's? Matched rows are compared
  on n, mean and SD. Rows only the human has are drops; rows only CONFIRM
  has are spurious.

Row matching is on (pmcid, variable, group), normalised for case and
whitespace. That key is not reliable - papers reuse variable names across
panels, and the human's wording for a group will not match the parser's
column header - so the row-level numbers here are a starting point for a
manual reconciliation, not a final figure. Unmatched rows are listed in
full for that reason. The coverage numbers, which join only on pmcid, do
not have this problem and can be quoted directly.

Usage:
    python audit/compare_gold.py
    python audit/compare_gold.py --gold audit/gold --results results
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def yes(s: str) -> bool:
    return norm(s) in {"y", "yes", "true", "1"}


def no(s: str) -> bool:
    return norm(s) in {"n", "no", "false", "0"}


def load(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"{path} not found")
    return list(csv.DictReader(path.open(encoding="utf-8-sig")))


def coverage(tier1: list[dict], extracted: list[dict]) -> None:
    got_rows: dict[str, int] = defaultdict(int)
    for r in extracted:
        got_rows[r["pmcid"].strip().upper()] += 1

    rated = [r for r in tier1 if norm(r["baseline_table_exists"])]
    unrated = len(tier1) - len(rated)

    in_scope, out_of_scope = [], []
    for r in rated:
        if yes(r["baseline_table_exists"]) and yes(r["integer_rows_present"]):
            in_scope.append(r)
        else:
            out_of_scope.append(r)

    hit = [r for r in in_scope if got_rows[r["pmcid"].upper()]]
    miss = [r for r in in_scope if not got_rows[r["pmcid"].upper()]]
    false_pos = [r for r in out_of_scope if got_rows[r["pmcid"].upper()]]

    print("COVERAGE  (tier 1, join on pmcid only)")
    print("=" * 66)
    print(f"papers in the sample:            {len(tier1)}")
    if unrated:
        print(f"  not yet rated, excluded:       {unrated}")
    print(f"  rated:                         {len(rated)}")
    print()
    print(f"human says in scope:             {len(in_scope)}"
          f"   ({len(in_scope) / len(rated):.1%} of rated)"
          if rated else "")
    print(f"  CONFIRM extracted something:   {len(hit)}")
    print(f"  CONFIRM extracted nothing:     {len(miss)}   <- false negatives")
    if in_scope:
        print(f"  recall:                        {len(hit) / len(in_scope):.1%}")
    print()
    print(f"human says out of scope:         {len(out_of_scope)}")
    print(f"  CONFIRM extracted anyway:      {len(false_pos)}   <- check these")
    print()

    hand_rows = sum(int(r["integer_row_count"] or 0) for r in in_scope)
    tool_rows = sum(got_rows[r["pmcid"].upper()] for r in in_scope)
    if hand_rows:
        print(f"integer rows the human counted:  {hand_rows}")
        print(f"rows CONFIRM extracted on those: {tool_rows}"
              f"   ({tool_rows / hand_rows:.1%})")
        print("  (CONFIRM's rows are not restricted to integer measures, so")
        print("   this ratio is indicative only - it can exceed 100%.)")
        print()

    if miss:
        print("papers the human could extract from and CONFIRM could not:")
        for r in sorted(miss, key=lambda r: r["pmcid"]):
            note = f"  {r['notes'].strip()}" if r.get("notes", "").strip() else ""
            print(f"  {r['pmcid']:<14} {r.get('table_number', ''):<10}"
                  f"{r.get('integer_row_count', ''):>5} rows{note}")
        print()
    if false_pos:
        print("papers CONFIRM extracted from but the human ruled out:")
        for r in sorted(false_pos, key=lambda r: r["pmcid"]):
            note = f"  {r['notes'].strip()}" if r.get("notes", "").strip() else ""
            print(f"  {r['pmcid']:<14} {got_rows[r['pmcid'].upper()]:>4} rows{note}")
        print()


def key(r: dict) -> tuple[str, str, str]:
    return (r["pmcid"].strip().upper(), norm(r["variable"]), norm(r["group"]))


def accuracy(tier2: list[dict], extracted: list[dict]) -> None:
    rated_papers = {r["pmcid"].strip().upper() for r in tier2
                    if norm(r["variable"])}
    hand = {key(r): r for r in tier2 if norm(r["variable"])}
    tool = {key(r): r for r in extracted
            if r["pmcid"].strip().upper() in rated_papers}

    both = sorted(set(hand) & set(tool))
    only_hand = sorted(set(hand) - set(tool))
    only_tool = sorted(set(tool) - set(hand))

    print("EXTRACTION ACCURACY  (tier 2, key = pmcid + variable + group)")
    print("=" * 66)
    print(f"papers transcribed:              {len(rated_papers)}")
    print(f"rows transcribed by hand:        {len(hand)}")
    print(f"rows CONFIRM has on those papers:{len(tool)}")
    print()
    print(f"  matched on the key:            {len(both)}")
    print(f"  only the human has:            {len(only_hand)}")
    print(f"  only CONFIRM has:              {len(only_tool)}")
    print()
    print("A key mismatch is usually different wording, not a missing row.")
    print("Reconcile the two lists below by hand before quoting any of this.")
    print()

    mismatch: list[tuple] = []
    for k in both:
        h, t = hand[k], tool[k]
        for field in ("n", "mean", "sd"):
            hv, tv = norm(h.get(field, "")), norm(t.get(field, ""))
            if hv != tv:
                mismatch.append((k, field, hv, tv))

    if both:
        bad_rows = len({m[0] for m in mismatch})
        print(f"matched rows agreeing on n, mean and SD: "
              f"{len(both) - bad_rows}/{len(both)}"
              f" = {(len(both) - bad_rows) / len(both):.1%}")
        print()
    if mismatch:
        print("disagreements on matched rows:")
        for (pmcid, var, group), field, hv, tv in mismatch:
            print(f"  {pmcid}  {var[:34]:<34} {group[:16]:<16}")
            print(f"      {field}: human {hv!r}  CONFIRM {tv!r}")
        print()

    if only_hand:
        print("rows only the human has (candidate drops):")
        for pmcid, var, group in only_hand:
            print(f"  {pmcid}  {var[:40]:<40} {group[:20]}")
        print()
    if only_tool:
        print("rows only CONFIRM has (candidate spurious):")
        for pmcid, var, group in only_tool:
            print(f"  {pmcid}  {var[:40]:<40} {group[:20]}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gold", type=Path, default=Path("audit/gold"))
    parser.add_argument("--results", type=Path, default=Path("results"))
    args = parser.parse_args()

    tier1 = load(args.gold / "tier1_coverage.csv")
    tier2 = load(args.gold / "tier2_transcription.csv")
    extracted = load(args.results / "extracted_data.csv")

    if not any(norm(r["baseline_table_exists"]) for r in tier1):
        print("tier1_coverage.csv has no ratings in it yet.", file=sys.stderr)
        return 1

    coverage(tier1, extracted)
    print()
    if any(norm(r["variable"]) for r in tier2):
        accuracy(tier2, extracted)
    else:
        print("tier2_transcription.csv is still empty; skipping accuracy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
