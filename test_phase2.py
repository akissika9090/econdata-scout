"""
第二阶段（使用关系、条件归属、期间形态）的离线验收测试。检查的是最终报告和核对结果，不是只看中间字段。
不联网、不调用 AI：
  - Liebman 1998、Bowen 2011 使用真实 PDF；“旧结果”是保存下来的真实提取结果（旧提示词，没有新字段）；
  - “新结构的模拟输出”是按新 schema 手写的固定内容，假设模型给出了某种判断——它只能检验程序对这种判断的处理，
    不能证明真实模型会这样判断（这要靠之后的 2 次真实提取）。
预期结果写于实现之前（CONTRACT_PHASE2_DRAFT.md 的六项固定验收和预期报告示例）。

运行：
    python test_phase2.py
"""
from test_support import require_materials

require_materials(['runs/20261106_114218/pdfs/W1586548773.pdf', 'runs/20261106_113629/pdfs/W2301419888.pdf', 'runs/20261106_114218/extract/Liebman1998.json', 'runs/20261106_113629/extract/Bowen2011.json'], "test_phase2")


import copy
import json

import step1_pdf_evidence as step1
import step2_ai_extract as step2
import step3_merge as step3

failures = 0


def check(name, ok, detail=""):
    global failures
    print(f"{'✓' if ok else '✗'}  {name}" + ("" if ok else f"\n     相关内容：{str(detail)[:600]}"))
    if not ok:
        failures += 1


residuals = []


def residual(name, still_wrong, fixed):
    """已知的残留错误：不算通过，也不让测试失败；如实打印当前状态，状态变化时能看到。"""
    state = "仍然存在" if still_wrong else ("已不再出现" if fixed else "状态变化，请检查")
    residuals.append((name, state))
    print(f"⚠  残留错误：{name} —— {state}")


def ev(quote, page=1):
    return {"quote": quote, "page": page}


def new_source(name, source_quote, page=1, cat="unknown", access_quote=None, applies=None, usage="analyzed",
               usage_quote=None, period=None, period_quote=None, form=None, years=None):
    """新 schema 的一条记录（所有新字段都给出）。"""
    return {"name": name, "role": "main", "kind": "dataset", "provider": None, "unit": None,
            "sample_period": period, "period_evidence": ev(period_quote, page) if period_quote else None,
            "access_category": cat, "source_evidence": ev(source_quote, page),
            "access_evidence": ev(access_quote, page) if access_quote else None, "access_applies_to": applies,
            "usage": usage, "usage_evidence": ev(usage_quote or source_quote, page), "period_form": form, "period_years": years}


def verify(pages, sources, limitations=(), statement=None):
    raw = {"data_sources": sources, "sample_limitations": [ev(q, p) for q, p in limitations], "availability_statement": statement}
    return step2.verify_result(pages, copy.deepcopy(raw))


def section(text, title):
    """报告中某一节（## 标题到下一个 ## 之前）。"""
    if f"## {title}" not in text:
        return ""
    return text.split(f"## {title}", 1)[1].split("\n## ", 1)[0]


def find(rep, name, key="data_sources"):
    return next((x for x in rep[key] if x["name"] == name), None)


L_PAGES, _ = step1.extract_pages("runs/20261106_114218/pdfs/W1586548773.pdf")
B_PAGES, _ = step1.extract_pages("runs/20261106_113629/pdfs/W2301419888.pdf")
L_RAW = json.load(open("runs/20261106_114218/extract/Liebman1998.json", encoding="utf-8"))["ai_raw"]
B_RAW = json.load(open("runs/20261106_113629/extract/Bowen2011.json", encoding="utf-8"))["ai_raw"]
CPS, SOI, TCMP = "March Current Population Surveys (CPS)", "IRS Statistics of Income public use sample", "IRS Taxpayer Compliance Measurement Program (TCMP)"


def liebman_new(**changes):
    """Liebman 的新结构模拟输出：在真实提取结果上补上新字段（引用、页码不变）。changes: {名称: {字段: 值}}"""
    raw = copy.deepcopy(L_RAW)
    defaults = {CPS: {"period_form": "discrete", "period_years": [1977, 1997]},
                SOI: {"period_form": "single", "period_years": [1992]},
                TCMP: {"usage": "cited", "period_form": "range", "period_years": [1985, 1988]},
                "1988 IRS non-filer study": {"period_form": "single", "period_years": [1988]}}
    for s in raw["data_sources"]:
        s.update({"access_applies_to": None, "usage": "analyzed", "usage_evidence": s["source_evidence"],
                  "period_form": None, "period_years": None})
        s.update(defaults.get(s["name"], {}))
        s.update(changes.get(s["name"], {}))
    return raw


def run(pages, raw):
    return step2.verify_result(pages, copy.deepcopy(raw))


# ======== 验收 4：Liebman 的离散年份保持离散，不生成连续覆盖 ========
print("\n验收 4：Liebman 的离散年份")
old = run(L_PAGES, L_RAW)
cps = find(old, CPS)
check("4a. 旧结果（模型写 1977–1997，原文是 “1977 and 1997”）→ 区间写法不成立，期间形态未核实",
      cps["period_form"] == "range" and cps.get("period_form_unverified") and step2.period_year_set(cps) is None, cps.get("rule_notes"))
text_old = step3.report_markdown([("Liebman1998", old)])
cps_sec = section(text_old, "Current Population Survey")
# 2026-11-06 取消年份覆盖判断：原预期“覆盖比较无法比对”改为“不计入最晚用到”
check("4a. 旧结果的报告：CPS 期间照常显示并标为形态未核实，不计入“最晚用到”（不生成 1977–1997 连续年份）",
      "period form unverified" in cps_sec and "not counted in \"latest year used\"" in cps_sec and "latest year used 1997" not in cps_sec, cps_sec)

new = run(L_PAGES, liebman_new())
cps = find(new, CPS)
check("4b. 新结构：discrete [1977, 1997] → 结构检查通过，覆盖年份只有 {1977, 1997}",
      not cps.get("period_unverified") and step2.period_year_set(cps) == {1977, 1997}, cps.get("rule_notes"))
text_new = step3.report_markdown([("Liebman1998", new)])
cps_sec = section(text_new, "Current Population Survey")
# 2026-11-06：原预期“1978–1996 年列为尚无论文证据”随年份覆盖判断取消；改为检查离散年份按列出的年份显示
check("4b. 报告：显示“离散年份”、期间原文和页码；年份写成 1977、1997，不写成 1977–1997",
      "discrete years" in cps_sec and "p. 14" in cps_sec and "1977, 1997 (" in cps_sec and "1977–1997 (" not in cps_sec, cps_sec)

wrong = run(L_PAGES, liebman_new(**{CPS: {"period_form": "range", "period_years": [1977, 1997]}}))
cps = find(wrong, CPS)
check("4c. 模型把 “1977 and 1997” 判为 range → 期间形态未核实；程序不替模型改判为离散",
      cps.get("period_form_unverified") and cps["period_form"] == "range" and step2.period_year_set(cps) is None, cps.get("rule_notes"))
pages_r = ["Data. We use the March CPS files from 1985 to 1997 for the main analysis. End."]
r = verify(pages_r, [new_source("March CPS", "We use the March CPS files from 1985 to 1997 for the main analysis.",
                                period="1985–1997", period_quote="We use the March CPS files from 1985 to 1997 for the main analysis.",
                                form="range", years=[1985, 1997])])
check("4d. 原文 “from 1985 to 1997” + range → 通过，覆盖 1985–1997 的每一年",
      step2.period_year_set(r["data_sources"][0]) == set(range(1985, 1998)), r["data_sources"][0].get("rule_notes"))
# 2026-11-06：原 4e 检查 coverage_gap 的并集计算；年份覆盖判断已取消，改为检查报告中不再出现覆盖结论
check("4e. 年份覆盖判断已取消：报告中没有“尚无论文证据”“覆盖风险”",
      "no evidence in prior papers" not in text_new and "coverage risk" not in text_new and not hasattr(step3, "coverage_gap"))

# ======== 验收 5：SOI 已有的 public-use 引文进入核对并正确归属 ========
# 2026-11-06 评审决定：程序从来源句找到的条件词语只是线索，不升级为最终分类；
# “SOI 得到正确的明确条件”要由模型在提取请求中判断获取对象和范围，靠之后的真实提取检验（这里只检验程序的处理）
print("\n验收 5：SOI public use sample")
soi = find(old, SOI)
check("5a. 旧结果（模型判 unknown）→ 来源句中的 public use 只作为词面线索，最终分类仍是 unknown（有词面线索，未确认）",
      soi["access_category"] == "unknown" and step2.unknown_reason(soi) == "lexical clue, unconfirmed", soi.get("rule_notes"))
soi_sec = section(text_old, "IRS Statistics of Income")
check("5b. 报告：显示线索、第24页原文和词语涉及的对象 public use sample，不写成已验证",
      "lexical clue, unconfirmed" in soi_sec and "p. 24" in soi_sec and "public use sample" in soi_sec and " (verified" not in soi_sec, soi_sec)
SOI_Q = L_RAW["data_sources"][2]["source_evidence"]["quote"]
mock_soi = liebman_new(**{SOI: {"access_category": "public", "access_evidence": {"quote": SOI_Q, "page": 24},
                                "access_applies_to": "public use sample"}})
rep5 = run(L_PAGES, mock_soi)
soi = find(rep5, SOI)
check("5c. 新结构（模型判 public、适用于 public use sample、引用第24页）→ 已验证，范围为 public use sample",
      soi["access_category"] == "public" and soi["verification"] == "verified" and soi["access_scope"] == "public use sample",
      (soi["access_category"], soi["verification"], soi.get("access_scope")))
text5 = step3.report_markdown([("Liebman1998", rep5)])
soi_sec5 = section(text5, "IRS Statistics of Income")
check("5c. 报告：公开（适用于：public use sample），显示第24页原文", "applies to: public use sample" in soi_sec5 and "p. 24" in soi_sec5, soi_sec5)
check("5d. 所有样本限制留在论文级：Michigan（第26页）不挂在任何数据源下面",
      "Michigan" not in soi_sec and "Michigan" not in section(text_old, "1988 IRS non-filer study")
      and "Michigan" in section(text_old, "Paper-level sample restrictions"), section(text_old, "Paper-level sample restrictions"))

# ======== 验收 3：Bowen 引用 Dell，不算 Bowen 使用的数据 ========
print("\n验收 3：Bowen 引用 Dell")
b_new = copy.deepcopy(B_RAW)
for s in b_new["data_sources"]:
    s.update({"access_applies_to": None, "usage": "cited", "usage_evidence": s["source_evidence"],
              "period_form": "range", "period_years": [1950, 2003]})
rep_b = run(B_PAGES, b_new)
text_b = step3.report_markdown([("Bowen2011", rep_b)])
check("3a. 新结构（模型判 cited）→ 不在本文使用的数据中，进入“引用或介绍的数据”",
      not rep_b["data_sources"] and len(rep_b["referenced"]) == 1, rep_b["data_sources"])
ref = section(text_b, "Data cited or described")
check("3b. 报告：引用一节显示 Dell、使用关系（模型判断）、第7页原文，并说明引文年份不是本文的样本期间",
      "Dell" in ref and "cites others' research" in ref and "p. 7" in ref and "are not this paper's sample period" in ref, ref)
check("3c. 报告：没有 “Dell et al. data（1 篇论文使用）” 这一组，也没有 1950–2003 的覆盖结论",
      "(used by" not in text_b and "latest year used 2003" not in text_b, text_b[:800])
check("3d. 报告：Bowen2011 列在“没有本文使用数据的论文”中", "Bowen2011" in section(text_b, "Papers with no data used in this paper"), text_b[:800])
b_old = run(B_PAGES, B_RAW)
residual("3e. 旧结果 / 模型判 analyzed 时，程序不用关键词改判，Dell 仍算 Bowen 本文使用的数据",
         len(b_old["data_sources"]) == 1, not b_old["data_sources"])
b_bad = copy.deepcopy(b_new)
b_bad["data_sources"][0]["usage"] = "analyzed"
b_bad["data_sources"][0]["usage_evidence"] = ev("We analyze the Dell et al. data in our own regressions.", 7)
rep_bad = run(B_PAGES, b_bad)
check("3f. 模型判 analyzed 但使用依据在原文中找不到 → 使用关系待确认，不算本文使用",
      not rep_bad["data_sources"] and len(rep_bad["usage_pending"]) == 1, rep_bad["usage_pending"])
check("3f. 报告中有“使用关系待确认”一节", "Dell" in section(step3.report_markdown([("Bowen2011", rep_bad)]), "Usage relation to be confirmed"))

# ======== 验收 1：Wind 不继承只属于 CSMAR 的条件 ========
print("\n验收 1：Wind 不继承 CSMAR 的条件")
S1 = "Firm data are drawn from the CSMAR and WIND databases."
A1 = "CSMAR is a commercial database that requires a paid subscription."
pages1 = [f"Data. {S1} {A1} End."]
r1 = verify(pages1, [new_source("CSMAR and WIND databases", S1, cat="subscription", access_quote=A1, applies="whole")])
csmar, wind = (next(x for x in r1["data_sources"] if n in x["name"]) for n in ("CSMAR", "Wind"))
check("1a. 新结构的联合来源拆分后：CSMAR 订阅已验证；Wind 不继承，最终未确认（归属不明）",
      csmar["access_category"] == "subscription" and wind["access_category"] == "unknown"
      and step2.unknown_reason(wind) == "attribution unclear", [(x["name"], x["access_category"], x["verification"]) for x in r1["data_sources"]])
S1b = "Firm data are drawn from the CSMAR and WIND databases; CSMAR requires a paid subscription."
r1b = verify([f"Data. {S1b} End."], [new_source("Wind database", S1b), new_source("CSMAR database", S1b)])
wind = next(x for x in r1b["data_sources"] if "Wind" in x["name"] or "WIND" in x["name"])
check("1b. 来源句里 CSMAR 的订阅说法不让 Wind 得到分类：Wind 最终未确认（只记为词面线索）",
      wind["access_category"] == "unknown" and wind["verification"] != "verified", (wind["access_category"], wind.get("candidate")))

# ======== 验收 2：去重不把未核实年份升级为覆盖依据 ========
print("\n验收 2：去重与期间")
S2a = "Subsidy data come from the CSMAR database."
S2b = "Board data are also from CSMAR, covering 2008 and 2012."
pages2 = [f"Data. {S2a} {S2b} End."]
r2 = verify(pages2, [new_source("CSMAR", S2a),
                     new_source("CSMAR database", S2b, period="2008–2012", period_quote=S2b, form="range", years=[2008, 2012])])
kept = r2["data_sources"]
check("2a. 两条 CSMAR 合并为一条，期间连同“形态未核实”一起搬过来（2008 and 2012 不是区间）",
      len(kept) == 1 and kept[0]["sample_period"] == "2008–2012" and kept[0].get("period_form_unverified")
      and step2.period_year_set(kept[0]) is None, [(x["name"], x.get("period_form_unverified")) for x in kept])
S2c = "We use the CPS public use files, which are publicly available."
S2d = "The CPS data are publicly available from the Census Bureau."
pages2c = [f"Data. {S2c} {S2d} End."]
r2c = verify(pages2c, [new_source("Current Population Survey (CPS)", S2c, cat="public", access_quote=S2c, applies="CPS public use files"),
                       new_source("Current Population Survey (CPS) data", S2d, cat="public", access_quote=S2d, applies="whole")])
merged = step3.merge_reports([("P", r2c)])
g = merged[0]
check("2b. 分类相同、范围不同（public use files / 整个数据源）的两条，合并时不合成一条",
      len([u for u in g["uses"] if u["paper"] == "P"]) == 2, [(u["src"]["name"], u["src"].get("access_scope")) for u in g["uses"]])
check("2c. 组结论分别列出两个范围，不把 public use 部分的条件概括成整个数据源",
      "applies to: CPS public use files" in g["verdict"][0] and "listed separately" in g["verdict"][0], g["verdict"])

# ======== 验收 6：零数据源论文的限制信息保留 ========
print("\n验收 6：零数据源论文的限制")
all_cited = liebman_new(**{n: {"usage": "cited"} for n in [s["name"] for s in L_RAW["data_sources"]]})
rep6 = run(L_PAGES, all_cited)
text6 = step3.report_markdown([("Liebman1998", rep6)])
lims = section(text6, "Paper-level sample restrictions")
check("6. 所有记录都判为 cited（本文使用的数据为零）→ 第7页、第26页的限制仍在论文级限制中",
      not rep6["data_sources"] and "p. 7" in lims and "p. 26" in lims, lims)

# ======== 字段在拆分、去重、合并后不丢失 ========
print("\n字段传递")
SJ = "Firm data from 2010 to 2015 are drawn from the CSMAR and WIND databases."
rj = verify([f"Data. {SJ} End."], [new_source("CSMAR and WIND databases", SJ, period="2010–2015", period_quote=SJ,
                                              form="range", years=[2010, 2015])])
check("拆分：两部分都保留使用关系和期间形态",
      len(rj["data_sources"]) == 2 and all(x["usage"] == "analyzed" and x["period_form"] == "range"
                                           and step2.period_year_set(x) == set(range(2010, 2016)) for x in rj["data_sources"]),
      [(x["name"], x.get("usage"), x.get("period_form")) for x in rj["data_sources"]])
check("合并：报告中每篇论文一行显示适用范围",
      any("Liebman1998: [public (applies to: public use sample)]" in ln for ln in text5.splitlines()), soi_sec5)

# ======== 适用范围的核对 ========
print("\n适用范围")
SA = "The public use files of the survey are freely available online."
# 2026-11-17：指代链规则下，点名句后紧跟的指代句会确认归属。为保留本项的原意（范围不放宽点名检查），中间插入一句另起话题的句子
ra = verify([f"Data. We use the Panel Survey of Things. We thank the survey team. {SA} End."],
            [new_source("Panel Survey of Things", "We use the Panel Survey of Things.", cat="public",
                        access_quote="The public use files of the survey are freely available online.", applies="public use files")])
x = ra["data_sources"][0]
check("条件句没有点名数据（以 The 开头的指代句）→ 仍然不通过（范围不放宽点名检查）",
      x["verification"] in ("unclear_reference", "anaphor_reference") and x["access_category"] == "unknown", x["verification"])
SB = "The Panel Survey of Things public use files are freely available online."
rb = verify([f"Data. {SB} End."], [new_source("Panel Survey of Things", SB, cat="public", access_quote=SB, applies="public use files")])
x = rb["data_sources"][0]
check("部分名称逐字出现在条件句中 → 通过，范围为 public use files", x["verification"] == "verified" and x["access_scope"] == "public use files",
      (x["verification"], x.get("access_scope")))
rc = verify([f"Data. {SB} End."], [new_source("Panel Survey of Things", SB, cat="public", access_quote=SB, applies="restricted geocode files")])
x = rc["data_sources"][0]
check("部分名称没有出现在条件句中 → 适用范围未核实，最终未确认（归属不明）",
      x["verification"] == "scope_unverified" and x["access_category"] == "unknown" and step2.unknown_reason(x) == "attribution unclear", x["verification"])
rd = verify([f"Data. {SB} End."], [new_source("Panel Survey of Things", SB, cat="public", access_quote=SB, applies=None)])
check("模型给了分类却没给适用范围 → 适用范围未核实（不默认为整个数据源）", rd["data_sources"][0]["verification"] == "scope_unverified")
SC = "We use the Panel Survey of Things, which is publicly available."
re_ = verify([f"Data. {SC} End."], [new_source("Panel Survey of Things", SC)])
x = re_["data_sources"][0]
check("来源句里的条件词语没有对象 → 线索的范围为“未确定”（不默认为 whole），最终未确认、不显示为已验证",
      x["access_category"] == "unknown" and x["candidate"]["scope"] == "undetermined"
      and " (verified" not in step3.report_markdown([("P", re_)]), (x["access_category"], x.get("candidate")))
UHS_Q = "We use the Urban Household Survey (UHS) to estimate the impact of temperature on AC purchases."
ru = verify([f"Data. {UHS_Q} End."], [new_source("Urban Household Survey (UHS)", UHS_Q)])
x = ru["data_sources"][0]
check("评审复现例：AC purchases（研究内容）→ 不判为订阅、不标已验证，只记为词面线索",
      x["access_category"] == "unknown" and x["verification"] == "none" and step2.unknown_reason(x) == "lexical clue, unconfirmed",
      (x["access_category"], x["verification"], x.get("access_scope")))

# ======== unknown 细分 ========
print("\nunknown 细分")
SN = "We use the Panel Survey of Things for household income."
cases = [
    ("no statement found", [new_source("Panel Survey of Things", SN)], [SN]),
    ("unclear wording", [new_source("Panel Survey of Things", SN, cat="public", access_quote=SN, applies="whole")], [SN]),
    ("quote cannot be checked", [new_source("Panel Survey of Things", SN, cat="public", access_quote="It is publicly available here.", applies="whole")], [SN]),
    ("conflicting evidence", [new_source("Panel Survey of Things", SN, cat="public",
                         access_quote="The Panel Survey of Things is publicly available, but the Panel Survey of Things geocodes are restricted.",
                         applies="whole")],
     [SN, "The Panel Survey of Things is publicly available, but the Panel Survey of Things geocodes are restricted."]),
    ("attribution unclear", [new_source("Panel Survey of Things", SN, cat="public", access_quote="These data are publicly available.", applies="whole")],
     [SN, "We thank the survey team.", "These data are publicly available."]),   # 中间另起话题，指代链中断（2026-11-17）
]
for label, srcs, sentences in cases:
    rep = verify(["Data. " + " ".join(sentences) + " End."], srcs)
    x = rep["data_sources"][0]
    text = step3.report_markdown([("P", rep)])
    check(f"{label}：unknown_reason 和报告中的标签一致", step2.unknown_reason(x) == label and f"[{label}]" in text,
          (step2.unknown_reason(x), x["verification"]))

# ======== 点名收紧 ========
print("\n点名收紧")
# 已知局限（程序行为，不属于六项固定验收）：名称本身含机构缩写时，这个缩写也算点名；程序不猜测它是不是机构
residual("名称 “IRS Statistics of Income …” 中的 IRS 被当作点名依据（机构缩写）",
         step2.names_source("Unfortunately, the IRS has stopped releasing data.", {"name": SOI}), False)
check("名称中的单个普通词（mortality）不能单独成立",
      not step2.names_source("Mortality rates rose.", {"name": "Mortality Multiple Cause Files"}))
check("名称中的几个词同时出现也不算点名（评审决定移除未约定的两词共现路径）",
      not step2.names_source("The multiple cause mortality files are restricted.", {"name": "Mortality Multiple Cause Files"}))
check("完整名称逐字出现 → 成立", step2.names_source("The Mortality Multiple Cause Files are restricted.", {"name": "Mortality Multiple Cause Files"}))
check("缩写 → 成立", step2.names_source("TCMP tabulations show ...", {"name": TCMP}))

# ======== 交付核对修复（2026-11-06，只改显示和已决定删除的功能，不改语义规则） ========
print("\n交付核对修复")
Q_LFS = "The present study utilizes the public-use files of the Canadian LFS (July 2001–June 2015)."
legacy = {"name": "Canadian LFS", "role": "main", "kind": "dataset", "provider": None, "unit": None,
          "sample_period": "July 2001–June 2015", "period_evidence": ev(Q_LFS), "access_category": "unknown",
          "source_evidence": ev(Q_LFS), "access_evidence": None}
rep_l = verify([f"Data. {Q_LFS} End."], [legacy])
lfs = rep_l["data_sources"][0]
check("D1. 旧结果 “July 2001–June 2015”：按区间写法推断为连续区间（以前误推断为离散年份）",
      lfs["period_form"] == "range" and lfs["period_years"] == [2001, 2015] and not lfs.get("period_unverified"), lfs.get("rule_notes"))
text_l = step3.report_markdown([("P", rep_l)])
check("D1. 报告标明形态是由期间写法推断的", "continuous range, inferred from how the period is written" in text_l, text_l)
check("D2. 每篇论文显示“本文使用”的依据原文和页码（旧结果注明用的是来源句）",
      "Basis for \"used in this paper\" (the source sentence (older results have no usage-relation field); source text located): p. 1" in text_l, text_l)
Q_TC = "My data for this study were 1985 and 1988 cross sections from the TCMP files."
rep_t = verify([f"Data. {Q_TC} End."], [new_source("TCMP files", Q_TC, period="1985–1988", period_quote=Q_TC,
                                                   form="discrete", years=[1985, 1988])])
text_t = step3.report_markdown([("P", rep_t)])
check("D3. 离散年份按列出的年份显示 1985、1988（模型字符串写成 1985–1988 也不照抄）",
      "1985, 1988 (discrete years" in text_t and "1985–1988（" not in text_t, text_t)
check("D4. 使用关系依据注明是模型判断", "Basis for \"used in this paper\" (the usage relation is a model judgment; source text located)" in text_t, text_t)
soi_sec_old = section(text_old, "IRS Statistics of Income")
check("D5. 只有词面线索时不写“论文中未说明”“所有论文都没有说明获取条件”",
      "not stated in the paper" not in soi_sec_old and "no paper states an access condition" not in soi_sec_old
      and "no verified statement of conditions" in soi_sec_old, soi_sec_old)
check("D6. 已验证的条件注明：原文已定位并通过核对，分类是模型的判断",
      "verified: source text located and checks passed; the condition category is a model judgment" in section(text5, "IRS Statistics of Income"), section(text5, "IRS Statistics of Income"))


# ======== 2026-11-17 指代链：范围检查照常生效 ========
print("\n指代链 + 适用范围")
rd = verify([f"Data. We use the Panel Survey of Things. {SA} End."],
            [new_source("Panel Survey of Things", "We use the Panel Survey of Things.", cat="public",
                        access_quote=SA, applies="public use files")])
x = rd["data_sources"][0]
check("指代句紧跟点名句 → 归属确认；部分名称 public use files 出现在条件句中 → 通过，范围为 public use files",
      x["verification"] == "verified" and x["access_scope"] == "public use files", (x["verification"], x.get("access_scope")))
re_ = verify([f"Data. We use the Panel Survey of Things. {SA} End."],
             [new_source("Panel Survey of Things", "We use the Panel Survey of Things.", cat="public",
                         access_quote=SA, applies="restricted geocode files")])
x = re_["data_sources"][0]
check("指代链确认归属，但部分名称不在条件句中 → 仍然是适用范围未核实",
      x["verification"] == "scope_unverified" and x["access_category"] == "unknown", x["verification"])


if residuals:
    print(f"\n已知残留错误 {len(residuals)} 项（不计入通过）：" + "；".join(f"{n}（{st}）" for n, st in residuals))
print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
