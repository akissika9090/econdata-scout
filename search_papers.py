"""
检索步骤：根据研究方向，从 OpenAlex 找出候选论文（自动调查约 3 篇 + 建议上传的收费论文），并标明每篇能否读到全文。

分工：
    AI（Gemini）：把研究方向拆成“政策”和“结果变量”并生成检索词；根据标题和摘要，回答每篇论文的政策、结果变量是否相同、是否做实证分析
    OpenAlex   ：返回真实存在的论文（标题、摘要、年份、开放获取状态、PDF 地址）
    程序        ：根据 AI 的三个回答按固定的表算出相关度；去重；按“相关性为主、全文可获取性为辅”选出候选；判断每篇是“可下载全文”还是“待上传”

原则（见需求定义）：
    - 只根据标题和摘要判断相关度，不根据摘要推断论文用了什么数据
    - 高度相关但读不到全文的论文也保留，列为“待上传”，由用户用学校权限下载
    - 开放获取的版本可能是工作论文版或作者稿，和期刊正式版的数据可能不同，结果里标明版本

准备：
    export GEMINI_API_KEY="你的key"
    export OPENALEX_API_KEY="你的key"   # openalex.org/settings/api，免费
运行：
    python search_papers.py "the effect of low-carbon city pilots on local employment structure in China"

注意：这一步会把研究方向和论文摘要（公开信息）发送给 Gemini，不发送任何 PDF。
"""

import json
import os
import re
import sys
from datetime import datetime

import gemini_client

OPENALEX_URL = "https://api.openalex.org/works"
PER_QUERY = 15        # 每组检索词取回的论文数
N_AUTO = 3            # 自动调查：能读到全文的论文，约 3 篇
N_UPLOAD = 5          # 建议上传：读不到全文的高相关论文，最多列出几篇
MIN_RELEVANCE = 2     # 相关度 0–3，低于这个分数的不进候选

# 面向用户的文字（英语输出），集中放在这里
VERSION_LABELS = {
    "publishedVersion": "published version",
    "acceptedVersion": "accepted manuscript",
    "submittedVersion": "submitted / working-paper version",
    None: "version unknown",
}


# ============ 1. Gemini（生成检索词、判断相关度） ============

QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "policy": {"type": "string"},
        "outcome": {"type": "string"},
        "queries": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["policy", "outcome", "queries"],
}

QUERY_PROMPT = """You are a literature-search assistant for economics. The user gives a research direction.
First, state the research direction's two core elements in a few English words each:
    policy  = the policy, program or phenomenon being studied (the cause)
    outcome = the outcome variable being studied (the effect)
Then generate 2 to 3 English search queries for finding related empirical economics papers in OpenAlex.
Rules:
1. Each query has 3 to 8 English words with key concepts only; no Boolean operators such as AND / OR
2. Every query must keep the same policy and the same outcome. Synonyms are fine (e.g. the official policy name or a common abbreviation),
   but do not replace them with a broader or different policy or outcome
3. The first query stays closest to the original wording
4. Output JSON only"""

MATCH_LEVELS = ["same", "similar", "different", "unclear"]
DATA_LEVELS = ["yes", "no", "unclear"]

SCREEN_SCHEMA = {
    "type": "object",
    "properties": {
        "papers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "policy_match": {"type": "string", "enum": MATCH_LEVELS},
                    "outcome_match": {"type": "string", "enum": MATCH_LEVELS},
                    "uses_data": {"type": "string", "enum": DATA_LEVELS},
                    "study_area": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "policy_match", "outcome_match", "uses_data", "study_area", "reason"],
            },
        }
    },
    "required": ["papers"],
}

SCREEN_PROMPT = """You are a literature-screening assistant for economics. The user gives a research direction
(its policy and its outcome) and the titles and abstracts of several papers. For each paper, answer three questions:

policy_match: is the paper's policy or phenomenon the same as the research direction's policy?
    same      = the same policy or phenomenon (its official name, abbreviation or translation counts as the same)
    similar   = a related but distinct policy or phenomenon (e.g. a different program in the same field)
    different = an unrelated policy or phenomenon
    unclear   = cannot be told from the title and abstract
outcome_match: is the paper's main outcome variable the same as the research direction's outcome?
    same      = the same outcome concept, at the same level of detail
                (e.g. if the direction is about household saving rates, a paper whose main outcome is household saving)
    similar   = a related but different outcome, including a broader or narrower version of it
                (in that example: household consumption, household wealth, or "household finances" in general)
    different = an unrelated outcome
    unclear   = cannot be told from the title and abstract
    Judge by the paper's main dependent variable. A variable that the abstract mentions only as a mechanism, channel
    or intermediate step is not the paper's outcome (in that example: a paper on income inequality that discusses saving
    as a channel has outcome "different" or "similar", not "same")
uses_data: does the paper analyse data empirically?
    yes = an empirical analysis using data; no = a review, a theoretical model or a commentary; unclear = cannot be told
study_area: the country or region the paper studies, as stated in the title or abstract (e.g. "China", "United States",
    "OECD countries"); write "not stated" if the title and abstract do not say. This is shown to the user only and is not
    part of the relevance judgement, so judge policy_match and outcome_match without considering the country

Rules:
1. Judge from the title and abstract only; do not guess what data the paper used
2. Judge each question separately. A paper that studies the same policy but a different outcome is policy "same", outcome "different"
3. If the abstract is missing, judge from the title only and write "no abstract" in the reason
4. Write the reason as one short English sentence
5. Give a result for every paper and copy the id exactly
6. Output JSON only"""

# 【2026-11-05 冻结】相关度评分（下表、relevance_score、SCREEN_PROMPT 的三个问题）已冻结，不再增加维度或特殊规则。
# 研究地区（study_area）只显示，不参与计分。要改动请先在 DEVLOG 写明理由，并用两个以上主题重新验证。
# 相关度由程序按下表计算，不由 AI 直接给分（AI 只回答上面三个具体问题）。
# 行：政策是否相同；列：结果变量是否相同。“unclear” 按 “similar” 计分（看不出来时取中间）。
# 例：同一政策、相近的结果变量（如就业结构 vs 就业规模）→ 2；相近但不同的政策、相同的结果变量 → 2
RELEVANCE_TABLE = {
    "same":      {"same": 3, "similar": 2, "different": 2},
    "similar":   {"same": 2, "similar": 1, "different": 1},
    "different": {"same": 1, "similar": 0, "different": 0},
}
NO_DATA_CAP = 1   # 综述、理论模型等不分析数据的论文，最多 1 分（对了解“前人用了什么数据”帮助不大）


def relevance_score(policy: str, outcome: str, uses_data: str) -> int:
    """根据 AI 的三个回答计算相关度 0–3。AI 返回了不认识的值时按 “different” 处理（宁可漏，不把不相关的当成相关）。"""
    def level(x):
        if x == "unclear":
            return "similar"
        return x if x in RELEVANCE_TABLE else "different"
    score = RELEVANCE_TABLE[level(policy)][level(outcome)]
    return min(score, NO_DATA_CAP) if uses_data == "no" else score


MODELS_USED = []   # 本次检索中每次调用实际成功的模型，写进结果，方便判断结果是否来自备用模型


def gemini_json(system: str, content: str, schema: dict) -> dict:
    """调用 Gemini 并返回 JSON（重试、换备用模型的做法在 gemini_client 里，和 step2 共用），记下实际使用的模型。"""
    data, model = gemini_client.generate_json(system, content, schema, fast_fallback=True)   # 検索は待たずに予備モデルへ
    MODELS_USED.append(model)
    return data


def plan_search(topic: str) -> dict:
    """把研究方向拆成“政策”和“结果变量”，并生成检索词。返回 {policy, outcome, queries}。
    拆出的两项会显示给用户，并在筛选时作为每篇论文比较的同一个标准。"""
    result = gemini_json(QUERY_PROMPT, f"Research direction: {topic}", QUERY_SCHEMA)
    queries = [q.strip() for q in result.get("queries", []) if q and q.strip()]
    return {"policy": (result.get("policy") or "").strip() or topic,
            "outcome": (result.get("outcome") or "").strip() or topic,
            "queries": queries[:3] or [topic]}


def screen(topic: str, focus: dict, works: list[dict]) -> dict[str, dict]:
    """让 Gemini 对每篇论文回答三个问题，再由程序算出相关度。
    返回 {id: {relevance, policy_match, outcome_match, uses_data, reason}}。
    AI 漏掉的论文记为相关度 0，并注明，不会被悄悄当成相关。"""
    items = []
    for w in works:
        abstract = w["abstract"] or "(no abstract)"
        items.append(f"id: {w['id']}\ntitle: {w['title']}\nabstract: {abstract[:1500]}")
    content = (f"Research direction: {topic}\nPolicy: {focus['policy']}\nOutcome: {focus['outcome']}\n\n"
               + "\n\n---\n\n".join(items))
    result = gemini_json(SCREEN_PROMPT, content, SCREEN_SCHEMA)
    known = {w["id"] for w in works}
    scores = {}
    for p in result.get("papers", []):
        if p.get("id") in known:
            pm, om, ud = p.get("policy_match"), p.get("outcome_match"), p.get("uses_data")
            # study_area 只显示，不参与计分：论文研究哪个国家，不等于它用的数据覆盖哪里，读全文后才能确认
            scores[p["id"]] = {"relevance": relevance_score(pm, om, ud), "policy_match": pm,
                               "outcome_match": om, "uses_data": ud,
                               "study_area": (p.get("study_area") or "").strip() or "not stated",
                               "reason": p.get("reason", "")}
    for wid in known - scores.keys():
        scores[wid] = {"relevance": 0, "policy_match": None, "outcome_match": None, "uses_data": None,
                       "study_area": None, "reason": "no judgement returned by the AI"}
    return scores


# ============ 2. OpenAlex ============

def openalex_search(query: str, per_page: int = PER_QUERY) -> list[dict]:
    import requests
    params = {
        "search": query,
        "per_page": per_page,
        # 不加 has_abstract:true：OpenAlex 里很多收费期刊论文没有摘要，加了会把它们整批排除
        "filter": "type:article|preprint",
        "select": "id,doi,title,publication_year,type,cited_by_count,abstract_inverted_index,"
                  "open_access,best_oa_location,primary_location,authorships",
    }
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        params["api_key"] = key
    else:
        print("  ⚠ OPENALEX_API_KEY is not set; the free quota without a key is only 100 credits a day")
    r = requests.get(OPENALEX_URL, params=params, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"OpenAlex returned error {r.status_code}: {r.text[:300]}")
    return [normalize_work(w) for w in r.json().get("results", [])]


def rebuild_abstract(inverted: dict | None) -> str | None:
    """OpenAlex 的摘要以“词 → 位置列表”的倒排形式给出，这里还原成正常文字。"""
    if not inverted:
        return None
    positions = {}
    for word, places in inverted.items():
        for p in places:
            positions[p] = word
    return " ".join(positions[i] for i in sorted(positions))


NO_TITLE = "(no title)"


def normalize_work(w: dict) -> dict:
    """把 OpenAlex 的原始记录整理成我们需要的字段。"""
    best = w.get("best_oa_location") or {}
    primary = w.get("primary_location") or {}
    oa = w.get("open_access") or {}
    venue = (primary.get("source") or {}).get("display_name")
    authors = [a.get("author", {}).get("display_name") for a in (w.get("authorships") or [])]
    return {
        "id": (w.get("id") or "").rsplit("/", 1)[-1],
        "title": w.get("title") or NO_TITLE,
        "year": w.get("publication_year"),
        "authors": [a for a in authors if a][:3],
        "venue": venue,
        "doi": w.get("doi"),
        "cited_by": w.get("cited_by_count") or 0,
        "abstract": rebuild_abstract(w.get("abstract_inverted_index")),
        "is_oa": bool(oa.get("is_oa")),
        "pdf_url": best.get("pdf_url"),
        "landing_url": best.get("landing_page_url") or primary.get("landing_page_url"),
        "oa_version": best.get("version"),
    }


# ============ 3. 程序：去重、排序、选候选 ============

def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def dedupe(works: list[dict]) -> list[dict]:
    """同一篇论文可能被多组检索词找到，也可能同时有工作论文版和期刊版（不同 id、相同标题）。
    按 id 和标题去重；同标题时保留有 PDF 的那条。"""
    by_title = {}
    for w in works:
        # 没有标题（或标题去掉符号后为空）时只能按 id 区分，否则所有无标题论文会被合并成一篇
        k = title_key(w["title"]) if w["title"] != NO_TITLE else ""
        k = k or f"id:{w['id']}"
        old = by_title.get(k)
        if old is None or (not old["pdf_url"] and w["pdf_url"]):
            by_title[k] = w
    return list(by_title.values())


def access_status(w: dict) -> str:
    if w["pdf_url"]:
        return "pdf"          # 可下载全文
    if w["is_oa"]:
        return "oa_page"      # 开放获取，但 OpenAlex 没给 PDF 地址，需要打开页面确认
    return "upload"           # 待上传


ACCESS_LABELS = {
    "pdf": "full text downloadable",
    "oa_page": "open access, but the full text has to be found on the landing page",
    "upload": "not freely available - please download it with your institution's access and upload it",
}


def score_rows(works: list[dict], scores: dict[str, dict]) -> list[dict]:
    """把每篇论文的相关度和全文状态合在一起，全部保存（包括没进候选的），方便事后检查筛选是否合理。"""
    rows = []
    for w in works:
        s = scores.get(w["id"], {"relevance": 0, "reason": "not scored"})
        rows.append({**w, **s, "access": access_status(w)})
    return rows


def select_candidates(rows: list[dict], n_auto: int = N_AUTO, n_upload: int = N_UPLOAD) -> tuple[list[dict], list[dict]]:
    """相关性为主、可获取性为辅，分成两组：
    - 自动调查：能读到全文的论文（可下载 > 开放获取页面），按相关度、被引次数取前 n_auto 篇
    - 建议上传：读不到全文的论文，按相关度、被引次数取前 n_upload 篇，由用户决定要不要上传
    两组分开选，所以读不到全文的高相关论文不会被能下载的论文挤掉。
    相关度低于 MIN_RELEVANCE 的论文两组都不进——宁可少，不拿不相关的论文凑数。"""
    order = {"pdf": 0, "oa_page": 1}
    relevant = [r for r in rows if r["relevance"] >= MIN_RELEVANCE]
    readable = [r for r in relevant if r["access"] != "upload"]
    readable.sort(key=lambda r: (-r["relevance"], order[r["access"]], -r["cited_by"]))
    unreadable = [r for r in relevant if r["access"] == "upload"]
    unreadable.sort(key=lambda r: (-r["relevance"], -r["cited_by"]))
    return readable[:n_auto], unreadable[:n_upload]


# ============ 4. 主流程 ============

def search(topic: str) -> dict:
    import time
    MODELS_USED.clear()
    t0 = time.perf_counter()
    plan = plan_search(topic)
    t1 = time.perf_counter()
    queries = plan["queries"]
    print(f"Policy: {plan['policy']}  |  Outcome: {plan['outcome']}")
    print(f"Queries: {queries}")
    found = []
    for q in queries:
        hits = openalex_search(q)
        print(f'  "{q}" -> {len(hits)} papers')
        found.extend(hits)
    works = dedupe(found)
    t2 = time.perf_counter()
    print(f"{len(works)} papers after de-duplication; asking the AI to judge relevance...")
    scores = screen(topic, plan, works)
    t3 = time.perf_counter()
    # 各段階の所要時間（2026-11-18：どこが遅いかを実測するため。判定には影響しない）
    print(f"Timing: planning {t1 - t0:.0f}s | OpenAlex {t2 - t1:.0f}s | relevance judging {t3 - t2:.0f}s ({len(works)} papers)")
    rows = score_rows(works, scores)
    auto, upload = select_candidates(rows)
    return {"topic": topic, "policy": plan["policy"], "outcome": plan["outcome"], "queries": queries,
            "models_used": list(MODELS_USED),
            "n_found": len(works), "auto": auto, "upload": upload, "all": rows}


def paper_lines(i: int, c: dict) -> list[str]:
    authors = ", ".join(c["authors"]) + (" et al." if len(c["authors"]) == 3 else "")
    lines = [f"\n{i}. {c['title']} ({c['year']})",
             f"   {authors}" + (f"  |  {c['venue']}" if c["venue"] else ""),
             f"   Relevance {c['relevance']} (policy: {c['policy_match']}, outcome: {c['outcome_match']}, "
             f"empirical: {c['uses_data']})  |  cited by {c['cited_by']}",
             f"   {c['reason']}",
             f"   Study area (from title/abstract, not used in scoring): {c.get('study_area') or 'not stated'}"]
    status = ACCESS_LABELS[c["access"]]
    if c["access"] == "pdf":
        status += f" ({VERSION_LABELS.get(c['oa_version'], VERSION_LABELS[None])})"
    lines.append(f"   Full text: {status}")
    link = c["pdf_url"] or c["landing_url"] or c["doi"]
    if link:
        lines.append(f"   {link}")
    return lines


def print_candidates(result: dict) -> None:
    models = sorted(set(result["models_used"]))
    print(f"\n(Model used: {', '.join(models) or 'unknown'})")
    print(f"Research direction -> policy: {result['policy']}  |  outcome: {result['outcome']}")
    print(f"\n=== Papers to investigate automatically ({len(result['auto'])}) ===")
    if not result["auto"]:
        print("No sufficiently relevant paper with a freely readable full text was found.")
    for i, c in enumerate(result["auto"], start=1):
        print("\n".join(paper_lines(i, c)))
    print(f"\n=== Relevant papers you may want to upload ({len(result['upload'])}) ===")
    if not result["upload"]:
        print("(none)")
    else:
        print("These papers are not freely available. If you can download them with your institution's access,")
        print("upload them and they will be investigated in the same way.")
    for i, c in enumerate(result["upload"], start=1):
        print("\n".join(paper_lines(i, c)))
    print("\nRelevance is computed by the program from the AI's three judgements (policy, outcome, empirical):")
    print("same policy + same outcome = 3; one same and the other similar or different, or similar policy + same outcome = 2.")
    print("The study area is shown for reference only: the data a paper actually covers is confirmed only from its full text.")
    print("\nNote: relevance is judged from titles and abstracts only. What data a paper actually used")
    print('can only be confirmed after reading its full text. "Full text downloadable" is based on OpenAlex')
    print("metadata and is confirmed only when the PDF is actually downloaded.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python search_papers.py "research direction (in English)"')
        raise SystemExit(1)
    topic = " ".join(sys.argv[1:])
    result = search(topic)
    print_candidates(result)
    os.makedirs("candidates", exist_ok=True)
    out = os.path.join("candidates", datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {out}")
