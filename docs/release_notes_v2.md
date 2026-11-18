# EconData Scout V2 — release notes (release candidate)

Date: 2026-11-18 · Rules version: v2.5d · Status: **release candidate, not yet published**; personal portfolio project, not a production tool.

EconData Scout is a citation-backed data-provenance tool: it reports which data prior papers used and what their text says, with the quote and page. V2 adds optional source and access leads from provider websites.

## What V2 answers

Give it a research direction. It finds prior papers, reads which data they used, and for each data source answers two questions:

1. **Is there data?** Can the data the paper used be obtained today?
2. **Where does it come from?** The website you get it from: the original provider, or a distributor (labelled as such).

When it cannot answer, it says so and lists the pages it reached, for you to check yourself. It does not guess.

```bash
export OPENALEX_API_KEY=...   # paper search
export DEEPSEEK_API_KEY=...   # extraction, official-site check, web search
LLM_PROVIDER=deepseek python scout.py "your research direction"                      # papers + data sources
LLM_PROVIDER=deepseek python scout.py "your research direction" --official           # + where to get each one today
LLM_PROVIDER=deepseek python scout.py "your research direction" --official --pdf a.pdf b.pdf   # add PDFs you downloaded
```

Without `LLM_PROVIDER=deepseek` the paper search and extraction use Gemini (`GEMINI_API_KEY`); the official-site check always uses DeepSeek.

## How well it works

Independent tests: three new research directions, each scored on its **first run** (no rule changes in between). Answer keys were drafted by Claude from the providers' websites and confirmed by the author. In rounds 4 and 5 the key was written before the tool's official-site results were seen; in round 3 it was written afterwards, so round 3 is not blind.

| Round | Research direction | Rules | Papers read / selected | Is there data? | Where from? | Wrong answers |
|---|---|---|---|---|---|---|
| 3 | Environmental regulation and employment (US) | v2.4c | 2 / 3 | 3 / 4 | 3 / 4 | 0 |
| 4 | Minimum wage and employment | v2.4d | 1 / 3 | 0 / 4 | 0 / 4 | 0 |
| 5 | Trade liberalisation and wage inequality | v2.5a | 3 / 3 (downloaded by hand) | 4 / 5 | 4 / 9 | 0 |
| **Total (first runs, three rule versions)** | | | | **7 / 13** | **7 / 17** (6 / 17 by exact product) | **0** |

**What the two questions measure, and what they do not.** The scoring is coarse, so read the numbers with these definitions:

- *Is there data?* The tool counts as answering "yes" whenever it returns an official page that passed the program's checks; it answers "no" only when the page says the data is discontinued. In practice this question measures whether the tool found the provider's page for the data, not a separate judgement of whether the data can be obtained.
- *Where from?* is scored by website domain only (see the World Bank example below).
- **The access channel, eligibility and restrictions shown in the report (public download, registration, subscription, purchase, apply to the provider) were not scored in rounds 3–5.** They were scored only in the pilot (channel agreed in 6 of 7, eligibility 4 of 4; see [evaluation.md](evaluation.md#5-v2-official-site-check-pilot)), whose rules were tuned on the same sources. Whether a particular user (e.g. a student) can obtain the data is not assessed.
- Because of these definitions, "0 wrong answers" is a low bar: it means no answered item pointed to the wrong provider site or wrongly said the data exists.

- **In this sample, under the fixed scoring rules, 0 wrong answers were observed among the items the tool answered.** This is 17 data sources in 6 papers; it is not evidence that the tool cannot be wrong.
- Not every miss comes with a lead. When the official-site check runs and finds nothing, the report says "please check this yourself" and lists the pages reached. The 4 sources missed at the extraction step never reached the official-site check, so the report gives no lead for them.
- **Big public providers are answered well**: US federal statistics (BEA, EIA, BLS), World Bank, UNCTAD, university data projects, and commercial databases whose site names the product (CMIE Prowess).
- "Where from" is scored by website domain. In round 5, "World Bank income classification" was answered with the World Bank's WDI catalogue page: right provider, not the exact product, hence 6 / 17 by exact product.
- Each round ran under the rule version current at the time (v2.4c, v2.4d, v2.5a), so the total mixes three versions. v2.5b–v2.5d have not had an independent round; under v2.5d the table above would read 5 / 13 and 5 / 17 (see below).
- In round 5, four sources (two Tunisian institute databases, a firm survey, "IMF tariff data") could not be confirmed by hand either; they are left out of question 1 and kept in question 2.
- Rounds 1–2 used an older scoring scheme (channel, eligibility, version) and are not included. Details: [evaluation.md](evaluation.md).

### Why the other 10 were not answered

| Reason | Count | Status in v2.5b |
|---|---|---|
| The data was not recognised as used by the paper | 4 | 2 now recovered (offline replay): quotes broken by PDF noise, and names listed in a sources table. 2 remain. |
| Small-institution data that a person could not confirm either | 4 | Not fixable by the tool; the report lists leads. |
| The right site was found but not accepted | 2 | 1 now recovered (distributor rule, offline replay). EPS still fails: its site never uses the database's full name. |

The v2.5–v2.5b fixes were checked by replaying saved model answers and saved pages, not by a new independent round, so they are not in the table above.

## Before you use it

- **You will usually have to download some PDFs yourself.** In the three test rounds, 3 of 9 automatically selected papers downloaded; publishers refused the rest (HTTP 401/403, login pages) even when the paper is open access. The report lists each failed paper with its link. Download them in your browser and pass them with `--pdf`. The tool does not get around publisher bot blocking.
- **Distributor answers are labelled.** A site that is not the original provider (e.g. NBER for CPS extracts) is accepted when the page names the data, and the report says "Distributor site — not the original provider and not confirmed as official". Such a page could also be a blog or a copycat site; check the original provider if you need the authoritative version.
- **Answers reflect the page on the date checked.** Prices, registration rules and URLs change.

## Changes since V1

- **Official-site check** (`--official`): an agent searches the provider's site; a finding is shown only when the program has confirmed the page and found the quoted text on it.
- **Country per paper** (v2.4d): the study country now comes from each paper, not from the research direction. Before, a China paper in a "United States" search had its Chinese government source rejected.
- **PDF-noise-tolerant quotes** (v2.5): evidence that a paper *used* a dataset may be interrupted by formula symbols, a footnote, or a page break; every word must still appear in order. Quotes about *access conditions* must still match word for word.
- **"Please check this yourself" with leads** (v2.5): when the check finds no answer, the report lists the pages submitted but not accepted (with the reason) and the pages read.
- **Distributor sites** (v2.5a): see above.
- **Sources tables** (v2.5b): a short table-cell entry under a table that mentions sources counts as a data source, not a variable.
- **Curly and straight quotes** (v2.5c): quote verification treats ’ and ', “ ” and " as the same character. A model often types China's where the PDF has China’s; before, such a quote failed and the data source was dropped (found in the V2 demo: Chang et al.'s main data). Offline check: the recall baseline (18 papers, 80 sources) is unchanged at 73/80; of 349 saved quotes in 41 saved results, 5 changed from failing to passing, all from that paper and all present in the PDF.
- **Uploaded PDFs matched to search results** (2026-11-18, `scout.py` only; check rules unchanged): a PDF passed with `--pdf` is matched to the paper it belongs to by DOI or full title on its first two pages, keeps that paper's name, and is no longer listed as "not analysed"; a second copy of a paper already read is skipped.
- **Access quote must state how to get the data** (v2.5d): a download, application, purchase or subscription answer is accepted only if the quoted page sentence states that way of access (download / online public use / register; apply / approval / consult on site; buy / bookshop / price; subscribe / licence / institutional access rights). Otherwise the check is sent back, and if nothing better is found the page is kept as a lead with the next step. Offline re-check of the saved results: of 21 findings in the demo and rounds 3–5, 6 are now leads (2010 census yearbook table, real-time air-quality release, MERRA-2 ×2, UNCTAD TRAINS, CMIE Prowess) and 15 are unchanged. TRAINS and Prowess had the right channel but quoted sentences that do not state it, so the two-question totals fall from 7 / 13 and 7 / 17 to 5 / 13 and 5 / 17, still with 0 wrong answers.
- **Main data by paper** (2026-11-18, report layout only; check rules unchanged): the report opens with each paper's main data (the model's role judgment) with the checked source sentence and page and a one-line official-site status. Candidates the model marked as main data whose evidence failed a check are shown under "To verify" with what is missing and where to look, instead of only at the end of the report; they are still not counted as used. On the 18-paper recall baseline, 54 of 65 main-text sources appear in the main-data list, 1 under To verify, 7 by name under "other data used" (the model judged them robustness or supplementary), and 2 do not appear (the model did not list them).
- **V2 demo** (`python demo/replay.py official`): saved report of a real run on air pollution and labour productivity in China, with the errors found by hand listed in demo/README.md.
- **Two-question scoring**: the test rounds were scored with an internal script that is not part of the public package.

## Known limitations

- **Missed data sources remain the main weakness.** Still missed after v2.5b: a dataset whose only mention is a body sentence while the table uses a different wording (10-K reports), and a quote the model altered (it typed "(Z)" where the PDF has a formula).
- **Commercial databases known by a short brand name** (EPS DATA for "Economy Prediction System") are not matched to their site, so they end up as leads.
- **Small or national institutions** with unreachable or sparse websites (e.g. ITCEQ Tunisia) are rarely answered; a person often cannot confirm them either.
- **Results vary between runs**, and runs make many paid calls (round 5: 35 searches, 12 page reads).
- **Small test set**: 17 data sources in 6 papers over three topics, scored by host. Treat the percentages as indicative.
- Scanned PDFs are not supported.
