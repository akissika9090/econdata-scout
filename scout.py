"""
EconData Scout 端到端流程：输入研究方向 → 检索文献 → 下载开放获取全文 → 提取与核对数据来源 →（可选）Agent 回查 → 合并报告。

每一步都调用已有的模块，这个文件只负责把它们按顺序串起来，并记录每篇论文走到了哪一步：
    1. 检索      search_papers.search()          候选论文：自动调查组 + 建议上传组
    2. 下载      fetch_fulltext.fetch_one()       只下载开放获取 PDF，逐项核对；失败的记下原因，不推断正文
    3. 提取      step2_ai_extract.extract()       AI 提取数据来源，程序核对每一条引用
    4. 回查      agent.recover_report()           （加 --agent 时）对仍为“未确认”的数据源，让 Agent 回到 PDF 找证据
    4b. 官网     official_check.check_merged()   （加 --official 时，V2）对合并后的每个数据源查提供方官网“现在怎么拿”；
                                                   结论须通过程序核对（官方来源、引文逐字在页面上），读不到的官方页面列入手动核对
    5. 合并      step3_merge.merge_reports()      多篇论文按数据源合并，生成报告（加 --official 时，每个数据源有“论文｜官网”两栏对照）

一次运行的所有文件都放在 runs/日期_时间/ 里（候选、PDF、每篇的提取结果、Agent 日志、报告），
不读写 papers/ 和 results/，所以不会和开发集、诊断集、历史测试结果混在一起。

运行（需要 GEMINI_API_KEY 和 OPENALEX_API_KEY）：
    python scout.py "the effect of minimum wage increases on teen employment in the United States"
    python scout.py "research direction" --agent           # also run the Evidence Recovery Agent (many more calls)
    python scout.py "research direction" --pdf my_paper.pdf ...   # add PDFs you obtained yourself (e.g. paywalled)
    python scout.py "research direction" --official      # V2: also check each data source on the official site (needs DEEPSEEK_API_KEY)
"""

import argparse
import json
import os
import re
import shutil
from datetime import datetime

import agent
import fetch_fulltext
import search_papers
import step1_pdf_evidence as step1
import step2_ai_extract as step2
import step3_merge as step3


ANALYSIS_LABELS = {"extract_failed": "the AI extraction failed (e.g. all Gemini models were busy) - run again later"}


def paper_label(paper: dict, used: set) -> str:
    """报告里用的论文简称：第一作者姓 + 年份（如 Meyer1981）；重名时加 a、b。"""
    first = (paper.get("authors") or ["Unknown"])[0].split()[-1]
    base = re.sub(r"[^A-Za-z]", "", first) + str(paper.get("year") or "")
    label, n = base, 0
    while label in used:
        n += 1
        label = base + "abcdefghij"[n - 1]
    used.add(label)
    return label


def _norm(text: str) -> str:
    """配对用：小写、只留字母数字、合并空白（PDF 断行和连字符不影响）。"""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower().replace("-\n", "")).split())


def first_pages_text(path: str, pages: int = 2) -> str:
    """读上传 PDF 前两页的文字，只用来和检索结果配对；读不了返回空字符串（照常按文件名处理）。"""
    try:
        import pymupdf
        with pymupdf.open(path) as doc:
            return "\n".join(doc[i].get_text() for i in range(min(pages, len(doc))))
    except Exception:
        return ""


def match_upload(text: str, candidates: list[dict]) -> dict | None:
    """上传的 PDF 是不是检索到但没能读到的某篇论文：前两页出现该论文的 DOI，或出现完整标题（至少 4 个词）。
    只认唯一匹配；对不上或对上多篇就返回 None，按文件名单独处理。"""
    body, hits = _norm(text), []
    for c in candidates:
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", (c.get("doi") or c.get("landing_url") or "").strip(), flags=re.I)
        doi_hit = doi.lower().startswith("10.") and _norm(doi) in body
        title = _norm(c.get("title"))
        title_hit = len(title.split()) >= 4 and title in body
        if doi_hit or title_hit:
            hits.append(c)
    return hits[0] if len(hits) == 1 else None


def save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def analyse_pdf(paper: dict, pdf_path: str, run_dir: str, use_agent: bool) -> dict:
    """对一篇已下载并核对过的 PDF 做提取（和可选的 Agent 回查）。返回 {status, report, ...}。
    任何一步失败都只影响这一篇：记下原因，其他论文继续。"""
    try:
        extracted = step2.extract(pdf_path)
    except (Exception, SystemExit) as e:   # 例如所有 Gemini 模型都暂时不可用
        return {"status": "extract_failed", "detail": str(e)[:300]}
    save_json(os.path.join(run_dir, "extract", f"{paper['label']}.json"), extracted)
    result = {"status": "extracted", "model": extracted["model"], "report": extracted["report"]}
    if use_agent:
        try:
            pages, _ = step1.extract_pages(pdf_path)
            agent_report = agent.recover_report(pages, extracted["report"])
        except Exception as e:   # Agent 阶段出错：这篇保留基础流程的结果，记录原因，其他论文继续
            result["agent_error"] = f"{type(e).__name__}: {str(e)[:250]}"
            return result
        save_json(os.path.join(run_dir, "agent", f"{paper['label']}.json"),
                  {"base_report": extracted["report"], "agent_report": agent_report})
        result["report"] = agent_report
        result["agent_used"] = True
    return result


def default_official_check(merged: list[dict], topic: str = "") -> dict:
    import official_check as oc
    from web_tools import Web
    return oc.check_merged(merged, Web(), oc.load_learned(), verbose=True)


def run(topic: str, use_agent: bool = False, extra_pdfs: list[str] | None = None, run_dir: str | None = None,
        search=search_papers.search, get=fetch_fulltext.default_get, use_official: bool = False,
        official_check=default_official_check) -> dict:
    """完整流程。search、get、official_check 只在测试时替换（不联网）。返回这次运行的记录（也保存为 run.json）。"""
    run_dir = run_dir or os.path.join("runs", datetime.now().strftime("%Y%m%d_%H%M%S"))
    for sub in ("extract", "agent"):
        os.makedirs(os.path.join(run_dir, sub), exist_ok=True)

    # 1. 检索
    print(f"\n[1/5] Searching OpenAlex for: {topic}")
    found = search(topic)
    save_json(os.path.join(run_dir, "candidates.json"), found)
    search_papers.print_candidates(found)

    # 2. 下载：自动调查组 + 用户自己提供的 PDF
    print("\n[2/5] Downloading open-access full texts...")
    used, papers = set(), []
    for c in found.get("auto", []):
        rec = fetch_fulltext.fetch_one(c, run_dir, get=get)
        papers.append({**rec, "label": paper_label(c, used), "year": c.get("year"), "venue": c.get("venue"),
                       "origin": "open access (OpenAlex)", "study_area": c.get("study_area")})
    # 用户上传的 PDF 先和“下载失败”“需要上传”的论文配对（DOI 或完整标题），配上的沿用那篇论文的简称和书目信息，
    # 不再在报告末尾列为“未分析”；配不上的按文件名单独列出。
    to_upload = list(found.get("upload", []))
    uploaded_note = "uploaded by the user; version not checked"
    duplicate_uploads = []
    for path in extra_pdfs or []:
        failed = [p for p in papers if p["status"] != "ok"]
        downloaded = [p for p in papers if p["status"] == "ok"]
        hit = match_upload(first_pages_text(path), failed + to_upload + downloaded)
        if hit is not None and any(hit is p for p in downloaded):
            # 同一篇已经自动下载成功（或前面上传过）：不再分析第二遍，否则同一篇论文会被算成两篇
            duplicate_uploads.append({"file": os.path.basename(path), "same_as": hit["label"]})
            print(f"  = {os.path.basename(path)}: same paper as {hit['label']} (already read) - not analysed twice")
            continue
        if hit is not None and any(hit is p for p in failed):
            paper = hit
            paper.update({"auto_download_status": paper["status"], "status": "ok",
                          "origin": "uploaded by the user (automatic download had failed)", "version_note": uploaded_note})
            paper.pop("version_openalex", None)   # OpenAlex 记录的版本不一定是用户上传的这一份
        elif hit is not None:
            to_upload.remove(hit)
            label = paper_label(hit, used)
            paper = {"id": hit.get("id") or label, "title": hit.get("title"), "label": label, "year": hit.get("year"),
                     "venue": hit.get("venue"), "landing_url": hit.get("landing_url"), "study_area": hit.get("study_area"),
                     "origin": "uploaded by the user (listed as not freely available)", "version_note": uploaded_note}
            papers.append(paper)
        else:
            name = os.path.basename(path)
            while name.lower().endswith(".pdf"):
                name = name[:-4]
            label = paper_label({"authors": [name], "year": ""}, used)
            paper = {"id": label, "title": os.path.basename(path), "label": label,
                     "origin": "uploaded by the user", "version_note": uploaded_note}
            papers.append(paper)
        dest = os.path.join(run_dir, "pdfs", f"{paper['label']}_upload.pdf")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(path, dest)   # 复制一份，不改动用户的原文件
        paper.update({"status": "ok", "path": dest, "uploaded_file": os.path.basename(path)})
    found = {**found, "upload": to_upload}   # 报告和 run.json 里只列仍未上传的；candidates.json 已按原样保存
    for p in papers:
        mark = "✓" if p["status"] == "ok" else "✗"
        print(f"  {mark} {p['label']}: {p['status']} - {p['title'][:80]}")

    # 3–4. 提取（和可选的 Agent 回查）
    print(f"\n[3/5] Extracting data sources{' and running the Evidence Recovery Agent' if use_agent else ''}...")
    reports = []
    for p in papers:
        if p["status"] != "ok":
            continue
        print(f"  - {p['label']}")
        result = analyse_pdf(p, p["path"], run_dir, use_agent)
        p["analysis"] = {k: v for k, v in result.items() if k != "report"}
        if result["status"] == "extracted":
            report = result["report"]
            if use_official:
                from official_check import paper_country
                area = paper_country(p)
                for source in report["data_sources"]:
                    source["study_area"] = area
            reports.append((p["label"], report))
        else:
            print(f"    ✗ {result['status']}: {result.get('detail', '')[:120]}")

    # 4. 官网核查（V2，可选）：对合并后的每个数据源查官网；某个数据源出错只影响它自己（check_merged 内部已回退）
    official = None
    if use_official:
        print("\n[4/5] Checking official sites for how each data source can be obtained now...")
        try:
            official = official_check(step3.merge_reports(reports), topic)
            save_json(os.path.join(run_dir, "official.json"), official)
        except Exception as e:   # 例如没有 DeepSeek key、网络不通：报告照常生成，说明官网核查没有完成
            print(f"  ✗ official check failed: {type(e).__name__}: {str(e)[:200]}")
            official = {}

    # 5. 合并与报告
    print("\n[5/5] Merging and writing the report...")
    report_text = format_run_report(topic, found, papers, reports, use_agent, official)
    report_path = os.path.join(run_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    # 6. 入手経路カタログ（中国経済データ 9 種）：主要データごとの日本語結果表。失敗しても本体のレポートには影響しない
    try:
        from access_catalog import render_table_ja
        with open(os.path.join(run_dir, "access_table_ja.md"), "w", encoding="utf-8") as f:
            f.write(render_table_ja(reports))
        print(f"Access table (catalog) saved to {os.path.join(run_dir, 'access_table_ja.md')}")
    except Exception as e:
        print(f"  ✗ access table failed: {type(e).__name__}: {str(e)[:200]}")
    record = {"topic": topic, "run_dir": run_dir, "agent": use_agent, "official": use_official, "papers": papers,
              "duplicate_uploads": duplicate_uploads, "upload_suggested": found.get("upload", []), "report": report_path}
    save_json(os.path.join(run_dir, "run.json"), record)
    print(f"\nReport saved to {report_path}")
    return record


def format_run_report(topic: str, found: dict, papers: list[dict], reports: list[tuple[str, dict]], use_agent: bool,
                      official: dict | None = None) -> str:
    """报告 = 这次调查了哪些论文（来源、版本、状态）+ 按数据源合并的结果（step3）+ 尚未确认的事项。"""
    lines = [f"# EconData Scout report", "", f"- Research direction: {topic}",
             f"- Policy: {found.get('policy')}  |  Outcome: {found.get('outcome')}",
             f"- Evidence Recovery Agent: {'used' if use_agent else 'not used'}",
             f"- Official-site check (V2): {'used' if official is not None else 'not used'}", "", "## Papers investigated", ""]
    for p in papers:
        if p["status"] == "ok" and (p.get("analysis") or {}).get("status") == "extracted":
            version = p.get("version_openalex") or ""
            lines.append(f"- **{p['label']}** {p['title']} ({p.get('venue') or p['origin']})")
            lines.append(f"  - full text: {p['origin']}; version: {version + ' - ' if version else ''}{p.get('version_note', '')}")
            if p.get("version_warning"):
                lines.append(f"  - ⚠ {p['version_warning']}")
    lines += ["", step3.report_markdown(reports, official=official),
              "", "## Not yet confirmed", ""]
    failed = [p for p in papers if p["status"] != "ok" or (p.get("analysis") or {}).get("status") != "extracted"]
    for p in failed:
        reason = p["status"] if p["status"] != "ok" else p["analysis"]["status"]
        label = fetch_fulltext.STATUS_LABELS.get(reason) or ANALYSIS_LABELS.get(reason, reason)
        lines.append(f"- **{p['label']}** {p['title']}: not analysed ({label}). {p.get('landing_url') or p.get('url') or ''}")
    for u in found.get("upload", []):
        lines.append(f"- {u['title']} ({u.get('year')}, {u.get('venue') or 'venue unknown'}): not freely available - "
                     f"upload it if you can get it. {u.get('landing_url') or u.get('doi') or ''}")
    if not failed and not found.get("upload"):
        lines.append("- (none)")
    lines += ["", "Nothing is inferred about papers that could not be read. Access conditions are as described by the "
              "authors at the time of publication; check them with the data provider."]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="EconData Scout: research direction -> data-source report")
    parser.add_argument("topic", help="research direction, in English")
    parser.add_argument("--agent", action="store_true", help="run the Evidence Recovery Agent on unconfirmed sources")
    parser.add_argument("--pdf", nargs="*", default=[], help="PDFs you downloaded yourself (e.g. paywalled papers)")
    parser.add_argument("--official", action="store_true",
                        help="V2: check each data source on the provider's official site (needs DEEPSEEK_API_KEY)")
    args = parser.parse_args()
    run(args.topic, use_agent=args.agent, extra_pdfs=args.pdf, use_official=args.official)


if __name__ == "__main__":
    main()
