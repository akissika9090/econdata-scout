"""
Run the test suites. No test calls an API or needs a key.

    python run_tests.py            # public tests: synthetic data and saved demo results only (no key, no network, no paper PDFs)

Tests that read real paper PDFs are kept in the author's development copy and are not distributed (2026-11-23): the PDFs
cannot be distributed, and those tests quote the papers at length.

Each test file runs in its own process from the repository root. Exit code 0 = passed, 77 = skipped, anything else = failed.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT = ["test_chain.py", "test_step3.py", "test_final_report.py", "test_v2_fields.py", "test_official.py", "test_fetch.py",
           "test_search.py", "test_scout.py", "test_gemini_client.py", "test_access_catalog.py",
           "test_channel_consistency.py",
           "test_time_limit.py", "test_time_resources.py", "test_reset.py",
           "test_site_text.py", "test_site.py"]
SKIP_CODE = 77


def main() -> int:
    files = DEFAULT
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
