"""Draw a blind sample from every fetched paper, for hand-rating.

The October hand-check sampled from extracted_data.csv - that is, from the
papers CONFIRM already succeeded on. That design can measure extraction
accuracy but it cannot measure coverage, because the papers that produced
nothing are not in the frame. 6,914 of 9,698 fetched papers produced no rows
at all, so the larger question is how many of those a human would have
extracted from. This samples from raw_papers/ instead, which is every paper
fetched regardless of outcome.

Two tiers, written as separate worksheets:

  Tier 1 (coverage, cheap - about 2 minutes a paper). Does a baseline table
  exist, does it contain rows on integer-valued measures, and roughly how
  many? Answers "what fraction of the literature is in scope, and what
  fraction of that does CONFIRM reach".

  Tier 2 (accuracy, expensive - about 20 minutes a paper). Transcribe every
  integer-valued row by hand: variable, group, n, mean, SD. Answers "when
  CONFIRM does extract, is the extraction right", and - unlike the October
  check - also catches rows it silently dropped.

Neither worksheet contains any CONFIRM output. The rater sees the PMCID, a
link, and empty columns. That makes the rating blind by construction rather
than by discipline, which is the only version of it that survives a reviewer
asking how the comparison was done. Compare afterwards, with a join on
pmcid, by a separate script.

Sampling is seeded, so the draw is reproducible and the sample frame can be
stated in a methods section. Tier 2 is drawn as a subset of tier 1 so the
same papers carry both ratings.

Usage:
    python audit/sample_all_papers.py
    python audit/sample_all_papers.py --tier1 300 --tier2 50 --seed 20261117
    python audit/sample_all_papers.py --raw raw_papers --outdir audit/gold
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

TIER1_FIELDS = [
    "pmcid",
    "url",
    "is_rct",                 # y / n / unclear
    "baseline_table_exists",  # y / n
    "table_number",           # e.g. "Table 1", blank if none
    "integer_rows_present",   # y / n
    "integer_row_count",      # how many rows x arms are GRIM-eligible
    "notes",
]

TIER2_FIELDS = [
    "pmcid",
    "url",
    "table_number",
    "variable",
    "group",
    "n",
    "mean",
    "sd",
    "is_integer_measure",     # y / n / unclear
    "notes",
]

URL = "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"


def pmcids(raw: Path) -> list[str]:
    """Every fetched paper, by PMCID, in sorted order so the seed governs."""
    ids = sorted({p.stem for p in raw.glob("*.xml")})
    if not ids:
        raise SystemExit(
            f"No .xml files under {raw}. Point --raw at the directory "
            "fetch_papers.py wrote to.")
    return ids


def write(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, default=Path("raw_papers"),
                        help="directory of fetched PMC XML (default: raw_papers)")
    parser.add_argument("--outdir", type=Path, default=Path("audit/gold"),
                        help="where to write the worksheets")
    parser.add_argument("--tier1", type=int, default=300,
                        help="papers in the coverage sample")
    parser.add_argument("--tier2", type=int, default=50,
                        help="papers in the transcription sample (subset of tier 1)")
    parser.add_argument("--seed", type=int, default=20261117,
                        help="random seed; record this in the write-up")
    args = parser.parse_args()

    if args.tier2 > args.tier1:
        print("--tier2 must not exceed --tier1 (it is drawn from it)",
              file=sys.stderr)
        return 1

    everything = pmcids(args.raw)
    if args.tier1 > len(everything):
        print(f"only {len(everything)} papers available; sampling all of them",
              file=sys.stderr)

    rng = random.Random(args.seed)
    tier1 = sorted(rng.sample(everything, min(args.tier1, len(everything))))
    tier2 = sorted(rng.sample(tier1, min(args.tier2, len(tier1))))

    t1_rows = [{"pmcid": p, "url": URL.format(pmcid=p),
                **{f: "" for f in TIER1_FIELDS[2:]}} for p in tier1]

    # One blank line per paper to start; the rater adds rows as needed.
    t2_rows = [{"pmcid": p, "url": URL.format(pmcid=p),
                **{f: "" for f in TIER2_FIELDS[2:]}} for p in tier2]

    t1_path = args.outdir / "tier1_coverage.csv"
    t2_path = args.outdir / "tier2_transcription.csv"
    write(t1_path, TIER1_FIELDS, t1_rows)
    write(t2_path, TIER2_FIELDS, t2_rows)

    frame = args.outdir / "sample_frame.txt"
    frame.write_text(
        f"sample frame: {len(everything)} papers under {args.raw}\n"
        f"seed: {args.seed}\n"
        f"tier 1: {len(tier1)} papers (coverage)\n"
        f"tier 2: {len(tier2)} papers (transcription, drawn from tier 1)\n"
        "No CONFIRM output appears in either worksheet; the rating is blind.\n",
        encoding="utf-8")

    print(f"papers available:   {len(everything)}")
    print(f"tier 1 (coverage):  {len(tier1):4}  -> {t1_path}")
    print(f"tier 2 (transcribe):{len(tier2):4}  -> {t2_path}")
    print(f"frame recorded      -> {frame}")
    print()
    print("Rate the worksheets from the papers themselves. Do not open")
    print("CONFIRM's results until both are finished, or the comparison")
    print("is no longer blind.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
