"""
测试 Evidence Recovery Agent：停止条件、安全规则、失败回退、行动日志。
不联网：用“假模型”按预定的顺序给出决定；工具在真实论文 PDF（papers/deng2020.pdf、zhou2022.pdf）上运行。

运行：
    python test_agent.py
"""
from test_support import require_materials

require_materials(['papers/deng2020.pdf', 'papers/zhou2022.pdf', 'results/deng2020_1105_093521_run1.json', 'ground_truth.json', 'evaluate.py'], "test_agent")


import copy

import agent
import agent_tools as tools
import step1_pdf_evidence as step1

failures = 0


def check(name, ok):
    global failures
    print(f"{'✓' if ok else '✗'}  {name}")
    if not ok:
        failures += 1


def fake_model(decisions, calls=None):
    """按顺序返回预定的决定。calls 用来记录每次发给模型的内容。"""
    queue = list(decisions)

    def ask(system, content):
        if calls is not None:
            calls.append(content)
        d = queue.pop(0)
        if isinstance(d, BaseException):
            raise d
        full = {"thought": "test", "query": None, "page": None, "category": None, "quote": None}
        full.update(d)
        return full, "fake-model"
    return ask


pages, _ = step1.extract_pages("papers/deng2020.pdf")
REAL = "Since the dataset is not available to the public, we can only get the data from 2002 to 2009."
# 2026-11-06 起，上面这句（指代句，没点名 UHS）不再能确认归属。“找到证据”的场景改用一句点名了 UHS 的证据，
# 作为附加的一页加在 deng2020 后面（原文里没有这句，只用于测试 Agent 的流程）
NAMED = "The UHS microdata are not available to the public and were obtained under an agreement with the NBS."
pages = pages + [f"Appendix. {NAMED} End of appendix."]
NAMED_PAGE = len(pages)
UHS = {"name": "Urban Household Survey (UHS)", "provider": "National Bureau of Statistics of China", "kind": "dataset",
       "access_category": "unknown", "ai_category": "unknown", "verification": "none", "access_evidence": None,
       "source_evidence": {"quote": "Our data come from the Urban Household Survey (UHS) since 1986 conducted by the "
                                    "National Bureau of Statistics of China.", "page": 3, "verified": True},
       "db_hint": None, "rule_notes": []}

# --- 工具 ---
r = tools.search_pdf(pages, "not available public")
check("search_pdf：找到含关键词的句子并附页码", "[page 3]" in r and "not available to the public" in r)
check("search_pdf：没有可用的关键词 → 提示，不报错", tools.search_pdf(pages, "the a").startswith("Error"))
check("search_pdf：找不到 → 如实说找不到", tools.search_pdf(pages, "zzqxw").startswith("No sentence"))
check("read_page：页码越界 → 提示，不报错", tools.read_page(pages, 999).startswith("Error"))
check("read_page：页码不是数字 → 提示，不报错", tools.read_page(pages, "3").startswith("Error"))
check("read_page：给了 near 时返回那附近的文字", "not available to the public" in tools.read_page(pages, 3, "not available"))

# --- 停止条件 1：找到证据并通过核对 ---
calls = []
res = agent.run_agent(pages, UHS, ask=fake_model([
    {"action": "search_pdf", "query": "available public"},
    {"action": "submit_evidence", "category": "restricted", "quote": NAMED, "page": NAMED_PAGE}], calls))
check("找到证据：结果为 recovered，分类和证据来自核对通过的引用",
      res["outcome"] == "recovered" and res["category"] == "restricted" and res["evidence"]["verified"])
check("找到证据：用了 2 步就停，不继续调用模型", len(res["steps"]) == 2 and len(calls) == 2)
check("模型每一步都能看到之前的工具结果", "not available to the public" in calls[1] and "Step 1: search_pdf" in calls[1])
check("行动日志：每一步都有想法、动作、参数、结果、模型",
      all({"thought", "action", "args", "observation", "model"} <= set(s) for s in res["steps"]))

# --- 安全规则：模型不能绕过程序核对 ---
res = agent.run_agent(pages, UHS, ask=fake_model([
    {"action": "submit_evidence", "category": "restricted", "quote": REAL, "page": 3}, {"action": "give_up"}]))
check("指代句（“Since the dataset ...”，没点名 UHS）→ 拒绝，说明留给人工复核；之后放弃，分类不变",
      res["outcome"] == "gave_up" and "manual review" in res["steps"][0]["observation"])
res = agent.run_agent(pages, UHS, ask=fake_model([
    {"action": "submit_evidence", "category": "public", "quote": "The UHS data are publicly available online.", "page": 3},
    {"action": "give_up"}]))
check("编造的引用（原文没有）→ 拒绝；之后放弃，分类不变",
      res["outcome"] == "gave_up" and "not found" in res["steps"][0]["observation"])
res = agent.run_agent(pages, UHS, ask=fake_model([
    {"action": "submit_evidence", "category": "public", "quote": UHS["source_evidence"]["quote"], "page": 3},
    {"action": "give_up"}]))
check("真实存在但没有说明获取条件的句子，提交为“公开” → 拒绝（防止误判公开）",
      res["outcome"] == "gave_up" and "does not explicitly state" in res["steps"][0]["observation"])
res = agent.run_agent(pages, UHS, ask=fake_model([
    {"action": "submit_evidence", "category": "public", "quote": REAL, "page": 3}, {"action": "give_up"}]))
check("真实的“不公开”句子，却提交为“公开” → 拒绝", res["outcome"] == "gave_up")
res = agent.run_agent(pages, UHS, ask=fake_model([
    {"action": "submit_evidence", "category": "unknown", "quote": REAL, "page": 3}, {"action": "give_up"}]))
check("提交的分类不是公开 / 订阅 / 受限 → 拒绝", res["steps"][0]["observation"].startswith("Rejected"))
zpages, _ = step1.extract_pages("papers/zhou2022.pdf")
cfps = {**UHS, "name": "China Family Panel Studies (CFPS)", "provider": None,
        "source_evidence": {"quote": "Household-level data is from China Family Panel Studies (CFPS) in 2014 and 2016", "page": 2}}
res = agent.run_agent(zpages, cfps, ask=fake_model([
    {"action": "submit_evidence", "category": "public", "quote": "Publicly available datasets were analyzed in this study.", "page": 8},
    {"action": "give_up"}]))
check("论文的总体声明（没点名这个数据）→ 拒绝，和基础流程的规则一致",
      "general statement" in res["steps"][0]["observation"])

# --- 停止条件 2：主动放弃 ---
res = agent.run_agent(pages, UHS, ask=fake_model([{"action": "give_up"}]))
check("主动放弃：结果为 gave_up，1 步就停", res["outcome"] == "gave_up" and len(res["steps"]) == 1)

# --- 停止条件 3：步数用完 ---
res = agent.run_agent(pages, UHS, max_steps=3, ask=fake_model([
    {"action": "search_pdf", "query": "weather"}, {"action": "search_pdf", "query": "station"},
    {"action": "read_page", "page": 2}]))
check("步数用完：结果为 budget_exhausted，正好用了上限的步数", res["outcome"] == "budget_exhausted" and len(res["steps"]) == 3)

# --- 重复调用 ---
res = agent.run_agent(pages, UHS, max_steps=3, ask=fake_model([
    {"action": "search_pdf", "query": "weather"}, {"action": "search_pdf", "query": "  Weather "},
    {"action": "give_up"}]))
check("同样的工具和参数（大小写、空白不同也算）→ 不执行第二次，但计入步数",
      res["steps"][1]["observation"].startswith("Not executed") and len(res["steps"]) == 3)

# --- 失败回退 ---
res = agent.run_agent(pages, UHS, ask=fake_model([{"action": "search_pdf", "query": "public"}, SystemExit("all models busy")]))
check("模型调用失败（如所有模型都 503）→ agent_error，保留已有的行动日志", res["outcome"] == "agent_error" and len(res["steps"]) == 1)
res = agent.run_agent(pages, UHS, ask=fake_model([RuntimeError("Gemini returned invalid JSON")]))
check("模型返回的不是 JSON → agent_error，不让程序崩溃", res["outcome"] == "agent_error")
res = agent.run_agent(pages, UHS, max_steps=2, ask=fake_model([{"action": "fly_to_moon"}, {"action": "give_up"}]))
check("模型给出不存在的动作 → 记一步并提示，继续", res["steps"][0]["observation"].startswith("Error: unknown action"))
orig = tools.search_pdf
tools.search_pdf = lambda pages, query: 1 / 0
res = agent.run_agent(pages, UHS, max_steps=2, ask=fake_model([{"action": "search_pdf", "query": "x"}, {"action": "give_up"}]))
tools.search_pdf = orig
check("工具内部出错 → 记一步并提示模型，不让程序崩溃", "the tool failed" in res["steps"][0]["observation"])

# --- 整份报告 ---
confirmed = {**UHS, "name": "Confirmed", "access_category": "restricted", "verification": "verified"}
policy = {**UHS, "name": "Pilot list", "kind": "policy_info"}
report = {"data_sources": [copy.deepcopy(UHS), confirmed, policy], "availability_statement": None}
before = copy.deepcopy(report)
new = agent.recover_report(pages, report, ask=fake_model([
    {"action": "submit_evidence", "category": "restricted", "quote": NAMED, "page": NAMED_PAGE}]))
check("整份报告：只调查“未确认”的数据源，已确认的和政策信息跳过",
      [s["agent"]["outcome"] for s in new["data_sources"]] == ["recovered", "skipped", "skipped"])
s0 = new["data_sources"][0]
check("找到证据后：分类、证据、验证状态一起更新，并写明是 Agent 找到的",
      s0["access_category"] == "restricted" and s0["verification"] == "verified" and "Agent" in s0["rule_notes"][-1])
check("不改动原来的报告（基础流程的结果保留，方便对比）", report == before)
new = agent.recover_report(pages, copy.deepcopy(before), ask=fake_model([SystemExit("busy")]))
check("模型失败时：分类保持“未确认”", new["data_sources"][0]["access_category"] == "unknown")

# --- 对比评估（evaluate.py --agent）：改对、改错要分开数，误判公开要单独数 ---
import contextlib, io, json, os, tempfile
import evaluate
truth = json.load(open("ground_truth.json", encoding="utf-8"))
uhs_unknown = {**UHS, "access_category": "unknown"}
met = {**UHS, "name": "daily meteorological data", "provider": "Chinese National Meteorological Information Center",
       "source_evidence": {"quote": "The daily meteorological data of China comes from the Chinese National Meteorological Information Center.", "page": 3}}
base = {"data_sources": [uhs_unknown, met], "availability_statement": None, "sample_limitations": []}
after = copy.deepcopy(base)
after["data_sources"][0].update(access_category="restricted", agent={"outcome": "recovered", "steps": [{}, {}]})
after["data_sources"][1].update(access_category="public", agent={"outcome": "recovered", "steps": [{}]})
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "deng2020_x.json")
    json.dump({"source_file": "results/deng2020_1105_093521_run1.json", "base_report": base, "agent_report": after},
              open(path, "w", encoding="utf-8"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        evaluate.compare_agent([path], truth)
    out = buf.getvalue()
check("对比评估：Agent 把“未确认”改成正确的分类 → 记为改对", "Urban Household Survey (UHS)：论文未说明 → 受限  【改对】" in out)
check("对比评估：改成错误的分类 → 记为改错，并显示标准答案", "daily meteorological data：论文未说明 → 公开  【改错" in out)
check("对比评估：Agent 造成的误判公开会被单独数出来（不会被总分掩盖）",
      [l for l in out.splitlines() if l.startswith("误判为公开")][0].split()[1:3] == ["0", "1"])

print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
