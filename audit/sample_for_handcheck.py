"""Draw a reproducible random sample of extracted papers for hand-checking.

The arithmetic in CONFIRM is verified exhaustively; the extraction layer is not.
This asks the open question: does the pipeline read the same cells from a
published baseline table that a person reading it would?

For each sampled paper it writes every extracted row alongside blank columns to
record what the table actually says. Filling those in gives per-cell agreement
figures, and more importantly shows whether any rows were missed or invented,
which a row-by-row comparison alone would hide.

Sampling is seeded, so the same seed always draws the same papers and the
sample cannot be re-rolled until it looks favourable.

Usage:
    python audit/sample_for_handcheck.py --n 10
    python audit/sample_for_handcheck.py --n 20 --seed 7 --out handcheck_b.csv
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

PMC_URL = "https://pmc.ncbi.nlm.nih.gov/articles/{}/"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=Path("extracted_data.csv"))
    parser.add_argument("--n", type=int, default=10,
                        help="number of papers to sample (default 10)")
    parser.add_argument("--seed", type=int, default=1,
                        help="sampling seed; keep it fixed so the draw is "
                             "reproducible and cannot be re-rolled")
    parser.add_argument("--out", type=Path, default=Path("handcheck_sheet.csv"))
    args = parser.parse_args()

    if not args.data.exists():
        print(f"{args.data} not found", file=sys.stderr)
        return 1

    rows = list(csv.DictReader(args.data.open(encoding="utf-8")))
    if not rows:
        print(f"{args.data} has no rows", file=sys.stderr)
        return 1

    by_paper: dict[str, list[dict]] = {}
    for r in rows:
        by_paper.setdefault(r["pmcid"], []).append(r)

    papers = sorted(by_paper)
    if args.n > len(papers):
        print(f"only {len(papers)} papers available", file=sys.stderr)
        return 1

    rng = random.Random(args.seed)
    sample = sorted(rng.sample(papers, args.n))

    out_rows = []
    for pmcid in sample:
        for r in by_paper[pmcid]:
            out_rows.append({
                "pmcid": pmcid,
                "url": PMC_URL.format(pmcid),
                "variable_extracted": r["variable"],
                "group_extracted": r["group"],
                "n_extracted": r["n"],
                "mean_extracted": r["mean"],
                "sd_extracted": r["sd"],
                # filled in by hand, reading the published table
                "table_number": "",
                "n_actual": "",
                "mean_actual": "",
                "sd_actual": "",
                "row_matches": "",        # yes / no
                "notes": "",
            })
        # one blank row per paper, for rows the pipeline missed entirely
        out_rows.append({
            "pmcid": pmcid,
            "url": PMC_URL.format(pmcid),
            "variable_extracted": "<< rows in the table but NOT extracted >>",
            "group_extracted": "", "n_extracted": "", "mean_extracted": "",
            "sd_extracted": "", "table_number": "", "n_actual": "",
            "mean_actual": "", "sd_actual": "", "row_matches": "", "notes": "",
        })

    fields = list(out_rows[0])
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"sampled {args.n} papers (seed {args.seed}) from "
          f"{len(papers)} with extracted data\n")
    for pmcid in sample:
        print(f"  {pmcid:14} {len(by_paper[pmcid]):3} rows  "
              f"{PMC_URL.format(pmcid)}")
    print(f"\nworksheet -> {args.out}")
    print("\nFor each paper: open the URL, find the baseline table, and for "
          "every row\nrecord what the table says. Add any row the table has "
          "that the pipeline\ndid not extract under the << >> marker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
