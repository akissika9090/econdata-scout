"""重置：步数用完后再查一次，两次尝试的记录都保留（2026-11-19 合入）。python3 experiments/agent_round/test_variant_reset.py"""
import importlib.util, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
REL = os.path.join(os.path.dirname(ROOT), "econdata-scout")
def load(n, path_first):
    sys.path.insert(0, HERE)
    sp = importlib.util.spec_from_file_location(n, os.path.join(HERE, "official_check.py")); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    return m

OFF = "https://stats.example.gov/data"      # 官方页面（会被认定为官方站点）
DEAD = "https://stats.example.gov/dead"     # 官方域名、读不到 → 线索
SRC = {"name": "Example Household Survey", "provider": "Example Statistics Agency", "study_area": None, "urls": [],
       "version": None, "sample_period": None}
class FakeWeb:
    def fetch(self, url, timeout=25, deepseek_retry=True):
        if url == DEAD: return {"url": url, "error": "HTTP 503"}
        if url.startswith(OFF):
            return {"url": url, "final_url": url, "title": "Example Household Survey", "method": "direct", "fetched_on": "2026-11-19",
                    "text": "Example Household Survey by Example Statistics Agency. Microdata can be downloaded free of charge from this page.",
                    "links": [{"url": OFF + "/files", "text": "files"}]}
        return {"url": url, "error": "not found"}
    def search(self, q, count=8): return {"results": [{"url": OFF, "title": "t", "snippet": ""}]}

def first_attempt(n=12):   # 12 步都在读（每步不同网址），最后一步提交了被退回的结论
    decs = [{"action": "read_page", "url": OFF}, {"action": "read_page", "url": DEAD}]
    decs += [{"action": "read_page", "url": f"{OFF}?p={i}"} for i in range(n - 3)]
    decs += [{"action": "submit_finding", "url": OFF, "channel": "public_download", "eligibility": "not_stated",
              "check_result": "same_version_found", "access_quote": "this sentence is not on the page"}]
    return decs
FOUND = {"action": "submit_finding", "url": OFF, "channel": "public_download", "eligibility": "individuals",
         "check_result": "same_version_found", "access_quote": "Microdata can be downloaded free of charge from this page.",
         "version_quote": "Example Household Survey"}
class Boom(Exception): pass
def scripted(decs, seen_prompts):
    it = iter(decs)
    def ask(system, content):
        seen_prompts.append(content)
        d = next(it, None)
        if d == "ERROR": raise Boom("model call failed")
        if d == "SLOW": time.sleep(5); return {"action": "give_up"}, "f"
        if d is None: raise Boom("script ended")
        return d, "f"
    return ask

results = []
def check(name, cond, info=""):
    results.append(cond); print(("✓ " if cond else "✗ ") + name + ("" if cond else f"\n    {info}"))

for M in (load("v3_reset", HERE),):
    print(f"== {M.__name__}"); start = len(results)
    kw = {"time_limit": None}
    # 1 第二次找到
    pr = []; res = M.run_check(SRC, FakeWeb(), {"domains": []}, ask=scripted(first_attempt() + [FOUND], pr), **kw)
    a1 = [s for s in res["steps"] if s.get("attempt") == 1]
    check("1 第二次找到：结论已核实；第一次的 12 步仍在结果里", res["outcome"] == "found" and len(a1) == 12, (res["outcome"], len(res["steps"])))
    check("1 标明结论来自第二次尝试", res.get("verified_in") == 2, res.get("verified_in"))
    # 2 第二次放弃：第一次读过的页面、官方站点、线索都在
    pr = []; res = M.run_check(SRC, FakeWeb(), {"domains": []}, ask=scripted(first_attempt() + [{"action": "give_up", "reason": "nothing"}], pr), **kw)
    check("2 第二次放弃：保留第一次读过的页面", OFF in (res.get("read") or {}), list(res.get("read") or {})[:3])
    check("2 保留第一次认定的官方站点", OFF in (res.get("official_sites") or []), res.get("official_sites"))
    check("2 保留第一次读不到的官方入口（线索）", DEAD in (res.get("leads") or {}), list(res.get("leads") or {}))
    check("2 两次的结果和失败原因都列出", [a.get("outcome") for a in res.get("attempts") or []] == ["budget_exhausted", "not_found"]
          and (res["attempts"][1].get("reason") == "nothing"), res.get("attempts"))
    check("2 第二次的提示里有第一次被退回的提交和原因", any("Submissions rejected" in p and "not found word-for-word" in p for p in pr[12:13]), pr[12][-600:] if len(pr) > 12 else pr)
    # 3 第二次模型出错：结论按第一次，错误照记，第一次的依据不丢
    pr = []; res = M.run_check(SRC, FakeWeb(), {"domains": []}, ask=scripted(first_attempt() + ["ERROR"], pr), **kw)
    check("3 第二次出错：结论按第一次（步数用完），记下第二次的错误，第一次依据保留",
          res["outcome"] == "budget_exhausted" and "model call failed" in str(res.get("second_attempt_error") or res.get("reset"))
          and OFF in (res.get("official_sites") or []) and len(res["steps"]) == 12, (res["outcome"], res.get("reset"), res.get("second_attempt_error")))
    # 4 读不到的入口 → 手动核对时第一次的线索在列
    res = M.mark_manual(M.run_check(SRC, FakeWeb(), {"domains": []}, ask=scripted(first_attempt() + [{"action": "give_up"}], []), **kw))
    check("4 手动核对列出第一次读不到的官方入口", res["outcome"] == "manual_check" and DEAD in res["leads"], (res["outcome"], list(res.get("leads") or {})))
    # 4b 第二次失败后，报告（step3）里仍显示第一次读过的官方页面和读不到的入口
    import step3_merge as step3
    res = M.run_check(SRC, FakeWeb(), {"domains": []}, ask=scripted(first_attempt() + [{"action": "give_up", "reason": "nothing"}], []), **kw)
    shown = " ".join(step3.unanswered_leads(res))
    check("4b 第二次失败后，报告的线索里有第一次的页面", OFF in shown, shown[:300])
    # 5 第二次超时（v3 有总时限）：标 timed_out，第一次依据保留
    if M.__name__ == "v3_reset":
        res = M.run_check(SRC, FakeWeb(), {"domains": []}, ask=scripted(first_attempt() + ["SLOW"], []), time_limit=1.5)
        check("5 第二次超时：timed_out，第一次依据保留", res["outcome"] == "timed_out" and OFF in (res.get("official_sites") or [])
              and DEAD in (res.get("leads") or {}), (res["outcome"], res.get("attempts")))
    print(f"{M.__name__}: {sum(results[start:])}/{len(results) - start} 通过\n"); v3 = results[start:]
sys.exit(0 if all(v3) else 1)
