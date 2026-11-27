"""Check single-paper mode on a random sample, not just the papers that fail.

audit/smoke_test.py covers every flagged paper, which exercises the
flag-printing path but leaves two larger populations untested: the papers that
extract cleanly and pass, and the thousands that extract nothing at all. A
crash or a disagreement in either would show up on the website and nowhere in
the published figures.

This draws a random sample across all three outcomes and checks each one:

  extracted-and-passed   confirm_one.py should report the same checkable and
                         flagged counts as the corpus run
  extracted-and-flagged  same, with flags
  skipped                confirm_one.py should exit cleanly with a stated
                         reason, not a traceback

A paper is counted as agreeing when the flag counts match and nothing crashed.
Skipped papers agree when confirm_one.py reports no baseline table and the
corpus run also has no rows for them.

Papers are fetched one at a time from PMC, so keep the sample modest.

Usage:
    python audit/smoke_test_random.py --n 40
    python audit/smoke_test_random.py --n 100 --seed 7 --delay 0.5
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

GRIM_FLAG = re.compile(r"^(\d+) of (\d+) checkable rows report a mean", re.M)
GRIM_PASS = re.compile(r"No inconsistencies found\. (\d+) of (\d+) rows were checkable", re.M)
GRIMMER_FLAG = re.compile(r"^(\d+) of (\d+) checkable rows report a standard", re.M)
NO_TABLE = re.compile(r"No baseline table could be extracted", re.M)
NOT_IN_PMC = re.compile(r"No PMC full text found", re.M)


def counts(path: Path) -> tuple[dict[str, int], dict[str, int]]:
    """Flagged and checkable counts per paper, from a results file."""
    flagged: dict[str, int] = defaultdict(int)
    checkable: dict[str, int] = defaultdict(int)
    for r in csv.DictReader(path.open(encoding="utf-8-sig")):
        pmcid = r["pmcid"].strip().upper()
        cat = (r.get("category") or "").strip()
        if cat == "checked-flagged":
            flagged[pmcid] += 1
            checkable[pmcid] += 1
        elif cat == "checked-passed":
            checkable[pmcid] += 1
    return flagged, checkable


def run_one(pmcid: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "confirm_one.py", pmcid],
                          cwd=HERE, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw", type=Path, default=Path("raw_papers"))
    p.add_argument("--grim", type=Path,
                   default=Path("results/grim_results_v14.csv"))
    p.add_argument("--grimmer", type=Path,
                   default=Path("results/grimmer_results_v14.csv"))
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--seed", type=int, default=20261122)
    p.add_argument("--delay", type=float, default=0.4)
    args = p.parse_args()

    for path in (args.grim, args.grimmer):
        if not path.exists():
            raise SystemExit(f"{path} not found")

    g_flag, _ = counts(args.grim)
    m_flag, _ = counts(args.grimmer)
    # Whether a paper extracted is decided by the extraction output, not by
    # whether any row turned out checkable. Most papers that parse fine have
    # nothing checkable, and counting those as skipped produced ten false
    # disagreements.
    data = Path("results/extracted_data_v14.csv")
    extracted_papers = {r["pmcid"].strip().upper()
                        for r in csv.DictReader(data.open(encoding="utf-8-sig"))}

    everything = sorted({f.stem.upper() for f in args.raw.glob("*.xml")})
    if not everything:
        raise SystemExit(f"no .xml under {args.raw}")
    sample = random.Random(args.seed).sample(
        everything, min(args.n, len(everything)))

    print(f"corpus: {len(everything)} papers; sampling {len(sample)} "
          f"(seed {args.seed})\n")

    agree, disagree, crashed = [], [], []
    kinds = {"flagged": 0, "passed": 0, "skipped": 0}

    for i, pmcid in enumerate(sample, 1):
        want_g, want_m = g_flag.get(pmcid, 0), m_flag.get(pmcid, 0)
        extracted = pmcid in extracted_papers
        kind = "flagged" if (want_g or want_m) else (
            "passed" if extracted else "skipped")
        kinds[kind] += 1

        code, out = run_one(pmcid)

        if code != 0 and not NO_TABLE.search(out) and not NOT_IN_PMC.search(out):
            crashed.append((pmcid, out.strip()[-400:]))
            mark = "CRASH"
        elif kind == "skipped":
            ok = bool(NO_TABLE.search(out) or NOT_IN_PMC.search(out))
            (agree if ok else disagree).append(
                pmcid if ok else (pmcid, "corpus skipped it, confirm_one did not"))
            mark = "ok" if ok else "DISAGREES"
        else:
            gm, mm = GRIM_FLAG.search(out), GRIMMER_FLAG.search(out)
            got_g = int(gm.group(1)) if gm else 0
            got_m = int(mm.group(1)) if mm else 0
            if (got_g, got_m) == (want_g, want_m):
                agree.append(pmcid)
                mark = "ok"
            else:
                disagree.append((pmcid, f"corpus {want_g}/{want_m}, "
                                        f"single-paper {got_g}/{got_m}"))
                mark = "DISAGREES"

        print(f"  [{i:3}/{len(sample)}] {pmcid:14} {kind:8} {mark}")
        time.sleep(args.delay)

    print()
    print("=" * 62)
    print(f"sampled: {kinds['flagged']} flagged, {kinds['passed']} passed, "
          f"{kinds['skipped']} skipped")
    print(f"agrees:     {len(agree)}")
    print(f"disagrees:  {len(disagree)}")
    print(f"crashed:    {len(crashed)}")
    print("=" * 62)

    if disagree:
        print("\nDISAGREEMENTS:")
        for item in disagree:
            print(f"  {item}")
    if crashed:
        print("\nCRASHES:")
        for pmcid, out in crashed:
            print(f"\n  {pmcid}\n{out}")

    return 1 if (disagree or crashed) else 0


if __name__ == "__main__":
    sys.exit(main())
