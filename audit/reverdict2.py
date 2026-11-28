"""Re-decide every checked row by interval arithmetic, and compare verdicts.

The oracle test checks grim() and grimmer() in isolation. This checks the
verdicts actually recorded against the corpus, which is a different question:
a row can be decided correctly by the function and still come out wrong if the
precision was read off the wrong string, or the sample size parsed oddly, or a
value carried a stray character.

It also covers the case nothing else does. Every test so far looks at flagged
rows. A row that passed but should have failed is a missed inconsistency, and
there are several hundred passes that nobody has ever re-derived.

The method here is deliberately not the pipeline's. grim() works forwards:
take the candidate totals around the mean, divide, round, and see whether any
lands on the reported value. This works backwards from the rounding interval:
a mean reported to d decimals stands for an interval of width 10^-d, so the
total must be an integer inside [n*(mean-h), n*(mean+h)]. Whether such an
integer exists is a question about that interval alone. The same inversion
gives the sum of squares for GRIMMER.

Two derivations of the same mathematics should agree on every row. Where they
do not, one is wrong and the row needs working by hand.

Usage:
    python audit/reverdict.py
    python audit/reverdict.py --grim results/grim_results_v14.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from decimal import Decimal, ROUND_HALF_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP
from pathlib import Path


def decimals(s: str) -> int:
    return len(s.partition(".")[2])


def totals_in_interval(mean: str, n: int) -> list[int]:
    """Every integer total consistent with the reported mean.

    A value printed as 12.18 to two decimals came from something in
    [12.175, 12.185). Multiplying by n gives the interval the total must lie
    in, and the attainable totals are the integers inside it. Half-even
    rounding can put an exact boundary either way, so both endpoints are
    admitted.
    """
    d = decimals(mean)
    h = 0.5 * 10 ** (-d)
    m = float(mean)
    lo, hi = (m - h) * n, (m + h) * n
    first = math.ceil(lo - 1e-9)
    last = math.floor(hi + 1e-9)
    quant = Decimal(1).scaleb(-d)
    out = []
    for t in range(first, last + 1):
        on_edge = abs(t - lo) < 1e-9 or abs(t - hi) < 1e-9
        if not on_edge:
            out.append(t)
            continue
        # A total sitting exactly on the boundary is a tie, and a tie only
        # counts if it rounds inward. 78/8 is 9.75, which goes to 9.8 under
        # both conventions and so cannot produce a reported 9.7.
        quotient = Decimal(t) / Decimal(n)
        if any(quotient.quantize(quant, rounding=mode) == Decimal(mean)
               for mode in (ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN)):
            out.append(t)
    return out


def grim_ok(mean: str, n: int) -> bool:
    return bool(totals_in_interval(mean, n))


def grimmer_ok(mean: str, sd: str, n: int) -> bool:
    """Is some integer sum of squares consistent with both reported values?"""
    if n < 2:
        return True
    totals = totals_in_interval(mean, n)
    if not totals:
        return False
    h = 0.5 * 10 ** (-decimals(sd))
    s = float(sd)
    lo_sd, hi_sd = max(0.0, s - h), s + h
    for total in totals:
        offset = total * total / n
        lo = lo_sd * lo_sd * (n - 1) + offset
        hi = hi_sd * hi_sd * (n - 1) + offset
        for ss in range(math.ceil(lo - 1e-9), math.floor(hi + 1e-9) + 1):
            if (ss - total) % 2:
                continue                       # parity: x and x^2 agree mod 2
            if ss * n >= total * total:        # variance cannot be negative
                return True
    return False


def check(path: Path, which: str) -> list[str]:
    if not path.exists():
        raise SystemExit(f"{path} not found")
    problems = []
    checked = passed = flagged = 0
    for r in csv.DictReader(path.open(encoding="utf-8-sig")):
        cat = (r.get("category") or "").strip()
        if not cat.startswith("checked"):
            continue
        checked += 1
        said_ok = cat == "checked-passed"
        passed += said_ok
        flagged += not said_ok
        try:
            n = int(r["n"])
        except (TypeError, ValueError):
            continue
        if which == "GRIM":
            mine = grim_ok(r["mean"], n)
        else:
            if not (r.get("sd") or "").strip():
                continue
            mine = grimmer_ok(r["mean"], r["sd"], n)
        if mine != said_ok:
            kind = ("pipeline FLAGGED, interval method says reachable"
                    if said_ok is False else
                    "pipeline PASSED, interval method says unreachable")
            problems.append(
                f"{which} {r['pmcid']}  {r['variable'][:40]}  "
                f"group {r['group'][:20]!r} n={n} mean={r['mean']} "
                f"sd={r.get('sd','')}\n      {kind}")
    print(f"{which}: {checked} checked rows ({flagged} flagged, {passed} passed)")
    print(f"  verdicts that differ: {len(problems)}")
    return problems


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--grim", type=Path,
                   default=Path("results/grim_results_v14.csv"))
    p.add_argument("--grimmer", type=Path,
                   default=Path("results/grimmer_results_v14.csv"))
    p.add_argument("--show", type=int, default=20)
    args = p.parse_args()

    problems = check(args.grim, "GRIM")
    print()
    problems += check(args.grimmer, "GRIMMER")

    print()
    print("=" * 66)
    if not problems:
        print("Both derivations agree on every checked row.")
        print("=" * 66)
        return 0
    print(f"{len(problems)} rows where the two derivations disagree.")
    print("One of them is wrong; work each by hand before publishing.")
    print("=" * 66)
    for line in problems[:args.show]:
        print(f"  {line}")
    if len(problems) > args.show:
        print(f"  ... and {len(problems) - args.show} more")
    return 1


if __name__ == "__main__":
    sys.exit(main())
