"""Check single-paper mode against the corpus run, paper by paper.

The website runs confirm_one.py, not the batch pipeline, so the two can drift:
a paper that the corpus run flags could come back clean on the site, or crash
on a code path the batch run never reaches. The flag-printing branch in
particular only executes when a paper actually fails a test, which is a few
dozen papers out of nine thousand.

This runs confirm_one.py over every flagged paper and compares what it reports
against the corpus results. Three outcomes are possible for each:

  agrees      same flag count from both paths
  DISAGREES   different counts - the site and the published figures do not
              match, which has to be resolved before either is quoted
  crashed     confirm_one.py exited non-zero, with its output shown

Papers are fetched one at a time from PMC, so this is slow and rate-limited.
Set NCBI_API_KEY first if you have one.

Usage:
    python audit/smoke_test.py
    python audit/smoke_test.py --limit 20 --delay 0.5
    python audit/smoke_test.py --grim results/grim_results_v14.csv \
        --grimmer results/grimmer_results_v14.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

GRIM_LINE = re.compile(r"^(\d+) of (\d+) checkable rows report a mean", re.M)
GRIMMER_LINE = re.compile(r"^(\d+) of (\d+) checkable rows report a standard", re.M)
NO_TABLE = re.compile(r"No baseline table could be extracted", re.M)


def flagged_by_paper(path: Path) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    if not path.exists():
        raise SystemExit(f"{path} not found")
    for r in csv.DictReader(path.open(encoding="utf-8-sig")):
        if (r.get("category") or "").strip() == "checked-flagged":
            out[r["pmcid"].strip().upper()] += 1
    return out


def run_one(pmcid: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "confirm_one.py", pmcid],
                          cwd=HERE, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--grim", type=Path,
                   default=Path("results/grim_results_v14.csv"))
    p.add_argument("--grimmer", type=Path,
                   default=Path("results/grimmer_results_v14.csv"))
    p.add_argument("--limit", type=int, default=0,
                   help="check only the first N papers (0 = all)")
    p.add_argument("--delay", type=float, default=0.4,
                   help="seconds between fetches")
    args = p.parse_args()

    grim = flagged_by_paper(args.grim)
    grimmer = flagged_by_paper(args.grimmer)
    papers = sorted(set(grim) | set(grimmer))
    if args.limit:
        papers = papers[:args.limit]

    print(f"flagged papers to check: {len(papers)}\n")

    agree, disagree, crashed = [], [], []
    for i, pmcid in enumerate(papers, 1):
        code, out = run_one(pmcid)
        want_g, want_m = grim.get(pmcid, 0), grimmer.get(pmcid, 0)

        if code != 0:
            crashed.append((pmcid, out.strip()[-400:]))
            mark = "CRASH"
        else:
            gm = GRIM_LINE.search(out)
            mm = GRIMMER_LINE.search(out)
            got_g = int(gm.group(1)) if gm else 0
            got_m = int(mm.group(1)) if mm else 0
            if NO_TABLE.search(out):
                disagree.append((pmcid, want_g, want_m, "no table extracted"))
                mark = "DISAGREES"
            elif (got_g, got_m) == (want_g, want_m):
                agree.append(pmcid)
                mark = "ok"
            else:
                disagree.append((pmcid, want_g, want_m,
                                 f"single-paper mode reports {got_g}/{got_m}"))
                mark = "DISAGREES"

        print(f"  [{i:3}/{len(papers)}] {pmcid:14} corpus {want_g}/{want_m}  {mark}")
        time.sleep(args.delay)

    print()
    print("=" * 62)
    print(f"agrees:     {len(agree)}")
    print(f"disagrees:  {len(disagree)}")
    print(f"crashed:    {len(crashed)}")
    print("=" * 62)

    if disagree:
        print("\nDISAGREEMENTS - the site and the published figures differ here:")
        for pmcid, g, m, why in disagree:
            print(f"  {pmcid}  corpus says GRIM {g}, GRIMMER {m}; {why}")
    if crashed:
        print("\nCRASHES:")
        for pmcid, out in crashed:
            print(f"\n  {pmcid}\n{out}")

    return 1 if (disagree or crashed) else 0


if __name__ == "__main__":
    sys.exit(main())
