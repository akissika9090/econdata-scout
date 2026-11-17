"""
Offline demos. No API call, no key, no network.

Default mode — saved-result replay, NOT re-verified (works in a fresh copy of the repository):
    python demo/replay.py normal      # shows the saved report demo/outputs/normal.md
    python demo/replay.py review      # shows the saved report demo/outputs/review.md
    python demo/replay.py fallback    # replays the saved run record of a real run: download status, error reasons,
                                      # model fallback, and the run continuing (from demo/data/fallback/)

Optional mode — re-verify with local PDFs (the PDFs are not distributed):
    python demo/replay.py normal --reverify
    python demo/replay.py review --reverify
Re-runs verification (step2.verify_result) and the report (step3) on the saved model output in demo/data/, and
rewrites demo/outputs/<case>.md. If the PDF is missing, it reports SKIPPED (exit code 77) and changes nothing.
"""
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
SKIP_CODE = 77

CASES = {
    "normal": {"saved": "demo/data/yip2018_1105_105410_run1.json", "key": "ai_raw", "label": "yip2018",
               "pdf": ["demo/pdfs/yip2018.pdf", "papers/yip2018.pdf"],
               "about": "saved model output of 2026-11-05 (older prompt without usage/scope fields; gemini-3.5-flash-lite)"},
    "review": {"saved": "demo/data/A_Liebman1998.json", "key": "raw", "label": "Liebman1998",
               "pdf": ["demo/pdfs/Liebman1998.pdf", "runs/20261106_114218/pdfs/W1586548773.pdf"],
               "about": "saved model output of 2026-11-06 14:21 (current prompt; gemini-3.1-flash-lite)"},
}
NOT_REVERIFIED = ("SAVED-RESULT REPLAY — NOT RE-VERIFIED. This prints a report file that was generated earlier. "
                  "The PDF was not read and nothing was checked again in this run.")


def path(rel: str) -> str:
    return os.path.join(ROOT, rel)


def show_saved(case: str) -> int:
    out = path(f"demo/outputs/{case}.md")
    print(f"<!-- {NOT_REVERIFIED} -->")
    print(f"<!-- File: demo/outputs/{case}.md -->\n")
    print(open(out, encoding="utf-8").read())
    return 0


def reverify(case: str) -> int:
    c = CASES[case]
    pdf = next((p for p in c["pdf"] if os.path.exists(path(p))), None)
    if pdf is None:
        print(f"SKIPPED (reverify {case}): missing local PDF (not distributed); put it at {c['pdf'][0]}")
        return SKIP_CODE
    import step1_pdf_evidence as step1
    import step2_ai_extract as step2
    import step3_merge as step3
    saved = json.load(open(path(c["saved"]), encoding="utf-8"))
    rep = step2.verify_result(step1.extract_pages(path(pdf))[0], saved[c["key"]])
    header = (f"<!-- Generated on {date.today().isoformat()} by `python demo/replay.py {case} --reverify`: "
              f"verification and report re-run with the code in this repository on {c['saved']} — {c['about']}. -->\n")
    text = header + step3.report_markdown([(c["label"], rep)])
    open(path(f"demo/outputs/{case}.md"), "w", encoding="utf-8").write(text + "\n")
    print(text)
    return 0


def fallback() -> int:
    """Replays the saved record of a real end-to-end run (2026-11-06 11:36). Shows what failed, why, and that the run
    continued. The data-source section of that old run is not shown (older prompt; known Dell et al. attribution error)."""
    import fetch_fulltext
    d = path("demo/data/fallback")
    rec = json.load(open(os.path.join(d, "run.json"), encoding="utf-8"))
    found = json.load(open(os.path.join(d, "candidates.json"), encoding="utf-8"))
    log = open(os.path.join(d, "console.log"), encoding="utf-8").read().splitlines()
    out = [f"<!-- {NOT_REVERIFIED} Source: demo/data/fallback/ (unmodified copies of run.json, candidates.json and the "
           "console log of a real run on 2026-11-06 11:36; checksums in demo/data/SOURCES.sha256). -->", "",
           f"# Failure fallback: a real run on \"{rec['topic']}\"", "",
           "## 1. The model was busy: retries, then the fallback model", "",
           "Selected lines of the saved console log (line numbers refer to demo/data/fallback/console.log):", "", "```"]
    keep = ("[1/5]", "[2/5]", "[3/5]", "[5/5]", "temporarily unavailable", "retrying in", "failed repeatedly", "✓ ", "✗ ",
            "Report saved")
    out += [f"{i:>3}: {ln}" for i, ln in enumerate(log, 1) if any(k in ln for k in keep)]
    n429 = sum("temporarily unavailable (429)" in ln for ln in log)
    out += ["```", "", f"The primary model returned HTTP 429 {n429} times. After three attempts per call the client switched to "
            "the fallback model; the run did not stop.", "",
            "## 2. Download status of each automatically selected paper", "",
            "| Paper | Download | Reason | Analysis |", "|---|---|---|---|"]
    for p in rec["papers"]:
        reason = "—" if p["status"] == "ok" else fetch_fulltext.STATUS_LABELS.get(p["status"], p["status"])
        a = p.get("analysis") or {}
        analysis = f"extracted ({a.get('model')})" if a.get("status") == "extracted" else ("not analysed" if p["status"] != "ok" else a.get("status"))
        out.append(f"| {p['label']} — {p['title']} | {p['status']} | {reason} | {analysis} |")
    out += ["", "## 3. Papers that were not freely available (listed for the user to upload)", ""]
    out += [f"- {u['title']} ({u.get('year')}, {u.get('venue') or 'venue unknown'}): {u.get('landing_url') or u.get('doi') or ''}"
            for u in found.get("upload", [])]
    ok = [p for p in rec["papers"] if (p.get("analysis") or {}).get("status") == "extracted"]
    out += ["", "## 4. The run continued", "",
            f"{len(ok)} of {len(rec['papers'])} selected papers were analysed and the report was written "
            f"({rec['report']}; not included in this repository). Nothing was inferred about the paper that could not be "
            "downloaded.", "",
            "The data-source section of this old run is not shown here: it came from an older prompt and contains a known "
            "error (data from Dell et al. listed as used by Bowen 2011, which only cites it). See demo/README.md."]
    print("\n".join(out))
    return 0


def main() -> int:
    args = sys.argv[1:]
    case = args[0] if args else ""
    if case == "fallback" and len(args) == 1:
        return fallback()
    if case in CASES and len(args) == 1:
        return show_saved(case)
    if case in CASES and args[1:] == ["--reverify"]:
        return reverify(case)
    print("usage: python demo/replay.py normal|review|fallback   (add --reverify to normal/review to re-check with local PDFs)")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
