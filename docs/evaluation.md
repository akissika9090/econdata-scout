# Evaluation summary

These are diagnostic results on a small set chosen by the author. They are not an independent benchmark. The author annotated the ground truth for 18 papers; some entries were drafted with AI help and then checked by the author, so annotation errors are possible. The raw evaluation materials (paper PDFs, saved outputs, ground truth) are not distributed.

## 1. Program checks on saved extractions

- **Material**: 62 saved extraction outputs for 18 papers, produced on 2026-11-04 and 2026-11-05 by `gemini-3.5-flash-lite` with the older prompt (no usage/scope fields). Most papers have 1 run; some have 3, 7 or 10 runs. The 238 judgments therefore include repeated runs of the same papers.
- **Code**: the program checks as of 2026-11-17 (anaphor-chain rule, section 1.1). The "2026-11-06" column is the frozen release before that change, re-run on the same 62 outputs.

| Measure | 2026-11-06 | 2026-11-17 |
|---|---|---|
| Main data sources found | 203 / 211 | 203 / 211 |
| Access category correct | 213 / 238 | 221 / 238 |
| — of which the answer was "not stated" | 200 / 200 | 200 / 200 |
| — of which the answer was "public" | 13 / 23 | 13 / 23 |
| — of which the answer was "restricted" | 0 / 15 | 8 / 15 |
| Wrongly shown as public | 0 | 0 |
| Wrongly shown as restricted | 0 | 0 |
| Sample period correct | 92 / 105 | 92 / 105 |
| Checks corrected a wrong model answer | 11 | 11 |
| Checks turned a correct model answer into "unconfirmed" | 23 | 15 |

How to read this: answering "unconfirmed" for everything would already score 200 / 238. The checks avoid wrong conclusions: none of the 238 judgments was wrongly shown as public or restricted. Explicit conditions are still often lost (7 of 15 restricted, 10 of 23 public).

### 1.1 Why restricted was 0 / 15, and the 2026-11-17 change

Each of the 15 restricted judgments was traced to the step where it was lost (current checks, same saved outputs):

| Where it was lost | Count |
|---|---|
| Candidate passages did not include the sentence | 0 |
| The model did not classify it as restricted | 2 (chen2022 census, 2 of 3 runs) |
| The model was right; the program's check blocked it | 13 |

The 13 blocked cases: 7 were an anaphoric sentence (deng2020 UHS: "Since the dataset is not available to the public, …", where the data is named a few sentences earlier); 3 named the data with different wording from the model's name (e.g. "2015 Census" vs "2015 Population Census of China"); 3 did not name the data at all (NVSS).

Change: an evidence sentence that starts with a reference ("the dataset", "this survey") is now attributed to a data source when (1) an earlier sentence on the same page names it, (2) every sentence in between also starts with a reference, so the chain is not interrupted, and (3) no other data source of the paper is named from that sentence to the evidence sentence. Condition (2) keeps the earlier safeguard: a sentence such as "We obtain weather data from NOAA." in between breaks the chain even if NOAA was not extracted.

Effect: 8 restricted cases recovered (deng2020 ×7, mobarak2021 ×1); no new wrong conclusion; the 11 corrections of wrong model answers are unchanged. Known cost of condition (2): CHNS in teng2026 (10 runs) stays unconfirmed, because a sentence about the survey's supervising institution sits inside the chain. The rule was written after this diagnosis, on the same material, so these numbers are diagnostic. A test on papers not used for any rule is pending.

## 2. Evidence Recovery Agent (optional, off by default)

- **Material**: 2026-11-06. Agent V1 (frozen during the evaluation) ran on 12 papers: 7 diagnostic papers and 5 development papers. Each paper used its latest saved extraction (one run per paper, older prompt). Most model calls fell back to `gemini-3.1-flash-lite` because the primary model returned 429/503.
- **Result** (Agent run of 2026-11-06, checked with the rules of that date; not re-run after the 2026-11-17 change): no change in accuracy (24/25 → 24/25 and 13/13 → 13/13); 0 wrongly shown as public before and after.
- The Agent investigated 34 unconfirmed sources with 133 model calls. It submitted evidence 8 times, and the program rejected all 8. Two of the rejections stopped wrong changes, and one stopped a correct change (the check was too conservative).
- 28 of the 34 sources have no evidence in the paper at all. The evaluation design also had a flaw: no case the Agent could win was included.

## 3. Condition-judge experiment (frozen, not part of the pipeline)

A second model pass judged 4 development cases. It blocked 2 errors, kept 1 correct condition and wrongly rejected 1 correct condition. This does not show it is worth integrating.

## 4. Small user acceptance

3 end-to-end runs on 2 topics. All finished without crashes. 4 of 9 downloads were refused (HTTP 403). Because the primary model kept returning 429/503, calls were retried, and the runs took 4–6 minutes.

## 5. V2 official-site check (pilot)

- **Material**: 10 data sources from 9 papers, chosen to include a case where the paper used a restricted version while a public version exists (NVSS restricted files, Canadian LFS public files, UHS, census micro samples, CHNS, CFPS, CLDS, CSMAR, SEDAC PM2.5, QWI). Paper-side records come from V2 extractions (2026-11-17, Gemini). The official-site check uses `deepseek-flash` with DeepSeek web search and page fetch.
- **Ground truth**: drafted by Claude from web searches with URLs and quotes, then checked item by item by the author before the runs. One entry (CLDS) was corrected after a tool run showed an official notice that the draft had missed; it is marked in the file. Items the author could not determine are excluded from scoring.
- **Results** (each run is a single run per source):

| Run | Findings | Channel agrees | Eligibility agrees | Version misapplied | Manual check | New verifiable channels |
|---|---|---|---|---|---|---|
| 2 | 6 | 6 / 6 | 3 / 3 | 0 | — | 5 |
| 3 | 8 | 6 / 8 | 4 / 4 | 1 | — | 7 |
| 4 | 7 | 6 / 7 | 4 / 4 | 0 | 2 | 6 |

"Version misapplied" = the tool said the page covers the paper's version while its channel differs from the ground truth. "New verifiable channels" = sources whose paper side had no verified access statement and now have an official URL and quote.

- **What held**: across all runs, no fabricated quote and no non-official page was accepted. NVSS, LFS, UHS, census, CHNS and QWI gave the same result in every run.
- **Errors, checked against the official pages**: CLDS was classified as "free download after registration" twice, but the official notice says users register, apply, and download after review (apply to provider). In run 3 the version was also over-claimed: the page only says a later wave was completed, not released. CSMAR (run 3) was classified from a personal-account login guide; the same page says the account has the same rights as the user's school subscription and that other data must be bought (subscription). In both cases the quote was real and the category was wrong.
- **Changes made on this material**: decoding of Chinese pages; the data's own domain counts as official; http fallback on TLS errors; a free channel on a page that mentions subscription/purchase is sent back once; unreadable official pages go straight to a manual-check list (a retry pass recovered none and was removed). Because these rules were written on these 10 sources, the pilot is no longer an independent test.
- **Variability**: with nearly identical code, CSMAR was found in run 3 and not in run 4 (the agent went to vendor domains that failed TLS). Repeating each check was considered and not adopted: two identical answers can both be wrong (CLDS), and cost doubles. Results are reported as single runs.
- **Next**: an independent test on papers not used for any rule, with ground truth fixed before the run and rules frozen.

