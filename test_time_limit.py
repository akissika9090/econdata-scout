"""总时限（2026-11-19 合入）。用发布版的 web_tools（econdata-scout），模拟慢响应、重定向、重试、兜底搜索。
python3 experiments/agent_round/test_variant_timeout.py"""
import importlib.util, os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
REL = HERE
sys.path.insert(0, REL)   # 发布版的 web_tools / gemini_client
import web_tools
assert os.path.dirname(web_tools.__file__) == REL
sp = importlib.util.spec_from_file_location("v2", os.path.join(HERE, "official_check.py")); oc = importlib.util.module_from_spec(sp); sp.loader.exec_module(oc)
LIMIT, SLACK = 2.0, 0.5
results = []
def check(name, cond, info=""):
    results.append(cond); print(("✓ " if cond else "✗ ") + name + ("" if cond else f"\n    {info}"))

SRC = {"name": "Test Data", "provider": "Test Agency", "study_area": None, "urls": []}
CN = {"name": "China City Statistical Yearbook (2010)", "provider": "National Bureau of Statistics", "study_area": "China", "urls": []}
def script(*decs):
    it = iter(decs)
    return lambda system, content: (next(it), "fake")
READ = {"action": "read_page", "url": "https://example.gov/data"}
GIVE_UP = {"action": "give_up", "reason": "none"}

class Resp:
    status_code, headers, url, encoding = 200, {"content-type": "text/html"}, "https://example.gov/data", "utf-8"
    content = b"<html><title>t</title><body>Download the data here.</body></html>"
    text = content.decode()
    apparent_encoding = "utf-8"
    def raise_for_status(self): pass

class SlowSession:
    """get：模拟重定向链 + 慢慢滴数据（每一跳都没超过单次 timeout，但合计很长）；post：DeepSeek 一直 503。"""
    headers = {}
    def __init__(self, hops=10, per_hop=0.5): self.hops, self.per_hop, self.posts = hops, per_hop, 0
    def get(self, url, timeout=None, allow_redirects=True, **k):
        for _ in range(self.hops): time.sleep(self.per_hop)
        return Resp()
    def post(self, *a, **k):
        self.posts += 1
        class R: status_code = 503; text = "busy"
        def bad(): raise RuntimeError("503")
        R.raise_for_status = staticmethod(bad); R.json = staticmethod(lambda: {})
        return R()

def run(src, ask, web, limit=LIMIT):
    t = time.monotonic(); res = oc.run_check(src, web, {"domains": []}, ask=ask, time_limit=limit); return res, time.monotonic() - t

tmp = tempfile.mkdtemp()
# 1 慢模型：一次调用就超过时限
def slow_model(system, content): time.sleep(5); return GIVE_UP, "fake"
res, el = run(SRC, slow_model, web_tools.Web(cache_dir=tmp, offline=True))
check("1 慢模型 → timed_out，在时限内返回，记下“model call”", res["outcome"] == "timed_out" and el <= LIMIT + SLACK
      and "model call" in (res["timing"]["stopped_by"] or ""), (res["outcome"], el, res.get("timing")))
# 2 模型内部重试（每次失败后等待）：总耗时也受限
def retrying_model(system, content):
    for wait in (1, 2, 4):
        time.sleep(wait)
    return GIVE_UP, "fake"
res, el = run(SRC, retrying_model, web_tools.Web(cache_dir=tmp, offline=True))
check("2 模型重试等待 → timed_out，在时限内", res["outcome"] == "timed_out" and el <= LIMIT + SLACK, (res["outcome"], el))
# 3 慢响应 + 重定向链（真实 Web 类，假 session）：每跳 0.5 秒、10 跳
web = web_tools.Web(cache_dir=tempfile.mkdtemp(), session=SlowSession(), deepseek_key="")
res, el = run(SRC, script(READ, GIVE_UP), web)
check("3 慢响应 / 重定向 → timed_out，在时限内，记下读取哪个网页", res["outcome"] == "timed_out" and el <= LIMIT + SLACK
      and "reading https://example.gov/data" in (res["timing"]["stopped_by"] or "") and len(res["steps"]) == 1,
      (res["outcome"], el, res.get("timing")))
# 4 直接读取失败后走 DeepSeek Fetch 及其重试等待（RETRY_WAITS）
class FailGet(SlowSession):
    def get(self, *a, **k): raise ConnectionError("refused")
sess = FailGet()
web = web_tools.Web(cache_dir=tempfile.mkdtemp(), session=sess, deepseek_key="x")
res, el = run(SRC, script(READ, GIVE_UP), web)
check("4 DeepSeek Fetch 重试等待 → timed_out，在时限内", res["outcome"] == "timed_out" and el <= LIMIT + SLACK, (res["outcome"], el, res.get("timing")))
# 5 兜底搜索（中国纸质统计资料）慢：Agent 已结束，兜底到时停下，保留 Agent 的结果
class SlowSearchWeb(web_tools.Web):
    def search(self, q, count=8): time.sleep(5); return {"results": []}
res, el = run(CN, script(GIVE_UP), SlowSearchWeb(cache_dir=tempfile.mkdtemp(), offline=True))
check("5 兜底搜索慢 → 在时限内停下，结果保持 not_found，注明兜底被时限中止", res["outcome"] == "not_found" and el <= LIMIT + SLACK
      and (res.get("fallback") or "").startswith("stopped") and "fallback" in (res["timing"]["stopped_by"] or ""),
      (res["outcome"], el, res.get("fallback"), res.get("timing")))
# 6 正常：很快结束，记录耗时，没有到时原因
res, el = run(SRC, script(GIVE_UP), web_tools.Web(cache_dir=tmp, offline=True))
check("6 正常结束：记录实际耗时，stopped_by 为空", res["outcome"] == "not_found" and res["timing"]["stopped_by"] is None
      and res["timing"]["limit"] == LIMIT and res["timing"]["seconds"] < 1, res.get("timing"))
# 7 结束后不留截止时间；time_limit=None（离线回放）照常执行
check("7 run_check 结束后没有残留的截止时间", oc.remaining() is None)
def slowish(system, content): time.sleep(0.2); return GIVE_UP, "fake"
res, el = run(SRC, slowish, web_tools.Web(cache_dir=tmp, offline=True), limit=None)
check("7 time_limit=None 不设时限", res["outcome"] == "not_found" and res["timing"]["limit"] is None)
# 8 报告一行写清到时原因
line = oc.summary_line(SRC, run(SRC, slow_model, web_tools.Web(cache_dir=tmp, offline=True))[0])
check("8 结论写明时限、到时原因，且不说成“没找到”", "time limit (2.0 s)" in line and "model call" in line and "does not mean unavailable" in line, line)
# 9 多步累计：每步都不慢，但合计超过时限
def each(system, content): time.sleep(0.4); return {"action": "search_web", "query": f"q{time.monotonic()}"}, "fake"
res, el = run(SRC, each, web_tools.Web(cache_dir=tmp, offline=True))
check("9 多步累计超时 → timed_out，在时限内", res["outcome"] == "timed_out" and el <= LIMIT + SLACK, (res["outcome"], el, res.get("timing")))
import step3_merge as step3
res = run(SRC, slow_model, web_tools.Web(cache_dir=tmp, offline=True))[0]
label = step3.NOT_FOUND_LABELS.get(res["outcome"], "")
check("10 报告（step3）把时限内未查完写成“未查完”，不是“没找到”", "not checked to the end" in label and res["outcome"] in step3.CHECK_FAILED, label)
print(f"\n{sum(results)}/{len(results)} 通过")
sys.exit(0 if all(results) else 1)
