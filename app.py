"""Web front end for CONFIRM: enter trial identifiers, get the arithmetic back.

The command-line tools assume Python and a terminal. Reviewers working through
a trustworthiness assessment have neither, and all the pipeline needs is an
identifier, so this puts a box in front of the same stages and accepts a list.

It shells out to the existing scripts rather than reimplementing them, exactly
as confirm_one.py does, so the code path that runs here is the one that was
verified. Nothing about the checks changes.

Run locally:
    streamlit run app.py
"""

from __future__ import annotations

import csv
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
REPO = "https://github.com/koridoesstuff/CONFIRM"
DOI = "https://doi.org/10.5281/zenodo.21740555"

_DASHES = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-",
                         "\u2013": "-", "\u2014": "-", "\u2212": "-"})

# A trailing count/percent fragment left behind when the sample size was lifted
# out of the column header: "... frequency (%", "..., n (%)", "... (%".
_TRAILING_COUNT = re.compile(
    r"[\s,;:-]*(?:frequency|freq\.?|no\.?|n)?\s*\(\s*%\s*\)?\s*$", re.I)

# Square corners, Aller throughout, and no animation on the tab underline.
STYLE = """
<style>
@import url('https://fonts.cdnfonts.com/css/aller');

/* Aller for text. Deliberately NOT applied with !important to every element:
   Streamlit draws its icons as Material Symbols ligatures, and overriding the
   font there makes the ligature names render as literal text ("upload",
   "key_double_arrow"). */
html, body, .stApp, [data-testid="stSidebar"],
h1, h2, h3, h4, h5, h6, p, li, label, table, th, td,
input, textarea, select, .stMarkdown, .stDataFrame {
    font-family: 'Aller', 'Segoe UI', Helvetica, Arial, sans-serif;
}

/* icons keep their own font */
[data-testid="stIconMaterial"], .material-icons,
[class*="material-symbols"], [class*="material-icons"] {
    font-family: 'Material Symbols Rounded', 'Material Icons' !important;
}

/* square corners everywhere */
*, *::before, *::after { border-radius: 0 !important; }

/* no transitions or animations, so tabs switch instantly */
*, *::before, *::after {
    transition: none !important;
    animation: none !important;
}

/* tighter top margin and a smaller title */
.block-container { padding-top: 2.2rem !important; }
h1 { font-size: 2.1rem !important; margin-bottom: 0.4rem !important; }

/* pull the sidebar content to the very top, so the mark is not floating
   below empty space */
[data-testid="stSidebarUserContent"] { padding-top: 0.5rem !important; }
[data-testid="stSidebarHeader"] { padding-bottom: 0 !important; height: auto !important; }

.confirm-mark { display: flex; justify-content: flex-start; margin: 0 0 2px 0; }

/* the results table scrolls sideways on a phone rather than squashing */
[data-testid="stDataFrame"] { overflow-x: auto; }

/* narrow screens: tighter margins, smaller type, no wasted width */
@media (max-width: 640px) {
    .block-container {
        padding-top: 1rem !important;
        padding-left: 0.9rem !important;
        padding-right: 0.9rem !important;
    }
    h1 { font-size: 1.55rem !important; }
    h3, h4 { font-size: 1.05rem !important; }
    .stMarkdown p, .stMarkdown li { font-size: 0.92rem; }
    [data-testid="stDataFrame"] { font-size: 0.82rem; }
    .stTabs [data-baseweb="tab"] { padding-left: 6px; padding-right: 6px; }
    .stTabs [data-baseweb="tab"] p { font-size: 0.85rem; }
}
</style>
"""

# Heptagon mark. Both colours were specified; they sit close together, so the
# letter is deliberately large and heavy to stay legible.
LOGO = """
<svg width="44" height="44" viewBox="0 0 100 100" aria-label="CONFIRM">
  <polygon points="50,2 93,23 100,68 65,98 35,98 0,68 7,23" fill="#ABA8B2"/>
  <text x="50" y="50" text-anchor="middle" dominant-baseline="central"
        font-family="Aller, Segoe UI, Helvetica, Arial, sans-serif"
        font-size="58" font-weight="700" fill="#C3C3C3">C</text>
</svg>
"""


def clean_label(label: str) -> str:
    """Tidy a column header for display. Does not touch the stored data."""
    s = label.translate(_DASHES).strip()
    s = _TRAILING_COUNT.sub("", s)
    if s.count("(") > s.count(")"):
        s = s[:s.rfind("(")]
    return s.strip(" ,;:-") or label


def short_variable(label: str) -> str:
    """Row labels carry their section heading as a prefix; drop it for display."""
    return (label.rpartition(" - ")[2] or label).strip()


def build_query(identifier: str) -> str:
    """PubMed query for one article, from either identifier form."""
    ident = identifier.strip().upper()
    if ident.startswith("PMC"):
        return f"{ident}[pmcid]"
    if ident.isdigit():
        return f"{ident}[pmid]"
    raise ValueError(
        f"{identifier!r} is not a PMID (digits, e.g. 42345586) "
        "or a PMCID (e.g. PMC13296589)."
    )


def parse_identifiers(text: str) -> list[str]:
    """Pull identifiers out of pasted or uploaded text.

    Keeps only tokens shaped like a PMID (all digits) or a PMCID (PMC then
    digits), so a CSV column header, a comment line or stray prose in an
    exported list is dropped rather than fetched. If nothing survives, the
    caller reports that no identifier was found.
    """
    looks_like_id = re.compile(r"^(?:PMC\d+|\d{4,9})$", re.I)
    seen, out = set(), []
    for token in re.split(r"[\s,;]+", (text or "").strip()):
        token = token.strip().strip('"').strip("'").rstrip(".")
        if looks_like_id.match(token) and token.upper() not in seen:
            seen.add(token.upper())
            out.append(token)
    return out


def neighbours(mean: str, n: int) -> str:
    """The two achievable means bracketing a reported value, as fractions."""
    d = len(mean.partition(".")[2])
    quant = Decimal(1).scaleb(-d)
    lo = math.floor(float(mean) * n)
    while (Decimal(lo) / Decimal(n)).quantize(
            quant, rounding=ROUND_HALF_UP) > Decimal(mean):
        lo -= 1
    hi = lo + 1
    lo_v = (Decimal(lo) / Decimal(n)).quantize(quant, rounding=ROUND_HALF_UP)
    hi_v = (Decimal(hi) / Decimal(n)).quantize(quant, rounding=ROUND_HALF_EVEN)
    return f"{lo}/{n} = {lo_v}, {hi}/{n} = {hi_v}"


def run_stage(cmd: list[str]) -> None:
    """Run one pipeline stage, raising with its output if it fails."""
    result = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"{Path(cmd[1]).name} failed.\n\n{result.stdout}\n{result.stderr}")


def api_key() -> str:
    """NCBI key from Streamlit secrets if configured, else the environment."""
    try:
        return st.secrets["NCBI_API_KEY"]
    except Exception:
        return os.environ.get("NCBI_API_KEY", "")


@st.cache_data(show_spinner=False, ttl=3600)
def analyse(identifier: str) -> dict:
    """Fetch, extract and check one trial. Cached, so a repeat is instant."""
    query = build_query(identifier)
    workdir = Path(tempfile.mkdtemp(prefix="confirm_web_"))
    xml_dir = workdir / "xml"
    data_csv = workdir / "extracted.csv"
    grim_csv = workdir / "grim.csv"
    grimmer_csv = workdir / "grimmer.csv"

    try:
        run_stage([sys.executable, "fetch_papers.py", "--query", query,
                   "--retmax", "1", "--outdir", str(xml_dir),
                   "--failed", str(workdir / "failed.csv")])

        xml_files = list(xml_dir.glob("*.xml"))
        if not xml_files:
            raise RuntimeError(
                "No PubMed Central full text found. The article may not be "
                "deposited in PMC, or the identifier may be wrong."
            )

        run_stage([sys.executable, "extract_tables.py", "--indir", str(xml_dir),
                   "--out", str(data_csv),
                   "--skipped", str(workdir / "skipped.csv"),
                   "--unverified", str(workdir / "unverified.csv"),
                   "--borderline", str(workdir / "borderline.csv")])

        extracted = list(csv.DictReader(data_csv.open(encoding="utf-8")))
        if not extracted:
            raise RuntimeError(
                "No baseline characteristics table found. This is expected "
                "for reviews, meta-analyses, protocols and other non-trial "
                "articles. For a trial, it means no table caption matched a "
                "baseline or characteristics pattern, or the table's "
                "structure could not be parsed. CONFIRM selects tables by "
                "caption and does not guess."
            )

        run_stage([sys.executable, "grim_check.py",
                   "--data", str(data_csv), "--out", str(grim_csv)])
        run_stage([sys.executable, "grimmer_check.py",
                   "--data", str(data_csv), "--out", str(grimmer_csv)])

        return {
            "id": identifier,
            "pmcid": xml_files[0].stem,
            "total": len(extracted),
            "grim": list(csv.DictReader(grim_csv.open(encoding="utf-8"))),
            "grimmer": list(csv.DictReader(grimmer_csv.open(encoding="utf-8"))),
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def tested(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["category"].startswith("checked-")]


def excluded(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["category"] == "not-applicable"]


def result_frame(results: list[dict]) -> pd.DataFrame:
    """One row per tested value, across every paper checked."""
    out = []
    for res in results:
        for r in tested(res["grim"]):
            n = int(r["n"])
            ok = r["category"] == "checked-passed"
            out.append({
                "Paper": res["pmcid"],
                "Test": "GRIM",
                "Variable": short_variable(r["variable"]),
                "Group": clean_label(r["group"]),
                "n": n,
                "Reported": r["mean"],
                "Attainable values": "" if ok else neighbours(r["mean"], n),
                "Consistent": ok,
            })
        for r in tested(res["grimmer"]):
            out.append({
                "Paper": res["pmcid"],
                "Test": "GRIMMER",
                "Variable": short_variable(r["variable"]),
                "Group": clean_label(r["group"]),
                "n": int(r["n"]),
                "Reported": f"{r['mean']} ({r['sd']})",
                "Attainable values": "",
                "Consistent": r["category"] == "checked-passed",
            })
    frame = pd.DataFrame(out)
    if frame.empty:
        return frame
    return frame.sort_values(["Consistent", "Paper", "Test"], kind="stable")


def coverage_frame(results: list[dict]) -> pd.DataFrame:
    out = []
    for res in results:
        for test, rows in (("GRIM", res["grim"]), ("GRIMMER", res["grimmer"])):
            counts: dict[str, int] = {}
            for r in excluded(rows):
                key = r["reason"].replace("not applicable - ", "")
                counts[key] = counts.get(key, 0) + 1
            out.append({
                "Paper": res["pmcid"],
                "Test": test,
                "Rows read": res["total"],
                "Rows tested": len(tested(rows)),
                "Not tested": len(excluded(rows)),
                "Main reason": max(counts, key=counts.get) if counts else "",
            })
    return pd.DataFrame(out)


def reason_frame(results: list[dict]) -> pd.DataFrame:
    counts: dict[tuple[str, str], int] = {}
    for res in results:
        for test, rows in (("GRIM", res["grim"]), ("GRIMMER", res["grimmer"])):
            for r in excluded(rows):
                key = (test, r["reason"].replace("not applicable - ", ""))
                counts[key] = counts.get(key, 0) + 1
    return pd.DataFrame(
        [{"Test": t, "Reason not tested": why, "Rows": n}
         for (t, why), n in sorted(counts.items(), key=lambda kv: -kv[1])]
    )


def show_results(results: list[dict], failures: list[tuple[str, str]],
                 compact: bool = False) -> None:
    for ident, message in failures:
        st.warning(f"**{ident}** — {message}")

    if not results:
        return

    frame = result_frame(results)
    if frame.empty:
        st.info(
            "Nothing in these papers was testable. Both checks apply only to "
            "measures that can take whole numbers; see **What was tested**."
        )
        return

    failed = int((~frame["Consistent"]).sum())
    papers = frame.loc[~frame["Consistent"], "Paper"].nunique()
    if failed:
        st.markdown(
            f"**{failed} of {len(frame)} tested values are inconsistent**, "
            f"across {papers} of {len(results)} paper(s) checked."
        )
    else:
        st.markdown(
            f"**No inconsistencies found** in {len(frame)} tested values "
            f"across {len(results)} paper(s)."
        )

    # The full frame always goes to the CSV; the view can be narrowed.
    view = frame
    if len(results) == 1:
        view = view.drop(columns=["Paper"])          # redundant for one paper
    if compact:
        keep = [c for c in ("Test", "Variable", "Reported", "Consistent")
                if c in view.columns]
        view = view[keep]

    st.dataframe(view, hide_index=True, use_container_width=True)
    if compact:
        st.caption(
            "Compact view. Group, sample size and attainable values are in "
            "the CSV."
        )
    st.download_button(
        "Download results (CSV)",
        frame.to_csv(index=False).encode("utf-8"),
        file_name="confirm_results.csv",
        mime="text/csv",
    )


def show_coverage(results: list[dict]) -> None:
    st.markdown(
        "Both checks apply only to measures that can take whole numbers, at "
        "sample sizes small enough for the test to discriminate. Rows that do "
        "not qualify are excluded and logged rather than guessed at, which is "
        "why most of a typical baseline table is not testable. Excluded rows "
        "were not tested, and no conclusion should be drawn about them."
    )
    st.dataframe(coverage_frame(results), hide_index=True,
                 use_container_width=True)
    st.markdown("**Why rows were not tested**")
    st.dataframe(reason_frame(results), hide_index=True,
                 use_container_width=True)


def show_guidance() -> None:
    st.markdown("""
#### GRIM — reported means

If a measure can only take whole numbers, the total across a group is a whole
number, so the mean must equal that total divided by the number of
participants. Only certain means are therefore attainable, and the gaps
between them widen as the group gets smaller.

With eleven participants, 24/11 rounds to 2.18 and 25/11 rounds to 2.27.
Nothing lies between them, so a reported mean of 2.22 cannot have come from
eleven whole numbers. GRIM is from Brown and Heathers (2017).

#### GRIMMER — reported standard deviations

Calculating a standard deviation involves squaring each value, and squares of
whole numbers are whole numbers, so the sum of squares is also an integer.
That constrains which standard deviations are attainable. A further condition
sharpens it: for any whole number, the value and its square are both odd or
both even, so the sum of squares must match the total in parity.

GRIMMER is from Anaya (2016).

#### Rounding

A reported value is treated as attainable if it is reachable under either
round-half-up or round-half-even, since journals differ. Assuming one
convention alone produces false positives.

#### When the checks do not apply

- The measure is continuous (age, weight, laboratory values), so no gaps exist
- The measure type cannot be established from the row label
- The table gives no sample size for that column
- The row reports a median and interquartile range rather than a mean and SD
- The sample is large enough that every value at the reported precision is
  attainable, so the check cannot fail and a pass carries no information
- The reported mean falls outside the instrument's valid range, or is low
  enough to suggest a per-item rather than a total score

#### What an inconsistent value means

That the reported figure cannot have come from whole-number data at the
stated sample size. It does not establish why. A transcription error, an
analysed denominator different from the tabulated one, missing data, or a
mislabelled measure would all produce the same result.
""")


def show_about() -> None:
    st.markdown(f"""
CONFIRM retrieves randomised controlled trials with full text in PubMed
Central, extracts the baseline characteristics table from the article's JATS
XML, and applies the GRIM and GRIMMER arithmetic-consistency tests to the
reported means and standard deviations. It runs against a single trial or
across a corpus; the published run screened 9,698 trials and 45,724
extracted rows.

**What it can read.** The article must be in PubMed Central as full text and
must contain a baseline characteristics table. Reviews, meta-analyses and
protocols have no such table and will return nothing. There is no support for
PDFs.

**Limitations.** Extraction, rather than the arithmetic, is the least audited
layer. Tables are selected by caption with no positional fallback, so a trial
whose baseline table is captioned unusually is skipped entirely rather than
guessed at.

Source, results, documented limitations and version history:
[{REPO}]({REPO})

Archived release: [10.5281/zenodo.21740555]({DOI})
""")


def main() -> None:
    icon = HERE / "assets" / "confirm-icon.png"
    st.set_page_config(
        page_title="CONFIRM",
        page_icon=str(icon) if icon.exists() else None,
        layout="wide",
    )
    st.markdown(STYLE, unsafe_allow_html=True)

    key = api_key()
    if key:
        os.environ["NCBI_API_KEY"] = key

    with st.sidebar:
        st.markdown(f'<div class="confirm-mark">{LOGO}</div>',
                    unsafe_allow_html=True)
        st.markdown("### Trials")
        pasted = st.text_area(
            "PMIDs or PMCIDs",
            placeholder="42345586\nPMC13296589\n…",
            height=140,
            help="One per line, or separated by commas or spaces. "
                 "A PMID is all digits; a PMCID starts with PMC.",
        )
        st.caption("or upload a list of identifiers")
        uploaded = st.file_uploader(
            "List of identifiers", type=["txt", "csv"],
            label_visibility="collapsed",
        )
        go = st.button("Check", type="primary", use_container_width=True)

        compact = st.toggle(
            "Compact table",
            help="Fewer columns, for narrow screens. The full set is always "
                 "in the CSV download.",
        )

        st.divider()
        st.markdown("### Examples")
        st.caption(
            "Three trials with known inconsistencies, for trying the tool "
            "without looking up an identifier."
        )
        ex_a = st.button("Means and SDs flagged", use_container_width=True)
        ex_b = st.button("SDs only", use_container_width=True)
        ex_c = st.button("A count variable", use_container_width=True)
        st.caption(
            "Each trial is fetched from PubMed Central and checked in turn, "
            "which takes up to a minute per article."
        )
        st.divider()
        st.caption(f"[Source and documentation]({REPO})")

    st.title("CONFIRM")
    st.markdown(
        "Each row checks a reported mean or standard deviation against the "
        "values that are arithmetically attainable from whole-number data at "
        "the stated sample size. If a measure can only take whole numbers, "
        "the group total is a whole number, so the mean must be that total "
        "divided by the number of participants, and only certain values are "
        "possible. The Consistent column is FALSE where the reported "
        "figure falls between two attainable values, and so cannot have "
        "come from the data as described."
    )

    if ex_a:
        st.session_state["queued"] = ["42345586"]
    elif ex_b:
        st.session_state["queued"] = ["PMC12815704"]
    elif ex_c:
        st.session_state["queued"] = ["PMC13393941"]
    elif go:
        text = pasted or ""
        if uploaded is not None:
            text += "\n" + uploaded.getvalue().decode("utf-8", errors="ignore")
        st.session_state["queued"] = parse_identifiers(text)

    identifiers = st.session_state.pop("queued", None)
    if identifiers is not None:
        if not identifiers:
            st.session_state["results"] = []
            st.session_state["failures"] = []
            st.warning("No PMIDs or PMCIDs found. A PMID is all digits; a PMCID "
                       "starts with PMC. Other text is ignored.")
        else:
            results, failures = [], []
            progress = st.progress(0.0, text="Starting…")
            for i, ident in enumerate(identifiers, start=1):
                progress.progress(
                    (i - 1) / len(identifiers),
                    text=f"Checking {ident} ({i} of {len(identifiers)})…")
                try:
                    results.append(analyse(ident))
                except (ValueError, RuntimeError) as exc:
                    failures.append((ident, str(exc)))
            progress.empty()
            st.session_state["results"] = results
            st.session_state["failures"] = failures

    results = st.session_state.get("results", [])
    failures = st.session_state.get("failures", [])

    results_tab, coverage_tab, guidance_tab, about_tab = st.tabs(
        ["Results", "What was tested", "Guidance", "About"])

    with results_tab:
        if results or failures:
            show_results(results, failures, compact)
        else:
            st.info("Enter one or more identifiers in the sidebar and "
                    "select Check.")
            st.caption(
                f"Screening at scale, with no identifiers, runs from the "
                f"command line rather than here: the published sweep covered "
                f"9,698 trials. See [the repository]({REPO})."
            )

    with coverage_tab:
        if results:
            show_coverage(results)
        else:
            st.info("No trial checked yet.")

    with guidance_tab:
        show_guidance()

    with about_tab:
        show_about()


if __name__ == "__main__":
    main()