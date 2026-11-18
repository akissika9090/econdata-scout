# Demos (offline)

No demo calls an API or needs a key or network access.

## Default mode: saved-result replay, not re-verified

```bash
python demo/replay.py normal
python demo/replay.py review
python demo/replay.py fallback
```

| Demo | What is shown | Source |
|---|---|---|
| `normal` | The saved report `demo/outputs/normal.md` (yip 2018). A verified condition from an older extraction that has no scope field: the report says "original record category: public; scope not recorded" and shows the quote ("public-use files of the Canadian LFS") instead of claiming the whole LFS is public. A second source (NBER) has no stated condition; its provider is shown separately and is not treated as an access channel | Saved model output `demo/data/yip2018_1105_105410_run1.json` (2026-11-05, older prompt) |
| `review` | The saved report `demo/outputs/review.md` (Liebman 1998). A lexical clue that is not promoted to a conclusion (SOI "public use sample"); a record whose usage relation cannot be confirmed (CPS p. 14); paper-level sample restrictions that are not attributed to any source; discrete years shown as "1985, 1988"; a provider written by the model as "Internal Revenue Service" kept next to the source sentence ("IRS") | Saved model output `demo/data/A_Liebman1998.json` (2026-11-06, current prompt) |
| `fallback` | The saved record of a real end-to-end run on 2026-11-06: the primary model returned HTTP 429 and the client switched to the fallback model; one download was refused (HTTP 403) with the reason shown; five paywalled papers were listed for upload; the run continued and analysed the other two papers | Copies in `demo/data/fallback/` (`run.json`, `candidates.json`, console log); the OpenAlex abstracts were removed, everything else is unchanged |

In default mode nothing is re-checked. `normal` and `review` print report files that were generated earlier. Each file's first line says when it was generated, by which command, and from which saved model output. `fallback` reads the saved run record. The `demo/data/` files are copies of the originals; the only change is that the paper abstracts from OpenAlex were removed from `fallback/run.json` and `fallback/candidates.json` (the demo does not use them). `demo/data/SOURCES.sha256` lists the checksums of the files as distributed.

## Optional mode: re-verify with local PDFs

```bash
python demo/replay.py normal --reverify    # needs demo/pdfs/yip2018.pdf
python demo/replay.py review --reverify    # needs demo/pdfs/Liebman1998.pdf
```

This mode re-runs verification and report generation with the code in this repository, and rewrites `demo/outputs/<case>.md`. The PDFs are not distributed. If a PDF is missing, the demo reports `SKIPPED` (exit code 77) and changes nothing.

## Known errors and what is not shown

- `review`: the model missed several data sources in Liebman 1998 (the restricted CPS–tax-return matched file, the 1988 IRS non-filer study, the March CPS 1985–1997 and 1993). These are known limitations.
- `fallback`: the data-source section of that run is deliberately not shown. That run used an older prompt without a usage-relation field, and its report lists data from Dell et al. as used by Bowen 2011, although the paper only cites it. With the current prompt the same paper is handled correctly. The historical result was not edited.
- Two fallback paths have no real saved occurrence, so they are covered only by offline tests (`test_scout.py` in the default suite; `test_agent.py` in the optional paper suite): an extraction failure (all models busy) and an Agent error.
