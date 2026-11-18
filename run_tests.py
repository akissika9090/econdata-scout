"""
Run the test suites. No test calls an API or needs a key.

    python run_tests.py            # default public tests: synthetic data only (no key, no network, no paper PDFs)
    python run_tests.py --papers   # optional paper tests: need local PDFs / saved results that are not distributed;
                                   # each file reports SKIPPED (exit code 77) and lists what is missing

Each test file runs in its own process from the repository root. Exit code 0 = passed, 77 = skipped, anything else = failed.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT = ["test_chain.py", "test_step3.py", "test_final_report.py", "test_v2_fields.py", "test_official.py", "test_fetch.py",
           "test_search.py", "test_scout.py", "test_gemini_client.py"]
PAPERS = ["test_final_report_papers.py", "test_step1.py", "test_step2.py", "test_contract.py", "test_phase2.py", "test_agent.py"]
SKIP_CODE = 77


def main() -> int:
    files = PAPERS if "--papers" in sys.argv[1:] else DEFAULT
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    for f in files:
        r = subprocess.run([sys.executable, f], cwd=ROOT, capture_output=True, text=True)
        status = {0: "passed", SKIP_CODE: "skipped"}.get(r.returncode, "failed")
        counts[status] += 1
        last = (r.stdout.strip().splitlines() or [""])[-1]
        print(f"{status.upper():8} {f}" + (f"  — {last}" if status != "passed" else ""))
        if status == "failed":
            print((r.stdout[-3000:] + r.stderr[-3000:]).rstrip())
    print(f"\n{counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped ({len(files)} files)")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
