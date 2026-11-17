# EconData Scout

EconData Scout reads prior economics papers and reports **which data the authors used, what the paper says about access to that data, and which sample years they used**.

Access conditions are shown as conclusions only when the program has found the model's quote verbatim on the stated page and the quote passes the checks in [docs/contract.md](docs/contract.md). Everything else is shown as unconfirmed, with the reason and, where available, the quote. Usage relations, which period belongs to which data, and which part a condition applies to are **model judgments**; the program checks their quotes and structure, not their meaning.

The tool is meant for the stage **before choosing a research topic**. Data used in prior papers are only candidates: they may not be available to you today and may not fit your research.

> Status: a personal portfolio project, frozen on 2026-11-06. Not a production tool. See [Known limitations](#known-limitations). License: MIT for the project's own code and documentation; third-party material is excluded (see [License](#license)).

## What it does and does not do

| Does | Does not |
|---|---|
| Separates data **used in the paper** from data **cited from other studies** or mentioned as background (model judgment; its quote is checked) | Judge whether a topic is good, or evaluate identification strategies |
| Shows an access condition as a conclusion only after the checks pass; otherwise "unconfirmed" with the reason | Infer that data are public because the authors used them, or restricted because the authors "obtained tabulations" |
| Records sample years as a historical record (single year / discrete years / range), with the quote | Judge whether those years meet your needs |
| Lists URLs found in verified quotes as "links in the paper's text" | Verify official entry points, or treat links as access channels |
| Keeps unconfirmed model output visible with the reason | Search the web or guess availability |

## How it works

```
research direction
  → 1. search_papers.py    OpenAlex search + Gemini relevance scoring (3 questions; the score is computed by the program)
  → 2. fetch_fulltext.py   download open-access PDFs only; failures are recorded with the reason
  → 3. step2_ai_extract.py Gemini extracts data sources (quotes + attributes); the program checks each quote
  → 4. agent.py            optional (--agent): Evidence Recovery Agent re-reads the PDF for unconfirmed sources
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

## Installation

Tested with Python 3.14 on macOS.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

API keys are needed only for new runs. Tests and demos run without keys:

```bash
export GEMINI_API_KEY='your key'     # Google AI Studio (newer keys start with "AQ."; paste it exactly once)
export OPENALEX_API_KEY='your key'   # openalex.org, free
```

Keys are read from the environment only and are never written to files.

## Usage

```bash
python scout.py "the effect of the Earned Income Tax Credit on the labor supply of single mothers in the United States"
python scout.py "research direction" --pdf my_paper.pdf     # add PDFs you obtained yourself (e.g. paywalled)
python scout.py "research direction" --agent                # also run the Evidence Recovery Agent (many more calls)
```

The free Gemini tier often returns 429/503. The client waits and retries, then switches to a lighter fallback model.

## Tests

```bash
python run_tests.py            # default public tests: no key, no network, no paper PDFs
python run_tests.py --papers   # optional: tests on real papers; each file reports SKIPPED when its local materials are missing
```

The default suite has 7 files and uses synthetic text only. The optional suite has 6 files; they read paper PDFs and saved results, which are not distributed. A file in the optional suite stops before reading anything when its materials are missing, and lists the missing files.

## Demos

```bash
python demo/replay.py normal     # saved report (yip 2018)
python demo/replay.py review     # saved report (Liebman 1998)
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
- **Access category correct: 213 of 238**, but answering "unconfirmed" for everything would already score 200. Of the explicit answers, 13 of 23 public cases and 0 of 15 restricted cases were given correctly.
- **Evidence Recovery Agent: no change in accuracy.** Agent V1 ran on 12 papers, using the latest saved run of each (one run per paper, older prompt, 2026-11-06). It investigated 34 unconfirmed sources with 133 model calls and changed no category. The program rejected all 8 of its submissions; this stopped 2 wrong changes and also 1 correct one. The Agent is optional and off by default.

## Known limitations

- **Missed data sources**: the model does not find everything. In Liebman (1998) it missed the restricted CPS–tax-return matched file, the 1988 IRS non-filer study and two CPS records, and did not confirm the SOI "public use sample" condition (it is shown only as a clue).
- **Explicit conditions are often lost** by the conservative checks (see the evaluation).
- **Access channels are not structured**: download locations and application procedures are not extracted as fields; they are visible only inside quoted condition sentences. URLs are extracted mechanically and not verified.
- **Official entry points are not verified**: the report ends with a checklist of what to verify with the data provider.
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
| `known_databases.json` | Hand-maintained database hints (not evidence from papers) |
| `run_tests.py`, `test_support.py`, `test_*.py` | Default and optional test suites |
| `demo/` | Replay script, saved reports, unmodified copies of the saved inputs |
| `docs/contract.md`, `docs/evaluation.md` | What each part may decide; evaluation summary |
| `LICENSE`, `THIRD_PARTY.md` | MIT License; third-party material that the license does not cover |

Paper PDFs, saved evaluation materials, run logs and the development log are not included.

## License

The code and documentation written for this project are released under the [MIT License](LICENSE).

The MIT License does not cover third-party material in this repository. This includes the short quotations from published papers in the demo and test files, the OpenAlex bibliographic metadata (abstracts removed) in `demo/data/fallback/`, and the saved model outputs that contain those quotations. That material remains the property of its authors and publishers, and no permission to reuse it has been obtained. Sources are listed in [THIRD_PARTY.md](THIRD_PARTY.md).

## How this was built

The author set the requirements, made the design and evaluation decisions, annotated the ground truth, ran everything locally and reviewed the results. Most of the code was written by an AI coding assistant (Claude). An external AI review (Codex) reported eight issues; each was reproduced before it was fixed. The Agent did not improve accuracy, and this is reported as measured.
