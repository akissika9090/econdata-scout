"""
第三步：合并多篇论文的证据。

同一个数据（例如城镇住户调查 UHS）常被多篇论文使用。一篇没写获取条件，另一篇可能写了；
各篇用的年份也不同。把它们放在一起，才能回答“这个数据前人是怎么拿到的、用过哪些年份”。

用法：
    python step3_merge.py                       合并 results/ 中每篇论文最新的一次结果
    python step3_merge.py --papers deng2020 yu2019
    python step3_merge.py --out report.md       另存为 Markdown 报告
    python step3_merge.py --results-dir results_v2 --official --out report_v2.md
                                                V2：对每个数据源查官网（DeepSeek），报告加“论文｜官网”两栏对照；结果存到 official_checks/
    python step3_merge.py --results-dir results_v2 --official-from official_checks/<文件>.json --out report_v2.md
                                                重用已保存的官网核查结果，不调用 API

不加 --official 时不调用 API：读取已保存的 AI 原始回答，用当前版本的规则重新核对后再合并。
"""

import argparse
import glob
import json
import os
import re
from collections import defaultdict

import step1_pdf_evidence as step1
import step2_ai_extract as step2

LABELS = step2.ACCESS_LABELS
# 数据库提示中这些类型的名字足够具体，可以直接当作“同一个数据”的依据；
# “政府部门发布”“统计年鉴”太笼统（国家统计局发布的数据有很多种），需要另外处理。
# 与 step2 拆分联合来源用的是同一份定义，直接引用，避免两处不一致
SPECIFIC_HINT_TYPES = step2.SPECIFIC_HINT_TYPES
# 调查系列（如 CPS）：同一系列的不同部分（ASEC、ORG、月度基本调查）合并为一组，
# 但每篇论文的每个部分各占一行，保留原始名称、年份和证据，不当作完全相同的数据版本
SERIES_HINT_TYPES = {"gov_public_micro"}
# 年鉴名称：“China City Statistical Yearbook”“City Statistical Yearbooks”“China's Electric Power Yearbooks” 等
YEARBOOK_NAME = re.compile(r"(?:China(?:'s)?\s+)?((?:[A-Z][\w-]*\s+){0,3}?(?:Statistical\s+)?Yearbooks?)")


# results/ 中结果文件的命名：论文名_日期_时间_run次数.json
#   新格式：deng2020_20261105_093521_run1.json（日期带年份）
#   旧格式：deng2020_1105_093521_run1.json（只有月日，2026-11-05 之前保存的文件）
RESULT_NAME = re.compile(r"(?P<paper>.+?)_(?P<date>\d{8}|\d{4})_(?P<time>\d{6})_run(?P<run>\d+)\.json$")


def parse_result_name(path: str) -> dict | None:
    """解析结果文件名，返回 {paper, stamp}；不符合命名格式时返回 None（调用方跳过并提示，而不是报错退出）。
    stamp 用来比较新旧：旧格式没有年份，一律视为早于新格式（旧格式文件都是改格式之前保存的）。"""
    m = RESULT_NAME.match(os.path.basename(path))
    if not m:
        return None
    date = m["date"] if len(m["date"]) == 8 else "0000" + m["date"]
    return {"paper": m["paper"], "stamp": (date, m["time"], int(m["run"]))}


def latest_results(papers: list[str] | None, results_dir: str = "results") -> dict[str, str]:
    """每篇论文取 results/（或 results_dir）中最新的一次结果文件。不符合命名格式的文件跳过并提示。"""
    latest = {}
    for path in sorted(glob.glob(f"{results_dir}/*.json")):
        info = parse_result_name(path)
        if info is None:
            print(f"(skipping a file that does not match the naming pattern: {path})")
            continue
        if papers and info["paper"] not in papers:
            continue
        old = latest.get(info["paper"])
        if old is None or info["stamp"] > old[0]:
            latest[info["paper"]] = (info["stamp"], path)
    return {paper: path for paper, (_, path) in latest.items()}


def canonical_key(src: dict) -> tuple[str, str]:
    """返回 (合并用的键, 显示名)。名字不同但其实是同一个数据的，要得到同一个键。"""
    hint = src.get("db_hint") or {}
    if hint.get("type") in SPECIFIC_HINT_TYPES or hint.get("type") in SERIES_HINT_TYPES:
        return f"{hint['type']}:{hint['name']}", hint["name"]
    if hint.get("type") == "yearbook":
        ev = src.get("source_evidence") or {}
        m = YEARBOOK_NAME.search(f"{src.get('name', '')} {ev.get('quote', '')}")
        if m:
            # 去掉 “China” 前缀和复数，“City Statistical Yearbooks” 与 “China City Statistical Yearbook” 合并
            core = re.sub(r"\s+", " ", m.group(1)).strip()
            core = re.sub(r"(?i)yearbooks$", "Yearbook", core)
            core = re.sub(r"(?i)^(the|our|from|in)\s+", "", core)
            if core.lower() not in ("yearbook", "statistical yearbook"):
                return f"yearbook:{core.lower()}", "China " + core.title().replace(" Of ", " of ")
    name = re.sub(r"\s*\(.*?\)\s*", " ", src.get("name", "")).strip()
    return f"name:{name.lower()}", name


def related_limitations(src: dict, limitations: list[dict]) -> list[dict]:
    """论文中“因数据原因缩小样本”的说法，哪些归给这个数据：只有原文点名了这个数据的才归给它。
    只是“在同一页”不能证明限制属于这个数据——这类说法作为论文级限制单独列出（见 merge_reports），不丢掉。"""
    # 2026-11-06 评审决定：样本限制不再按名称自动归给数据源（名称匹配无法区分机构缩写和数据缩写，
    # 例：Michigan tax panel 的限制会因 IRS 挂到别的 IRS 数据下）。所有样本限制留在论文级，由用户看原文判断
    related = []
    # 获取条件的证据本身也可能是覆盖限制（如 “the data are only available to us for 2002 to 2009”）：
    # 只有这条证据已经确认针对这个数据（verification == verified）时才归给它
    ev = src.get("access_evidence") or {}
    if (src.get("verification") == "verified" and re.search(r"\bonly\b[^.]*\b(19|20)\d{2}\b", ev.get("quote", ""))
            and all(step1.squash(ev["quote"]) != step1.squash(x["quote"]) for x in related)):
        related.append({"quote": ev["quote"], "page": ev["page"]})
    return related


def collapse_by_paper(uses: list[dict], series: bool = False) -> list[dict]:
    """同一篇论文在同一组里出现多次时合并：条件相同、或一方没有条件信息的，只保留证据最强的那条；
    条件不同的（如公开版本和受限版本）都保留，不静默去掉冲突。
    series=True（调查系列）时，同一篇论文中名称不同的部分（如 CPS ASEC 和 CPS ORG）各自处理。"""
    buckets = {}
    for u in uses:
        key = (u["paper"], u["src"].get("name", "").strip().lower()) if series else u["paper"]
        buckets.setdefault(key, []).append(u)
    result = []
    for items in buckets.values():
        kept = []
        for u in sorted(items, key=lambda x: step2.evidence_rank(x["src"]), reverse=True):   # 稳定排序：同分保持原顺序
            if not any(step2.conditions_compatible(k["src"], u["src"]) for k in kept):
                kept.append(u)
        result += kept
    return result


def load_reports(papers: list[str] | None = None, results_dir: str = "results") -> list[tuple[str, dict]]:
    """读取 results/ 中每篇论文最新的一次结果，用当前规则重新核对（开发集、诊断集用）。
    results_dir="results_v2"：V2 提取结果（含版本、渠道等字段）。"""
    reports = []
    for paper, path in latest_results(papers, results_dir).items():
        pages, _ = step1.extract_pages(f"papers/{paper}.pdf")
        with open(path, encoding="utf-8") as f:
            reports.append((paper, step2.verify_result(pages, json.load(f)["ai_raw"])))
    return reports


def merge(papers: list[str] | None = None) -> list[dict]:
    return merge_reports(load_reports(papers))


def paper_limitations(reports: list[tuple[str, dict]], merged: list[dict], only_shared: bool = False) -> list[tuple[str, dict]]:
    """论文级的样本限制：报告中没有显示在任何数据源下面的限制，按论文单独保留。
    按**最终显示**的记录来判断（合并去重之后、only_shared 筛选之后）：一条限制只关联到一条被去重删掉的记录时，
    它不会显示在数据源下面，所以放到论文级——不转给保留下来的其他记录。
    和数据源分开收集，所以一篇论文即使一个数据源都没有，它的限制也不会消失。"""
    shown = {(u["paper"], step1.squash(lim["quote"]))
             for m in merged if not (only_shared and m["n_papers"] < 2)
             for u in m["uses"] for lim in u["limitations"]}
    return [(paper, lim) for paper, report in reports for lim in report.get("sample_limitations", [])
            if (paper, step1.squash(lim["quote"])) not in shown]


def other_mentions(reports: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    """各论文中没有算作数据来源的候选（来源引用找不到、笼统说法、可能只是变量），报告中单独列出，不丢掉。"""
    return [(paper, m) for paper, report in reports for m in report.get("other_mentions", [])]


def merge_reports(reports: list[tuple[str, dict]]) -> list[dict]:
    """把已经核对好的报告按数据源合并。reports = [(论文名, step2 核对后的报告), ...]。
    返回按数据源合并后的列表，每项包含使用它的各篇论文及其证据。
    merge()（读 results/）和 scout.py（这次运行刚提取的论文）都用这个函数，合并规则只有一份。"""
    groups = defaultdict(lambda: {"display": None, "uses": []})
    for paper, report in reports:
        limitations = report.get("sample_limitations", [])
        for src in report["data_sources"]:
            key, display = canonical_key(src)
            g = groups[key]
            g["display"] = g["display"] or display
            g["uses"].append({"paper": paper, "src": src, "limitations": related_limitations(src, limitations)})
    merged = []
    for key, g in groups.items():
        uses = collapse_by_paper(g["uses"], series=key.split(":")[0] in SERIES_HINT_TYPES)
        papers = lambda us: len({u["paper"] for u in us})   # 按论文计数（调查系列中一篇论文可能有几行）
        hint = next((u["src"]["db_hint"] for u in uses if u["src"].get("db_hint")), None)
        urls = []   # 网址是获取渠道，单独显示在各篇论文下面，不进入获取条件的结论
        # 只有“直接证据”才算这个数据的获取条件；“论文总体声明”“无法确认”是较弱的证据，单独计数
        # 已验证：引用存在、支持该分类、针对这个数据。未通过验证的 AI 初步判断单独计数，作为待核对的风险信号
        direct = [u for u in uses if u["src"].get("verification") == "verified"]
        weak = [u for u in uses if u["src"].get("ai_category", "unknown") != "unknown"
                and u["src"].get("verification") not in ("verified", "none", None)]
        direct_cats = {u["src"]["access_category"] for u in direct}
        # 条件 = (分类, 适用范围)。范围不同的分别列出：不把某一部分（如 public use 版本）的条件概括成整个数据源的条件
        conds = {}
        for u in direct:
            conds.setdefault((u["src"]["access_category"], step2.scope_key(u["src"].get("access_scope"))), u["src"])
        if len(conds) > 1:
            verdict = ("conditions differ between records, listed separately: " + ", ".join(cond_label(c, x.get("access_scope"))
                                                                                          for (c, _), x in sorted(conds.items())),
                       "may be different parts, periods or versions of the data; check each")
        elif direct_cats:
            cat = next(iter(direct_cats))
            text, basis = step2.conclusion(cat, hint, urls, n_evidence=papers(direct), scope="direct")
            only = next(iter(conds.values()))
            if only.get("access_scope") == "not_recorded":
                verdict = (cond_label(cat, "not_recorded"), NOT_RECORDED_BASIS + origin_text(direct))
            else:
                verdict = (text + scope_text(only.get("access_scope")), basis + origin_text(direct))
        elif weak:
            first = weak[0]["src"]
            verdict = step2.conclusion("unknown", hint, urls, ai_category=first["ai_category"],
                                       verification=first["verification"])
        else:
            text, basis = step2.conclusion("unknown", hint, urls)
            reasons = sorted({r for u in uses if (r := step2.unknown_reason(u["src"]))})
            if set(reasons) - {"no statement found"}:
                # 原文有线索或引用无法核对：不是“论文中未说明”
                basis = basis.replace("not stated in the paper", "no verified statement of conditions in the paper")
            verdict = (text, basis + (" — " + ", ".join(reasons) if reasons else ""))
        parts = []
        for c in ["public", "subscription", "restricted"]:
            nr = lambda u: u["src"].get("access_scope") == "not_recorded"
            n_d = papers([u for u in direct if u["src"]["access_category"] == c and not nr(u)])
            n_nr = papers([u for u in direct if u["src"]["access_category"] == c and nr(u)])
            n_w = papers([u for u in weak if u["src"]["ai_category"] == c])
            if n_d or n_w:
                parts.append(f"{LABELS[c]}: {n_d} {papers_word(n_d)} verified"
                             + (f", {n_w} {papers_word(n_w)} with only an initial AI judgment (not verified)" if n_w else ""))
            if n_nr:
                parts.append(f"original record category {LABELS[c]}, scope not recorded: {n_nr} {papers_word(n_nr)} (source text verified)")
        no_clue = all(step2.unknown_reason(u["src"]) in (None, "no statement found") for u in uses)
        evidence = "; ".join(parts) if parts else ("no paper states an access condition" if no_clue
                                                   else "no verified access condition (see the source-text clues under each paper below)")
        merged.append({"key": key, "display": g["display"], "uses": uses, "verdict": verdict,
                       "evidence": evidence, "hint": hint, "n_papers": papers(uses)})
    # 被多篇论文使用的排在前面
    merged.sort(key=lambda m: (-m["n_papers"], m["display"].lower()))
    return merged


def scope_text(scope: str | None) -> str:
    """结论旁边的适用范围说明：整个数据源不加说明；具体部分写出来；范围未确定 / 未记录也写出来。"""
    if scope == "whole":
        return ""
    if scope == "not_recorded":
        return " (scope not recorded)"
    return " (scope undetermined)" if scope in (None, "undetermined") else f" (applies to: {scope})"


def cond_label(category: str, scope: str | None) -> str:
    """一条已验证条件的标签。适用范围未记录（旧结果）时不写成这个数据的结论，只写“原记录分类”。"""
    if scope == "not_recorded":
        return f"original record category: {LABELS[category]}; scope not recorded"
    return LABELS[category] + scope_text(scope)


NOT_RECORDED_BASIS = ("source text of the paper; the earlier extraction did not record whether the condition applies to "
                      "the whole data or to a version or file — judge from the source text")


def papers_word(n: int) -> str:
    return "paper" if n == 1 else "papers"


def origin_text(uses_or_srcs: list) -> str:
    srcs = [u["src"] if "src" in u else u for u in uses_or_srcs]
    notes = []
    if any(x.get("access_origin") == "agent" for x in srcs):
        notes.append("found by Agent re-check")
    return "; " + "; ".join(notes) if notes else ""


def year_ranges(years) -> str:
    """把年份集合写成 “1977、1985–1997” 这样的形式。"""
    ys, out = sorted(years), []
    i = 0
    while i < len(ys):
        j = i
        while j + 1 < len(ys) and ys[j + 1] == ys[j] + 1:
            j += 1
        out.append(str(ys[i]) if i == j else f"{ys[i]}–{ys[j]}")
        i = j + 1
    return "、".join(out)


FORM_LABELS = {"single": "single year", "discrete": "discrete years", "range": "continuous range", "unclear": "form unclear"}


def format_report(merged: list[dict], only_shared: bool = False,
                  paper_limitations: list[tuple[str, dict]] | None = None,
                  other_mentions: list[tuple[str, dict]] | None = None,
                  referenced: list[tuple[str, dict]] | None = None, usage_pending: list[tuple[str, dict]] | None = None,
                  papers_without_sources: list[str] | None = None, official: dict | None = None) -> str:
    """paper_limitations：论文级限制（见 paper_limitations()）；other_mentions：排除 / 待核查的候选（见 other_mentions()）；
    referenced / usage_pending：引用或介绍的数据、使用关系待确认的数据。都单独传入，不依赖数据源是否存在。
    一般用 report_markdown(reports) 一次生成，不必分别准备这些参数。"""
    lines = ["# Data source summary (merged across papers)", "",
             "- **Access**: whether you can obtain this data. Direct evidence in the paper takes precedence; if the paper only "
             "makes a general statement, the conclusion is weakened; if the paper says nothing, the tool's built-in database "
             "list is used and named as the basis.",
             "- **Historical use record**: sample years used by prior papers and statements that \"the sample was narrowed for "
             "data reasons\". This is a historical record only; the tool does not judge whether these years meet your research "
             "needs, and it does not represent the years, regions, or variables the database covers today. Please check these yourself.",
             "- **Model judgments**: the usage relation (used in this paper / cites others / background), which data a period "
             "belongs to, and which part a condition applies to are all model judgments. The program only checks that quotes "
             "exist verbatim, are single sentences, name the data, and have a consistent year structure; it does not prove "
             "that these semantic judgments are correct."]
    if official is not None:
        lines.append(OFFICIAL_INTRO)
    lines.append("")
    for m in merged:
        if only_shared and m["n_papers"] < 2:
            continue
        lines.append(f"## {m['display']}　(used by {m['n_papers']} {papers_word(m['n_papers'])})")
        if official is not None:
            lines += comparison_block(m, official.get(m["key"]))
        text, basis = m["verdict"]
        lines.append(f"- **Access: {text}** (basis: {basis})")
        lines.append(f"  - Paper evidence: {m['evidence']}")
        shown_q = []
        for u in m["uses"]:
            ev = u["src"].get("access_evidence") or {}
            if u["src"].get("access_scope") == "not_recorded" and ev.get("verified") and ev["quote"] not in shown_q:
                shown_q.append(ev["quote"])
                lines.append(f"  - Source text ({u['paper']} p. {ev['page']}): “{ev['quote']}”")
        if m["hint"]:
            lines.append(f"  - {m['hint']['icon']} Database hint: {m['hint']['message']}")
        # 未核实的期间（期间证据核对不通过，或可能是年鉴出版年份）照常显示并标注，但不计入“最晚用到”
        periods = [(u["paper"], u["src"]) for u in m["uses"] if u["src"].get("sample_period")]
        lims = [(u["paper"], lim) for u in m["uses"] for lim in u["limitations"]]
        lines.append("- **Historical use record:** " + (
            f"{len(lims)} {'statement' if len(lims) == 1 else 'statements'} about narrowing the sample for data reasons" if lims
            else "the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are "
                 "complete; check the variables, years, and regions you need)"))
        spans = [(paper, ys) for paper, x in periods if (ys := step2.period_year_set(x))]
        if periods:
            line = "  - Sample years used by prior papers (that the period belongs to this data is a model judgment): "
            if spans:
                latest = max((max(ys), paper) for paper, ys in spans)
                line += f"latest year used {latest[0]} ({latest[1]})"
            lines.append(line)
            for paper, x in periods:
                lines.append("    - " + period_line(paper, x))
        for paper, lim in lims:
            lines.append(f"  - ⚠ {paper} p. {lim['page']}: “{lim['quote']}”")
        lines.append("- Per paper:")
        for u in m["uses"]:
            s = u["src"]
            lines.append("  - " + source_line(u["paper"], u["src"]))
        lines.append("")
    if papers_without_sources:
        lines += ["## Papers with no data used in this paper",
                  "The following papers have no data source that the model judged as \"used in this paper\" with a verified "
                  "basis (cited, background, or pending entries are listed below).", ""]
        lines += [f"- {paper}" for paper in papers_without_sources]
        lines.append("")
    if referenced:
        lines += ["## Data cited or described",
                  "The usage relation is a model judgment: these records were judged to cite others' research or to be "
                  "background, and they are excluded from the \"used in this paper\" count and from the year record. If the "
                  "same paper also has a \"used in this paper\" record for the same data, both are kept.", ""]
        for paper, x in referenced:
            lines.append(f"- {paper}: {x.get('name')} — usage relation (model judgment): {USAGE_LABELS.get(x.get('usage'), x.get('usage'))}"
                         + evidence_text(x.get("usage_evidence")))
            if x.get("sample_period"):
                lines.append(f"  - Years in the citation, {x['sample_period']}, are not this paper's sample period")
        lines.append("")
    if usage_pending:
        lines += ["## Usage relation to be confirmed",
                  "The usage relation of the following records cannot be confirmed (the model judged it undeterminable, or its "
                  "basis cannot be found in the source text). They are excluded from the \"used in this paper\" count and from "
                  "the year record.", ""]
        for paper, x in usage_pending:
            why = ("the model judged it undeterminable" if x.get("usage") == "unclear"
                   else "the basis for the usage relation cannot be found in the source text")
            lines.append(f"- {paper}: {x.get('name')} ({why})" + evidence_text(x.get("source_evidence")))
        lines.append("")
    if other_mentions:
        lines += ["## Excluded / candidates to check",
                  "The following entries were not counted as data sources used in the paper, for the reasons given. Source "
                  "text is shown only for quotes verified in the paper.", ""]
        for paper, m in other_mentions:
            se = m.get("source_evidence") or {}
            quote = f" — p. {se['page']}: “{se['quote']}”" if se.get("verified") else ""
            lines.append(f"- {paper}: {m.get('name')} ({step2.MENTION_LABELS.get(m.get('mention_reason'), m.get('mention_reason'))}){quote}")
        lines.append("")
    paper_lims = paper_limitations or []
    if paper_lims:
        lines += ["## Paper-level sample restrictions (attribution unverified)",
                  "The following statements do not name a specific data source, so the program cannot confirm which data "
                  "source they belong to. Please judge from the source text.", ""]
        lines += [f"- {paper} p. {lim['page']}: “{lim['quote']}”" for paper, lim in paper_lims]
        lines.append("")
    if any(not only_shared or m["n_papers"] >= 2 for m in merged):   # 没有显示任何数据源时不列
        lines += CHECKLIST if official is None else CHECKLIST[:-2] + [CHECKLIST_OFFICIAL, ""]
    return "\n".join(lines)


# 报告末尾的待核查事项：对所有数据源都适用，只列一次
CHECKLIST = ["## Items to verify (applies to all data above)",
             "Papers record the data and channels that prior authors used at the time. Before using the data, check each "
             "item with the data provider:",
             "",
             "- Current version, and the latest available data year",
             "- Whether the variables and geographic levels you need are included",
             "- Download or application conditions (eligibility, agreements, fees, approval time)",
             "- Official link and date checked (the tool has not verified any official entry point; URLs in papers may be "
             "outdated or may not be data entry points)",
             ""]


CHECKLIST_OFFICIAL = ("- Official link and date checked: see \"Official site now\" under each source. Only pages the program "
                      "could read and verify are shown as findings; official pages it could not read are listed for you to open")

OFFICIAL_INTRO = ("- **Official site now (V2)**: for each data source, an agent searched the provider's official website for how the "
                  "data can be obtained today. A finding is shown only if the program confirmed that the page is an official "
                  "source and that the quoted sentences appear on it word for word. The channel, eligibility and whether the page "
                  "covers the paper's version are the model's judgments on that quoted text. Official pages the program could not "
                  "read are listed for manual checking and are not counted as findings.")

CHECK_LABELS = {"same_version_found": "the page covers the version the paper used",
                "other_version_only": "only another version / the general route found; the paper's version is not confirmed on this page",
                "discontinued": "the provider states it is no longer provided",
                "version_unconfirmed": "not confirmed: the page does not name the years / volumes the paper used"}
VIA_LABELS = {"paper": "URL in the paper", "learned": "previously verified official domain", "search": "web search",
              "link": "linked from an official page", "model": "proposed by the model",
              "known_channel": "known channel (China Statistical Data Library)"}
NOT_FOUND_LABELS = {"not_found": "no verified official access route found", "budget_exhausted": "no verified official access route "
                    "found within the step budget", "agent_error": "the check could not run (model call failed)",
                    "parse_error": "official-site check failed: the model's answer could not be read",
                    "check_failed": "official-site check failed",
                    "timed_out": "official-site check stopped at the time limit before a verified finding — not checked to the end "
                                 "(does not mean unavailable); rerun later"}
CHECK_FAILED = ("agent_error", "parse_error", "check_failed", "timed_out")   # 核查本身没跑完（含时限内未查完）：不是“没找到”   # 核查本身没跑完：不是“没找到”，要说清楚


def unanswered_leads(res: dict, limit: int = 5) -> list[str]:
    """官网核查没有给出结论时，告诉用户自己查，并列出核查过程中到过的页面作为线索（不是结论）。
    先列模型提交过、但程序没能确认是官方来源的页面（附没通过的原因），再列读过的页面。"""
    leads = {}
    for s in res.get("steps") or []:
        url = (s.get("args") or {}).get("url")
        obs = s.get("observation") or ""
        if s.get("action") == "submit_finding" and url and obs.startswith("Rejected: the access quote does not say how"):
            # v2.5d 获取依据门槛：页面找到了，但交上来的那句原文没写怎么获取 → 给用户的下一步，不显示写给模型的提示
            leads.setdefault(url, "page found, but the quoted sentence does not say how to obtain the data — open it and "
                                  "look for a download or application page for the data the paper used")
        elif s.get("action") == "submit_finding" and url and obs.startswith("Rejected"):
            why = obs.split("—", 1)[-1].strip()
            why = why if len(why) <= 160 else why[:160].rsplit(" ", 1)[0] + " …"
            leads.setdefault(url, "submitted by the check but not confirmed: " + why)
    for url in res.get("read") or {}:
        leads.setdefault(url, "read during the check")
    if not leads:
        return ["  - The check reached no relevant page; search the data name and the provider yourself."]
    out = ["  - Leads from the check (not verified; open them and judge yourself):"]
    out += [f"    - {u} ({why})" for u, why in list(leads.items())[:limit]]
    return out


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def comparison_block(m: dict, entry: dict | None) -> list[str]:
    """V2 两栏对照：论文里怎么写（作者当时用的数据）｜官网现在怎么拿。下面附官网原文、官方依据和说明。"""
    srcs = [u["src"] for u in m["uses"]]
    chans = list(dict.fromkeys(CHANNEL_LABELS[s["access_channel_shown"]] for s in srcs if s.get("access_channel_shown")))
    eligs = list(dict.fromkeys(ELIGIBILITY_LABELS[s["eligibility_shown"]] for s in srcs if s.get("eligibility_shown")))
    restr = list(dict.fromkeys(r for s in srcs for r in s.get("use_restrictions_shown") or []))
    versions = list(dict.fromkeys(f"{u['src']['version']} ({u['paper']}{'' if u['src'].get('version_verified') else ', model wording'})"
                                  for u in m["uses"] if u["src"].get("version")))
    paper = {"channel": "; ".join(chans) or f"no channel stated (access: {m['verdict'][0]})",
             "elig": "; ".join(eligs) or "not stated", "restr": "; ".join(restr) or "none stated",
             "version": "; ".join(versions) or "not stated", "source": "see per-paper evidence below"}
    res = (entry or {}).get("result") or {}
    f = res.get("finding")
    extra = []
    if f:
        chan = CHANNEL_LABELS.get(f["channel"], f["channel"])
        if f.get("review_note"):
            chan += f" ({f['review_note']})"
        for k in f.get("pending") or (["review"] if f.get("review_pending") else []):
            chan += {"review": " — whether review / approval is required is unclear; please check",
                     "payment": " — whether a subscription or purchase is required is unclear; please check",
                     "free_quota": " — the site has a free quota; whether this product is included is unclear; please check",
                     "current": f" as of {f.get('as_of')} (release announcement) — current channel pending; please check",
                     "product": " — for another version or product; the channel for the product the paper used is pending",
                     "version": " — the page does not name the years / version the paper used; whether they are covered is pending"}[k]
        official = {"channel": chan,
                    "elig": ELIGIBILITY_LABELS.get(f["eligibility"], "not stated on the page"),
                    "restr": "; ".join(f.get("restrictions") or []) or "none stated on the page",
                    "version": CHECK_LABELS.get(f["check_result"], f["check_result"]),
                    "source": f"{f['url']} — found via {VIA_LABELS.get(f.get('discovered_via'), f.get('discovered_via'))}"}
        head = (f"Distributor site now (checked {f.get('checked_on')})" if f.get("evidence_source") == "distributor"
                else f"Official site now (checked {f.get('checked_on')})")
        extra.append(f"  - Official-site text (access): “{f['access_quote']}”")
        if f.get("version_quote") and f["version_quote"] != f["access_quote"]:
            extra.append(f"  - Official-site text (version): “{f['version_quote']}”")
        src_label = {"official_page": "the official page itself",
                     "linked_platform": "a platform linked from the official page",
                     "distributor": "a distributor's site — not the original provider and not confirmed as official; "
                                    "check the original provider if you need the authoritative version"}.get(f.get("evidence_source"))
        if src_label:
            extra.append(f"  - Evidence comes from: {src_label}")
        extra.append(f"  - Why this counts as official: {f.get('official_basis')}")
        for n in f.get("notes") or []:
            extra.append(f"  - Note: {n}")
        extra.append("  - Channel, eligibility and version correspondence are model judgments on the quoted official text.")
    elif res.get("outcome") == "manual_check":
        head = "Official site now (not verified)"
        official = {k: "—" for k in paper}
        official["channel"] = "official page found but the program could not read it — please check manually"
        extra += [f"  - Please open: {u}" for u in res.get("leads", {})]
    else:
        head = "Official site now"
        official = {k: "—" for k in paper}
        official["channel"] = NOT_FOUND_LABELS.get(res.get("outcome"), "not checked") if entry else "not checked"
        why = res.get("error") or res.get("stopped_by")   # 时限内未查完：写出在做什么时到的时限
        if entry and res.get("outcome") in CHECK_FAILED and why:
            official["channel"] += f" ({why[:120]})"
        if entry:
            official["channel"] += " — please check this yourself"
            extra += unanswered_leads(res)
    rows = [("Access channel", "channel"), ("Eligibility", "elig"), ("Use restrictions", "restr"),
            ("Version", "version"), ("Source", "source")]
    table = ["", f"| | In the papers (what prior authors used) | {head} |", "|---|---|---|"]
    table += [f"| {label} | {_cell(paper[k])} | {_cell(official[k])} |" for label, k in rows]
    return table + [""] + extra + ([""] if extra else [])


USAGE_LABELS = {"analyzed": "used in this paper", "cited": "cites others' research", "described": "background, introduction or comparison",
                "unclear": "cannot determine"}


def evidence_text(ev: dict | None) -> str:
    """只有在原文中核对通过的引用才显示原文和页码。"""
    return f" — p. {ev['page']}: “{ev['quote']}”" if ev and ev.get("verified") else ""


def period_line(paper: str, src: dict) -> str:
    """期间显示：年份、形态、论文、核实状态，以及期间原文和页码。
    核对通过的离散年份按列出的年份显示（如 “1985、1988”），不沿用模型字符串里可能写成的 “1985–1988”。"""
    form = FORM_LABELS.get(src.get("period_form"), "form unknown")
    if src.get("period_form_unverified"):
        status = f", {src.get('period_form_note', 'period form unverified')}, not counted in \"latest year used\""
    elif src.get("period_unverified"):
        status = ", unverified, not counted in \"latest year used\""
    else:
        status = ", period form consistent with the source text"
    shown = src["sample_period"]
    if src.get("period_form") == "discrete" and not src.get("period_unverified") and src.get("period_years"):
        shown = ", ".join(str(y) for y in sorted(set(src["period_years"])))
    if src.get("period_form_inferred") and src.get("period_form"):
        form += ", inferred from how the period is written"
    return f"{shown} ({form}{status}; {paper}){evidence_text(src.get('period_evidence'))}"


def source_line(paper: str, s: dict) -> str:
    """每篇论文的一行：最终分类（未确认时写明是哪一种 unknown）、适用范围、条件来源和证据，
    以及“本文使用”的依据原文（使用关系是模型判断，程序只核对原文存在）。"""
    return _access_line(paper, s) + usage_text(s) + version_text(s) + details_text(s) + provider_text(s) + channel_text(s)


CHANNEL_LABELS = {"public_download": "public download", "registration_download": "free download after registration",
                  "subscription": "subscription", "purchase": "paid purchase", "apply_to_provider": "apply to the data provider",
                  "request_from_author": "request from the author", "special_agreement": "special agreement with the provider"}
ELIGIBILITY_LABELS = {"researchers": "researchers can apply", "individuals": "individuals can apply",
                      "institution_must_apply": "an institution must apply"}


def version_text(s: dict) -> str:
    """V2：论文使用的版本、文件或匹配方式。旧结果没有这个字段时不显示。"""
    v = s.get("version")
    if not v:
        return ""
    ev = s.get("version_evidence") or {}
    if s.get("version_verified"):
        return f"\n    - Version / file used in this paper: {v} (source text located) — p. {ev['page']}: “{ev['quote']}”"
    return f"\n    - Version / file used in this paper (model's wording; not found verbatim in a verified sentence): {v}"


def details_text(s: dict) -> str:
    """V2：论文中获取说明的细分（渠道｜资格｜使用限制）。只在条件已核对通过时出现；渠道和资格是模型对该原文的判断。"""
    parts = []
    if s.get("access_channel_shown"):
        parts.append(CHANNEL_LABELS[s["access_channel_shown"]])
    if s.get("eligibility_shown"):
        parts.append(ELIGIBILITY_LABELS[s["eligibility_shown"]])
    parts += [f"restriction: {r}" for r in s.get("use_restrictions_shown") or []]
    if not parts:
        return ""
    return ("\n    - Access details in the paper (channel and eligibility are model judgments on the verified sentence above; "
            "restrictions are copied verbatim): " + " | ".join(parts))


def provider_text(s: dict) -> str:
    """提供机构单独显示，不算作获取渠道。模型给的写法不一定是原文写法（如 IRS 写成全称），所以附来源句供对照。"""
    prov = s.get("provider")
    if not prov:
        return ""
    se = s.get("source_evidence") or {}
    if not se.get("verified"):
        how = "the source sentence did not pass verification, so it cannot be compared"
    elif prov.lower() in se["quote"].lower():
        how = f"appears verbatim in the source sentence on p. {se['page']}"
    elif se["quote"] == (s.get("usage_evidence") or {}).get("quote"):
        how = "this wording does not appear verbatim in the source sentence; compare with the source text above"
    else:
        how = f"this wording does not appear verbatim in the source sentence; compare with: p. {se['page']}: “{se['quote']}”"
    return f"\n    - Provider (extracted by the model; not an access channel): {prov} ({how})"


def channel_text(s: dict) -> str:
    """论文原文中的链接：从核对通过的原文中机械提取的网址，附原文和页码；不声称它们是获取渠道。
    没有链接时说明“当前提取结果未记录获取渠道”。下载位置、申请方式等文字说明没有结构化提取；条件原文照常显示在上面。"""
    items = []
    for key in ("source_evidence", "access_evidence"):
        ev = s.get(key) or {}
        for url in step2.find_urls({key: ev}):
            if all(url != u for u, _ in items):
                items.append((url, ev))
    if not items:
        return ("\n    - Access channel recorded in the paper: not recorded in the current extraction results "
                "(this does not mean the paper does not describe one)")
    return "".join(f"\n    - Link in the paper's text: {url} (extracted mechanically; not claimed to be an access channel; the tool "
                   f"has not checked whether it is an official entry point or still works) — p. {ev['page']}: “{ev['quote']}”"
                   for url, ev in items)


def usage_text(s: dict) -> str:
    ev = s.get("usage_evidence") or {}
    if not ev.get("verified"):
        return ""
    who = "the source sentence (older results have no usage-relation field)" if s.get("usage_legacy") else "the usage relation is a model judgment"
    return f"\n    - Basis for \"used in this paper\" ({who}; source text located): p. {ev['page']}: “{ev['quote']}”"


def _access_line(paper: str, s: dict) -> str:
    label = (cond_label(s["access_category"], s.get("access_scope")) if s["access_category"] != "unknown"
             else step2.unknown_reason(s))
    line = f"{paper}: [{label}] {s['name']}"
    # 按当前的核对结果展示证据（不看模型最初的判断：Agent 找回证据时 ai_category 仍是原来的“未确认”）
    ev = s.get("access_evidence") or {}
    status = s.get("verification")
    if s["access_category"] != "unknown":
        found_by = {"agent": ", found by Agent re-check"}.get(s.get("access_origin"), "")
        if not found_by and (s.get("agent") or {}).get("outcome") == "recovered":
            found_by = ", found by Agent re-check"
        return line + (f" — p. {ev.get('page')} (verified{found_by}: source text located and checks passed; the condition "
                       f"category is a model judgment): “{ev.get('quote')}”")
    cand = s.get("candidate")
    if s.get("needs_review") and status not in ("none", None) and not cand:
        reason = f"needs manual review: initial AI judgment was {LABELS[s['ai_category']]}, but {step2.VERIFICATION_LABELS.get(status, status)}"
        # 引用在原文中存在才显示原文；找不到的引用不显示，只说明原因
        return line + (f" — p. {ev['page']} ({reason}): “{ev['quote']}”" if ev.get("verified") else f" — {reason}")
    if cand:
        kinds = ", ".join(LABELS[c] for c in cand["categories"])
        scope = "" if cand["scope"] == "undetermined" else f"; the word refers to: {cand['scope']}"
        reason = (f"needs manual review: the {'source sentence' if cand['from'] == 'source_evidence' else 'period sentence'} "
                  f"contains a \"{kinds}\"-type word (not judged by the model; the program cannot confirm that it describes "
                  f"the access condition of this data{scope})")
        return line + f" — p. {cand['evidence']['page']} ({reason}): “{cand['evidence']['quote']}”"
    return line


ROLE_LABELS = {"robustness": "robustness check", "supplementary": "supplementary analysis", "main": "main", "control": "control variables"}


MAIN_INTRO = ("For each paper: the data the authors analysed as their main data (the model's role judgment), with the source "
              "sentence and page checked in the PDF, and where the official-site check got to. Main-data candidates whose evidence "
              "did not pass the checks are listed under **To verify**, with what is missing and where to look. Only data sources "
              "and access routes are checked; details for each data source are in the summary below. Data used only for "
              "control variables are listed separately as auxiliary data; data that also feed the main analysis stay under main "
              "data with a note.")


def official_short(entry: dict | None) -> str:
    """主要数据一览里的一行官网状态（详细内容在下面的两栏对照里）。"""
    if entry is None:
        return ""
    res = entry.get("result") or {}
    f = res.get("finding")
    if f:
        from urllib.parse import urlparse
        host = urlparse(f.get("final_url") or f.get("url") or "").hostname or ""
        text = f"{CHANNEL_LABELS.get(f['channel'], f['channel'])} ({host}"
        text += ", distributor)" if f.get("evidence_source") == "distributor" else ")"
        pend = f.get("pending") or []
        if "product" in pend:
            text += "; the page is for another version or product — pending"
        elif "version" in pend:
            text += "; years / version used by the paper not named on the page — pending"
        if pend and set(pend) - {"product", "version"}:
            text += "; other conditions pending"
        return text
    if res.get("outcome") == "manual_check":
        return "official page found but could not be read — check manually"
    if res.get("outcome") in CHECK_FAILED:
        why = res.get("error") or res.get("stopped_by")
        return f"{NOT_FOUND_LABELS[res['outcome']]}" + (f" ({why[:120]})" if why else "") + " — check this yourself"
    return "no verified access route found — leads in the summary below"


def missing_evidence(src: dict) -> tuple[str, str]:
    """待核对的主要数据候选：缺什么证据、下一步看哪里。只描述程序核对到哪一步没通过，不断言论文怎么写，
    也不推断这条数据是不是本文的主数据。"""
    sev, uev = src.get("source_evidence") or {}, src.get("usage_evidence") or {}
    page = lambda ev: f" (the model pointed to p. {ev['page']})" if isinstance(ev.get("page"), int) else ""
    reason = src.get("mention_reason")
    if reason == "source_unverified":
        return (f"the sentence naming where the data come from was not found in the PDF{page(sev)}",
                "open that page and the data section; check whether the paper names the source of these data")
    if reason == "possible_variable":
        return ("the program found no source wording (such as \"from\", \"provided by\", \"source:\") in the quoted sentence, "
                "so it cannot tell a dataset from a variable or indicator",
                "read the quoted sentence and the table notes; if they name a provider, treat this as a data source")
    if reason == "unspecified":
        return ("the paper uses a general phrase without a specific data name", "check the data section for the specific dataset")
    if src.get("usage") == "unclear":
        return ("the model could not tell whether this paper analyses these data or only mentions them",
                "read the data / empirical section around the quoted sentence")
    return (f"the sentence showing that this paper analyses these data was not found in the PDF{page(uev)}",
            "check that page, the data section and the tables for how the data are used")


def main_data_markdown(reports: list[tuple[str, dict]], official: dict | None = None) -> str:
    """报告开头：按论文列出主要数据（role = main，已进入“本文使用”）和证据不足的主要数据候选（待核对）。
    只调整显示位置，不改变任何核对结果：待核对的候选仍不计入“本文使用”。"""
    lines = ["# Main data by paper", "", MAIN_INTRO, ""]
    for paper, rep in reports:
        used = rep.get("data_sources", [])
        no_role = used and not any("role" in s for s in used)   # 旧提示词没有 role 字段
        main = used if no_role else [s for s in used if s.get("role") == "main"]
        pending = [s for b in ("usage_pending", "other_mentions") for s in rep.get(b, []) if s.get("role") == "main"]
        lines += [f"## {paper}", ""]
        lines.append("**Main data (source text checked)**" + (" — older result without a role field: all data used are listed" if no_role else ""))
        if not main:
            lines.append("- none confirmed" + (" — see To verify" if pending else ""))
        for s in main:
            ev = s.get("source_evidence") or {}
            quote = f" — p. {ev['page']}: “{ev['quote']}”" if ev.get("verified") else ""
            also = " _(also provides control variables)_" if s.get("also_controls") else ""
            lines.append(f"- **{s['name']}**{also}{quote}")
            if official is not None:
                lines.append(f"  - Official site now: {official_short(official.get(canonical_key(s)[0])) or 'not checked'}")
        if pending:
            lines += ["", "**⚠ To verify — main-data candidates with incomplete evidence** (not counted as used; the official-site check was not run for them)"]
            for s in pending:
                miss, nxt = missing_evidence(s)
                ev = s.get("source_evidence") or {}
                quote = f" — p. {ev['page']}: “{ev['quote']}”" if ev.get("verified") else ""
                lines.append(f"- **{s['name']}**{quote}")
                lines.append(f"  - Missing: {miss}")
                lines.append(f"  - Next: {nxt}")
        controls = [s for s in used if s not in main and s.get("role") == "control"]
        if controls:
            # 2026-11-18 本人定：只提供控制变量的数据放进辅助数据，附原文页码
            lines += ["", "**Auxiliary data (control variables only)**"]
            for s in controls:
                ev = s.get("source_evidence") or {}
                quote = f" — p. {ev['page']}: “{ev['quote']}”" if ev.get("verified") else ""
                lines.append(f"- **{s['name']}**{quote}")
        others = [s for s in used if s not in main and s.get("role") != "control"]
        if others:
            # 2026-11-18：按实际用途分组，附原文页码，用户可以自己判断模型的角色划分（以前只列名称）
            lines += ["", "**Other data used** (the model judged these as robustness or supplementary; check the quote if you disagree)"]
            for s in others:
                ev = s.get("source_evidence") or {}
                quote = f" — p. {ev['page']}: “{ev['quote']}”" if ev.get("verified") else ""
                lines.append(f"- [{ROLE_LABELS.get(s.get('role'), 'role not stated')}] **{s['name']}**{quote}")
        lines.append("")
    return "\n".join(lines)


def report_markdown(reports: list[tuple[str, dict]], only_shared: bool = False, official: dict | None = None) -> str:
    """从核对好的报告一次生成完整的 Markdown 报告（合并、论文级限制、其他提及、引用 / 待确认的数据）。
    step3 main 和 scout.py 都用这个函数，报告的组成只有一份。"""
    merged = merge_reports(reports)
    return main_data_markdown(reports, official) + "\n" + format_report(
        merged, only_shared=only_shared,
        paper_limitations=paper_limitations(reports, merged, only_shared=only_shared),
        other_mentions=other_mentions(reports),
        referenced=[(p, x) for p, r in reports for x in r.get("referenced", [])],
        usage_pending=[(p, x) for p, r in reports for x in r.get("usage_pending", [])],
        papers_without_sources=[p for p, r in reports if not r.get("data_sources")], official=official)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--papers", nargs="*", help="merge only these papers")
    parser.add_argument("--shared", action="store_true", help="show only data used by two or more papers")
    parser.add_argument("--out", help="also save the report as a Markdown file")
    parser.add_argument("--results-dir", default="results", help="where the saved extraction results are (results_v2 for V2)")
    parser.add_argument("--official", action="store_true",
                        help="V2: check each data source on the provider's official site (DeepSeek; costs API calls) "
                             "and save the results to official_checks/")
    parser.add_argument("--official-from", help="V2: reuse saved official-check results (a JSON file from --official); no API calls")
    args = parser.parse_args()
    reports = load_reports(args.papers, args.results_dir)
    official = None
    if args.official_from:
        with open(args.official_from, encoding="utf-8") as f:
            official = json.load(f)
    elif args.official:
        import official_check as oc
        from datetime import datetime
        from web_tools import Web
        print("Checking official sites...")
        official = oc.check_merged(merge_reports(reports), Web(), oc.load_learned(), verbose=True)
        os.makedirs("official_checks", exist_ok=True)
        path = f"official_checks/{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(official, f, ensure_ascii=False, indent=1)
        print(f"Official-check results saved to {path} (reuse with --official-from {path})\n")
    text = report_markdown(reports, only_shared=args.shared, official=official)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"\nReport saved to {args.out}")


if __name__ == "__main__":
    main()
