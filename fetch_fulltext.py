"""
下载“自动调查”候选论文的开放获取 PDF，并逐项核对，确认拿到的真的是那篇论文的全文。

只下载 OpenAlex 标注为开放获取的 PDF 地址（search_papers 的“自动调查”组）。
每篇论文依次核对，任何一项不通过就停在那一项，记下原因，不推断正文内容：
    1. HTTP 下载成功（状态码 200）                         → 否则 http_403 / http_error / network_error
                                                           （403 多半是网站拦截程序下载，不代表论文不公开）
    2. 下载到的确实是 PDF（文件以 %PDF 开头）               → 否则 not_pdf（常见：收费墙返回的登录网页）
    3. 文件能打开，而且能提取出文字                        → 否则 unreadable / no_text（扫描版）
    4. 第 1–2 页里能找到这篇论文的标题                      → 否则 title_mismatch（下载到的是别的文件）
全部通过 → ok，PDF 保存到这次运行自己的文件夹（runs/日期_时间/pdfs/），不和 papers/ 里的开发集、诊断集混在一起。
title_mismatch 的文件单独保存在 rejected/，方便人工确认；其他失败不保存文件。

版本只记录 OpenAlex 的标注，并注明“未核实”：标注不一定准确（例如工作论文的 DOI 被标为期刊正式版）。
唯一的检查：标为正式版、首页却写着 “Working Paper” 时给出不一致警告。

运行：
    python fetch_fulltext.py candidates/20261105_134526.json
"""

# 【2026-11-05 冻结】下载模块：不再追求下载成功率（不尝试多个开放获取地址、不伪装浏览器绕过 403），只修 Bug。

import json
import os
import re
import sys
from datetime import datetime

import pymupdf

import step1_pdf_evidence as step1

TIMEOUT = 60                  # 秒
MAX_BYTES = 50 * 1024 * 1024  # 超过 50MB 的不下载
MIN_TEXT_CHARS = 1000         # 全文能提取出的文字少于这个数，视为没有文字层（扫描版）
HEADERS = {"User-Agent": "EconDataScout/0.1 (academic research tool; open-access PDFs only)"}

STATUS_LABELS = {
    "ok": "downloaded and verified",
    "no_pdf_link": "no PDF link in OpenAlex - open the landing page and upload the PDF if you can get it",
    "network_error": "could not connect",
    "http_error": "the server did not return the file",
    "http_403": ("the server refused the automated download (HTTP 403). This does NOT mean the paper is not open access: "
                 "open the link in your browser, download the PDF and upload it"),
    "too_large": "file larger than 50 MB, not downloaded",
    "not_pdf": "the link did not return a PDF (often a login or paywall page)",
    "unreadable": "the file could not be opened as a PDF",
    "no_text": "the PDF has no extractable text (probably scanned)",
    "title_mismatch": "the PDF does not seem to be this paper (title not found on its first pages)",
}


def letters_only(text: str) -> str:
    """只保留字母和数字（先用 step1.squash 合并换行断词、统一大小写）。
    标题里的标点在 PDF 和 OpenAlex 中常常写法不同：China’s（弯撇号）/ China's、– / -、引号等。"""
    return re.sub(r"[^a-z0-9]", "", step1.squash(text))


def title_found(title: str, first_pages: list[str]) -> bool:
    """标题是否出现在前两页。只比较字母和数字，所以换行、断词、标点写法不同都不影响。
    只比较冒号前的主标题也可以：有的 PDF 首页只印主标题。"""
    text = letters_only(" ".join(first_pages))
    candidates = [title, re.split(r"[:?]\s", title)[0]]
    for t in candidates:
        key = letters_only(t)
        if len(key) >= 15 and key in text:
            return True
    return False


def default_get(url: str):
    import requests
    return requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)


def fetch_one(paper: dict, out_dir: str, get=default_get) -> dict:
    """下载并核对一篇论文。返回记录 {id, title, url, status, detail, ...}。get 只在测试时替换。"""
    rec = {"id": paper["id"], "title": paper["title"], "url": paper.get("pdf_url"),
           "landing_url": paper.get("landing_url") or paper.get("doi"),
           "version_openalex": paper.get("oa_version"), "version_note": "OpenAlex metadata, not verified"}
    if not rec["url"]:
        return {**rec, "status": "no_pdf_link"}
    try:
        r = get(rec["url"])
    except Exception as e:
        return {**rec, "status": "network_error", "detail": f"{type(e).__name__}: {str(e)[:150]}"}
    rec["http_status"] = r.status_code
    if r.status_code != 200:
        # 403 多半是网站拦截程序下载（不是论文不公开），单独说明，提示用户用浏览器下载
        return {**rec, "status": "http_403" if r.status_code == 403 else "http_error", "detail": f"HTTP {r.status_code}"}
    data = r.content or b""
    rec["bytes"] = len(data)
    if len(data) > MAX_BYTES:
        return {**rec, "status": "too_large"}
    if not data.lstrip()[:5].startswith(b"%PDF"):
        return {**rec, "status": "not_pdf", "detail": f"content-type: {r.headers.get('content-type', 'unknown')}"}
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            pages = [page.get_text() for page in doc]
    except Exception as e:
        return {**rec, "status": "unreadable", "detail": f"{type(e).__name__}"}
    rec["pages"] = len(pages)
    if sum(len(p.strip()) for p in pages) < MIN_TEXT_CHARS:
        return {**rec, "status": "no_text"}
    ok = title_found(paper["title"], pages[:2])
    # 版本：只做一个很小的检查——OpenAlex 标为期刊正式版，但 PDF 首页明确写着 “Working Paper” 时，提示两者不一致。
    # 不判断“真正的版本”是什么，只报告不一致（例：Meyer & Wise 1981 被标为正式版，首页却是 NBER Working Paper No. 711）
    if paper.get("oa_version") == "publishedVersion" and re.search(r"working\s+paper", " ".join(pages[:1]), re.IGNORECASE):
        rec["version_warning"] = "OpenAlex says published version, but the first page says 'Working Paper'"
    folder = os.path.join(out_dir, "pdfs" if ok else "rejected")
    os.makedirs(folder, exist_ok=True)
    rec["path"] = os.path.join(folder, f"{paper['id']}.pdf")
    with open(rec["path"], "wb") as f:
        f.write(data)
    return {**rec, "status": "ok" if ok else "title_mismatch"}


def fetch_candidates(candidates_path: str, out_dir: str | None = None, get=default_get) -> dict:
    """对 search_papers 保存的结果中“自动调查”组的每篇论文下载并核对。结果写进 out_dir/fetch_report.json。"""
    with open(candidates_path, encoding="utf-8") as f:
        result = json.load(f)
    out_dir = out_dir or os.path.join("runs", datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    records = [fetch_one(p, out_dir, get=get) for p in result.get("auto", [])]
    report = {"candidates_file": candidates_path, "topic": result.get("topic"), "out_dir": out_dir,
              "fetched": records, "upload_suggested": [{"id": p["id"], "title": p["title"],
                                                        "link": p.get("landing_url") or p.get("doi")}
                                                       for p in result.get("upload", [])]}
    with open(os.path.join(out_dir, "fetch_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def print_fetch_report(report: dict) -> None:
    print(f"\n=== Full-text download ({report['out_dir']}) ===")
    for i, r in enumerate(report["fetched"], start=1):
        mark = "✓" if r["status"] == "ok" else "✗"
        print(f"\n{i}. {mark} {r['title']}")
        print(f"   {r['status']}: {STATUS_LABELS[r['status']]}" + (f" ({r['detail']})" if r.get("detail") else ""))
        if r["status"] == "ok":
            print(f"   {r['pages']} pages, saved to {r['path']}  |  version (OpenAlex, not verified): {r['version_openalex']}")
            if r.get("version_warning"):
                print(f"   ⚠ {r['version_warning']}")
        elif r.get("landing_url"):
            print(f"   {r['landing_url']}")
    n_ok = sum(1 for r in report["fetched"] if r["status"] == "ok")
    print(f"\n{n_ok} of {len(report['fetched'])} papers downloaded and verified. "
          "Papers that failed are not analysed; nothing is inferred about their content.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_fulltext.py candidates/<file>.json")
        raise SystemExit(1)
    print_fetch_report(fetch_candidates(sys.argv[1]))
