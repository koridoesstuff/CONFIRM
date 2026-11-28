# Findings

Investigated findings from the pipeline, recorded as they are resolved. Each entry
states what was found, how strongly it is corroborated, and what remains open.
Papers are cited by PMCID. Same convention as `LIMITATIONS.md`.

## Overview

**Corpus: 9,698 papers** (the first 9,999 PMIDs of the query, less publisher-blocked
records), yielding 51,082 extracted rows from 3,236 papers with usable baseline
tables. Of **531 checkable rows, 63 are flagged (11.9%)**, across 28 papers.

GRIMMER, added in v1.1, tests the standard deviation on the same principle.
It is checkable on 413 rows and flags 32 across 26 papers, none of which
overlap the GRIM flags. Two fall in PMC13296589, on rows that pass GRIM:
SPPB in the exercise arm (n = 12, mean 8.75, SD 1.55) and GAD-7 in the
COMBAT-ICU arm (n = 13, mean 3.77, SD 2.00). Both were confirmed by
enumerating every achievable sum of squares within the instrument's range,
and both remain unreachable under the population-SD convention as well.
Three more fall in PMC12815704, where GRIM finds nothing at all — see the
GRIMMER finding below.

Ten flags were investigated during the initial 947-paper corpus. Nine survive
unchanged in the full run; the BDI flag was later withdrawn as a rounding
artifact (see "Correction to the v1.0 results" below):

Charlson Comorbidity Index ×4 and APACHE II ×3 (both in PMC13296589, both
corroborated by an independent pooled-column check beyond GRIM alone — see
flagship entry), PHQ-9 ×1 (PMC13370186), Day 7 MADRS ×1 (PMC13389161 — see MADRS
entry), BDI ×1 (PMC13260263). The PHQ-9 flag is confirmed unreachable by GRIM 
and hand-verified arithmetically,
but has not been investigated further beyond
that. The BDI flag was withdrawn: the
mean is reachable under round-half-even
rounding.

**54 of the 63 flags are uninvestigated.** They are arithmetically confirmed
unreachable but nothing further is known about them. Papers with the most flags:
PMC13296589 (7), PMC12660629 (5), PMC12625294 (4), PMC12625497 (4). Do not treat
the uninvestigated flags as findings — the MADRS entry below shows how readily a
confirmed-unreachable mean dissolves under one plausible attrition scenario, and
`LIMITATIONS.md` lists flags that survive only because their measure type is still
misclassified.

Arithmetic for the two of the ten confirmed by hand but not examined further
(the BDI row has since been withdrawn):

| Flag | n | Mean | Nearest reachable values | Verdict |
| --- | --- | --- | --- | --- |
| PHQ-9, PMC13370186, Waitlist | 44 | 9.38 | 412/44 = 9.36, 413/44 = 9.39 | unreachable |
| BDI, PMC13260263, arm T | 8 | 9.2 | 74/8 = 9.25 | withdrawn — see correction |

The 11.9% rate rests on a denominator of 531 — 1.0% of all extracted rows. See
`LIMITATIONS.md` on GRIM's narrow reach.

## Flagship finding — PMC13296589, Table 3

The pooled 'All' column cannot be reconciled with the n-weighted average of the
three arms for Age, APACHE II, and the Charlson Comorbidity Index, while all
twelve outcome-measure rows in the same table reconcile to within rounding.
Exhaustive search over possible per-arm analysed sample sizes finds no plausible
missing-data pattern that resolves the CCI or APACHE II discrepancies. This is the
strongest finding in the dataset — corroborated by GRIM, the pooled-column check,
and elimination of the missing-data explanation.

Supporting detail:

| Variable | Pooled 'All' | n-weighted arms | Missingness that would be needed |
| --- | --- | --- | --- |
| Age | 65.12 | 66.024 | drop 8 of 11 controls |
| APACHE II | 18.61 | 18.506 | drop 7 of 12 from Exercise |
| Charlson CI | 2.21 | 2.177 | drop 11 of 13 from COMBAT-ICU |

Arm sizes are 13 / 12 / 11 (total 36), each stated explicitly in its own header
cell. GRIM independently flags all four CCI columns and three of four APACHE II
columns. Age is supported by the pooled-column check alone — GRIM does not apply,
since age may have been recorded continuously rather than in whole years. Age is
an eligibility criterion ("adults aged 18 years or older") and a pre-specified GEE
covariate, and the words "missing", "imputation" and "complete case" appear zero
times in the paper, which is what makes the required dropout implausible rather
than merely unreported. Length of stay (hospital and ICU) reconciles once
one-decimal rounding is accounted for and should **not** be cited as inconsistent.

*Artifacts:* `PMC13296589_table3_raw.xml` (complete source table).

## MADRS anomaly — PMC13389161

Resolved as a weaker, open finding, not a flagship result. Day 7 MADRS mean for
Midazolam arm (15.57, n=12) is mathematically unreachable at the stated n — but
fully explained if only 7 of 12 patients had a Day 7 assessment (109/7 = 15.5714,
matches exactly). The unusual SD (21.3) is NOT anomalous — it's consistent with a
normal bimodal responder/non-responder pattern, well within the statistically
possible range for that mean. Resolving this needs the paper's actual Day 7
analysis population (a CONSORT flow-diagram question), which this pipeline can't
determine from the table alone.

Supporting detail: at n=12 the nearest attainable means are 186/12 = 15.50 and
187/12 = 15.58. Sweeping every n from 2 to 12, **n=7 is the only value at which
15.57 is reachable**. The other three MADRS cells in the same table (Ketamine Day
7 at 15.94/n=18, and both baseline values) are independently reachable, isolating
the discrepancy to this one cell. On the SD: maximum attainable SD for a 0–60
scale at mean 15.57 is 26.30 (population) or 27.47 (sample, n−1), so 21.3 sits at
77.5% of the maximum; an integer sample such as [60, 60, 6×10] yields mean 15.00,
SD 21.02.

## GRIMMER finding — PMC12815704, Table 1

All three MMSE arms report a standard deviation that no set of integer scores
can produce at the stated sample size, under the standard sample-SD convention.
GRIM passes every checkable row in this paper, so v1.0 would not have surfaced
it.

| Group | n | Reported | Nearest achievable |
|---|---|---|---|
| CG | 28 | 24.50 (2.00) | 1.99 and 2.01 |
| TCG | 28 | 25.00 (1.75) | 1.74 and 1.76 |
| TCOG | 29 | 25.00 (1.50) | 1.49 and 1.51 |

Each was confirmed by enumerating every achievable sum of squares for n integer
scores in the MMSE range 0–30 summing to the implied total: 1,781 for CG, 1,630
for TCG, 1,708 for TCOG. In each case the reported SD falls between two adjacent
achievable values rather than on one. Values verified against the published
Table 1.

The MMSE's 0–30 range is not load-bearing: the values remain unreachable when
the range constraint is dropped entirely. The SD convention is load-bearing for
one arm — TCG's 1.75 is reachable if the SD was computed with an n denominator
rather than n−1. CG and TCOG remain unreachable under either convention, and no
single convention accounts for all three.

Separately, every mean and SD in the row is a multiple of 0.25 (24.50, 25.00,
25.00; 2.00, 1.75, 1.50), which INSPECT-SR check 4.3 lists as a marker worth
noting. That observation is independent of GRIMMER.

## GRIMMER finding — PMC13259436, Table 1

Dual-task gait training with visual adaptation versus control, two arms of 20.
Table 1 reports MoCA-K as 22.15 ± 1.73 (DGTVAG) and **21.35 ± 1.67 (CG)**.

The control arm's standard deviation is not reachable from 20 integer scores
with a mean of 21.35, under either the sample (n−1) or the population (n)
denominator. MoCA-K is a summed 30-point instrument, so every participant's
score is a whole number and the test applies cleanly. The sample size is stated
in the column header, not inferred.

GRIM passes both arms; only GRIMMER fails, and only on the control arm.

## GRIMMER finding — PMC13328705, Table 1

Transcranial magnetic stimulation in anorexia nervosa, three arms (TMS, Sham
TMS, TAU). Table 1 reports MADRS-S as 25.20 (10.84), **22.40 (3.87)** and
19.60 (8.49).

The sham arm's standard deviation is not reachable from 10 integer scores with
a mean of 22.40, under either denominator. MADRS-S is a summed nine-item scale
scored 0–54.

*Caveat:* the arm's sample size is not stated in the column header. It was
recovered as 10 from rows reporting 100% of the arm (the cohort is entirely
female), and is consistent with the caption's stated total of 40 across three
arms. The finding depends on that recovery being right.

## Unresolved — PMC12590661, Table 1

Three continuous renal replacement modalities, 40 / 40 / 41. Table 1 reports
SOFA as **12.18 ± 2.28** in the CVVH arm.

The SD is unreachable under the sample SD convention but **reachable under the
population SD** (total 487, sum of squares 6137). It therefore fails only if
the authors used the n−1 denominator, which cannot be determined from the
paper. Recorded here as unresolved, in the same category as the MMSE TCG case
in PMC12815704.

## Correction to the v1.0 results

The v1.0 run reported 71 flagged rows of 516 checkable (13.8%) across 33 papers.
A subsequent audit found four of those flags to be artifacts of the rounding
convention used by the check, not reporting inconsistencies.

GRIM in v1.0 assessed reachability under round-half-up only. Where a journal
rounds using round-half-even (banker's rounding), a quotient ending in exactly 5
at the next decimal place rounds down rather than up, and the reported mean is in
fact reachable.

| PMCID | Variable | n | Reported mean | Reachable as |
|---|---|---|---|---|
| PMC12641942 | MMSE | 8 | 26.2 | 210/8 = 26.25 |
| PMC13103870 | Charlson comorbidity index | 40 | 3.72 | 149/40 = 3.725 |
| PMC13175143 | GAD-7 | 80 | 9.12 | 730/80 = 9.125 |
| PMC13260263 | BDI | 8 | 9.2 | 74/8 = 9.25 |

**Corrected v1.0 result: 67 flagged rows of 516 checkable (13.0%) across 30 papers.**

From v1.1 onward a mean is treated as unreachable only if it is unreachable under
both conventions. The original v1.0 output is retained unchanged in
`grim_results.csv`; the corrected run is in `grim_results_corrected.csv`. The
script that identified the artifacts is in `audit/`.

## Changes in v1.4

Four extraction changes, measured against a rating of 300 papers drawn at
random from all 9,698 fetched (`audit/gold/`). Of those 300, 21.3% have no
participant characteristics table at all, 63.0% have one with no
integer-valued mean rows, and 15.7% are in scope for GRIM. CONFIRM reached
40% of the in-scope papers before these changes and 55% after.

Those ratings were produced with AI assistance, before any CONFIRM output
existed for the sampled papers, and were spot-checked by the author rather
than produced independently. An audit of them found the rater's own caption
matching had missed five characteristics tables. The scope figures and the
40%/55% recall are therefore the project's own estimate of its reach, not a
validated measurement: a rating by someone with no stake in the result would
be required for that, and none exists yet.

- **Caption pattern widened.** A bare "characteristic" now matches, plus
  "basic/general information" and sample descriptions. Captions such as
  "Characteristics of participants randomized to COMPASS" were previously
  missed. Recovered 968 papers.
- **Missing sample sizes recovered.** A column header with no n no longer
  kills the table; the group total is inferred by inverting a count's own
  percentage, subject to agreement or a complementary sum. Resolved ~5,900
  cells previously withheld as unverifiable.
- **Spaced decimals normalised.** One publisher's JATS writes "9. 37 (3. 49)",
  which read as a table with no numbers in it.
- **Table selection prefers baseline over outcomes.** Where several captions
  match, one that does not also promise outcomes wins. Previously the first
  match was taken, so "Clinical characteristics and outcomes" was read as a
  baseline table in PMC13181993 and a post-treatment sedation score was flagged.

Two guards were added after the fixes surfaced new false flags:

- **Subgroup denominators.** A mean row directly beneath "Received X, n (%)"
  is averaged over that subgroup, not the arm. In PMC12797902 the mean number
  of chemotherapy treatments is over the 14 who received it, and 5.64 is
  unreachable at n=40 but reachable at n=14.
- **Ranges running on after the SD.** "2.1 ± 2.220–8" is mean 2.1, SD 2.22,
  range 0–8; the SD read as 2.220. Withheld 447 cells across 23 papers and
  retracted four false GRIMMER flags.

"steps" was also removed from the generic integer tier, where it matched gait
measures in metres and steps per second.

**Flag changes.** GRIM 67 → 65: two steps rows retracted as continuous.
GRIMMER 33 → 32: four retracted (two outcome-stratified tables, two fused
SDs), three added, of which two are findings and one is unresolved.

## Changes in v1.4.2

Three faults in the parsing of numeric cells, all found by tests written after
v1.4.1, and none of which moved a flag. At that version GRIM stood at 65 of
531 and GRIMMER at 32 of 414.

- **A dash used as a minus sign was dropped.** Journals typeset a negative with
  an en dash, em dash, figure dash or non-breaking hyphen as readily as with the
  ASCII hyphen or the true minus; only the latter two were recognised, so the
  sign was discarded and the magnitude kept. PMC12819071's height
  standard-deviation scores of -1.64, -2.07 and -1.84 were stored positive. 455
  values across 100 papers now carry their sign. No verdict changed, because
  negative means fall almost entirely in Z-scores and change scores, which the
  classifier treats as continuous and excludes.
- **A median with an interquartile range was read as a mean and an SD whenever
  no space followed the comma.** "69(67,71)" became mean 69, SD 6771, because
  the number pattern accepted a comma as a thousands separator however many
  digits followed it. A separator now requires exactly three. 212 rows across 46
  papers were affected; none had reached a verdict, so no flag rested on one. Two
  had produced negative standard deviations, which is what exposed the fault --
  an SD cannot be negative, and that one free test found what four agreement
  tests had missed.
- **The guard against a range fused to an SD discarded cells it should have
  kept.** It anchored on any parenthesis, so "53.2 +- 3.1, (45-59)", where the
  SD is unambiguous, was thrown away entire. It now fires only on a dash fused
  directly to the SD digits. 440 rows across 47 papers were recovered, all of
  them in excluded buckets.

**Verification.** Every one of the 97 flagged rows was re-read from the source
XML by a parser sharing no code with the extractor: 97 verified, 0 mismatches,
0 unlocated. Of 400 randomly drawn ordinary rows, 364 verified and 2 mismatched,
both the unresolved comma-as-decimal-separator case in `LIMITATIONS.md`.
Single-paper runs reproduce the corpus verdict on all 49 flagged papers, GRIM
and GRIMMER agree with an independent interval re-derivation on all 943 checked
rows, and neither raises a false flag against exhaustive enumeration.

## Changes in v1.4.3

Two rules for commas inside numeric cells, where a comma between digits has
three incompatible readings and the parser had been choosing among them badly.

- **A comma followed by fewer than three digits is not a thousands
  separator.** No convention writes one that way, so "18,84 +- 5.51" is
  European decimal notation for 18.84. Having failed to match across the comma,
  the number pattern began matching after it and returned a mean of 84. Such
  cells are now refused outright.
- **A median sits inside its own interval; a standard deviation does not.**
  "134 (131,135)" and "100(50,100)" are medians with interquartile ranges, but
  "131,135" is a syntactically valid thousands group, so only the betweenness
  of the first value distinguishes the two readings. Where it holds, the cell
  is refused. "15,860 (16.2)" and "32,236 +- 9194" are unaffected.

A census of all 9,698 papers (`audit/comma_census.py`) found 4,357 cells
carrying such a comma while parsing as a mean and an SD. Most were already
discarded downstream as counts with percentages or for want of a group n, so
only 92 rows left the dataset: 51,174 to 51,082. Two of those had been reaching
GRIMMER verdicts on a corrupted standard deviation, which is why its
denominator falls from 414 to 412. GRIM is unchanged at 65 of 531 and GRIMMER
still flags 32.

`audit/sanity_check.py` reports no impossible values, and its warnings about
suspect shapes fall from 43 to 14. Every one of the 14 was checked: each sits
on a row already excluded from verdicts, and two are not parsing faults at all
but a space-separated thousands value and a separator missing from the
publisher's XML. Both are recorded in `LIMITATIONS.md`.

## Changes in v1.5.0

One rounding convention added, and the first verification by an implementation
this project did not write.

**Half-down rounding is now accepted.** A mean was previously treated as
unreachable unless it was unreachable under both half-up and half-even
(banker's) rounding. Half-down was missing, and it is the convention that
decides an exact tie. 78/8 is 9.75, which half-up and half-even both render as
9.8 but half-down renders as 9.7; 316/32 is 9.875, which half-down renders as
9.87. Two GRIM flags rested entirely on that omission and have been retracted:

| paper | variable | mean | n | attainable total |
|---|---|---|---|---|
| PMC12641942 | Functional capacity (SPPB, 0 to 12) | 9.7 | 8 | 78, as 9.75 rounded half-down |
| PMC12660629 | PHQ-9 T2 | 9.87 | 32 | 316, as 9.875 rounded half-down |

Neither was an arithmetic error. Both were flagged because the pipeline assumed
a rounding convention the papers never stated, which is not a safe assumption to
make against an author. **GRIM falls from 65 of 531 (12.2%) to 63 of 531
(11.9%), across 28 papers rather than 29.** One of the two means now passes GRIM
and so enters GRIMMER's checkable set, raising its denominator from 412 to 413;
GRIMMER still flags 32 (7.7%). The same convention was added to
`grimmer_check.py` and to `audit/reverdict2.py`, which encoded the old
assumption in its boundary rule.

**Cross-checked against scrutiny.** All 95 flagged rows were run through the
scrutiny R package (version 1.0.0) by Lukas Jung, whose GRIMMER follows Allard's
Analytic-GRIMMER algorithm rather than the parity condition on the sum of
squares used here. scrutiny agrees on all 63 GRIM and all 32 GRIMMER flags,
under both its permissive default rounding and strict half-up. That is the first
check of this pipeline's arithmetic by code written by someone else; the oracle
and interval tests, though independent in method, are both the author's own. The
script is `audit/scrutiny_check_v2.R`, which needs R and is not part of the
pipeline.

Running that comparison is what exposed the missing convention. Under scrutiny's
default the two tie rows came back consistent while CONFIRM called them
inconsistent, and the disagreement was the finding.

