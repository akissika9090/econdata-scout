# EconData Scout

日本語 README：[README.ja.md](README.ja.md)　｜　日本語の概要：[docs/overview_ja.md](docs/overview_ja.md)　｜　中国経済データの入手経路カタログ（設計と評価）：[docs/access_catalog_ja.md](docs/access_catalog_ja.md)　｜　出力例：[demo/outputs/access_table_ja.md](demo/outputs/access_table_ja.md)

EconData Scout is a **citation-backed data-provenance tool for economics papers**. Give it a research direction: it finds prior papers and reports **which data each paper used and what the paper's own text says about that data** — access conditions, sample years, links — with the quote and page for every conclusion, so you can check each one yourself.

Conclusions are shown only when the program has found the model's quote verbatim on the stated page and the quote passes the checks in [docs/contract.md](docs/contract.md). Everything else is shown as unconfirmed, with the reason and, where available, the quote. Usage relations, which period belongs to which data, and which part a condition applies to are **model judgments**; the program checks their quotes and structure, not their meaning.

The tool is meant for the stage **before choosing a research topic**. Data used in prior papers are only candidates: they may not be available to you today and may not fit your research. The report also shows where the tool did not answer, and why.

**V2 (optional, `--official`): source and access leads.** Papers rarely say how to get their data (in our material, 28 of 34 unconfirmed sources had no access statement). V2 lets an agent search the **provider's website** for each data source and adds a second column: where the data comes from today and how it is obtained, with the URL, the quoted page text and the date checked. A finding is shown only if the program confirmed that the page is an official source and that the quotes appear on it word for word. A site that is not the original provider but names the data (e.g. NBER for CPS extracts) is shown as a **distributor**, labelled as such. When the check finds nothing, the report says "please check this yourself" and lists the pages it reached. V2 cannot help with data the extraction step missed.

> Status: a personal portfolio project. V1 was frozen on 2026-11-06. **V2 is a release candidate (rules v2.5d, 2026-11-18)**, not yet published; see [docs/release_notes_v2.md](docs/release_notes_v2.md). Not a production tool. See [Known limitations](#known-limitations). License: MIT for the project's own code and documentation; third-party material is excluded (see [License](#license)).

**Access catalog for Chinese economic data (Japanese output).** For 9 frequently used Chinese data sources (China Statistical Yearbook, China City Statistical Yearbook, population census tabulations, China Meteorological Data Service, air-quality data, CGSS, CFPS, CSMAR, China Industrial Enterprise Database), every run also writes `access_table_ja.md`: for each main data source, what the paper used, the access restriction and how far it was verified, the official entry page, the next step and what remains unconfirmed. Restriction and verification are reported separately: "institutional eligibility required" is itself a useful finding before choosing a topic. In an independent test after freezing the catalog (13 papers), it gave **0 wrong entries**; it also confirmed **0** version-specific access paths, which shows the limits of its verification. Details (Japanese): [docs/access_catalog_ja.md](docs/access_catalog_ja.md).

## What it does and does not do

| Does | Does not |
|---|---|
| Separates data **used in the paper** from data **cited from other studies** or mentioned as background (model judgment; its quote is checked) | Judge whether a topic is good, or evaluate identification strategies |
| Shows an access condition as a conclusion only after the checks pass; otherwise "unconfirmed" with the reason | Infer that data are public because the authors used them, or restricted because the authors "obtained tabulations" |
| Records sample years as a historical record (single year / discrete years / range), with the quote | Judge whether those years meet your needs |
| Lists URLs found in verified quotes as "links in the paper's text" | Treat links in the paper as access channels |
| Keeps unconfirmed model output visible with the reason | Guess availability from memory |
| V2: checks the official site and shows a finding only with an official URL and a verbatim quote from it | Promise you will get the data (findings reflect the page on the date checked) |

## How it works

```
research direction
  → 1. search_papers.py    OpenAlex search + Gemini relevance scoring (3 questions; the score is computed by the program)
  → 2. fetch_fulltext.py   download open-access PDFs only; failures are recorded with the reason
  → 3. step2_ai_extract.py Gemini extracts data sources (quotes + attributes); the program checks each quote
  → 4. agent.py            optional (--agent): Evidence Recovery Agent re-reads the PDF for unconfirmed sources
  → 4b. official_check.py  optional (--official, V2): per data source, an agent searches and reads the provider's
                           official site (DeepSeek model + search/fetch); the program checks every finding
  → 5. step3_merge.py      merge by data source and write the report (English)
scout.py runs all five steps; each run is saved under runs/<date_time>/
```

| Model (Gemini) | Program (Python) |
|---|---|
| Which data sources a paper mentions, and their names | Checks that each quote appears verbatim on the stated page (corrects the page if it is on another page) |
| Usage relation: used in this paper / cites others / background | Checks the usage quote; records that cannot be checked go to "usage relation to be confirmed" |
| Access category and which part it applies to | Accepts a category only if the quote is one sentence, contains a supporting expression, names this data, and names no other source of the paper; otherwise "unconfirmed" with the reason |
| Sample period, its form and quote | Checks the year structure against the quote (e.g. "1977 and 1997" cannot be a range) |
| — | Merges sources across papers, keeps different conditions apart, leaves paper-level sample restrictions unattributed |
| V2: which page to read, the access channel / eligibility / restrictions on it, whether it covers the paper's version | V2: re-reads the page itself; accepts it only if it is official (government/university domain naming the data, the data's own domain, a domain verified before, or a page linked from one); checks that the access, version and restriction quotes are on the page; "same version" needs a located version quote; a free channel on a page that mentions subscription/purchase is sent back once; unreadable official pages go to a manual-check list |

## Installation

Tested with Python 3.14 on macOS; the default tests also pass on Python 3.10 (Linux).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

API keys are needed only for new runs (`--pdf` without a research direction needs only `GEMINI_API_KEY`). Tests and demos run without keys:

```bash
export GEMINI_API_KEY='your key'     # Google AI Studio (newer keys start with "AQ."; paste it exactly once)
export OPENALEX_API_KEY='your key'   # openalex.org, free
export DEEPSEEK_API_KEY='your key'   # only for V2 --official (model, web search and page fetch; paid per call)
```

Keys are read from the environment only and are never written to files.

## Usage

```bash
python scout.py "the effect of the Earned Income Tax Credit on the labor supply of single mothers in the United States"
python scout.py --pdf paper1.pdf paper2.pdf                 # start from your own papers: no search, only these PDFs are analysed
python scout.py "research direction" --pdf my_paper.pdf     # add PDFs you obtained yourself (e.g. paywalled)
python scout.py "research direction" --agent                # also run the Evidence Recovery Agent (many more calls)
python scout.py "research direction" --official             # V2: also check each data source on the official site
LLM_PROVIDER=deepseek python scout.py "research direction"   # use DeepSeek instead of Gemini for search scoring and extraction

# V2 on saved extraction results, without re-reading papers:
python step3_merge.py --results-dir results_v2 --official --out report_v2.md
python step3_merge.py --results-dir results_v2 --official-from official_checks/<file>.json --out report_v2.md   # reuse, no API calls
```

The free Gemini tier often returns 429/503. The client waits and retries, then switches to a lighter fallback model.

## Tests

```bash
python run_tests.py            # default public tests: no key, no network, no paper PDFs
python run_tests.py --papers   # optional: tests on real papers; each file reports SKIPPED when its local materials are missing
```

The default suite has 10 files and uses synthetic text only (the V2 tests use saved-page fakes and a fake model, no network). The optional suite has 6 files; they read paper PDFs and saved results, which are not distributed. A file in the optional suite stops before reading anything when its materials are missing, and lists the missing files.

## Demos

```bash
python demo/replay.py normal     # saved report (yip 2018)
python demo/replay.py review     # saved report (Liebman 1998)
python demo/replay.py official   # V2: saved two-column report with the official-site check (air pollution and productivity, 3 papers)
python demo/replay.py fallback   # saved record of a real run: 429 retries, model fallback, an HTTP 403 download, the run continuing
```

By default these are **saved-result replays, not re-verified**: no PDF is read and nothing is checked again. `--reverify` re-runs the checks for `normal` and `review` if you have the PDFs locally. See [demo/README.md](demo/README.md).

Excerpt from `demo/outputs/review.md` (a real report generated by the program from a saved model output):

```
## IRS Taxpayer Compliance Measurement Program　(used by 1 paper)
- **Access: cannot determine** (basis: not stated in the paper, and this data is not in the tool's list — no statement found)
  ...
    - 1985, 1988 (discrete years, period form consistent with the source text; Liebman1998) — p. 31: “Tabulations from the IRS's ...”
- Per paper:
  - Liebman1998: [no statement found] IRS Taxpayer Compliance Measurement Program (TCMP)
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 34: “My data for this study were 1985 and 1988 cross sections from the IRS's Taxpayer Compliance Measurement Program.”
    - Provider (extracted by the model; not an access channel): Internal Revenue Service (this wording does not appear verbatim in the source sentence; compare with: p. 31: “...”)
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)
```

## Evaluation (summary)

Details are in [docs/evaluation.md](docs/evaluation.md). These are diagnostic results on 18 papers whose ground truth the author annotated; they are not an independent benchmark.

- **No case was wrongly shown as public**: 0 of 238 judgments. Material: 62 saved extraction outputs of 18 papers (2026-11-04/05, older prompt, `gemini-3.5-flash-lite`). Some papers have repeated runs (up to 10), so the 238 judgments are not independent. Checked with the program code of this release.
- **Access category correct: 221 of 238** (213 before the 2026-11-17 change), but answering "unconfirmed" for everything would already score 200. Of the explicit answers, 13 of 23 public cases and 8 of 15 restricted cases (0 before) were given correctly.
- **2026-11-17 change, found by diagnosis**: in 13 of the 15 missed restricted cases the model was right and the program's check blocked it. 7 of them were one paper's sentence starting with "the dataset". The check now follows a chain of referring sentences back to the sentence that names the data, when nothing else interrupts the chain. Both error counts stayed at 0. The rule was written after looking at these cases, so the new numbers are still diagnostic, not an independent test.
- **V2 tests (first run of rounds 3–5, three new research directions; rules v2.4c, v2.4d and v2.5a respectively)**: two questions per data source. *Is there data*: 7 of 13. *Where does it come from*: 7 of 17 by provider website (6 of 17 if the exact product must match). In this sample, under the fixed scoring rules, **0 wrong answers were observed among the items the tool answered**. Of the 10 unanswered items, 4 were missed at the extraction step, so the official-site check never ran for them and the report gives no lead for them; 4 were small-institution data that a person could not confirm either; 2 were correct sites the program did not accept. Answer keys were drafted by Claude and confirmed by the author; in round 3 the key was written after the tool's results had been seen. Only 3 of 9 automatically selected papers downloaded. The v2.5–v2.5b fixes were checked only by replaying saved outputs offline. Small sample: treat the numbers as indicative. Scoring is coarse: *is there data* is "yes" whenever the tool returns a checked official page, *where from* is scored by domain, and the access channel / eligibility shown in the report were not scored in these rounds (only in the pilot below). See [docs/release_notes_v2.md](docs/release_notes_v2.md).
- **V2 official-site check (pilot, 10 data sources, single run)**: 7 findings with an official URL and a verbatim quote, 2 official pages listed for manual checking, 1 not found. Channel agreed with the author's ground truth in 6 of 7, eligibility in 4 of 4; 0 version misapplications. Across 4 pilot runs no fabricated quote or non-official source was accepted; the errors were correct pages put in the wrong category. The rules were adjusted on these 10 sources, so this is a pilot, not an independent test. See [docs/evaluation.md](docs/evaluation.md#5-v2-official-site-check-pilot).
- **Evidence Recovery Agent: no change in accuracy.** Agent V1 ran on 12 papers, using the latest saved run of each (one run per paper, older prompt, 2026-11-06). It investigated 34 unconfirmed sources with 133 model calls and changed no category. The program rejected all 8 of its submissions; this stopped 2 wrong changes and also 1 correct one. The Agent is optional and off by default.

## Known limitations

- **Paper downloads**: publishers often refuse automated downloads even for open-access papers (3 of 9 succeeded in the V2 tests). Download the listed papers in your browser and pass them with `--pdf`.
- **Missed data sources**: the model does not find everything. In Liebman (1998) it missed the restricted CPS–tax-return matched file, the 1988 IRS non-filer study and two CPS records, and did not confirm the SOI "public use sample" condition (it is shown only as a clue).
- **Explicit conditions are often lost** by the conservative checks (see the evaluation).
- **Access channels in papers**: V2 adds channel / eligibility / restriction fields, but papers rarely state them; URLs in papers are extracted mechanically and not verified.
- **Official-site check (V2)**: the program verifies that a quote is on an official page, not that the model put it in the right category (in the pilot, a "register, then apply and pass review" route was classified as free download after registration). Company sites whose domain does not contain the data's name are not recognised as official; since v2.5a they are accepted as a labelled distributor if the page names the data, which a blog or copycat site can also do. Databases known by a short brand name (EPS DATA for "Economy Prediction System") are still not matched. Many Chinese university sites fail TLS or time out, so they end up on the manual-check list. Results vary between runs. Without `--official` the report ends with a checklist of what to verify with the data provider.
- **Data availability statements** marked by the model include supplementary-material notes, so they are not shown as data availability statements.
- **Older saved results** (before the usage/scope fields existed) show scope as "not recorded". Their usage relation defaults to "used in this paper", so a cited dataset may appear as used.
- **Name matching**: an institution abbreviation inside a dataset name (the "IRS" in "IRS Statistics of Income") counts as naming the data.
- **Model variability and speed**: repeated runs can differ, and the free tier is slow (runs took 4–6 minutes with retries).
- **Scanned PDFs** are not supported.

## Repository contents

| Path | Contents |
|---|---|
| `scout.py`, `search_papers.py`, `fetch_fulltext.py`, `step1_pdf_evidence.py`, `step2_ai_extract.py`, `step3_merge.py`, `gemini_client.py` | Pipeline |
| `agent.py`, `agent_tools.py` | Optional Evidence Recovery Agent |
| `official_check.py`, `web_tools.py`, `deepseek_client.py` | V2 official-site check (agent loop and program checks; web search/fetch with cache; DeepSeek client). Run it with `scout.py --official` |
| `known_databases.json` | Hand-maintained database hints (not evidence from papers) |
| `access_catalog.py`, `access_catalog.json` | Access catalog for 9 Chinese data sources and the Japanese access table (`access_table_ja.md`) |
| `run_tests.py`, `test_support.py`, `test_*.py` | Default and optional test suites |
| `demo/` | Replay script, saved reports, copies of the saved inputs (paper abstracts removed) |
| `docs/contract.md`, `docs/evaluation.md`, `docs/release_notes_v2.md`, `docs/overview_ja.md`, `docs/access_catalog_ja.md` | What each part may decide; evaluation summary; V2 release notes and test results |
| `LICENSE`, `THIRD_PARTY.md` | MIT License; third-party material that the license does not cover |

Paper PDFs, saved evaluation materials, run logs and the development log are not included.

## License

The code and documentation written for this project are released under the [MIT License](LICENSE).

The MIT License does not cover third-party material in this repository. This includes the short quotations from published papers in the demo and test files, the OpenAlex bibliographic metadata (titles, authors, venues, links; abstracts removed) in `demo/data/fallback/`, and the saved model outputs that contain those quotations. That material remains the property of its authors and publishers, and no permission to reuse it has been obtained. Sources are listed in [THIRD_PARTY.md](THIRD_PARTY.md).

## How this was built

The author set the requirements, made the design and evaluation decisions, annotated the ground truth, ran everything locally and reviewed the results. Most of the code was written by an AI coding assistant (Claude). An external AI review (Codex) reported eight issues; each was reproduced before it was fixed. The Agent did not improve accuracy, and this is reported as measured.
