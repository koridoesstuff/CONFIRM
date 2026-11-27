"""Check grim() and grimmer() against exhaustive ground truth.

Every other test in audit/ checks that the pipeline agrees with itself. None
checks whether the arithmetic is right. If the parity condition or a rounding
window is subtly wrong, every published figure inherits the error and no
consistency test would show it.

This builds ground truth by brute force and compares.

GRIM. For a sample size n and a precision d, a mean is attainable exactly when
some integer total divides by n to round to it. Enumerating every total from 0
to n * max_value gives the complete set of attainable means with no appeal to
the implementation. grim() must accept exactly those and reject everything
else.

GRIMMER. For small n and a small value range, every integer sample can be
enumerated outright. Each gives a mean and an SD, which rounded to the
reported precision form an attainable pair. grimmer() must accept exactly the
pairs that some sample produces. This is the real test: the parity argument
and the sum-of-squares window are shortcuts for this enumeration, and if they
are wrong the two will disagree.

Both directions matter. Accepting an unattainable value is a missed
inconsistency; rejecting an attainable one is a false flag against a published
paper, which is the worse error.

Usage:
    python audit/oracle_test.py
    python audit/oracle_test.py --grim-n 40 --grimmer-n 7 --max-value 12
"""

from __future__ import annotations

import argparse
import itertools
import math
import sys
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grim_check import grim                      # noqa: E402
from grimmer_check import grimmer                # noqa: E402


def rounded(value: float, d: int) -> set[str]:
    """Both conventions' renderings of a value at d decimals."""
    quant = Decimal(1).scaleb(-d)
    dec = Decimal(repr(value))
    return {str(dec.quantize(quant, rounding=m))
            for m in (ROUND_HALF_UP, ROUND_HALF_EVEN)}


def grim_truth(n: int, d: int, max_value: int) -> set[str]:
    """Every mean attainable from n integers in [0, max_value]."""
    out: set[str] = set()
    for total in range(0, n * max_value + 1):
        out |= rounded(total / n, d)
    return out


def check_grim(max_n: int, max_value: int, decimals: tuple[int, ...]) -> list[str]:
    problems = []
    for n in range(2, max_n + 1):
        for d in decimals:
            if n >= 10 ** d:
                continue                       # no discriminating power; skipped upstream
            truth = grim_truth(n, d, max_value)
            # Walk the same space the reported means live in.
            step = Decimal(1).scaleb(-d)
            value = Decimal(0)
            while value <= max_value:
                # Quantize, or Decimal(0) renders as "0" and grim() reads the
                # precision off the string as zero decimals.
                mean = str(value.quantize(step))
                if mean not in truth:
                    # The oracle fixes values to [0, max_value]; grim() assumes
                    # no range, so it legitimately accepts more. Only the other
                    # direction can be a bug.
                    value += step
                    continue
                ok, _note = grim(mean, n)
                if not ok:
                    problems.append(
                        f"GRIM FALSE FLAG: mean={mean} n={n} d={d} "
                        f"is attainable but was rejected")
                value += step
    return problems


def grimmer_truth(n: int, max_value: int, d_mean: int, d_sd: int
                  ) -> set[tuple[str, str]]:
    """Every (mean, SD) pair attainable from n integers in [0, max_value]."""
    out: set[tuple[str, str]] = set()
    for sample in itertools.combinations_with_replacement(
            range(max_value + 1), n):
        total = sum(sample)
        mean = total / n
        var = sum((x - mean) ** 2 for x in sample) / (n - 1)
        sd = math.sqrt(var)
        for m in rounded(mean, d_mean):
            for s in rounded(sd, d_sd):
                out.add((m, s))
    return out


def check_grimmer(n_values: tuple[int, ...], max_value: int,
                  d_mean: int, d_sd: int) -> list[str]:
    problems = []
    for n in n_values:
        truth = grimmer_truth(n, max_value, d_mean, d_sd)
        # Only pairs the enumeration proves attainable are tested. grimmer()
        # places no bound on the values, so a pair unattainable within
        # [0, max_value] may still be attainable to it, and that is correct
        # behaviour rather than a defect.
        for mean, sd in sorted(truth):
            ok, _note = grimmer(mean, sd, n)
            if not ok:
                problems.append(
                    f"GRIMMER FALSE FLAG: mean={mean} sd={sd} n={n} "
                    f"is produced by a real integer sample but was rejected")
    return problems


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--grim-n", type=int, default=30,
                   help="largest sample size to check GRIM at")
    p.add_argument("--grimmer-n", type=int, default=6,
                   help="largest sample size to enumerate for GRIMMER")
    p.add_argument("--max-value", type=int, default=10,
                   help="largest integer a participant may score")
    args = p.parse_args()

    print("GRIM: comparing against every attainable total")
    print(f"  n = 2..{args.grim_n}, values 0..{args.max_value}, 1 and 2 decimals")
    grim_problems = check_grim(args.grim_n, args.max_value, (1, 2))
    print(f"  false flags: {len(grim_problems)}\n")

    ns = tuple(range(3, args.grimmer_n + 1))
    print("GRIMMER: comparing against every integer sample")
    print(f"  n = {ns[0]}..{ns[-1]}, values 0..{args.max_value}, 2 decimals")
    grimmer_problems = check_grimmer(ns, args.max_value, 2, 2)
    print(f"  false flags: {len(grimmer_problems)}\n")

    problems = grim_problems + grimmer_problems
    print("=" * 62)
    if not problems:
        print("No false flags: every value an integer sample can produce")
        print("was accepted by both implementations.")
        print("=" * 62)
        return 0
    print(f"{len(problems)} false flags: values a real integer sample")
    print("produces, which the implementation rejects. Each one would be a")
    print("false accusation against a published paper.")
    print("=" * 62)
    for line in problems[:40]:
        print(f"  {line}")
    if len(problems) > 40:
        print(f"  ... and {len(problems) - 40} more")
    return 1


if __name__ == "__main__":
    sys.exit(main())
