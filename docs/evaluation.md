# Evaluation summary

These are diagnostic results on a small set chosen by the author. They are not an independent benchmark. The author annotated the ground truth for 18 papers; some entries were drafted with AI help and then checked by the author, so annotation errors are possible. The raw evaluation materials (paper PDFs, saved outputs, ground truth) are not distributed.

## 1. Program checks on saved extractions

- **Material**: 62 saved extraction outputs for 18 papers, produced on 2026-11-04 and 2026-11-05 by `gemini-3.5-flash-lite` with the older prompt (no usage/scope fields). Most papers have 1 run; some have 3, 7 or 10 runs. The 238 judgments therefore include repeated runs of the same papers.
- **Code**: the program checks as of 2026-11-06. The script was re-run with the code of this release on the same 62 outputs, and its output is identical, line by line, to the 14:10 version on that date.

| Measure | Result |
|---|---|
| Main data sources found | 203 / 211 |
| Access category correct | 213 / 238 |
| — of which the answer was "not stated" | 200 / 200 correct |
| — of which the answer was "public" | 13 / 23 correct (10 shown as unconfirmed) |
| — of which the answer was "restricted" | 0 / 15 correct (all shown as unconfirmed) |
| Wrongly shown as public | 0 |
| Wrongly shown as restricted | 0 |
| Sample period correct | 92 / 105 |
| Second-stage checks overriding the model | corrected the model 11 times, turned a correct model answer into "unconfirmed" 23 times |

How to read this: answering "unconfirmed" for everything would already score 200 / 238. The checks avoid wrong conclusions: none of the 238 judgments was wrongly shown as public. But explicit conditions are often lost, most visibly all 15 restricted cases.

## 2. Evidence Recovery Agent (optional, off by default)

- **Material**: 2026-11-06. Agent V1 (frozen during the evaluation) ran on 12 papers: 7 diagnostic papers and 5 development papers. Each paper used its latest saved extraction (one run per paper, older prompt). Most model calls fell back to `gemini-3.1-flash-lite` because the primary model returned 429/503.
- **Result**: no change in accuracy (24/25 → 24/25 and 13/13 → 13/13); 0 wrongly shown as public before and after.
- The Agent investigated 34 unconfirmed sources with 133 model calls. It submitted evidence 8 times, and the program rejected all 8. Two of the rejections stopped wrong changes, and one stopped a correct change (the check was too conservative).
- 28 of the 34 sources have no evidence in the paper at all. The evaluation design also had a flaw: no case the Agent could win was included.

## 3. Condition-judge experiment (frozen, not part of the pipeline)

A second model pass judged 4 development cases. It blocked 2 errors, kept 1 correct condition and wrongly rejected 1 correct condition. This does not show it is worth integrating.

## 4. Small user acceptance

3 end-to-end runs on 2 topics. All finished without crashes. 4 of 9 downloads were refused (HTTP 403). Because the primary model kept returning 429/503, calls were retried, and the runs took 4–6 minutes.
