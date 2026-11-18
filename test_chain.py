"""
整条链路的测试：提取结果 → 核对（step2）→（Agent）→ 合并（step3）→ 报告文字。
检查的是最终报告，不是中间字段。预期结果在修复之前定好（2026-11-06，对应外部审查的第 1–8 项）。
不联网、不调用 AI：模型的提取结果和 Agent 的决定都是固定内容。

运行：
    python test_chain.py
"""

import copy

import agent
import step2_ai_extract as step2
import step3_merge as step3

failures = 0


def check(name, ok, detail=""):
    global failures
    print(f"{'✓' if ok else '✗'}  {name}" + ("" if ok else f"\n     报告相关内容：{detail[:400]}"))
    if not ok:
        failures += 1


def ev(quote, page=1):
    return {"quote": quote, "page": page}


def source(name, source_quote, cat="unknown", access_quote=None, period=None, period_quote=None):
    return {"name": name, "role": "main", "kind": "dataset", "provider": None, "unit": None,
            "sample_period": period, "period_evidence": ev(period_quote) if period_quote else None,
            "access_category": cat, "source_evidence": ev(source_quote),
            "access_evidence": ev(access_quote) if access_quote else None}


def report_text(pages, sources, paper="P", limitations=(), agent_ask=None):
    raw = {"data_sources": sources, "sample_limitations": [ev(q) for q in limitations], "availability_statement": None}
    rep = step2.verify_result(pages, copy.deepcopy(raw))
    if agent_ask:
        rep = agent.recover_report(pages, rep, ask=agent_ask)
    reports = [(paper, rep)]
    return step3.report_markdown(reports), rep


def section(text, name):
    """报告中某个数据源那一节的文字。"""
    parts = text.split("\n## ")
    return next((p for p in parts if p.startswith(name)), "")


QWI_SRC = "Employment data come from the Quarterly Workforce Indicators (QWI)."
NOAA_SRC = "Weather data come from the NOAA weather stations."

# ---- 1. 多句检查：短句、小写句首 ----
for q in ["We use QWI. Weather observations are restricted.", "QWI data are used here. weather observations are restricted."]:
    pages = [f"Data. {QWI_SRC} {q} End of the data section."]
    text, _ = report_text(pages, [source("Quarterly Workforce Indicators (QWI)", QWI_SRC, "restricted", q)])
    sec = section(text, "Quarterly Workforce Indicators")
    check(f"1. 多句引用（{q[:30]}…）→ 报告中 QWI 不是“受限 已验证”，显示为需要人工复核，引用保留",
          " (verified" not in sec and "needs manual review" in sec and "multi-sentence" in sec and q[:20] in sec, sec)
q = "Data are drawn from the 2010 U.S. Census Bureau files and are publicly available online for all researchers."
text, _ = report_text([f"Data. {q} End."], [source("U.S. Census Bureau files", q, "public", q)])
# 2026-11-06 K1：旧格式记录没有适用范围 → 报告写“原记录分类：公开；适用范围未记录”（原预期为“公开：1 篇已验证”）。
# 反向检查改为看每篇论文一行的“（已验证”标记：新的计数写法不再含“1 篇已验证”，原写法会让反向检查失效
check("1. 对照：句中有缩写 U.S. 的单句 → 仍然通过核对（已验证），旧格式显示为原记录分类、适用范围未记录",
      " (verified" in text and "original record category: public; scope not recorded" in text, text)

# ---- 2a. 指代句：前文出现过名称，不能证明指代的是它 ----
# 来源句要有“数据从哪里来”的说法（from），否则会被归为“其他提及”
pages = [f"Data. We use QWI employment data from the Census Bureau. We obtain weather data from NOAA. The data are restricted. End."]
text, _ = report_text(pages, [source("QWI employment data", "We use QWI employment data from the Census Bureau.", "restricted",
                                     "The data are restricted.")])
sec = section(text, "QWI employment data")
check("2a. 指代句（中间提到了别的数据）→ 不是“受限 已验证”；需要人工复核，说明是指代句，引用和页码保留",
      " (verified" not in sec and "needs manual review" in sec and "starts with a reference" in sec and "The data are restricted." in sec and "p. 1" in sec, sec)

# ---- 2a'. 指代链（2026-11-17 起）：点名句之后连续都是指代句、中间没有其他数据 → 确认归属 ----
QWI_NAME = "We use QWI employment data from the Census Bureau."
pages = [f"Data. {QWI_NAME} The data cover all counties in the United States. The data are restricted. End."]
text, _ = report_text(pages, [source("QWI employment data", QWI_NAME, "restricted", "The data are restricted.")])
sec = section(text, "QWI employment data")
check("2a'. 指代链没有中断、中间没有其他数据 → 受限 已验证", " (verified" in sec and "needs manual review" not in sec, sec)
# 中间夹了一句不是指代开头的句子（没有点名任何数据）→ 指代链中断，仍然需要人工复核
pages = [f"Data. {QWI_NAME} We thank the agency for its help. The data are restricted. End."]
text, _ = report_text(pages, [source("QWI employment data", QWI_NAME, "restricted", "The data are restricted.")])
sec = section(text, "QWI employment data")
check("2a'. 指代链被另起话题的句子打断 → 不确认，需要人工复核（指代句）",
      " (verified" not in sec and "needs manual review" in sec and "starts with a reference" in sec, sec)
# 指代链中的句子点名了本论文另一个已抽取的数据 → 不确认
pages = [f"Data. {QWI_NAME} {NOAA_SRC} The data are restricted. End."]
text, _ = report_text(pages, [source("QWI employment data", QWI_NAME, "restricted", "The data are restricted."),
                              source("NOAA weather data", NOAA_SRC)])
sec = section(text, "QWI employment data")
check("2a'. 点名句与证据句之间点名了本论文的其他数据 → 不确认", " (verified" not in sec and "needs manual review" in sec, sec)

# ---- 2b. 同一句提到多个数据：共同条件 / 分别描述 / 归属不明 ----
def two_sources(q, cat):
    pages = [f"Data. {QWI_SRC} {NOAA_SRC} {q} End."]
    text, _ = report_text(pages, [source("Quarterly Workforce Indicators (QWI)", QWI_SRC, cat, q),
                                  source("NOAA weather data", NOAA_SRC)])
    return section(text, "Quarterly Workforce Indicators")
for label, q, cat in [("共同条件", "QWI and NOAA data are publicly available.", "public"),
                      ("分别描述，提交为公开", "QWI data are public and NOAA data are restricted.", "public"),
                      ("分别描述，提交为受限", "QWI data are public and NOAA data are restricted.", "restricted"),
                      ("attribution unclear", "QWI observations are used, and NOAA weather observations are restricted.", "restricted")]:
    sec = two_sources(q, cat)
    check(f"2b. 同句提到另一个数据（{label}）→ QWI 不自动确认，需要人工复核，引用保留",
          " (verified" not in sec and "needs manual review" in sec and q[:25] in sec, sec)

# ---- 3. 未核实的样本年份不能进入覆盖结论 ----
pages = [f"Data. {QWI_SRC} We study county outcomes."]
text, _ = report_text(pages, [source("Quarterly Workforce Indicators (QWI)", QWI_SRC, period="1990–2020",
                                     period_quote="The sample covers 1990 to 2020 for all counties.")])
check("3. 未核实的期间：报告中显示并标注“未核实”", "1990–2020" in text and "unverified" in text, text)
check("3. 未核实的期间不计入“最晚用到”（2026-11-06 取消年份覆盖判断后，也不应出现“范围内”）",
      "latest year used 2020" not in text and "within the years" not in text, text)

# ---- 4. 年鉴期间：不自动改成别的数据的期间 ----
YB = "City-level controls come from the China City Statistical Yearbook (2004–2019)."
WX = "Weather data from the meteorological agency cover the sample period 2003–2018 for all stations."
text, rep = report_text([f"Data. {YB} {WX} End."], [source("China City Statistical Yearbook", YB, period="2004–2019", period_quote=YB)])
y = rep["data_sources"][0]
check("4. 年鉴期间保持模型给出的 2004–2019，不借用天气数据的 2003–2018；期间证据仍是年鉴那句",
      y["sample_period"] == "2004–2019" and y["period_evidence"]["quote"] == YB, str(y.get("sample_period")))
check("4. 报告提示“可能是出版年份”，且该期间不参与覆盖比较（标为未核实）",
      # 2026-11-06：报告改为英文（原为“出版年份”、按“年鉴出版年份通常”“覆盖”切分）
      "edition year" in text and "unverified" in text
      and "2003–2018" not in text.split("the edition year is usually")[0].split("Historical use record")[-1], text)

# ---- 5. Agent 找回的证据要显示在报告里 ----
# 证据句本身点名了 UHS（第 2a 项之后，只靠指代的句子不会被确认）
Q5 = "The UHS household microdata are confidential and were provided under a data use agreement."
SRC5 = "Our data come from the Urban Household Survey (UHS) conducted by the NBS."
fake = lambda s, c: ({"thought": "t", "action": "submit_evidence", "category": "restricted", "quote": Q5, "page": 1, "query": None}, "fake")
text, rep = report_text([f"Data. {SRC5} {Q5} End of page."], [source("Urban Household Survey (UHS)", SRC5)], agent_ask=fake)
check("5. Agent 找回证据后，报告中这个数据源显示引用、页码和“已验证”",
      Q5[:40] in text and "p. 1" in text and " (verified" in text, text)
base_review = [source("Urban Household Survey (UHS)", SRC5, "restricted", "Our data come from the Urban Household Survey (UHS) conducted by the NBS.")]
_, rep = report_text([f"Data. {SRC5} {Q5} End of page."], base_review, agent_ask=fake)
s = rep["data_sources"][0]
check("5. 找回后不再残留旧的“需要人工复核”说明；模型的原始判断（ai_category）保留",
      not s.get("downgraded") and not s.get("needs_review") and s["ai_category"] == "restricted", str({k: s.get(k) for k in ("downgraded", "needs_review")}))

# ---- 6. 同一论文中条件不同的记录不能被静默去重 ----
CF = "Household data come from the China Family Panel Studies (CFPS)."
PUB = "The CFPS public release data are publicly available to registered users."
RES = "The CFPS county identifiers are restricted and were obtained under a confidentiality agreement."
text, rep = report_text([f"Data. {CF} {PUB} {RES} End."],
                        [source("CFPS public release", CF, "public", PUB), source("CFPS county identifiers", CF, "restricted", RES)])
check("6. 同一论文中 CFPS 的公开版本和受限的识别码：两条都保留在报告中",
      "CFPS public release" in text and "CFPS county identifiers" in text, text)
check("6. 仍按论文计数（1 篇论文使用）", "(used by 1 paper)" in text, text)

# ---- 7. 同一页的限制：没点名这个数据的，不归给它 ----
pages = [f"Data. {QWI_SRC} Weather station records before 2005 are missing for some counties. End."]
text, _ = report_text(pages, [source("Quarterly Workforce Indicators (QWI)", QWI_SRC)],
                      limitations=["Weather station records before 2005 are missing for some counties."])
sec = section(text, "Quarterly Workforce Indicators")
check("7. 没点名 QWI 的同页限制 → 不列在 QWI 的覆盖下", "Weather station records" not in sec, sec)
check("7. 这条限制仍在报告中，作为论文级限制、标明“归属待核实”", "Weather station records" in text and "attribution unverified" in text, text)

# ---- 8. 模型返回合法 JSON 但结构不对 ----
pages = [f"Data. {SRC5} {Q5} End of page."]
try:
    text, rep = report_text(pages, [source("Urban Household Survey (UHS)", SRC5)], agent_ask=lambda s, c: ([], "fake"))
    a = rep["data_sources"][0]["agent"]
    check("8. Agent 收到 [] → 不崩溃，记录失败，分类保持未确认", rep["data_sources"][0]["access_category"] == "unknown"
          and a["outcome"] in ("agent_error", "budget_exhausted", "gave_up"), str(a))
except Exception as e:
    check("8. Agent 收到 [] → 不崩溃，记录失败，分类保持未确认", False, f"{type(e).__name__}: {e}")

# ======== 第一阶段（2026-11-06）：核对后的记录发生变化时，状态必须重新计算；信息不能丢 ========
print("\n--- 第一阶段 ---")

# P1-1. 联合来源拆分：Wind 不能继承只属于 CSMAR 的条件
J_SRC = "Firm-level data are drawn from the CSMAR and WIND databases."
J_ACC = "CSMAR data require a paid subscription."
text, rep = report_text([f"Data. {J_SRC} {J_ACC} End."],
                        [source("CSMAR and WIND databases", J_SRC, "subscription", J_ACC)])
by = {s["db_hint"]["name"] if s.get("db_hint") else s["name"]: s for s in rep["data_sources"]}
wind = next((s for k, s in by.items() if "Wind" in k), None)
csmar = next((s for k, s in by.items() if "CSMAR" in k), None)
check("P1-1. 拆分后 CSMAR 仍是“订阅 已验证”（证据点名了 CSMAR）",
      csmar is not None and csmar["access_category"] == "subscription" and csmar["verification"] == "verified", str(csmar))
check("P1-1. 拆分后 Wind 不继承 CSMAR 的条件（证据没点名 Wind）；报告中 Wind 那一节不是“订阅 已验证”",
      wind is not None and wind["access_category"] == "unknown" and " (verified" not in section(text, "Wind"), section(text, "Wind"))

# P1-2. 去重补入期间时，未核实状态要一起带过来
CF2 = "Household data come from the China Family Panel Studies (CFPS)."
PUB2 = "The CFPS data are publicly available to registered users."
text, rep = report_text([f"Data. {CF2} {PUB2} End."],
                        [source("CFPS", CF2, "public", PUB2),
                         source("China Family Panel Studies", CF2, period="2010–2020",
                                period_quote="The CFPS waves cover 2010 to 2020 for all provinces.")])
check("P1-2. 去重后保留的那条带着未核实的期间时，报告标“未核实”，不写“最晚用到 2020”或“范围内”",
      "unverified" in text and "latest year used 2020" not in text and "within the years" not in text, text)

# P1-3. 来源引用找不到 → 不能算“本文使用了这个数据”
REAL_SRC = "Employment data come from the Quarterly Workforce Indicators (QWI)."
text, rep = report_text([f"Data. {REAL_SRC} End of section."],
                        [source("Quarterly Workforce Indicators (QWI)", REAL_SRC),
                         source("Fake Survey of Things", "We also use the Fake Survey of Things provided by the ministry.")])
check("P1-3. 来源引用在原文中找不到的数据源，不出现在“数据来源汇总”的数据源里", "## Fake Survey" not in text, text)
check("P1-3. 但信息不丢：列在其他提及里，并说明“来源引用无法在原文中找到”",
      any(m["name"] == "Fake Survey of Things" and m.get("mention_reason") == "source_unverified" for m in rep["other_mentions"]),
      str([(m["name"], m.get("mention_reason")) for m in rep["other_mentions"]]))

# P1-3b. 引用是真的、只是页码写错（模型写了期刊印刷页码）→ 仍算本文使用，页码改为实际页（beck2015 真实出现）
pages = ["Cover page text only.", f"Resource and Energy Economics 41 (2015) 40–69 49 Data. {REAL_SRC} End of section."]
text, rep = report_text(pages, [source("Quarterly Workforce Indicators (QWI)", REAL_SRC)])
s0 = rep["data_sources"][0] if rep["data_sources"] else {}
raw_src = source("Quarterly Workforce Indicators (QWI)", REAL_SRC); raw_src["source_evidence"]["page"] = 49
rep = step2.verify_result(pages, {"data_sources": [raw_src], "sample_limitations": [], "availability_statement": None})
s0 = rep["data_sources"][0] if rep["data_sources"] else {}
check("P1-3b. 引用逐字存在、页码写错 → 仍是本文的数据来源，页码改为实际的第 2 页，保留模型写的 49",
      s0.get("source_evidence", {}).get("page") == 2 and s0["source_evidence"].get("page_given") == 49, str(rep))

# P1-4. 没有数据源的论文，限制信息也要保留
LIM = "Data for 2010 onward are missing for most provinces."
raw = {"data_sources": [], "sample_limitations": [ev(LIM)], "availability_statement": None}
rep = step2.verify_result([f"Data. {LIM} End."], copy.deepcopy(raw))
merged_z = step3.merge_reports([("Z", rep)])
text = step3.format_report(merged_z, paper_limitations=step3.paper_limitations([("Z", rep)], merged_z))
check("P1-4. 一个数据源都没有的论文，样本限制仍然出现在报告里（论文级限制）", LIM in text and "Z" in text, text)

# ======== 第一阶段补充（外部验收指出的三处信息丢失）========
print("\n--- 第一阶段补充 ---")

# P1-5. 无效来源不能在去重时淘汰有效来源（同一个 CSMAR 的两条记录）
C_SRC = "Subsidy data come from the CSMAR database."
C_ACC = "CSMAR data require a paid subscription."
text, rep = report_text([f"Data. {C_SRC} {C_ACC} End."],
                        [source("CSMAR database", C_SRC),                                        # 来源真实，条件未确认
                         source("CSMAR", "We purchase firm data from the CSMAR vendor.", "subscription", C_ACC)])  # 来源引用不存在，条件句通过
check("P1-5. 来源真实的那条 CSMAR 仍在报告的数据来源里（不被来源无效但条件更强的那条淘汰）",
      "CSMAR" in "".join(p for p in text.split("\n## ") if "(used by" in p.split("\n")[0]), text)

# P1-6. “其他提及”要进入最终报告：所属论文、名称、原因；找不到的引用不冒充原文
FAKE_Q = "We also use the Fake Survey of Things provided by the ministry."
text, rep = report_text([f"Data. {REAL_SRC} End of section."],
                        [source("Quarterly Workforce Indicators (QWI)", REAL_SRC), source("Fake Survey of Things", FAKE_Q)], paper="PaperX")
check("P1-6. 报告中有“排除 / 待核查的候选”，列出论文、名称和原因",
      "Excluded" in text and "PaperX" in text and "Fake Survey of Things" in text and "the source quote cannot be found in the paper" in text, text)
check("P1-6. 找不到的引用不在报告里当作原文显示", FAKE_Q not in text, text)

# P1-7. 合并去重后，样本限制不能消失：East 在前，合并去重时保留 East、去掉 West；限制只点名 West
W_SRC = "Household data for western provinces come from the Regional Household Survey (West)."
E_SRC = "Household data for eastern provinces come from the Regional Household Survey (East)."
W_LIM = "The West survey does not cover Tibet because of data limitations."
text, rep = report_text([f"Data. {E_SRC} {W_SRC} {W_LIM} End."],
                        [source("Regional Household Survey (East)", E_SRC), source("Regional Household Survey (West)", W_SRC)],
                        limitations=[W_LIM])
groups = [part for part in text.split("\n## ") if "(used by" in part.split("\n")[0]]
shown_names = " ".join(groups)
check("P1-7. 合并去重时只保留了一条（复现条件：West 不在报告的数据源里）",
      "Regional Household Survey (East)" in shown_names and "Regional Household Survey (West)" not in shown_names, shown_names)
check("P1-7. 只点名 West 的限制仍出现在报告里（论文级）", W_LIM in text, text)
check("P1-7. 这条限制没有被转到 East 名下", not any(W_LIM in g for g in groups), text)

print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
