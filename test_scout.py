"""
测试端到端流程 scout.py：各步骤是否按顺序串起来、失败是否只影响那一篇、文件是否只写进这次运行的文件夹。
不联网：检索、下载、AI 提取、Agent 都用假数据代替；PDF 用程序生成。

运行：
    python test_scout.py
"""

import json
import os
import tempfile

import pymupdf

import fetch_fulltext
import gemini_client
import scout
import step2_ai_extract as step2

failures = 0


def check(name, ok):
    global failures
    print(f"{'✓' if ok else '✗'}  {name}")
    if not ok:
        failures += 1


SOURCE = "Our data come from the Current Population Survey (CPS) conducted by the U.S. Census Bureau."
ACCESS = "The CPS microdata are publicly available from the Census Bureau website."


def make_pdf(title: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), title, fontsize=12)
    body = ("2. Data\n" + SOURCE + " " + ACCESS + " " + "We study state minimum wage changes. " * 40)
    page.insert_textbox(pymupdf.Rect(72, 100, 520, 780), body, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


class Resp:
    def __init__(self, status=200, content=b""):
        self.status_code, self.content, self.headers = status, content, {"content-type": "application/pdf"}


A = {"id": "WA", "title": "Minimum Wages and Teen Employment in the States", "year": 2015, "authors": ["Jane Smith"],
     "venue": "Journal X", "pdf_url": "https://ok.example/a.pdf", "oa_version": "publishedVersion"}
B = {"id": "WB", "title": "Another Minimum Wage Study of Teenage Workers", "year": 2010, "authors": ["Bob Lee"],
     "venue": "Journal Y", "pdf_url": "https://blocked.example/b.pdf", "landing_url": "https://blocked.example/b",
     "oa_version": "publishedVersion"}
C = {"id": "WC", "title": "Youth Employment and the Minimum Wage Revisited", "year": 2012, "authors": ["Ann Smith"],
     "venue": "Journal Z", "pdf_url": "https://ok.example/c.pdf", "oa_version": "submittedVersion"}
# 和 search_papers.search() 返回的字段一致（显示候选时会用到）
COMMON = {"doi": None, "landing_url": None, "cited_by": 1, "abstract": "x", "is_oa": True, "relevance": 3,
          "policy_match": "same", "outcome_match": "same", "uses_data": "yes", "study_area": "United States",
          "reason": "same question", "access": "pdf"}
A, B, C = ({**COMMON, **x} for x in (A, B, C))
U = {**COMMON, "id": "WU", "title": "A Paywalled Classic", "year": 1991, "authors": ["Old Author"], "venue": "JHR",
     "doi": "https://doi.org/x", "pdf_url": None, "is_oa": False, "access": "upload", "oa_version": None}
FOUND = {"topic": "t", "policy": "minimum wage", "outcome": "teen employment", "queries": ["q"],
         "models_used": ["fake"], "n_found": 4, "auto": [A, B, C], "upload": [U], "all": [A, B, C, U]}


def fake_get(url):
    if "blocked" in url:
        return Resp(status=403)
    return Resp(content=make_pdf(A["title"] if url.endswith("a.pdf") else C["title"]))


AI_ANSWER = {"data_sources": [{"name": "Current Population Survey (CPS)", "role": "main", "kind": "dataset",
                               "provider": "U.S. Census Bureau", "sample_period": None, "period_evidence": None,
                               "unit": "individual", "access_category": "public",
                               "source_evidence": {"quote": SOURCE, "page": 1},
                               "access_evidence": {"quote": ACCESS, "page": 1}}],
             "sample_limitations": [], "availability_statement": None}
calls = {"n": 0}


def fake_ask_ai(context):
    calls["n"] += 1
    if calls["n"] == 2:            # 第二篇（C）提取时模型全部不可用
        raise SystemExit("All Gemini models are unavailable")
    return json.loads(json.dumps(AI_ANSWER)), "Gemini (fake)"


orig_ask, orig_gen = step2.ask_ai, gemini_client.generate_json
step2.ask_ai = fake_ask_ai
gemini_client.generate_json = lambda system, content, schema: ({"thought": "t", "action": "give_up", "query": None,
                                                                  "page": None, "category": None, "quote": None}, "fake")
watched = {d: sorted(os.listdir(d)) for d in ("papers", "results") if os.path.isdir(d)}
try:
    with tempfile.TemporaryDirectory() as d:
        run_dir = os.path.join(d, "run")
        rec = scout.run("minimum wage and teen employment", use_agent=True, run_dir=run_dir,
                        search=lambda topic: FOUND, get=fake_get)
        by_id = {p["id"]: p for p in rec["papers"]}
        check("下载：可下载的论文核对通过，403 的论文记为 http_403 并保留链接",
              by_id["WA"]["status"] == "ok" and by_id["WB"]["status"] == "http_403" and by_id["WB"]["url"])
        check("提取：成功的论文有结果；模型失败只影响那一篇（C），其他继续",
              by_id["WA"]["analysis"]["status"] == "extracted" and by_id["WC"]["analysis"]["status"] == "extract_failed")
        check("403 的论文不做提取（不推断正文）", "analysis" not in by_id["WB"])
        report = open(rec["report"], encoding="utf-8").read()
        check("报告：列出调查了哪些论文（简称、标题、来源、版本说明）",
              "Smith2015" in report and A["title"] in report and "not verified" in report)
        check("报告：数据来源及其证据进入合并结果", "Current Population Survey" in report and ACCESS in report)
        check("报告：“尚未确认”列出 403 的论文（附链接、说明不代表不公开）、提取失败的论文、建议上传的论文",
              "Another Minimum Wage Study" in report and "NOT mean" in report and "https://blocked.example" in report
              and "Youth Employment and the Minimum Wage Revisited" in report and "A Paywalled Classic" in report
              and "AI extraction failed" in report)
        check("文件：候选、PDF、提取结果、Agent 日志、报告、运行记录都在这次运行的文件夹里",
              all(os.path.exists(os.path.join(run_dir, f)) for f in
                  ["candidates.json", "pdfs/WA.pdf", "extract/Smith2015.json", "agent/Smith2015.json", "report.md", "run.json"]))
        check("Agent：已经确认的数据源不交给 Agent（跳过）",
              json.load(open(os.path.join(run_dir, "agent", "Smith2015.json")))["agent_report"]["data_sources"][0]["agent"]["outcome"] == "skipped")
        up = os.path.join(d, "my_paper.pdf")
        open(up, "wb").write(make_pdf("Uploaded Paper on Minimum Wages"))
        calls["n"] = 10
        rec2 = scout.run("t", run_dir=os.path.join(d, "run2"), extra_pdfs=[up],
                         search=lambda topic: {**FOUND, "auto": []}, get=fake_get)
        p = rec2["papers"][0]
        check("用户自己提供的 PDF：复制进运行文件夹后同样提取，来源标明“用户上传”",
              p["origin"] == "uploaded by the user" and p["analysis"]["status"] == "extracted" and os.path.exists(up))
        rec3 = scout.run("t", run_dir=os.path.join(d, "run3"), search=lambda topic: FOUND,
                         get=lambda url: Resp(status=403))
        report3 = open(rec3["report"], encoding="utf-8").read()
        check("所有论文都下载失败：整次调查不报错，报告照样列出每篇的失败原因、链接和建议上传的论文",
              all(p["status"] == "http_403" for p in rec3["papers"]) and A["title"] in report3
              and "A Paywalled Classic" in report3 and "https://ok.example/a.pdf" in report3)
        sample = report
        orig_recover = scout.agent.recover_report
        scout.agent.recover_report = lambda pages, rep, **kw: (_ for _ in ()).throw(AttributeError("'list' object has no attribute 'get'"))
        calls["n"] = 20
        try:
            rec4 = scout.run("t", use_agent=True, run_dir=os.path.join(d, "run4"), search=lambda topic: FOUND, get=fake_get)
            a4 = {p["id"]: p for p in rec4["papers"]}["WA"]
            ok = a4["analysis"]["status"] == "extracted" and "agent_error" in a4["analysis"] and os.path.exists(rec4["report"])
        except Exception as e:
            ok = False
        finally:
            scout.agent.recover_report = orig_recover
        check("Agent 阶段出错（如模型返回格式不对）：这篇保留基础流程的结果并记录失败，整次调查不中断", ok)
    check("不读写 papers/ 和 results/（不会混进开发集、诊断集和历史测试结果）",
          {d: sorted(os.listdir(d)) for d in watched} == watched)
    check("论文简称：同名同年时加 a、b 区分",
          [scout.paper_label({"authors": ["X Wang"], "year": 2020}, s) for s in [set()] for _ in range(2)] == ["Wang2020", "Wang2020a"])
finally:
    step2.ask_ai, gemini_client.generate_json = orig_ask, orig_gen

if os.environ.get("SHOW_REPORT"):
    print("\n----- 报告示例 -----\n" + sample)
print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
