"""总时限的资源检查（2026-11-19 本人要求）：超时返回后，后台线程是否还在请求、重试或等待；是否还会发出付费请求；
批量运行会不会累积线程。时限 2 秒；“截止后”的请求 = 截止时间之后才发出的请求（截止时已在进行中的那一次不算新请求）。
python3 test_time_resources.py（在本目录运行，用本目录的 official_check / web_tools / deepseek_client / time_budget）"""
import os, sys, tempfile, threading, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
os.environ["DEEPSEEK_API_KEY"] = "test-key"
import official_check as oc, web_tools, deepseek_client
assert os.path.dirname(oc.__file__) == HERE and os.path.dirname(web_tools.__file__) == HERE
LIMIT, GRACE = 2.0, 3.0
results = []
def check(name, cond, info=""):
    cond = bool(cond); results.append(cond); print(("✓ " if cond else "✗ ") + name + ("" if cond else f"\n    {info}"))

class Log:
    def __init__(self): self.events = []
    def add(self, kind): self.events.append((time.monotonic(), kind))
    def after(self, t, kind=None): return [e for e in self.events if e[0] > t and (kind is None or e[1] == kind)]

class R503:
    status_code, text, headers = 503, "busy", {}
    def json(self): return {}

class ModelSession:   # DeepSeek 对话一直 503，每次请求耗时 0.8 秒
    def __init__(self, log): self.log = log
    def post(self, url, **k): self.log.add("chat"); time.sleep(0.8); return R503()

class DripResp:   # 慢慢滴数据：每 0.3 秒给一块，共 60 块
    status_code, headers, url = 200, {"Content-Type": "text/html"}, "https://example.gov/data"
    apparent_encoding = "utf-8"
    def __init__(self, log): self.log, self.closed = log, False
    def iter_content(self, n):
        for i in range(60):
            if self.closed: return
            time.sleep(0.3); self.log.add("chunk"); yield b"<p>data data data data</p>" * 10
    def close(self): self.closed = True; self.log.add("close")

class R302:
    status_code, url = 302, ""
    def __init__(self, loc): self.headers = {"Location": loc}
    def close(self): pass

class PageSession:
    def __init__(self, log, mode): self.log, self.mode, self.n = log, mode, 0
    def get(self, url, timeout=None, allow_redirects=True, stream=False, **k):
        self.log.add("get"); self.n += 1
        if self.mode == "drip": return DripResp(self.log)
        if self.mode == "redirect": time.sleep(0.4); return R302(f"https://example.gov/hop{self.n}")
        raise ConnectionError("refused")
    def post(self, url, **k):   # DeepSeek Fetch：一直 503
        self.log.add("tools"); time.sleep(0.3); return R503()

SRC = {"name": "Test Data", "provider": "Test Agency", "study_area": None, "urls": []}
READ = {"action": "read_page", "url": "https://example.gov/data"}
def script(*decs):
    it = iter(decs); return lambda s, c: (next(it), "fake")

def run(src, ask, web):
    t0 = time.monotonic(); res = oc.run_check(src, web, {"domains": []}, ask=ask, time_limit=LIMIT)
    return res, t0 + LIMIT, time.monotonic() - t0

base_threads = threading.active_count()
# 1 模型重试：截止后不再发 DeepSeek 请求
log = Log(); deepseek_client.RETRY_WAITS = [0, 0.5, 0.5, 0.5, 0.5, 0.5]
ask = lambda s, c: deepseek_client.generate_json(s, c, session=ModelSession(log), sleep=time.sleep)
res, deadline, el = run(SRC, ask, web_tools.Web(cache_dir=tempfile.mkdtemp(), offline=True)); time.sleep(GRACE)
check("1 模型调用重试：按时返回，截止后发出的 DeepSeek 请求 0 次", res["outcome"] == "timed_out" and el <= LIMIT + 0.5
      and not log.after(deadline, "chat"), (res["outcome"], el, len(log.events), log.after(deadline)))
# 2 慢速网页：截止后最多再收到 1 块，连接被关闭
log = Log()
res, deadline, el = run(SRC, script(READ), web_tools.Web(cache_dir=tempfile.mkdtemp(), session=PageSession(log, "drip"), deepseek_key=""))
time.sleep(GRACE)
check("2 慢速网页：按时返回，截止后最多再读 1 块并关闭连接", res["outcome"] == "timed_out" and el <= LIMIT + 0.5
      and len(log.after(deadline, "chunk")) <= 1 and log.after(deadline - 0.5, "close"),
      (res["outcome"], el, len(log.after(deadline, "chunk")), [e[1] for e in log.events][-3:]))
# 3 重定向链：截止后不再发起新的跳转
log = Log()
res, deadline, el = run(SRC, script(READ), web_tools.Web(cache_dir=tempfile.mkdtemp(), session=PageSession(log, "redirect"), deepseek_key=""))
time.sleep(GRACE)
check("3 重定向链：按时返回，截止后新发起的请求 0 次", res["outcome"] == "timed_out" and el <= LIMIT + 0.5 and not log.after(deadline, "get"),
      (el, len(log.events), len(log.after(deadline, "get"))))
# 4 直接读取失败 → DeepSeek Fetch 及其重试：截止后不再发付费请求
log = Log(); web_tools.RETRY_WAITS = [0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
res, deadline, el = run(SRC, script(READ), web_tools.Web(cache_dir=tempfile.mkdtemp(), session=PageSession(log, "fail"), deepseek_key="x"))
time.sleep(GRACE)
check("4 DeepSeek Fetch 重试：按时返回，截止后发出的付费请求 0 次", res["outcome"] == "timed_out" and el <= LIMIT + 0.5
      and not log.after(deadline, "tools"), (res["outcome"], el, len(log.after(deadline, "tools"))))
# 5 兜底搜索（DeepSeek 检索一直 503）：截止后不再发付费请求
log = Log()
CN = {"name": "China City Statistical Yearbook (2010)", "provider": "National Bureau of Statistics", "study_area": "China", "urls": []}
res, deadline, el = run(CN, script({"action": "give_up"}), web_tools.Web(cache_dir=tempfile.mkdtemp(), session=PageSession(log, "fail"), deepseek_key="x"))
time.sleep(GRACE)
check("5 兜底搜索：截止后发出的付费请求 0 次，结果保留 Agent 的结论", el <= LIMIT + 0.5 and not log.after(deadline, "tools")
      and res["outcome"] == "not_found", (res["outcome"], el, res.get("fallback"), len(log.after(deadline, "tools"))))
check("6 以上 5 次运行结束后，后台线程全部退出（不累积）", threading.active_count() == base_threads, (threading.active_count(), base_threads))
# 7 批量：连续 8 个超时的数据源
logs = []
for i in range(8):
    lg = Log(); logs.append(lg)
    oc.run_check(SRC, web_tools.Web(cache_dir=tempfile.mkdtemp(), session=PageSession(lg, "drip"), deepseek_key=""), {"domains": []},
                 ask=script(READ), time_limit=0.6)
peak = threading.active_count()
time.sleep(GRACE)
check("7 批量 8 个超时：结束后线程回到基线", threading.active_count() == base_threads, (peak, threading.active_count(), base_threads))
check("8 run_check 结束后没有残留的截止时间", oc.remaining() is None)
print(f"\n{sum(results)}/{len(results)} 通过")
sys.exit(0 if all(results) else 1)
