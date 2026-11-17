"""
Evidence Recovery Agent V1：基础流程结束后，对获取条件仍为“未确认”的数据源，让模型自己回到 PDF 里找证据。

一个数据源的调查过程（循环，每一步都写进行动日志）：
    1. 模型看到：这个数据源是什么、基础流程为什么没能确认、之前每一步做了什么和看到了什么
    2. 模型决定下一步：search_pdf / read_page / submit_evidence / give_up（按固定的 JSON 格式回答）
    3. 程序执行工具，把结果交回给模型
    4. 停止条件：提交的证据被程序核对通过（recovered）；模型判断原文确实没写，主动放弃（gave_up）；
       步数用完（budget_exhausted）；模型调用失败（agent_error）
       → 除了 recovered，其他情况都保留基础流程的结果，“未确认”仍是“未确认”

安全设计：
    - 模型不能直接改分类。只有 submit_evidence 的证据通过程序核对（和基础流程完全相同的规则），分类才会改变
    - 同样的工具和参数不会执行第二次（防止原地打转），但同样计入步数
    - 工具出错、模型返回格式不对，都作为一步记下来，不让程序崩溃

运行（需要 GEMINI_API_KEY）：
    python agent.py results/deng2020_1105_093521_run1.json   用已保存的 AI 提取结果（不再调用提取，只调用 Agent）
    python agent.py --latest                                 对每篇论文最新的一次结果运行（用于对比评估）
结果保存在 agent_runs/，用 python evaluate.py --agent agent_runs/*.json 和基础流程对比打分（不再调用 API）
"""

import copy
import json
import os
import re
import sys
from datetime import datetime

import agent_tools as tools
import gemini_client
import step1_pdf_evidence as step1
import step2_ai_extract as step2

MAX_STEPS = 6            # 每个数据源最多几步（每一步是一次模型调用）
MAX_OBSERVATION = 1500   # 放进提示词的每条工具结果最多多少字符
ACTIONS = ["search_pdf", "read_page", "submit_evidence", "give_up"]

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "action": {"type": "string", "enum": ACTIONS},
        "query": {"type": ["string", "null"]},
        "page": {"type": ["integer", "null"]},
        "category": {"type": ["string", "null"]},
        "quote": {"type": ["string", "null"]},
    },
    "required": ["thought", "action", "query", "page", "category", "quote"],
}

SYSTEM_PROMPT = """You are an evidence-recovery agent for economics research. You investigate ONE data source used in ONE paper.
Goal: find a sentence in the paper that explicitly states how this data source can be accessed:
    public       = the paper says it is publicly / freely available
    subscription = the paper says it requires a subscription, purchase or licence
    restricted   = the paper says it is confidential, not public, or available only on request / with permission
Each step, choose exactly one action:
    search_pdf      query = 1-5 keywords (e.g. "publicly available", "upon request", the dataset's name or acronym)
    read_page       page = page number; query = optional word to jump to on that page
    submit_evidence category, quote, page = a sentence copied word-for-word from a tool result, and its page
                    (a program checks it with fixed rules; you will see whether it was accepted and why not)
    give_up         when the paper does not state the access condition for this data source
Rules:
1. Use only what the tools show you. Do not use background knowledge about the database.
2. A sentence about the paper's data in general, about another dataset, or only a URL, is not enough.
3. Giving up is a correct outcome when the paper does not say. Do not submit weak evidence just to finish.
4. Do not repeat an action you have already taken with the same arguments.
5. Keep "thought" to one short sentence. Output JSON only."""


def describe_source(src: dict, n_pages: int, statement: dict | None) -> str:
    """给模型的任务说明：这个数据源是什么，基础流程为什么没能确认。"""
    se = src.get("source_evidence") or {}
    lines = [f"Data source: {src.get('name')}",
             f"Provider: {src.get('provider') or 'not stated'}",
             f"Where the paper mentions it: page {se.get('page')}: \"{se.get('quote', '')}\"",
             f"The paper has {n_pages} pages."]
    if src.get("verification") == "none":
        lines.append("First extraction: the access condition was judged as not stated in the paper.")
    else:
        ae = src.get("access_evidence") or {}
        lines.append(f"First extraction: judged '{src.get('ai_category')}' but the evidence was rejected "
                     f"({step2.VERIFICATION_LABELS_ZH.get(src.get('verification'), src.get('verification'))}); "
                     f"rejected quote: \"{ae.get('quote', '')}\" (page {ae.get('page')})")
    if statement:
        lines.append(f"The paper's data availability statement (page {statement.get('page')}): \"{statement.get('quote')}\"")
    return "\n".join(lines)


def action_key(decision: dict) -> tuple:
    """用来识别“同样的工具和参数”：大小写、多余空白不同也算同一个。"""
    norm = lambda x: re.sub(r"\s+", " ", str(x)).strip().lower() if x is not None else None
    return (decision.get("action"), norm(decision.get("query")), decision.get("page"),
            norm(decision.get("category")), norm(decision.get("quote")))


def ask_model(system: str, content: str) -> tuple[dict, str]:
    return gemini_client.generate_json(system, content, ACTION_SCHEMA)


def run_agent(pages: list[str], src: dict, statement: dict | None = None,
              max_steps: int = MAX_STEPS, ask=ask_model, others: list[dict] | None = None) -> dict:
    """调查一个数据源。返回 {outcome, category, evidence, steps}。
    ask 只在测试时替换成假模型，平时不用传。"""
    task = describe_source(src, len(pages), statement)
    steps, seen = [], set()
    for n in range(1, max_steps + 1):
        history = "\n\n".join(f"Step {s['step']}: {s['action']} {json.dumps(s['args'], ensure_ascii=False)}\n"
                              f"Result: {s['observation'][:MAX_OBSERVATION]}" for s in steps)
        content = f"{task}\n\n{history or '(no steps yet)'}\n\nSteps left (including this one): {max_steps - n + 1}"
        try:
            decision, model = ask(SYSTEM_PROMPT, content)
        except (Exception, SystemExit) as e:   # 模型调用失败：停下，保留基础流程的结果
            return {"outcome": "agent_error", "error": str(e)[:300], "steps": steps}
        if not isinstance(decision, dict):    # 合法的 JSON，但不是对象（如 []）：同样按调用失败处理
            return {"outcome": "agent_error", "error": f"model returned {type(decision).__name__}, not a JSON object",
                    "steps": steps}
        action = decision.get("action")
        args = {k: decision.get(k) for k in ("query", "page", "category", "quote") if decision.get(k) is not None}
        step = {"step": n, "model": model, "thought": decision.get("thought", ""), "action": action, "args": args}
        steps.append(step)
        if action == "give_up":
            step["observation"] = "Stopped: the agent judged that the paper does not state the access condition."
            return {"outcome": "gave_up", "steps": steps}
        key = action_key(decision)
        if key in seen:
            step["observation"] = "Not executed: you already did exactly this. Try something different, or give_up."
            continue
        seen.add(key)
        try:
            if action == "search_pdf":
                step["observation"] = tools.search_pdf(pages, decision.get("query"))
            elif action == "read_page":
                step["observation"] = tools.read_page(pages, decision.get("page"), decision.get("query"))
            elif action == "submit_evidence":
                ok, message, evidence = tools.submit_evidence(pages, src, decision.get("category"), decision.get("quote"),
                                                              decision.get("page"), statement, others)
                step["observation"] = message
                if ok:
                    return {"outcome": "recovered", "category": decision["category"], "evidence": evidence, "steps": steps}
            else:
                step["observation"] = f"Error: unknown action {action!r}. Use one of {', '.join(ACTIONS)}."
        except Exception as e:   # 工具出错：记下来，告诉模型，继续下一步
            step["observation"] = f"Error: the tool failed ({type(e).__name__}). Try a different action."
    return {"outcome": "budget_exhausted", "steps": steps}


def should_investigate(src: dict) -> str | None:
    """哪些数据源交给 Agent：获取条件仍为“未确认”的。返回跳过的原因，或 None（要调查）。
    政策信息（试点名单、实施时间等）本来就不是“获取条件”的问题，跳过，节省调用次数。"""
    if src.get("access_category") != "unknown":
        return "already confirmed by the base workflow"
    if src.get("kind") == "policy_info":
        return "policy information, not a dataset"
    return None


def recover_report(pages: list[str], report: dict, max_steps: int = MAX_STEPS, ask=ask_model) -> dict:
    """对一份基础流程的报告运行 Agent，返回新报告（不改动原报告）。
    每个数据源加上 agent 字段（结果、步数、行动日志）；只有 recovered 时才改变获取条件分类。"""
    new = copy.deepcopy(report)
    statement = new.get("availability_statement")
    for src in new["data_sources"]:
        skip = should_investigate(src)
        if skip:
            src["agent"] = {"outcome": "skipped", "reason": skip, "steps": []}
            continue
        result = run_agent(pages, src, statement, max_steps=max_steps, ask=ask, others=new["data_sources"])
        src["agent"] = {k: v for k, v in result.items() if k not in ("category", "evidence")}
        if result["outcome"] == "recovered":
            src["access_category"] = result["category"]
            src["access_evidence"] = result["evidence"]
            src["verification"], src["evidence_scope"] = "verified", "direct"
            src["needs_review"] = False
            # Agent 只提交分类和引用，不判断适用范围 → 范围未确定（不默认为整个数据源）
            src["access_scope"], src["access_origin"] = "undetermined", "agent"
            src.pop("downgraded", None)   # 旧的“需要人工复核”说明已不再成立；模型的原始判断 ai_category 保留不改
            src["rule_notes"] = src.get("rule_notes", []) + [
                f"Agent 回查 PDF 找到证据（第{result['evidence']['page']}页），程序核对通过，分类改为“{step2.ACCESS_LABELS[result['category']]}”"]
    return new


OUTCOME_LABELS = {"recovered": "找到证据并通过核对", "gave_up": "判断原文没有说明，主动停止",
                  "budget_exhausted": "步数用完，未找到", "agent_error": "模型调用失败，保留原结果", "skipped": "跳过"}


def print_agent_summary(report: dict) -> None:
    print("\n=== Evidence Recovery Agent ===")
    for src in report["data_sources"]:
        a = src.get("agent") or {}
        print(f"\n- {src['name']}：{OUTCOME_LABELS.get(a.get('outcome'), a.get('outcome'))}"
              + (f"（{a['reason']}）" if a.get("reason") else "") + (f"，{len(a['steps'])} 步" if a.get("steps") else ""))
        for s in a.get("steps", []):
            print(f"    {s['step']}. {s['action']} {json.dumps(s['args'], ensure_ascii=False)[:120]}")
            print(f"       想法：{s['thought'][:120]}")
            print(f"       结果：{s['observation'].splitlines()[0][:120]}")
        if a.get("outcome") == "recovered":
            ev = src["access_evidence"]
            print(f"    → 最终分类：{step2.ACCESS_LABELS[src['access_category']]}，第{ev['page']}页：{ev['quote']}")


def run_file(path: str) -> str:
    """对一份已保存的 AI 提取结果运行 Agent，保存基础报告、Agent 报告和完整行动日志，返回保存的路径。"""
    import step3_merge as step3
    info = step3.parse_result_name(path)
    if info is None:
        raise SystemExit(f"文件名不符合 results/ 的命名格式：{path}")
    pages, _ = step1.extract_pages(f"papers/{info['paper']}.pdf")
    with open(path, encoding="utf-8") as f:
        base = step2.verify_result(pages, json.load(f)["ai_raw"])   # 用当前规则重新核对，作为 Agent 的起点
    agent_report = recover_report(pages, base)
    print(f"\n##### {info['paper']}（{os.path.basename(path)}）")
    print_agent_summary(agent_report)
    os.makedirs("agent_runs", exist_ok=True)
    out = os.path.join("agent_runs", f"{info['paper']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source_file": path, "base_report": base, "agent_report": agent_report}, f, ensure_ascii=False, indent=2)
    print(f"\n结果和完整的行动日志已保存到 {out}")
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("用法：python agent.py results/论文_日期_时间_runN.json [更多文件...]")
        print("      python agent.py --latest [论文名 ...]   对每篇论文最新的一次结果运行（可只指定几篇）")
        raise SystemExit(1)
    if args[0] == "--latest":
        import step3_merge as step3
        paths = list(step3.latest_results(args[1:] or None).values())
    else:
        paths = args
    print(f"将对 {len(paths)} 份结果运行 Agent（每个未确认的数据源最多 {MAX_STEPS} 次模型调用）")
    for path in paths:
        run_file(path)
