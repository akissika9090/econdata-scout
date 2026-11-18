"""
获取条件证据的输入契约测试。这些测试的预期结果在修改核对函数之前就定好了（2026-11-06），
不是根据代码的输出决定什么算正确。

契约：
    单句引用           → 按现有规则核对（存在 → 支持该分类 → 针对这个数据）
    多句引用（连续）    → 不能直接通过：状态 multi_sentence（需要人工复核），最终“未确认”，保留 AI 的判断和引用
    拼接（原文不连续）  → quote_not_found（引用核对就过不了）
基础流程（step2.access_status）和 Agent（agent_tools.submit_evidence）用同一个函数，所以两边契约相同。

运行：
    python test_contract.py
"""
from test_support import require_materials

require_materials(['papers/borgschulte2022.pdf', 'papers/deng2020.pdf'], "test_contract")


import step1_pdf_evidence as step1
import step2_ai_extract as step2
import agent_tools as tools

failures = 0


def check(name, ok, detail=""):
    global failures
    print(f"{'✓' if ok else '✗'}  {name}" + ("" if ok else f"   （实际：{detail}）"))
    if not ok:
        failures += 1


def source(name, quote, page=1, provider=None):
    s = {"name": name, "provider": provider, "kind": "dataset",
         "source_evidence": {"quote": quote, "page": page, "verified": True}}
    s["db_hint"] = step2.database_hint(s)
    return s


def status(pages, src, category, quote, page):
    ev = step2.check_evidence(pages, {"quote": quote, "page": page})
    return step2.access_status(pages, src, category, ev)[0]


# ---- 1. A 数据的名称和 B 数据的受限条件出现在相邻两句 ----
A_NAME = "Employment data come from the Quarterly Workforce Indicators (QWI) of the Census Bureau."
B_RESTR = "Mortality micro-data from the vital statistics system are restricted and cannot be shared."
pages1 = [f"2. Data. {A_NAME} {B_RESTR} We combine them at the county level."]
qwi = source("Quarterly Workforce Indicators (QWI)", A_NAME)
st = status(pages1, qwi, "restricted", f"{A_NAME} {B_RESTR}", 1)
check("1. A 数据名称 + 相邻句中 B 数据的受限条件 → 不能判为 A 受限（multi_sentence）", st == "multi_sentence", st)

# ---- 2. 同一数据的跨句证据（NVSS，真实论文第 46 页）----
bpages, _ = step1.extract_pages("papers/borgschulte2022.pdf")
nvss = source("National Vital Statistics System",
              "We measure mortality outcomes using micro-data provided by the National Vital Statistics System.", 46)
NVSS_3 = ("We measure mortality outcomes using micro-data provided by the National Vital Statistics System. "
          "The underlying data are taken from death certiﬁcates which contain age of death. "
          "We use the restricted data ﬁles containing month of death and covering all counties in the United States "
          "to measuring monthly mortality at the county level.")
st = status(bpages, nvss, "restricted", NVSS_3, 46)
check("2. NVSS 连续三句（点名 + 受限分在不同句子）→ 不直接通过，留给人工复核（multi_sentence）", st == "multi_sentence", st)
ok, msg, _ = tools.submit_evidence(bpages, nvss, "restricted", NVSS_3, 46)
check("2b. Agent 提交同样的引用 → 被拒绝，并说明是多句引用", not ok and "more than one sentence" in msg, msg)

# ---- 3. 模型拼接不连续的句子 ----
SPLICED = ("We measure mortality outcomes using micro-data provided by the National Vital Statistics System. "
           "We use the restricted data ﬁles containing month of death and covering all counties in the United States "
           "to measuring monthly mortality at the county level.")
st = status(bpages, nvss, "restricted", SPLICED, 46)
check("3. 拼接原文中不连续的两句 → quote_not_found", st == "quote_not_found", st)

# ---- 4. 多句引用中同时有公开和受限 ----
P1 = "The CPS public-use files are publicly available from the Census Bureau website."
P2 = "Geographic identifiers below the state level in the CPS are restricted."
pages4 = [f"Data. {P1} {P2} We use state-level variables only."]
cps = source("Current Population Survey (CPS)", P1)
for cat in ("public", "restricted"):
    st = status(pages4, cps, cat, f"{P1} {P2}", 1)
    check(f"4. 多句引用中公开和受限并存，提交为“{cat}” → 不通过（multi_sentence）", st == "multi_sentence", st)

# ---- 对照：单句引用按现有规则 ----
dpages, _ = step1.extract_pages("papers/deng2020.pdf")
uhs = source("Urban Household Survey (UHS)",
             "Our data come from the Urban Household Survey (UHS) since 1986 conducted by the National Bureau of Statistics of China.", 3)
st = status(dpages, uhs, "restricted", "Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", 3)
# 2026-11-17：deng2020 中点名句之后连续是指代句（The survey… / Therefore, the dataset…），中间没有其他数据 → 指代链确认
check("对照：单句、指代链连续指向前文点名的数据（deng2020 UHS）→ verified（2026-11-06 至 11-16 为 anaphor_reference）",
      st == "verified", st)
NV1 = ("We use the restricted data ﬁles containing month of death and covering all counties in the United States "
       "to measuring monthly mortality at the county level.")
st = status(bpages, nvss, "restricted", NV1, 46)
check("对照：NVSS 单句（没点名）→ 仍然 unclear_reference（规则不放宽）", st == "unclear_reference", st)
US = "The 2000 data obtained from the U.S. Census Bureau are publicly available online."
st = status([f"Data. {US} More text here for the page."], source("Census data", US), "public", US, 1)
check("对照：句中有缩写 U.S.（不是两句）→ 不按多句引用拒绝", st != "multi_sentence", st)
# 2026-11-06 第二阶段“点名收紧”：数据名称 “Census data” 只有一个普通词，句中只出现机构名 Census Bureau → 不能确认点名。
# 以前是 verified；这是收紧带来的变化，记入回归报告
check("对照：名称只有一个普通词、句中只有机构名 → unclear_reference（以前是 verified）", st == "unclear_reference", st)
st = status([f"Data. {US} More text here for the page."], source("U.S. Census Bureau", US), "public", US, 1)
check("对照：句中有缩写 U.S.、完整名称逐字出现 → verified", st == "verified", st)

print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
