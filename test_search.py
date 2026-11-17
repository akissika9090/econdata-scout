"""
测试检索步骤中由程序负责的部分：摘要还原、字段整理、去重、可获取性判断、候选排序，
以及 AI 返回异常时的处理。不需要 API，也不联网（AI 的回答用固定内容代替）。

运行：
    python test_search.py
"""

import search_papers as sp

failures = 0


def check(name, ok):
    global failures
    print(f"{'✓' if ok else '✗'}  {name}")
    if not ok:
        failures += 1


def work(id, title, relevance_hint=None, pdf=None, is_oa=False, cited=0, version=None):
    return {"id": id, "title": title, "year": 2020, "authors": [], "venue": None, "doi": None,
            "cited_by": cited, "abstract": "x", "is_oa": is_oa, "pdf_url": pdf,
            "landing_url": None, "oa_version": version}


# --- 摘要还原 ---
inv = {"Low-carbon": [0], "city": [1, 4], "pilots": [2], "and": [3], "employment": [5]}
check("摘要还原：按位置排好", sp.rebuild_abstract(inv) == "Low-carbon city pilots and city employment")
check("摘要还原：没有摘要 → None", sp.rebuild_abstract(None) is None)

# --- 字段整理 ---
raw = {
    "id": "https://openalex.org/W123", "title": "LCCP and Jobs", "publication_year": 2021,
    "cited_by_count": 7, "abstract_inverted_index": inv,
    "open_access": {"is_oa": True},
    "best_oa_location": {"pdf_url": "https://x.org/a.pdf", "version": "submittedVersion"},
    "primary_location": {"source": {"display_name": "Energy Economics"}},
    "authorships": [{"author": {"display_name": "A"}}, {"author": {"display_name": "B"}}],
}
w = sp.normalize_work(raw)
check("字段整理：id 只留末尾", w["id"] == "W123")
check("字段整理：PDF 地址和版本", w["pdf_url"] == "https://x.org/a.pdf" and w["oa_version"] == "submittedVersion")
check("字段整理：期刊名", w["venue"] == "Energy Economics")
w2 = sp.normalize_work({"id": "https://openalex.org/W9", "title": None})
check("字段整理：字段缺失也不报错", w2["title"] == "(no title)" and w2["pdf_url"] is None and not w2["is_oa"])

# --- 可获取性 ---
check("可获取性：有 PDF → 可下载", sp.access_status(work("a", "t", pdf="u")) == "pdf")
check("可获取性：开放获取但无 PDF 地址 → 需打开页面", sp.access_status(work("a", "t", is_oa=True)) == "oa_page")
check("可获取性：非开放获取 → 待上传", sp.access_status(work("a", "t")) == "upload")

# --- 去重 ---
works = [
    work("W1", "Low-Carbon City Pilots and Employment"),
    work("W2", "Low-carbon city pilots and employment.", pdf="u"),   # 同标题的另一版本，有 PDF
    work("W3", "Something Else"),
]
d = sp.dedupe(works)
check("去重：同标题只留一条", len(d) == 2)
check("去重：同标题时保留有 PDF 的那条", any(x["id"] == "W2" for x in d) and not any(x["id"] == "W1" for x in d))
untitled = [sp.normalize_work({"id": "https://openalex.org/W7", "title": None}),
            sp.normalize_work({"id": "https://openalex.org/W8", "title": None}),
            work("W9", "???")]   # 标题只有符号
check("去重：没有标题的论文按 id 区分，不会被合并成一篇", len(sp.dedupe(untitled)) == 3)
check("去重：同一篇无标题论文被检索到两次 → 只留一条", len(sp.dedupe([untitled[0], dict(untitled[0])])) == 1)

# --- 候选选择：分成“自动调查”和“建议上传”两组 ---
pool = [
    work("A", "a", pdf="u", cited=1),     # 相关度 2，可下载
    work("B", "b", cited=100),            # 相关度 3，读不到
    work("C", "c", pdf="u", cited=5),     # 相关度 3，可下载
    work("D", "d", pdf="u", cited=999),   # 相关度 1，可下载但不相关
    work("E", "e", is_oa=True, cited=50), # 相关度 3，开放获取页面
    work("F", "f", cited=300),            # 相关度 3，读不到，被引更多
    work("G", "g", cited=900),            # 相关度 2，读不到
    work("H", "h", pdf="u", cited=2),     # 相关度 3，可下载
]
rel = {"A": 2, "B": 3, "C": 3, "D": 1, "E": 3, "F": 3, "G": 2, "H": 3}
rows = sp.score_rows(pool, {k: {"relevance": v, "reason": ""} for k, v in rel.items()})
auto, upload = sp.select_candidates(rows, n_auto=3, n_upload=5)
a, u = [x["id"] for x in auto], [x["id"] for x in upload]
check("自动调查：只放能读到全文的论文", all(x["access"] != "upload" for x in auto))
check("自动调查：最多 3 篇，相关度高的优先；同分时可下载 > 开放页面", a == ["C", "H", "E"])
check("自动调查：低相关的论文不进来，哪怕能下载、被引很多", "D" not in a and "A" not in a)
check("建议上传：读不到全文的高相关论文不会被挤掉", "B" in u and "F" in u)
check("建议上传：按相关度、再按被引次数排序", u == ["F", "B", "G"])
check("两组都不收相关度低于门槛的论文", "D" not in a + u)
check("全部论文都保存了全文状态（包括没进候选的）", len(rows) == len(pool) and all("access" in r for r in rows))
check("没有评分的论文不进候选", sp.select_candidates(sp.score_rows([work("Z", "z", pdf="u")], {})) == ([], []))

# --- 相关度由程序按表计算：AI 只回答政策、结果变量是否相同，是否做实证分析 ---
R = sp.relevance_score
check("相关度：同一政策 + 同一结果变量 + 实证 → 3", R("same", "same", "yes") == 3)
check("相关度：同一政策 + 相近的结果变量 → 2（之前这类论文常被 AI 直接给 3 分）", R("same", "similar", "yes") == 2)
check("相关度：同一政策 + 不同的结果变量 → 2（政策数据仍可参考）", R("same", "different", "yes") == 2)
check("相关度：相近但不同的政策 + 同一结果变量 → 2（如另一项同领域的试点）", R("similar", "same", "yes") == 2)
check("相关度：相近的政策 + 相近的结果变量 → 1，不进候选", R("similar", "similar", "yes") == 1)
check("相关度：不相关的政策 + 不同的结果变量 → 0", R("different", "different", "yes") == 0)
check("相关度：综述、理论（不分析数据）最多 1 分，哪怕政策和结果变量都相同", R("same", "same", "no") == 1)
check("相关度：看不出是否实证（如没有摘要）不扣分", R("same", "same", "unclear") == 3)
check("相关度：看不出政策是否相同 → 按“相近”计分", R("unclear", "same", "yes") == 2)
check("相关度：AI 返回不认识的值 → 按“不同”处理，不会被当成相关", R("identical", "same", "yes") == 1 and R(None, None, None) == 0)

# --- AI 返回异常时 ---
orig = sp.gemini_json
focus = {"policy": "p", "outcome": "o"}
sp.gemini_json = lambda system, content, schema: {"papers": [
    {"id": "A", "policy_match": "same", "outcome_match": "same", "uses_data": "yes", "study_area": "Canada", "reason": "same question"},
    {"id": "X", "policy_match": "same", "outcome_match": "same", "uses_data": "yes", "reason": "AI 编出来的 id"},
    {"id": "B", "policy_match": "SAME!", "outcome_match": "same", "uses_data": "yes", "reason": "格式不对"},
]}
s = sp.screen("topic", focus, [work("A", "a"), work("B", "b"), work("C", "c")])
check("AI 异常：检索结果里没有的 id 被忽略", "X" not in s)
check("AI 异常：正常的回答按表算分，并保留三个判断", s["A"]["relevance"] == 3 and s["A"]["policy_match"] == "same")
check("AI 异常：不认识的值按“不同”处理（不进候选）", s["B"]["relevance"] < sp.MIN_RELEVANCE)
check("研究地区：只作为辅助信息保存，不影响计分（国家不同的论文照样可以是 3 分）",
      s["A"]["study_area"] == "Canada" and s["A"]["relevance"] == 3)
check("研究地区：AI 没写时记为 not stated", s["B"]["study_area"] == "not stated")
check("AI 异常：漏掉的论文记为 0 并注明", s["C"]["relevance"] == 0 and "no judgement" in s["C"]["reason"])
seen = {}
sp.gemini_json = lambda system, content, schema: seen.setdefault("content", content) and {"papers": []}
sp.screen("topic", {"policy": "low-carbon city pilot", "outcome": "employment structure"}, [work("A", "a")])
check("筛选：每次都把同一个“政策 / 结果变量”定义发给 AI 作为比较标准",
      "Policy: low-carbon city pilot" in seen["content"] and "Outcome: employment structure" in seen["content"])

sp.gemini_json = lambda system, content, schema: {"policy": " LCCP ", "outcome": "employment structure",
                                                  "queries": ["  ", "low carbon city employment", "a", "b", "c"]}
plan = sp.plan_search("topic")
check("检索词：去掉空白，最多 3 组", plan["queries"] == ["low carbon city employment", "a", "b"])
check("检索词：同时给出政策和结果变量", plan["policy"] == "LCCP" and plan["outcome"] == "employment structure")
sp.gemini_json = lambda system, content, schema: {"queries": []}
plan = sp.plan_search("my topic")
check("检索词：AI 什么都没给 → 都用研究方向原文", plan["queries"] == ["my topic"] and plan["policy"] == "my topic")
sp.gemini_json = orig

# --- 记录实际使用的模型：gemini_client 报告用了备用模型时，检索结果里要能看出来 ---
orig_gen = sp.gemini_client.generate_json
returns = iter([({"policy": "p", "outcome": "o", "queries": ["q1"]}, "main-model"), ({"papers": []}, "backup-model")])
sp.gemini_client.generate_json = lambda system, content, schema: next(returns)
sp.MODELS_USED.clear()
sp.plan_search("topic")
sp.screen("topic", focus, [work("A", "a")])
check("模型记录：每次调用实际用的模型都记下来（包括备用模型）", sp.MODELS_USED == ["main-model", "backup-model"])
sp.gemini_client.generate_json = orig_gen

print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
