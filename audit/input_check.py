"""Feed confirm_one.py the things a stranger will actually type.

Every other test uses well-formed PMCIDs taken from the corpus. The website
takes free text, so the first thing an unfamiliar visitor does is type
something the pipeline has never seen: a DOI, a lowercase id, a PubMed record
with no PMC full text, a typo, an empty box.

The bar for each is not that it works. It is that it fails in a way a person
can act on: a stated reason and a clean exit, never a traceback. A Python
traceback on a public tool reads as broken, and tells the visitor nothing
about what to type instead.

Each case below carries what should happen. "handled" means the run either
succeeded or explained itself; "traceback" means it crashed.

Usage:
    python audit/input_check.py
    python audit/input_check.py --delay 0.6
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

TRACEBACK = re.compile(r"^Traceback \(most recent call last\)", re.M)

# (what is typed, why it is worth testing, what a good answer looks like)
CASES: list[tuple[str, str, str]] = [
    ("PMC13296589", "a PMCID that works", "full report"),
    ("pmc13296589", "lowercase", "should behave the same"),
    ("  PMC13296589  ", "stray whitespace", "should behave the same"),
    ("42345586", "a bare PMID", "resolved via PubMed"),
    ("PMC99999999", "a PMCID that does not exist", "stated, not crashed"),
    ("13296589", "digits that are really a PMCID", "treated as a PMID, likely not found"),
    ("10.1111/nicc.70548", "a DOI pasted by mistake", "rejected with a reason"),
    ("", "an empty box", "rejected with a reason"),
    ("abc", "nonsense", "rejected with a reason"),
    ("PMC-13296589", "a hyphen in the id", "rejected with a reason"),
    ("PMID:42345586", "a prefixed PMID", "rejected with a reason"),
    ("https://pmc.ncbi.nlm.nih.gov/articles/PMC13296589/",
     "the whole URL pasted", "accepted, id lifted out"),
]


def run(arg: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "confirm_one.py", arg],
                          cwd=HERE, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def first_line(out: str) -> str:
    for line in out.splitlines():
        line = line.strip()
        if line and not line.startswith("fetching") and not line.startswith("extracting"):
            return line[:78]
    return "(no output)"


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--delay", type=float, default=0.5)
    args = p.parse_args()

    crashed = []
    print(f"{len(CASES)} inputs\n")
    for typed, why, expected in CASES:
        code, out = run(typed)
        crash = bool(TRACEBACK.search(out))
        if crash:
            crashed.append((typed, why, out.strip()[-500:]))
        state = "TRACEBACK" if crash else f"handled (exit {code})"
        shown = repr(typed) if typed.strip() != typed or not typed else typed
        print(f"  {shown:<52} {state}")
        print(f"      {why}; expected {expected}")
        print(f"      said: {first_line(out)}")
        print()
        time.sleep(args.delay)

    print("=" * 62)
    print(f"handled cleanly: {len(CASES) - len(crashed)} of {len(CASES)}")
    print(f"tracebacks:      {len(crashed)}")
    print("=" * 62)
    for typed, why, out in crashed:
        print(f"\n  input {typed!r} ({why}):\n{out}")
    return 1 if crashed else 0


if __name__ == "__main__":
    sys.exit(main())
