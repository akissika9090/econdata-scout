"""
V2 官网核查的离线测试：假网页（临时缓存）+ 假模型，不联网、不调用 API。

检查的是程序核对能不能拦住错误：非官方网站、引文不在页面上、没有版本依据却说同一版本、编造的使用限制；
以及入口发现方式的记录、官方域名的自动记录、模型失败和步数用完时的回退。

运行：
    python test_official.py
"""

import tempfile

import official_check as oc
from web_tools import Web, decode_html, html_to_text, quote_in_text

failures = 0


def check(name, ok, detail=""):
    global failures
    print(f"{'✓' if ok else '✗'}  {name}" + ("" if ok else f"\n     相关内容：{str(detail)[:500]}"))
    if not ok:
        failures += 1


try:   # 内部评估脚本（不在公开包里）：没有它时，评分相关的检查跳过
    import run_official as ro
except ImportError:
    ro = None
    print("-  run_official.py not in this package: scoring checks skipped")


def fake_model(decisions):
    it = iter(decisions)

    def ask(system, content):
        return next(it), "fake-model"
    return ask


def make_web(pages: dict, searches: dict | None = None) -> Web:
    web = Web(cache_dir=tempfile.mkdtemp(), offline=True, deepseek_key="")
    for url, (title, text, links) in pages.items():
        web._save("page", url, {"url": url, "final_url": url, "title": title, "text": text,
                                "links": [{"url": u, "text": t} for t, u in links], "method": "direct", "fetched_on": "2026-11-17",
                                "cache_v": 2})
    for q, results in (searches or {}).items():
        web._save("search", f"{q}|8", {"query": q, "results": [{"title": t, "url": u, "snippet": s, "authority": 3} for t, u, s in results]})
    return web


NVSS = {"name": "National Vital Statistics System", "provider": None, "version": "restricted data files",
        "version_verified": True, "sample_period": None, "urls": [], "access_category": "unknown"}
R_URL = "https://www.cdc.gov/nchs/nvss/nvss-restricted-data.htm"
R_TEXT = ("Restricted-Use Vital Statistics Data. Since 2005, national vital statistics micro-data files that include state, "
          "county, or larger city geography are no longer available without approval. Researchers may apply for access "
          "to restricted data files through the NCHS application process. Users must sign a data use agreement. "
          "National Vital Statistics System (NVSS).")
P_URL = "https://www.cdc.gov/nchs/data_access/vitalstatsonline.htm"
P_TEXT = "Vital Statistics Online. Public-use mortality data files can be downloaded free of charge. National Vital Statistics System."
BLOG = "https://some-data-blog.com/nvss-guide"
BLOG_TEXT = "A guide to NVSS data. Researchers can apply for the restricted data files through NCHS. National Vital Statistics System."   # v2.5d：原文要写明获取方式
PAGES = {R_URL: ("Restricted-Use Vital Statistics Data", R_TEXT, [("Application form", "https://apply.example.org/nchs")]),
         P_URL: ("Vital Statistics Online", P_TEXT, []),
         BLOG: ("NVSS guide", BLOG_TEXT, []),
         "https://apply.example.org/nchs": ("NCHS data request", "Submit your NCHS restricted data request here. Approved researchers only.", [])}
SEARCH = {"NVSS restricted data files county": [("Restricted-Use Vital Statistics Data", R_URL, "apply for access")]}


def submit(url, channel="apply_to_provider", result="same_version_found",
           aq="Researchers may apply for access to restricted data files through the NCHS application process.",
           vq="Researchers may apply for access to restricted data files through the NCHS application process.",
           restrictions=None, elig="researchers"):
    return {"thought": "", "action": "submit_finding", "url": url, "channel": channel, "eligibility": elig,
            "restrictions": restrictions or [], "check_result": result, "access_quote": aq, "version_quote": vq,
            "provider_quote": None}


# ---- 1. 正常路径：搜索 → 读官网 → 提交，通过核对；记录发现方式与官方域名 ----
web, learned = make_web(PAGES, SEARCH), {"domains": []}
res = oc.run_check(NVSS, web, learned, ask=fake_model([
    {"thought": "", "action": "search_web", "query": "NVSS restricted data files county"},
    {"thought": "", "action": "read_page", "url": R_URL},
    submit(R_URL, restrictions=["Users must sign a data use agreement."])]))
f = res.get("finding") or {}
check("1. 搜索找到官网、引文在页面上 → found；渠道“向提供方申请”、同一版本",
      res["outcome"] == "found" and f["channel"] == "apply_to_provider" and f["check_result"] == "same_version_found", res)
check("1. 入口发现方式记为 search", f.get("discovered_via") == "search", f.get("discovered_via"))
check("1. 使用限制逐字在页面上 → 保留", f.get("restrictions") == ["Users must sign a data use agreement."], f.get("restrictions"))
check("1. 核对通过的域名自动记下（cdc.gov）", any(d["domain"] == "cdc.gov" for d in learned["domains"]), learned)

# ---- 2. 非官方网站（博客）→ 拒绝 ----
web, learned = make_web(PAGES), {"domains": []}
res = oc.run_check(NVSS, web, learned, max_steps=2, ask=fake_model([
    {"thought": "", "action": "read_page", "url": BLOG},
    submit(BLOG, aq="Researchers can apply for the restricted data files through NCHS.", vq="Researchers can apply for the restricted data files through NCHS.")]))
f2 = res.get("finding") or {}
check("2. 博客页面（非机构域名）点名了数据 → v2.5 起只作为分发方接受：标 distributor，不算官方、不记入已核实官方域名",
      res["outcome"] == "found" and f2.get("evidence_source") == "distributor" and f2["official_basis"].startswith("distributor")
      and not learned["domains"], (res.get("finding"), learned))
blog_page = {"text": "A blog post about mortality.", "final_url": BLOG}
check("2. 非机构域名、页面也没点名这个数据 → 仍然拒绝",
      not oc.official_status(BLOG, blog_page, NVSS, {"domains": []}, set())[0])

# ---- 3. 引文不在页面上（编造）→ 拒绝 ----
web, learned = make_web(PAGES), {"domains": []}
res = oc.run_check(NVSS, web, learned, max_steps=2, ask=fake_model([
    {"thought": "", "action": "read_page", "url": R_URL},
    submit(R_URL, aq="NVSS restricted files are free to download for everyone.")]))
check("3. 编造的获取说明 → 拒绝", res["outcome"] != "found" and "not found word-for-word" in res["steps"][-1]["observation"],
      res["steps"][-1])

# ---- 4. 说“同一版本”却没有版本原文 → 降为“仅找到其他版本” ----
web, learned = make_web(PAGES), {"domains": []}
res = oc.run_check(NVSS, web, learned, ask=fake_model([
    {"thought": "", "action": "read_page", "url": P_URL},
    submit(P_URL, channel="public_download", aq="Public-use mortality data files can be downloaded free of charge.", vq=None)]))
f = res.get("finding") or {}
check("4. 公开版页面、没有写到受限文件的原文 → 不能算同一版本，记为 other_version_only",
      res["outcome"] == "found" and f["check_result"] == "other_version_only" and f["version_quote"] is None, f)

# ---- 5. 编造的使用限制 → 丢弃并说明 ----
web, learned = make_web(PAGES), {"domains": []}
res = oc.run_check(NVSS, web, learned, ask=fake_model([
    {"thought": "", "action": "read_page", "url": R_URL},
    submit(R_URL, restrictions=["only at a Research Data Center"])]))
f = res.get("finding") or {}
check("5. 页面上没有的使用限制 → 丢弃，留下说明",
      f.get("restrictions") == [] and any("dropped" in n for n in f.get("notes", [])), f)

# ---- 6. 官方页面链接过去的申请平台（非机构域名）→ 算官方；发现方式记为 link ----
web, learned = make_web(PAGES), {"domains": []}
res = oc.run_check(NVSS, web, learned, ask=fake_model([
    {"thought": "", "action": "read_page", "url": R_URL},
    {"thought": "", "action": "read_page", "url": "https://apply.example.org/nchs"},
    submit("https://apply.example.org/nchs", aq="Submit your NCHS restricted data request here.",
           vq="Submit your NCHS restricted data request here.")]))
f = res.get("finding") or {}
check("6. 官网链接过去的申请平台 → 通过；依据写明“由官方页面链接”；发现方式 link",
      res["outcome"] == "found" and "linked from an official page" in f["official_basis"] and f["discovered_via"] == "link", f)

# ---- 7. 模型凭记忆给的网址 → 照常核对，发现方式记为 model ----
web, learned = make_web(PAGES), {"domains": []}
res = oc.run_check(NVSS, web, learned, ask=fake_model([
    {"thought": "", "action": "read_page", "url": R_URL}, submit(R_URL)]))
check("7. 没有经过搜索、直接读的网址 → 发现方式记为 model", (res.get("finding") or {}).get("discovered_via") == "model", res)

# ---- 8. 网页读不到 → 拒绝，不写成结论 ----
web, learned = make_web(PAGES), {"domains": []}
res = oc.run_check(NVSS, web, learned, max_steps=1, ask=fake_model([submit("https://www.cdc.gov/not-cached.htm")]))
check("8. 程序读不到页面 → 拒绝（网页未能核对）", res["outcome"] != "found" and "could not read" in res["steps"][-1]["observation"],
      res["steps"])

# ---- 9. 放弃 / 模型失败 / 步数用完 ----
web, learned = make_web(PAGES), {"domains": []}
res = oc.run_check(NVSS, web, learned, ask=fake_model([{"thought": "", "action": "give_up", "reason": "no page"}]))
check("9. 模型放弃 → not_found，原因保留", res["outcome"] == "not_found" and res["reason"] == "no page", res)


def broken(system, content):
    raise RuntimeError("503")


res = oc.run_check(NVSS, web, learned, ask=broken)
check("9. 模型调用失败 → agent_error，不崩溃", res["outcome"] == "agent_error", res)
res = oc.run_check(NVSS, web, learned, max_steps=2, ask=fake_model([
    {"thought": "", "action": "read_page", "url": R_URL}, {"thought": "", "action": "read_page", "url": R_URL}]))
check("9. 重复同一个动作 → 不执行；步数用完 → budget_exhausted",
      res["outcome"] == "budget_exhausted" and "already did exactly this" in res["steps"][-1]["observation"], res["steps"])

# ---- 10. 以前核对通过的域名 → 下一次直接算官方，发现方式 learned ----
learned = {"domains": [{"domain": "cdc.gov", "label": "National Vital Statistics System | ", "first_verified": "2026-11-17"}]}
web = make_web(PAGES)
res = oc.run_check(NVSS, web, learned, ask=fake_model([{"thought": "", "action": "read_page", "url": R_URL}, submit(R_URL)]))
f = res.get("finding") or {}
check("10. 已记下的官方域名 → 依据为“以前核对通过的域名”，发现方式 learned",
      f.get("official_basis", "").startswith("previously verified") and f.get("discovered_via") == "learned", f)

# ---- 10b. 搜索返回镜像子域名（portugues.cdc.gov），模型读的是 www.cdc.gov 同一路径 → 仍记为 search ----
MIRROR = "https://portugues.cdc.gov/nchs/nvss/nvss-restricted-data.htm"
web, learned = make_web(PAGES, {"nvss mirror": [("Restricted-Use Vital Statistics Data", MIRROR, "")]}), {"domains": []}
res = oc.run_check(NVSS, web, learned, ask=fake_model([
    {"thought": "", "action": "search_web", "query": "nvss mirror"},
    {"thought": "", "action": "read_page", "url": R_URL}, submit(R_URL)]))
check("10b. 同一网站同一路径的镜像网址 → 发现方式仍记为 search", (res.get("finding") or {}).get("discovered_via") == "search", res)

# ---- 10c. 商业数据库：数据自己的域名（csmar.com = CSMAR）→ 算官方；名字相近的其他域名 → 不算 ----
CSMAR = {"name": "CSMAR database", "provider": None, "version": None, "sample_period": None, "urls": []}
C_TEXT = "CSMAR 中国经济金融研究数据库。机构用户可订阅数据库，校园网 IP 范围内自动登录。"
web = make_web({"https://www.csmar.com/": ("CSMAR", C_TEXT, []),
                "https://csmar-guide.net/": ("guide", C_TEXT, [])})
learned = {"domains": []}
res = oc.run_check(CSMAR, web, learned, ask=fake_model([
    {"thought": "", "action": "read_page", "url": "https://www.csmar.com/"},
    submit("https://www.csmar.com/", channel="subscription", result="other_version_only", elig="institution_must_apply",
           aq="机构用户可订阅数据库，校园网 IP 范围内自动登录。", vq=None)]))
check("10c. csmar.com 是 CSMAR 自己的域名、页面写着 CSMAR → 官方，渠道“订阅”",
      res["outcome"] == "found" and "own domain" in res["finding"]["official_basis"], res)
res = oc.run_check(CSMAR, web, {"domains": []}, max_steps=2, ask=fake_model([
    {"thought": "", "action": "read_page", "url": "https://csmar-guide.net/"},
    submit("https://csmar-guide.net/", channel="subscription", aq="机构用户可订阅数据库，校园网 IP 范围内自动登录。", vq=None)]))
check("10c. csmar-guide.net（名字相近的其他网站）→ 不算官方", res["outcome"] != "found", res["steps"][-1])

# ---- 10d. 连续两次搜索前几条结果相同 → 提醒模型不要再搜 ----
web = make_web(PAGES, {"a": [("R", R_URL, ""), ("P", P_URL, "")], "b": [("R", R_URL, ""), ("P", P_URL, "")]})
res = oc.run_check(NVSS, web, {"domains": []}, max_steps=2, ask=fake_model([
    {"thought": "", "action": "search_web", "query": "a"}, {"thought": "", "action": "search_web", "query": "b"}]))
check("10d. 第二次搜索结果和上一次相同 → 结果中提醒“再搜也没用”", res["steps"][1]["observation"].startswith("Same top results"),
      res["steps"][1]["observation"][:80])

# ---- 11. 工具函数 ----
import deepseek_client
check("11. 模型在 JSON 后面多输出一段 → 只取第一个 JSON 对象（CLDS 的 Extra data 错误）",
      deepseek_client.parse_first_json('{"action": "give_up"}\n{"action": "x"}') == {"action": "give_up"})


class _Resp:
    def __init__(self, status, ctype, body):
        self.status_code, self.headers, self.content, self.url, self.apparent_encoding = status, {"Content-Type": ctype}, body, "", "utf-8"


class _SSLFailSession:
    """https 抛出 SSLError，http 正常返回（证书链不完整的网站）。"""
    def get(self, url, **kw):
        if url.startswith("https://"):
            raise type("SSLError", (Exception,), {})("bad chain")
        body = ("<html><body><p>" + "中国家庭追踪调查数据申请说明。" * 20 + "</p></body></html>").encode("utf-8")
        r = _Resp(200, "text/html; charset=utf-8", body)
        r.url = url
        return r


w = Web(cache_dir=tempfile.mkdtemp(), session=_SSLFailSession(), deepseek_key="")
pg = w.fetch("https://www.isss.pku.edu.cn/cfps/")
check("11. https 证书错误 → 改用 http 读同一地址，读取方式注明 direct_http_fallback（不关闭证书验证）",
      pg.get("method") == "direct_http_fallback" and "中国家庭追踪调查" in pg.get("text", ""), pg)
gbk = '<html><head><meta charset="gbk"><title>国家统计局</title></head><body><p>国家统计局微观数据实验室</p></body></html>'.encode("gbk")
check("11. 响应头没写编码、页面 <meta charset=gbk> → 按 GBK 解码，中文不乱码（国家统计局页面的问题）",
      "国家统计局微观数据实验室" in decode_html(gbk, "text/html", "ISO-8859-1"))
utf = "<html><body>中国家庭追踪调查</body></html>".encode("utf-8")
check("11. 没有任何编码信息 → 用自动检测的结果", "中国家庭追踪调查" in decode_html(utf, "text/html", "utf-8"))
text, links = html_to_text('<html><body><script>x=1</script><p>Data are <b>available</b>.</p><a href="/apply">Apply</a></body></html>',
                           "https://a.gov/x")
check("11. HTML 转文字：跳过脚本，保留链接（相对地址转成绝对地址）",
      "x=1" not in text and "Data are available." in text and links == [{"url": "https://a.gov/apply", "text": "Apply"}], (text, links))
check("11. 引文核对：忽略换行、大小写、弯引号", quote_in_text("Data are “available”", "data   are\n\"available\""))
web = make_web({})
check("11. 离线模式下没缓存的页面 → 返回错误，不联网", "error" in web.fetch("https://example.gov/x"))
check("11. 没有 DeepSeek key 时搜索 → 返回说明，不报错", Web(cache_dir=tempfile.mkdtemp(), deepseek_key="").search("x")["results"] == [])

# ---- 12. 页面读不到的提交 → 记为线索 → 直接列入手动核对（2026-11-17 本人定：不再重试） ----
web, learned = make_web(PAGES), {"domains": []}
res = oc.run_check(NVSS, web, learned, max_steps=1, ask=fake_model([submit("https://www.cdc.gov/never.htm")]))
check("12. 读不到的提交 → 记为线索（网址、模型的判断、发现方式）",
      res["outcome"] != "found" and res["leads"]["https://www.cdc.gov/never.htm"]["decision"]["channel"] == "apply_to_provider", res)
before = res["outcome"]
res = oc.mark_manual(res)
check("12. → manual_check，保留原来的结果", res["outcome"] == "manual_check" and res.get("outcome_before_manual") == before, res)
check("12. manual_check 的汇总行列出要手动核对的网址", "never.htm" in oc.summary_line(NVSS, res), oc.summary_line(NVSS, res))
res = oc.run_check(NVSS, make_web(PAGES), {"domains": []}, ask=fake_model([{"thought": "", "action": "give_up", "reason": "x"}]))
check("12. 没有线索 → 结果不变", oc.mark_manual(res)["outcome"] == "not_found", res)

truth = {"channel": "apply_to_provider", "eligibility": "researchers", "check_result": "same_version_found"}
manual = oc.mark_manual(oc.run_check(NVSS, make_web(PAGES), {"domains": []}, max_steps=1,
                                     ask=fake_model([submit("https://www.cdc.gov/never.htm")])))
if ro:
    table = ro.score([{"id": "nvss_restricted", "truth": truth, "paper_side": "—", "result": manual}])
    check("12. 评分：manual_check 单独统计，不计入对错", "需要用户手动核对：1" in table and "不计入对错" in table, table)

# ---- 13. 模型没提交、但读不到的官方域名页面 → 也记为线索 ----
GONE = "https://www.cdc.gov/nchs/unreachable.htm"
res = oc.run_check(NVSS, make_web(PAGES), {"domains": []}, ask=fake_model([
    {"thought": "", "action": "read_page", "url": GONE},
    {"thought": "", "action": "read_page", "url": "https://not-official.com/x"},
    {"thought": "", "action": "give_up", "reason": "cannot read"}]))
check("13. 读不到的官方域名页面记为线索；非官方域名不记", GONE in res["leads"] and "https://not-official.com/x" not in res["leads"], res.get("leads"))
res = oc.mark_manual(res)
check("13. 没有模型判断的线索 → manual_check", res["outcome"] == "manual_check", res)
if ro:
    table = ro.score([{"id": "nvss_restricted", "truth": truth, "paper_side": "—", "result": res}])
    check("13. 评分表能显示没有模型判断的线索", GONE in table, table)

# ---- 14. 页面提到订阅/购买时，“注册下载/公开下载”先退回一次；改成订阅 → 通过；原样再交 → 通过但注明 ----
CS = {"name": "CSMAR", "provider": "CSMAR", "version": None, "version_verified": None, "sample_period": None,
      "urls": [], "access_category": "unknown"}
CS_URL = "https://csmar.com/contents/9/861.html"
CS_TEXT = ("CSMAR 个人账号注册。注册CSMAR个人账号，即可享有和学校图书馆相同的数据权限。"
           "输入注册的手机号和密码即可登录成功，进行数据查询下载。若您的学校没有开通全部数据权限，更多数据可前往数据超市模块进行购买。")
cs_pages = {CS_URL: ("CSMAR", CS_TEXT, [])}
def cs_submit(channel, aq):
    return {"thought": "", "action": "submit_finding", "url": CS_URL, "channel": channel, "eligibility": "not_stated",
            "restrictions": [], "check_result": "other_version_only", "access_quote": aq, "version_quote": None, "provider_quote": None}
reg = cs_submit("registration_download", "输入注册的手机号和密码即可登录成功，进行数据查询下载。")
res = oc.run_check(CS, make_web(cs_pages), {"domains": []}, ask=fake_model([
    reg, cs_submit("subscription", "注册CSMAR个人账号，即可享有和学校图书馆相同的数据权限。")]))
check("14. 页面写着“开通”“购买”，交“注册下载” → 先退回；改成订阅 → 通过",
      res["outcome"] == "found" and res["finding"]["channel"] == "subscription"
      and res["steps"][0]["observation"].startswith("Rejected for now"), res["steps"])
res = oc.run_check(CS, make_web(cs_pages), {"domains": []}, ask=fake_model([reg, reg]))
check("14. 原样再交（不说明订阅/购买针对哪份数据）→ 保留入口，标“是否需要订阅或购买待核对”",
      res["outcome"] == "found" and "payment" in res["finding"].get("pending"), res["steps"])
def cs_scoped(scope, q, channel="registration_download"):
    d = cs_submit(channel, "输入注册的手机号和密码即可登录成功，进行数据查询下载。")
    d.update({"payment_scope": scope, "payment_quote": q})
    return d
Q_SUB = "注册CSMAR个人账号，即可享有和学校图书馆相同的数据权限。"
res = oc.run_check(CS, make_web(cs_pages), {"domains": []}, ask=fake_model([reg, cs_scoped("this_data", Q_SUB)]))
f = res.get("finding") or {}
check("14. 【回归】确实需要订阅：指出订阅要求针对所用数据并附原文 → 渠道改为“机构订阅”",
      res["outcome"] == "found" and f.get("channel") == "subscription" and f.get("review_note") == "institutional subscription required"
      and "payment" not in f.get("pending"), res["steps"])
res = oc.run_check(CS, make_web(cs_pages), {"domains": []}, ask=fake_model([cs_scoped("this_data", "编造的订阅句子。")]))
check("14. 订阅原文不在页面上 → 拒绝", res["outcome"] != "found" and "payment_quote was not found" in res["steps"][0]["observation"], res["steps"])
LF_URL = "https://www150.statcan.gc.ca/n1/pub/71m0001x/71m0001x2021001-eng.htm"
LF_TEXT = ("Labour Force Survey: Public Use Microdata File. Downloading a Public Use Microdata File (PUMF) allows you to conduct your own analysis. "
           "Custom tabulations of the master file are available for purchase on a cost-recovery basis.")
LF = {"name": "Labour Force Survey", "provider": None, "version": "public-use files", "version_verified": True,
      "sample_period": None, "urls": [], "access_category": "unknown"}
lf = {"thought": "", "action": "submit_finding", "url": LF_URL, "channel": "public_download", "eligibility": "not_stated",
      "restrictions": [], "check_result": "same_version_found",
      "access_quote": "Downloading a Public Use Microdata File (PUMF) allows you to conduct your own analysis.",
      "version_quote": "Downloading a Public Use Microdata File (PUMF) allows you to conduct your own analysis.",
      "provider_quote": None, "payment_scope": "other_part",
      "payment_quote": "Custom tabulations of the master file are available for purchase on a cost-recovery basis.",
      "other_part_name": "custom tabulations of the LFS master file",
      "scope_evidence": "Labour Force Survey: Public Use Microdata File."}
res = oc.run_check(LF, make_web({LF_URL: ("LFS PUMF", LF_TEXT, [])}), {"domains": []}, ask=fake_model([lf]))
f = res.get("finding") or {}
check("14. 【回归】只有另一版本需要购买：首次提交就带齐依据 → 直接核对（1 步），保留“公开下载”，注明另一版本要购买",
      res["outcome"] == "found" and len(res["steps"]) == 1 and f.get("channel") == "public_download" and not f.get("pending")
      and any("another version or part" in n for n in f.get("notes", [])), res["steps"])
lf_bad = dict(lf, access_quote="Custom tabulations of the master file are available for purchase on a cost-recovery basis.")
res = oc.run_check(LF, make_web({LF_URL: ("LFS PUMF", LF_TEXT, [])}), {"domains": []}, ask=fake_model([lf_bad]))
check("14. 说“只针对另一版本”，但下载依据本身就是购买那句 → 不保留免费渠道，标待核对",
      res["outcome"] == "found" and "payment" in res["finding"].get("pending"), res["steps"])
web, learned = make_web(PAGES, SEARCH), {"domains": []}
res = oc.run_check(NVSS, web, learned, ask=fake_model([submit(P_URL, channel="public_download", result="other_version_only",
    aq="Public-use mortality data files can be downloaded free of charge.", vq=None)]))
check("14. 页面没提订阅/购买 → 公开下载直接通过", res["outcome"] == "found", res["steps"])

# ---- 15. 读不到的官方页面直接列入手动核对：同一网站同一栏目只留一个，模型提交过的在前，最多 3 个 ----
r15 = {"outcome": "not_found", "leads": {
    "https://www.isss.pku.edu.cn/cfps/a": {"decision": None, "discovered_via": "model"},
    "https://www.isss.pku.edu.cn/cfps/b": {"decision": None, "discovered_via": "model"},
    "https://opendata.pku.edu.cn/dataset.xhtml?id=1": {"decision": None, "discovered_via": "search"},
    "https://opendata.pku.edu.cn/dataset.xhtml?id=1&v=44": {"decision": None, "discovered_via": "search"},
    "https://cfpsdata.pku.edu.cn/#/home": {"decision": {"channel": "registration_download"}, "discovered_via": "search"},
    "https://www.pku.edu.cn/x": {"decision": None, "discovered_via": "model"}}}
oc.mark_manual(r15)
check("15. 去重后最多 3 个，模型提交过的排第一；原始全部网址保留在 all_unreadable",
      r15["outcome"] == "manual_check" and len(r15["leads"]) == 3
      and list(r15["leads"])[0] == "https://cfpsdata.pku.edu.cn/#/home" and len(r15["all_unreadable"]) == 6, r15)
r15b = {"outcome": "found", "finding": {}, "leads": {"https://x.gov/a": {"decision": None}}}
check("15. 已有核对通过的结果 → 不改", oc.mark_manual(r15b)["outcome"] == "found", r15b)

# ---- 16. 报告整合：论文提取结果 → 合并 → 官网核查（假模型）→ “论文｜官网”两栏对照 ----
import copy
from datetime import date
import step2_ai_extract as step2
import step3_merge as step3
Q_N = "We use the restricted data files of the National Vital Statistics System (NVSS) for 2001–2015."
Q_C = "We use the China Labor-force Dynamics Survey (CLDS) for 2014."
pages16 = [f"Data. {Q_N} {Q_C} End."]
raw16 = {"data_sources": [
    {"name": "National Vital Statistics System", "role": "main", "kind": "dataset", "provider": None, "unit": None,
     "sample_period": "2001–2015", "period_evidence": {"quote": Q_N, "page": 1}, "access_category": "unknown",
     "source_evidence": {"quote": Q_N, "page": 1}, "access_evidence": None, "usage": "analyzed",
     "usage_evidence": {"quote": Q_N, "page": 1}, "version": "restricted data files", "version_evidence": {"quote": Q_N, "page": 1}},
    {"name": "China Labor-force Dynamics Survey", "role": "main", "kind": "dataset", "provider": None, "unit": None,
     "sample_period": "2014", "period_evidence": {"quote": Q_C, "page": 1}, "access_category": "unknown",
     "source_evidence": {"quote": Q_C, "page": 1}, "access_evidence": None, "usage": "analyzed",
     "usage_evidence": {"quote": Q_C, "page": 1}}],
    "sample_limitations": [], "availability_statement": None}
rep16 = step2.verify_result(pages16, copy.deepcopy(raw16))
merged16 = step3.merge_reports([("borg", rep16)])
n_key = next(m["key"] for m in merged16 if "Vital" in m["display"])
web = make_web(PAGES, SEARCH)
answers = {"National Vital Statistics System": [
               {"thought": "", "action": "search_web", "query": "NVSS restricted data files county"},
               {"thought": "", "action": "read_page", "url": R_URL},
               submit(R_URL, restrictions=["Users must sign a data use agreement."])],
           "China Labor-force Dynamics Survey": [
               {"thought": "", "action": "read_page", "url": "https://css.sysu.edu.cn/data"},
               {"thought": "", "action": "give_up", "reason": "cannot read"}]}
def ask16(system, content):
    name = content.split("Data source: ", 1)[1].split("\n", 1)[0]
    return answers[name].pop(0), "fake-model"
official16 = oc.check_merged(merged16, web, {"domains": []}, ask=ask16, learned_path=None)
check("16. 每个合并后的数据源各查一次；NVSS 通过核对，CLDS 官网读不到 → 手动核对",
      official16[n_key]["result"]["outcome"] == "found"
      and any(v["result"]["outcome"] == "manual_check" for k, v in official16.items() if k != n_key), official16)
check("16. 交给 Agent 的描述带上论文所用版本", official16[n_key]["checked_source"]["version"] == "restricted data files",
      official16[n_key]["checked_source"])
text16 = step3.report_markdown([("borg", rep16)], official=official16)
nv = text16.split("## National Vital Statistics System", 1)[1].split("\n## ", 1)[0]
check("16. 两栏对照表：论文栏写版本，官网栏写渠道、资格、核查日期",
      "| | In the papers (what prior authors used) | Official site now (checked 2026-11-17) |" in nv
      and "restricted data files (borg)" in nv and "apply to the data provider" in nv and "researchers can apply" in nv, nv)
check("16. 官网原文、官方依据、使用限制（逐字）、发现方式都显示", "Official-site text (access): “Researchers may apply" in nv
      and "Why this counts as official:" in nv and "Users must sign a data use agreement." in nv and "found via web search" in nv, nv)
cl = text16.split("## China Labor-force Dynamics Survey", 1)[1].split("\n## ", 1)[0]
check("16. 读不到的官方页面：写“请手动核对”并列出网址，不写成结论",
      "could not read it — please check manually" in cl and "Please open: https://css.sysu.edu.cn/data" in cl, cl)
check("16. 报告开头说明 V2 官网核查；末尾核查清单指向“Official site now”",
      "Official site now (V2)" in text16 and "see \"Official site now\" under each source" in text16, text16[-600:])
plain = step3.report_markdown([("borg", rep16)])
check("16. 不加 --official 时报告和以前一样（没有两栏对照）",
      "Official site now" not in plain and "the tool has not verified any official entry point" in plain, plain[-400:])
none16 = step3.report_markdown([("borg", rep16)], official={})
check("16. 官网核查没跑成（空结果）→ 每个数据源写“not checked”，不报错", "| Access channel |" in none16 and "not checked" in none16, none16[:1500])

# ---- 17. 审核规则：页面提到审核、模型交免费渠道 → 先退回；第二次必须指出审核针对哪份数据并附原文 ----
CL = {"name": "China Labor-force Dynamics Survey", "provider": None, "version": None, "version_verified": None,
      "sample_period": "2014", "urls": [], "access_category": "unknown"}
CL_URL = "https://isg.sysu.edu.cn/article/254"
CL_TEXT = ("China Labor-force Dynamics Survey. 中国劳动力动态调查（CLDS）数据获取。任何以学术研究为目的的研究人员，均可在中山大学社会科学调查中心网站注册免费申请CLDS2014年数据。"
           "注册用户后点击激活，就可再点击申请2014CLDS数据，通过审核即可下载使用。")
cl_pages = {CL_URL: ("CLDS", CL_TEXT, [])}
AQ_CL = "任何以学术研究为目的的研究人员，均可在中山大学社会科学调查中心网站注册免费申请CLDS2014年数据。"
RQ_CL = "注册用户后点击激活，就可再点击申请2014CLDS数据，通过审核即可下载使用。"
def cl_submit(scope=None, rq=None, channel="registration_download", aq=AQ_CL):
    return {"thought": "", "action": "submit_finding", "url": CL_URL, "channel": channel, "eligibility": "researchers",
            "restrictions": [], "check_result": "other_version_only", "access_quote": aq, "version_quote": None,
            "provider_quote": None, "review_scope": scope, "review_quote": rq}
res = oc.run_check(CL, make_web(cl_pages), {"domains": []}, ask=fake_model([cl_submit(), cl_submit("this_data", RQ_CL)]))
f = res.get("finding") or {}
check("17. CLDS：先退回；指出审核针对 2014 数据 → 改为“向提供方申请”，备注“需注册，审核通过后下载”",
      res["steps"][0]["observation"].startswith("Rejected for now: the page mentions review") and res["outcome"] == "found"
      and f.get("channel") == "apply_to_provider" and f.get("review_note") == "registration required; download after review approval", res["steps"])
res = oc.run_check(CL, make_web(cl_pages), {"domains": []}, ask=fake_model([cl_submit(), cl_submit()]))
check("17. 原样再交（不说明审核针对哪份数据）→ 保留入口，标“是否需要审核待核对”，不写成免费下载的结论",
      res["outcome"] == "found" and res["finding"].get("review_pending") is True, res["steps"])
res = oc.run_check(CL, make_web(cl_pages), {"domains": []}, max_steps=2, ask=fake_model([cl_submit(), cl_submit("this_data", "编造的审核句子。")]))
check("17. 审核原文不在页面上 → 拒绝", res["outcome"] != "found" and "review_quote was not found" in res["steps"][-1]["observation"], res["steps"])

CH_URL = "https://chns.cpc.unc.edu/data/datasets/"
CH_TEXT = ("China Health and Nutrition Survey. All household and individual data are consolidated in sets of master longitudinal files that are downloadable from the Dataverse. "
           "To obtain community-level data files, a CHNS data use agreement must be submitted and approved by the project director.")
CH = {"name": "China Health and Nutrition Survey", "provider": None, "version": None, "version_verified": None,
      "sample_period": "1989–2015", "urls": [], "access_category": "unknown"}
AQ_CH = "All household and individual data are consolidated in sets of master longitudinal files that are downloadable from the Dataverse."
RQ_CH = "To obtain community-level data files, a CHNS data use agreement must be submitted and approved by the project director."
def ch_submit(scope=None, rq=None, other="community-level data files", ev=AQ_CH):
    return {"thought": "", "action": "submit_finding", "url": CH_URL, "channel": "public_download", "eligibility": "not_stated",
            "restrictions": [], "check_result": "same_version_found", "access_quote": AQ_CH, "version_quote": AQ_CH,
            "provider_quote": None, "review_scope": scope, "review_quote": rq,
            "other_part_name": other if scope else None, "scope_evidence": ev if scope else None}
res = oc.run_check(CH, make_web({CH_URL: ("Data Sets 1989-2015 | CHNS", CH_TEXT, [])}), {"domains": []},
                   ask=fake_model([ch_submit(), ch_submit("other_part", RQ_CH)]))
f = res.get("finding") or {}
check("17. CHNS：审核针对社区层面数据（另一部分），住户数据另有直接下载依据 → 保留“公开下载”，注明另一部分要审核",
      res["outcome"] == "found" and f.get("channel") == "public_download" and not f.get("review_pending")
      and any("another version or part" in n for n in f.get("notes", [])), res["steps"])
res = oc.run_check(CH, make_web({CH_URL: ("Data Sets 1989-2015 | CHNS", CH_TEXT, [])}), {"domains": []},
                   ask=fake_model([ch_submit("other_part", RQ_CH)]))
check("17. 第一次提交就附上审核针对的数据和原文 → 不再退回，直接核对", res["outcome"] == "found" and len(res["steps"]) == 1, res["steps"])
res = oc.run_check(NVSS, make_web(PAGES, SEARCH), {"domains": []}, ask=fake_model([submit(P_URL, channel="public_download",
    result="other_version_only", aq="Public-use mortality data files can be downloaded free of charge.", vq=None)]))
check("17. 页面没有审核字样 → 不触发", res["outcome"] == "found" and not res["finding"].get("review_pending"), res["steps"])

# ---- 18. 每条结论注明依据来自哪里：官网本身 / 官网链接过去的平台 ----
web, learned = make_web(PAGES, SEARCH), {"domains": []}
res = oc.run_check(NVSS, web, learned, ask=fake_model([
    {"thought": "", "action": "read_page", "url": R_URL},
    submit("https://apply.example.org/nchs", aq="Submit your NCHS restricted data request here.", vq=None, result="other_version_only")]))
check("18. 官网链接过去的申请平台 → 依据来自 linked_platform", (res.get("finding") or {}).get("evidence_source") == "linked_platform", res)
check("18. 官网本身 → 依据来自 official_page", official16[n_key]["result"]["finding"]["evidence_source"] == "official_page", official16[n_key])
check("18. 报告写出依据来自哪里", "Evidence comes from: the official page itself" in text16, text16[:2000])

# ---- 19. 独立检验后的修复（回归）：JSON 控制字符、提供方域名、找到官方站点 vs 找到获取说明 ----
import deepseek_client as dc
raw = '{"thought": "line one\nline two", "action": "read_page", "url": "https://x.gov/a"}'.replace("\\n", "\n")
check("19. 字符串里有未转义的换行 → 照常解析，内容原样保留", dc.parse_first_json(raw)["thought"] == "line one\nline two", raw)
class _R:
    def __init__(self, text): self.status_code, self._t = 200, text
    def json(self): return {"choices": [{"message": {"content": self._t}}]}
class _S:
    def __init__(self, texts): self.texts = list(texts)
    def post(self, *a, **k): return _R(self.texts.pop(0))
import os
os.environ.setdefault("DEEPSEEK_API_KEY", "test")
out, _ = dc.generate_json("s", "c", session=_S(["not json at all", '{"action": "give_up", "reason": "x"}']), sleep=lambda s: None)
check("19. 第一次不是 JSON → 重新生成一次", out["action"] == "give_up", out)
try:
    dc.generate_json("s", "c", session=_S(["nope", "still nope"]), sleep=lambda s: None)
    check("19. 两次都不是 JSON → ParseError（带原始响应）", False)
except dc.ParseError as e:
    check("19. 两次都不是 JSON → ParseError（带原始响应）", e.raw == "still nope", e.raw)
def raise_parse(system, content):
    raise dc.ParseError("bad json twice", "RAW TEXT")
res = oc.run_check(NVSS, make_web(PAGES), {"domains": []}, ask=raise_parse)
check("19. run_check 遇到 ParseError → outcome parse_error，保留原始响应", res["outcome"] == "parse_error" and res["raw_response"] == "RAW TEXT", res)

WWO = {"name": "meteorological conditions (3-hourly)", "provider": "worldweatheronline.com", "version": None,
       "version_verified": None, "sample_period": None, "urls": ["www.worldweatheronline.com"], "access_category": "unknown"}
W_URL = "https://www.worldweatheronline.com/weather-api/api/historical-weather-api.aspx"
W_TEXT = ("Historical Weather API. Our historical or past weather API allows users to receive weather data from 1st July 2008 until present day. "
          "Historical data requires a paid subscription plan.")   # v2.5d：订阅结论要有写明订阅的原文
w = {"thought": "", "action": "submit_finding", "url": W_URL, "channel": "subscription", "eligibility": "individuals",
     "restrictions": [], "check_result": "other_version_only",
     "access_quote": "Historical data requires a paid subscription plan.",
     "version_quote": None, "provider_quote": None}
res = oc.run_check(WWO, make_web({W_URL: ("Historical Weather API", W_TEXT, [])}), {"domains": []}, ask=fake_model([w]))
check("19. 论文写明提供方是 worldweatheronline.com → 该网站算提供方官网", res["outcome"] == "found"
      and "the paper names worldweatheronline.com" in res["finding"]["official_basis"], res["steps"])
FAKE = "https://worldweatheronline.com.mirror-site.net/api.aspx"
res = oc.run_check(WWO, make_web({FAKE: ("copy", W_TEXT, [])}), {"domains": []}, max_steps=1, ask=fake_model([dict(w, url=FAKE)]))
check("19. 名字里带提供方域名的其他网站 → 不算", res["outcome"] != "found", res["steps"])
NOPROV = dict(WWO, provider=None)
res = oc.run_check(NOPROV, make_web({W_URL: ("Historical Weather API", W_TEXT, [])}), {"domains": []}, max_steps=1, ask=fake_model([w]))
check("19. 只有变量描述、没有提供方 → 拒绝并注明“提供方未确认”", res["outcome"] != "found"
      and "provider not confirmed" in res["steps"][0]["observation"], res["steps"])
res = oc.run_check(NVSS, make_web(PAGES, SEARCH), {"domains": []}, ask=fake_model([
    {"thought": "", "action": "read_page", "url": R_URL}, {"thought": "", "action": "give_up", "reason": "x"}]))
check("19. 读到官方站点但没提交 → 记入 official_sites（找到官方站点 ≠ 找到获取说明）", res["official_sites"] == [R_URL], res)

# ---- 20. 免费说明要对应到论文所用的数据（WWO 回归后的规则）----
WP_URL = "https://www.worldweatheronline.com/weather-api/api/historical-weather-api.aspx"
WP_TEXT = ("Historical Weather API | World Weather Online. Data is available at 1-hourly, 3-hourly, 6-hourly intervals. "
           "500 free calls/day — no credit card. Pro plans from $1/month with commercial use permitted. "
           "Pricing table: Historical weather data — Free plan: not included — Pro plan: included.")
def wp(aq, ev, other="Pro plans"):
    return {"thought": "", "action": "submit_finding", "url": WP_URL, "channel": "registration_download", "eligibility": "individuals",
            "restrictions": [], "check_result": "other_version_only", "access_quote": aq, "version_quote": None, "provider_quote": None,
            "payment_scope": "other_part", "payment_quote": "Pro plans from $1/month with commercial use permitted.",
            "other_part_name": other, "scope_evidence": ev}
wpages = {WP_URL: ("Historical Weather API | World Weather Online", WP_TEXT, [])}
res = oc.run_check(WWO, make_web(wpages), {"domains": []}, ask=fake_model([wp("500 free calls/day — no credit card.", "Historical Weather API")]))
f = res.get("finding") or {}
check("20. 【验收】WWO：全站免费额度 + 页面标题 → 不判免费，标“该产品是否包含在免费额度内，待核对”",
      res["outcome"] == "found" and "free_quota" in f.get("pending"), res["steps"])
res = oc.run_check(WWO, make_web(wpages), {"domains": []}, ask=fake_model([wp("500 free calls/day — no credit card.",
      "Pricing table: Historical weather data — Free plan: not included — Pro plan: included.")]))
check("20. 套餐表行写明免费方案不含历史数据 → 仍不能判免费（待核对）", "free_quota" in ((res.get("finding") or {}).get("pending") or []), res["steps"])
res = oc.run_check(CH, make_web({CH_URL: ("Data Sets 1989-2015 | CHNS", CH_TEXT, [])}), {"domains": []},
                   ask=fake_model([ch_submit("other_part", RQ_CH, other=None)]))
check("20. 说“只针对另一部分”却没说是哪一部分 → 待核对", (res.get("finding") or {}).get("pending") == ["review"], res["steps"])
res = oc.run_check(CH, make_web({CH_URL: ("Data Sets 1989-2015 | CHNS", CH_TEXT, [])}), {"domains": []},
                   ask=fake_model([ch_submit("other_part", RQ_CH, ev="Data Sets 1989-2015 | CHNS")]))
check("20. 【验收】CHNS：依据是页面标题（产品页）→ 仍能保留公开下载", res["outcome"] == "found"
      and res["finding"]["channel"] == "public_download" and not res["finding"].get("pending"), res["steps"])
res = oc.run_check(CH, make_web({CH_URL: ("Data Sets 1989-2015 | CHNS", CH_TEXT, [])}), {"domains": []},
                   ask=fake_model([ch_submit("other_part", RQ_CH, ev="编造的依据。")]))
check("20. 对应依据不在页面上（转述）→ 退回重交，不直接定成待核对",
      res["outcome"] != "found" and "scope_evidence was not found" in res["steps"][-1]["observation"], res["steps"])
res = oc.run_check(CH, make_web({CH_URL: ("Data Sets 1989-2015 | CHNS", CH_TEXT, [])}), {"domains": []},
                   ask=fake_model([ch_submit("other_part", RQ_CH, ev="Heading 'Data Sets' followed by the household data sentence"),
                                   ch_submit("other_part", RQ_CH, ev="Data Sets 1989-2015 | CHNS")]))
check("20. 【验收】CHNS：第一次依据是转述 → 退回；改成逐字的页面标题 → 保留公开下载",
      res["outcome"] == "found" and res["finding"]["channel"] == "public_download" and not res["finding"].get("pending"), res["steps"])

# ---- 21. 产品与时效：历史基线不能替代未来预测；历史售价只能写成发行时的条件；导航栏不触发审核 ----
WC = {"name": "WorldClim-Global Climate Data", "provider": "WorldClim", "version": None, "version_verified": None,
      "sample_period": None, "urls": [], "access_category": "unknown",
      "source_evidence": {"quote": "We use the publicly available WorldClim-Global Climate Data to project how climate change affects mortality in China.", "page": 3, "verified": True}}
check("21. 任务描述带上论文怎么描述这份数据（用于预测未来）", "to project how climate change affects mortality" in oc.describe_source(WC, {"domains": []}))
WC_URL = "https://www.worldclim.org/data/worldclim21.html"
WC_TEXT = "WorldClim Global Climate Data. This is WorldClim version 2.1 climate data for 1970-2000. Below you can download the standard (19) WorldClim Bioclimatic variables."
wc = {"thought": "", "action": "submit_finding", "url": WC_URL, "channel": "public_download", "eligibility": "not_stated",
      "restrictions": [], "check_result": "other_version_only",
      "access_quote": "Below you can download the standard (19) WorldClim Bioclimatic variables.",
      "version_quote": "This is WorldClim version 2.1 climate data for 1970-2000.", "provider_quote": None}
res = oc.run_check(WC, make_web({WC_URL: ("Historical climate data — WorldClim", WC_TEXT, [])}), {"domains": []}, ask=fake_model([wc]))
check("21. 【验收】WorldClim：只找到历史基线页 → 保留链接，目标产品（未来预测）的渠道待核对",
      res["outcome"] == "found" and "product" in res["finding"]["pending"], res["finding"])
if ro:
    truth_wc = {"accepted_channels": ["public_download"], "check_result": "undetermined"}
    table = ro.score_test([{"id": "worldclim_future", "truth": truth_wc, "result": res}])
    check("21. 评分：只找到其他产品的不算“找到正确渠道”，记为待核对", "找到正确渠道：0/1" in table, table)

SH = {"name": "Survey of Household Spending (SHS)", "provider": "Statistics Canada", "version": None, "version_verified": None,
      "sample_period": "2006", "urls": [], "access_category": "unknown"}
SH_URL = "https://www150.statcan.gc.ca/n1/daily-quotidien/080704/be080704a-eng.htm"
SH_AQ = "The Survey of Household Spending: Public Use Microdata File, 2006 (62M0004XCB, $3,210) is now available."
SH_TEXT = "Survey of Household Spending, Public Use Microdata File. " + SH_AQ + " Statistics Canada."
sh = {"thought": "", "action": "submit_finding", "url": SH_URL, "channel": "purchase", "eligibility": "not_stated",
      "restrictions": [], "check_result": "same_version_found", "access_quote": SH_AQ, "version_quote": SH_AQ, "provider_quote": None}
web = make_web({SH_URL: ("The Daily, Friday, July 4, 2008. Survey of Household Spending, Public Use Microdata File", SH_TEXT, [])})
res = oc.run_check(SH, web, {"domains": []}, ask=fake_model([sh]))
f = res.get("finding") or {}
check("21. 【验收】SHS：2008 年发布公告的售价 → 写成发行时的条件（as_of 2008-07-04），当前渠道待核对",
      res["outcome"] == "found" and f.get("as_of") == "2008-07-04" and "current" in f["pending"], f)
check("21. 网址里的日期也能识别（The Daily、国家统计局 t 日期）",
      oc.page_date({"title": "x", "text": ""}, SH_URL).isoformat() == "2008-07-04"
      and oc.page_date({"title": "x", "text": ""}, "https://www.stats.gov.cn/hd/lyzx/zxgk/202405/t20240524_1953617.html").isoformat() == "2024-05-24")
check("21. 三年内的页面、或不是发布公告 → 不算历史公告",
      oc.historical_announcement({"title": "咨询公开", "text": ""}, "https://www.stats.gov.cn/hd/lyzx/zxgk/202405/t20240524_1953617.html",
                                 "您可访问我局数据发布库，注册并下载相关数据。", date(2026, 11, 17)) is None
      and oc.historical_announcement({"title": "如何查询历史气象数据？", "text": ""}, "https://www.cma.gov.cn/wmhd/gzly/cjwt/202204/t20220415_4759049.html",
                                     "请登录本网“中国气象科学数据共享服务网”", date(2026, 11, 17)) is None)
NAV = "首页 机构设置 政务公开 规章库 政策文件 政策解读 行政审批 气象信息服务企业备案 局长信箱 公众留言 如何查询历史气象数据？请登录本网数据共享服务网，注册后即可下载。"
check("21. 导航栏里的“行政审批”不触发审核复查；正文句子里的“通过审核即可下载”仍触发",
      oc.payment_cues(NAV, oc.REVIEW_CUES) == [] and oc.payment_cues("就可再点击申请数据，通过审核即可下载使用。", oc.REVIEW_CUES) != [])

res = oc.run_check(WC, make_web({WC_URL: ("Historical climate data — WorldClim", WC_TEXT, [])}), {"domains": []},
                   ask=fake_model([dict(wc, check_result="same_version_found")]))
check("21. 【验收】WorldClim：模型说“同一版本”，但论文没写版本和年份 → 不能核对，目标产品渠道待核对",
      res["outcome"] == "found" and "product" in res["finding"]["pending"], res["finding"])

# ---- 22. v2.4：研究地区、搜索上限、中国纸质统计资料的已知渠道（第二轮之后） ----
check("22. 研究方向里只有一个国家时识别出来；没有或多个国家时不做国家核对",
      oc.country_in("manufacturing growth and local employment in Chinese cities") == "China"
      and oc.country_in("trade between China and Japan") is None and oc.country_in("minimum wage and teen employment") is None)
EST = "https://www.e-stat.go.jp/en/stat-search/files?toukei=00200521"
EST_TEXT = "Population Census 2010 Basic Complete Tabulation on Industries. Population Census. View / Download CSV"
CEN = {"name": "National Population Census (2010)", "provider": None, "version": None, "sample_period": "2010", "urls": [],
       "access_category": "unknown", "study_area": "China"}
est = {"thought": "", "action": "submit_finding", "url": EST, "channel": "public_download", "eligibility": "not_stated",
       "restrictions": [], "check_result": "same_version_found", "access_quote": "View / Download CSV",
       "version_quote": "Population Census 2010 Basic Complete Tabulation on Industries", "provider_quote": "Population Census 2010 Basic Complete Tabulation on Industries"}
res = oc.run_check(CEN, make_web({EST: ("Population Census 2010 Japan", EST_TEXT, [])}), {"domains": []},
                   ask=fake_model([est, {"thought": "", "action": "give_up", "reason": "x"}]))
check("22. 【验收】论文研究中国，证据页是日本政府网站（e-Stat）→ 拒绝",
      res["outcome"] == "not_found" and "Japan government site" in res["steps"][0]["observation"], res["steps"][0])
res = oc.run_check(dict(CEN, study_area=None), make_web({EST: ("Population Census 2010 Japan", EST_TEXT, [])}), {"domains": []},
                   ask=fake_model([est]))
check("22. 没有研究地区时不做国家核对（第一轮的行为不变）", res["outcome"] == "found", res)

srch = {"thought": "", "action": "search_web", "query": "q"}
res = oc.run_check(NVSS, make_web(PAGES), {"domains": []},
                   ask=fake_model([dict(srch, query=f"q{i}") for i in range(oc.MAX_SEARCHES + 1)] + [submit(R_URL)]))
check(f"22. 搜索超过 {oc.MAX_SEARCHES} 次后不再执行，提示去读页面或提交",
      res["outcome"] == "found" and res["steps"][oc.MAX_SEARCHES]["observation"].startswith("Not executed: search limit"), res["steps"][-2:])

LIB_TEXT = ("中国统计资料馆 一、简介 中国统计资料馆于2006年6月13日正式对外开放。同时，" + oc.CN_LIBRARY["access_quote"]
            + "，为社会公众提供阅览服务。截至目前，馆藏各类统计年鉴和资料已达9300余种，" + oc.CN_LIBRARY["version_quote"] + "，还包括全部省级年鉴。")
Q = "Industrial Economy Statistical Yearbook 2001 2011 电子版 在线"   # 程序按名称 + 卷次检索在线版时用的检索词
lib_web = lambda: make_web({oc.CN_LIBRARY["url"]: ("中国统计资料馆", LIB_TEXT, [])}, {Q: [("某书店", "https://shop.example.com/book", "售价")]})
BOOK = {"name": "Industrial Economy Statistical Yearbook (2001-2011)", "provider": None, "version": None, "sample_period": "2000–2010",
        "urls": [], "access_category": "unknown", "study_area": "China"}
res = oc.run_check(BOOK, lib_web(), {"domains": []}, ask=fake_model([{"thought": "", "action": "search_web", "query": "工业经济统计年鉴 电子版"},
                                                                    {"thought": "", "action": "give_up", "reason": "print only"}]))
f = res.get("finding") or {}
check("22. 【验收】中国的纸质统计年鉴，在线版检索只有第三方结果 → 归为到统计资料馆查阅（apply_to_provider），依据程序核对",
      res["outcome"] == "found" and f.get("channel") == "apply_to_provider" and f.get("discovered_via") == "known_channel"
      and res.get("agent_outcome") == "not_found", res)
check("22. 纸质资料的任务描述要求先检索官方在线版", "FIRST search whether an official online" in oc.describe_source(BOOK, {"domains": []}))
web = make_web({oc.CN_LIBRARY["url"]: ("中国统计资料馆", LIB_TEXT, [])},
               {Q: [("工业经济统计年鉴 在线", "https://tjj.example.gov.cn/nj/2011/index.htm", "年鉴在线版")]})
res = oc.mark_manual(oc.run_check(BOOK, web, {"domains": []}, ask=fake_model([{"thought": "", "action": "give_up", "reason": "x"}])))
check("22. 程序按名称 + 卷次检索在线版；有官方域名的结果 → 不归档，列入手动核对",
      res["outcome"] == "manual_check" and "https://tjj.example.gov.cn/nj/2011/index.htm" in res["leads"], res)
web = make_web({oc.CN_LIBRARY["url"]: ("中国统计资料馆", LIB_TEXT, [])}, {Q: [("某书店", "https://shop.example.com/book", "售价")]})
res = oc.run_check(BOOK, web, {"domains": []}, ask=fake_model([{"thought": "", "action": "give_up", "reason": "x"}]))
check("22. 程序检索只有第三方结果 → 归为到统计资料馆查阅", (res.get("finding") or {}).get("discovered_via") == "known_channel", res)
res = oc.run_check(dict(BOOK, study_area="Japan"), lib_web(), {"domains": []},
                   ask=fake_model([{"thought": "", "action": "give_up", "reason": "x"}]))
check("22. 不是中国的研究、或不是统计年鉴/普查资料 → 不套用这个已知渠道",
      res["outcome"] == "not_found" and not oc.china_print_stats(dict(BOOK, name="database of Chinese industrial enterprises")), res)

# ---- 23. v2.4b：国际组织域名、年份 / 版本证据、纸质资料回退的检索要求、线索分类（第二轮回归之后，本人定） ----
check("23. 国际组织域名（含子域名）算机构域名；名字相近的假域名不算",
      oc.is_institutional("data.worldbank.org") and oc.is_institutional("www.oecd.org") and oc.is_institutional("un.org")
      and not oc.is_institutional("fakeworldbank.org") and not oc.is_institutional("worldbank.org.evil.com"))
WDI = {"name": "World Bank World Development Indicators", "provider": "World Bank", "version": None, "sample_period": "1991–2013",
       "urls": [], "access_category": "unknown", "study_area": "China"}
WDI_URL = "https://datacatalog.worldbank.org/search/dataset/0037712/World-Development-Indicators"
WDI_TEXT = "World Development Indicators. The primary World Bank collection of development indicators, 1960-2023. Download the full dataset in CSV format. Free to download."
wdi = {"thought": "", "action": "submit_finding", "url": WDI_URL, "channel": "public_download", "eligibility": "not_stated",
       "restrictions": [], "check_result": "same_version_found", "access_quote": "Download the full dataset in CSV format.",
       "version_quote": "The primary World Bank collection of development indicators, 1960-2023.", "provider_quote": None}
res = oc.run_check(WDI, make_web({WDI_URL: ("World Development Indicators | World Bank", WDI_TEXT, [])}), {"domains": []}, ask=fake_model([wdi]))
check("23. 世界银行页面 → 能产出有引文支持的公开下载", res["outcome"] == "found" and res["finding"]["channel"] == "public_download"
      and not res["finding"]["pending"], res.get("finding") or res["steps"])
res = oc.run_check(WDI, make_web({"https://fakeworldbank.org/wdi": ("WDI", WDI_TEXT, [])}), {"domains": []},
                   ask=fake_model([dict(wdi, url="https://fakeworldbank.org/wdi"), {"thought": "", "action": "give_up", "reason": "x"}]))
check("23. fakeworldbank.org → 不算官方（v2.5 起点名了数据的只能标为分发方）",
      (res.get("finding") or {}).get("evidence_source") == "distributor" and not oc.is_institutional("fakeworldbank.org"), res.get("finding") or res["steps"])
nber = {"text": "Merged Outgoing Rotation Groups (MORG) are extracts of the Current Population Survey.", "final_url": "https://www.nber.org/x"}
cps = {"name": "Current Population Survey Outgoing Rotation Groups", "provider": None}
check("23. 分发方：名称里有区分度的词全部出现才算点名；缺一个不算",
      oc.names_data(cps, nber["text"]) is not None and oc.names_data(cps, "Current Population Survey basic monthly files") is None)

AS = {"name": "database of Chinese industrial enterprises", "provider": None, "version": None, "sample_period": "1998–2007",
      "urls": [], "access_category": "unknown", "study_area": "China"}
AS_URL = "https://www.stats.gov.cn/zt/microdata.html"
AS_TEXT = "国家统计局微观数据。目前已开放十二大类微观数据：（一）规模以上工业企业财务状况年度调查微观数据。研究人员可填写《微观数据使用申请表》提交审核。2021-02-19"
asd = {"thought": "", "action": "submit_finding", "url": AS_URL, "channel": "apply_to_provider", "eligibility": "institution_must_apply",
       "restrictions": [], "check_result": "same_version_found", "access_quote": "研究人员可填写《微观数据使用申请表》提交审核。",
       "version_quote": "（一）规模以上工业企业财务状况年度调查微观数据", "provider_quote": "国家统计局微观数据。"}
res = oc.run_check(AS, make_web({AS_URL: ("国家统计局微观数据", AS_TEXT, [])}), {"domains": []}, ask=fake_model([asd]))
check("23. 【验收】论文写了 1998–2007，官网引文没写年份 → 不能说同一版本，年份待核对",
      res["outcome"] == "found" and res["finding"]["pending"] == ["version"], res.get("finding"))
check("23. 引文或页面标题有落在论文年份内的年份、或写到论文版本号 → 算有对应证据",
      oc.covers_paper(AS, "规模以上工业企业 2004 年") and not oc.covers_paper(AS, "2021-02-19")
      and oc.covers_paper({"version": "v1.4"}, "WorldClim 1.4") and not oc.covers_paper({"version": "v1.4"}, "WorldClim 2.1"))

web = make_web({oc.CN_LIBRARY["url"]: ("中国统计资料馆", LIB_TEXT, [])},
               {Q: [("工业经济统计年鉴 在线", "https://tjj.example.gov.cn/nj/2011/index.htm", "年鉴在线版")]})
res = oc.mark_manual(oc.run_check(BOOK, web, {"domains": []}, ask=fake_model([
    {"thought": "", "action": "search_web", "query": "中国统计年鉴 2011 电子版"}, {"thought": "", "action": "give_up", "reason": "x"}])))
check("23. 【验收】Agent 搜的是别的年鉴 → 不能代替；程序按名称 + 卷次再搜，搜到疑似官方在线版 → 保留待核对入口，不归档",
      res["outcome"] == "manual_check" and "https://tjj.example.gov.cn/nj/2011/index.htm" in res["leads"], res)
res = oc.run_check(BOOK, make_web({oc.CN_LIBRARY["url"]: ("中国统计资料馆", LIB_TEXT, [])}), {"domains": []},
                   ask=fake_model([{"thought": "", "action": "give_up", "reason": "x"}]))
check("23. 【验收】在线版检索失败（出错 / 离线未缓存）→ 不能当作“没有在线版”，不归到资料馆",
      res["outcome"] == "not_found" and res.get("online_search") == "failed" and not res.get("finding"), res)
lib_res = oc.run_check(BOOK, lib_web(), {"domains": []}, ask=fake_model([{"thought": "", "action": "give_up", "reason": "x"}]))
f = lib_res.get("finding") or {}
check("23. 【验收】只找到资料馆的通用馆藏说明 → 到馆查阅是线索，具体卷册待核对；结论不是“覆盖论文所用版本”",
      f.get("channel") == "apply_to_provider" and f.get("pending") == ["version"] and f.get("check_result") == "version_unconfirmed"
      and "not stated" in " ".join(f.get("notes", [])), f)
off = dict(official16)
off[n_key] = dict(off[n_key], result=lib_res)
nv = step3.report_markdown([("borg", rep16)], official=off).split("## National Vital Statistics System", 1)[1].split("\n## ", 1)[0]
check("23. 卷册待核对：报告不写“覆盖论文所用版本”，写“未确认”",
      "the page covers the version the paper used" not in nv and "not confirmed: the page does not name the years / volumes" in nv, nv)
if ro:
    table = ro.score_test([{"id": "lib", "truth": {"accepted_channels": ["purchase", "apply_to_provider"], "check_result": "same_version_found"},
                            "result": lib_res}])
    check("23. 卷册待核对在评分里同一个意思：记“渠道已找到，年份 / 卷册待核对”，不算判对",
          "可用线索：渠道已找到，年份 / 卷册待核对" in table and "找到正确渠道：0/1" in table, table)
REG = {"name": "China Regional Statistical Yearbook (2001, 2011)", "sample_period": "2000, 2010"}
check("23. 年份反例：论文用 2000 和 2010 两卷，引文只写 2000 → 卷册待核对；两卷都写到 → 算有对应证据",
      not oc.covers_paper(REG, "《中国区域经济统计年鉴2000》") and oc.covers_paper(REG, "2000年、2010年两卷"))

truth23 = {"accepted_channels": ["public_download"], "check_result": "same_version_found"}
other = oc.run_check(SH, make_web({SH_URL: ("x", SH_TEXT, [])}), {"domains": []}, ask=fake_model([dict(sh, check_result="other_version_only")]))
rows = [{"id": "manual", "truth": truth23, "result": oc.mark_manual(oc.run_check(NVSS, make_web(PAGES), {"domains": []}, max_steps=1,
                                                                                ask=fake_model([submit("https://www.cdc.gov/never.htm")])))},
        {"id": "related", "truth": truth23, "result": other},
        {"id": "wrong", "truth": truth23, "override": "wrong_lead", "result": {"outcome": "manual_check", "leads": {"https://sedac.x/cddc": {}}}}]
if ro:
    table = ro.score_test(rows)
    check("23. 评分：页面读不到、只找到其他产品、错误线索都不算可用线索，分别计数",
          "可用线索（渠道已找到；条件、年份或卷册待核对）：0" in table and "相关资料（只找到其他版本或产品）：1" in table
          and "页面读不到（产品未确认）：1" in table and "错误线索（人工复核）：1" in table, table)

# ---- 24. 研究国家按每篇论文取，不取研究方向（第三轮：方向写美国，Qin2022 研究中国 → stats.gov.cn 被误拒）----
check("24. 研究国家取论文自己的 study_area；没写时用标题；用户上传的论文（标题是文件名）不猜",
      oc.paper_country({"study_area": "China", "title": "x"}) == "China"
      and oc.paper_country({"study_area": "United States (Northern California)"}) == "United States"
      and oc.paper_country({"study_area": "not stated", "title": "Environmental Regulation and Employment in Resource-Based Cities in China",
                            "origin": "open access (OpenAlex)"}) == "China"
      and oc.paper_country({"study_area": "not stated", "title": "Unemployment and environmental regulation in general equilibrium",
                            "origin": "open access (OpenAlex)"}) is None
      and oc.paper_country({"title": "china_paper.pdf", "origin": "uploaded by the user"}) is None)
mixed = {"uses": [{"src": {"name": "EPS", "study_area": "China"}}, {"src": {"name": "EPS", "study_area": "United States"}}]}
same = {"uses": [{"src": {"name": "EPS", "study_area": "China"}}, {"src": {"name": "EPS", "study_area": "China"}}]}
check("24. 同一数据源被不同国家的论文使用 → 不做国家核对；国家一致 → 用这个国家",
      oc.source_for_merged(mixed)["study_area"] is None and oc.source_for_merged(same)["study_area"] == "China")
qin = {"study_area": "China", "title": "Environmental Regulation and Employment in Resource-Based Cities in China"}
check("24. 第三轮反例：Qin2022 的数据源国家是中国，与 stats.gov.cn 的国家一致（verify_finding 不再拒绝）",
      oc.paper_country(qin) == oc.host_country("www.stats.gov.cn") == "China")
if ro:
    two = ro.score_two([
        {"id": "a", "truth": {"has_data": "yes", "from_hosts": ["bls.gov"]},
         "result": {"outcome": "found", "finding": {"final_url": "https://download.bls.gov/pub/x", "check_result": "same_version_found"}}},
        {"id": "b", "truth": {"has_data": "yes", "from_hosts": ["epsnet.com.cn"]}, "result": {"outcome": "manual_check"}},
        {"id": "c", "truth": {"has_data": "yes", "from_hosts": ["bea.gov"]},
         "result": {"outcome": "found", "finding": {"final_url": "https://notbea.gov.example.com/", "check_result": "same_version_found"}}}])
    check("24. 两问评分：子域名算对；手动核对算未回答；只是包含域名字样的假域名算错",
          "有没有数据：对 2/3" in two and "数据从哪里来：对 1/3**，错 1，未回答 1" in two, two)

    two_u = ro.score_two([{"id": "u", "truth": {"has_data": "undetermined", "from_hosts": ["ins.tn"]},
                           "result": {"outcome": "found", "finding": {"final_url": "https://www.ins.tn/x", "check_result": "same_version_found"}}}])
    check("24. 两问评分：标准答案“能否获取”未定 → 第一问不计入分母，第二问照常", "有没有数据：对 0/0" in two_u and "数据从哪里来：对 1/1" in two_u, two_u)

# ---- 25. 没给出结论时：报告告诉用户自己查，并列出线索（v2.5，通用）----
res25 = {"outcome": "budget_exhausted", "read": {"https://data.example.org/a": "search"},
         "steps": [{"action": "submit_finding", "args": {"url": "https://x.example.org/p"},
                    "observation": "Rejected: not an official source — x.example.org is not a government domain"}]}
leads25 = step3.unanswered_leads(res25)
check("25. 没结论 → 列出被拒的提交（附原因）和读过的页面，被拒的排在前面",
      "x.example.org/p (submitted by the check but not confirmed: x.example.org is not a government domain)" in leads25[1]
      and "data.example.org/a (read during the check)" in leads25[2], leads25)
check("25. 什么页面都没到过 → 提示自己按数据名和提供方搜索",
      "search the data name and the provider yourself" in step3.unanswered_leads({"outcome": "not_found"})[0])

# ---- 26. v2.5d 获取依据门槛：获取原文要写明获取方式，否则不能给出下载 / 申请 / 购买 / 订阅结论 ----
no_way = [("public_download", "本表是2010年第六次全国人口普查初步汇总的11月1日零时数。"),
          ("public_download", "自2015年1月1日起，向社会公开发布全国338个地级及以上城市空气质量实时监测数据。"),
          ("registration_download", "If you have a question, please read \"MERRA-2 File Specification Document\" and FAQs linked from the Documentation tab on this page."),
          ("public_download", "TRAINS tariff and trade data are disseminated through the World Integrated Trade Solution WITS application."),
          ("subscription", "Prowess is a service that delivers the largest database of the performance of Indian companies along with a powerful querying interface.")]
stated = [("registration_download", "登录的用户，在列表页点击“下载”按钮，可以实现裁判文书下载。"),
          ("registration_download", "如您需要相关气象数据，请登录中国气象数据网（data.cma.cn）注册获取。"),
          ("public_download", "Download all tables ZIP"),
          ("public_download", "The Quarterly Workforce Indicators (QWI) are available online for public use."),
          ("apply_to_provider", "各地可依据实际需求申请下载月报数据。"),
          ("apply_to_provider", "Access to restricted files requires research proposal review and approval by NCHS."),
          ("apply_to_provider", oc.CN_LIBRARY["access_quote"]),
          ("purchase", "您可在各大书店和中国统计资料馆中查阅纸质版本。"),
          ("purchase", "The Survey of Household Spending: Public Use Microdata File, 2006 (62M0004XCB, $3,210) is now available."),
          ("subscription", "注册CSMAR个人账号，即可享有和学校图书馆相同的数据权限。")]
check("26. 依据句没写获取方式（年鉴人口表、实时发布、“有问题请看文档”、只说经 WITS 发布、只介绍服务）→ 不算有依据",
      not any(oc.access_stated(c, q) for c, q in no_way), [q for c, q in no_way if oc.access_stated(c, q)])
check("26. 写明了下载、注册获取、在线公开、申请 / 审批、到馆查阅、书店 / 标价、机构订阅权限 → 算有依据",
      all(oc.access_stated(c, q) for c, q in stated), [q for c, q in stated if not oc.access_stated(c, q)])
check("26. 渠道和措辞要对应：写了“下载”不能当作“购买”的依据", not oc.access_stated("purchase", "Download all tables ZIP"))
G_URL = "https://www.stats.gov.cn/sj/ndsj/2011/html/D0309C.HTM"
G_TEXT = "国家统计局。第六次全国人口普查。本表是2010年第六次全国人口普查初步汇总的11月1日零时数。"
CEN = {"name": "China Census 2010", "provider": "国家统计局", "version": None, "version_verified": None,
       "sample_period": "2010", "urls": [], "access_category": "unknown"}
g = {"thought": "", "action": "submit_finding", "url": G_URL, "channel": "public_download", "eligibility": "not_stated",
     "restrictions": [], "check_result": "same_version_found", "access_quote": "本表是2010年第六次全国人口普查初步汇总的11月1日零时数。",
     "version_quote": "本表是2010年第六次全国人口普查初步汇总的11月1日零时数。", "provider_quote": "国家统计局"}
res26 = oc.run_check(CEN, make_web({G_URL: ("2010 census table", G_TEXT, [])}), {"domains": [{"domain": "stats.gov.cn", "label": "China Census 2010 | 国家统计局"}]},
                     max_steps=1, ask=fake_model([g]))
check("26. 实时运行：人口普查年鉴表交“公开下载” → 退回，没有结论",
      res26["outcome"] != "found" and res26["steps"][0]["observation"].startswith(oc.ACCESS_NOT_STATED), res26.get("steps"))
leads26 = step3.unanswered_leads(res26)
check("26. 报告线索：保留这个页面，写给用户的下一步（不显示写给模型的 give_up 提示）",
      any(G_URL in l and "does not say how to obtain the data" in l and "give_up" not in l for l in leads26), leads26)
saved = {"outcome": "found", "steps": [], "finding": {"url": G_URL, "channel": "public_download", "access_quote": g["access_quote"]}}
re26 = oc.apply_access_gate(saved)
check("26. 离线复核保存的结果：同样降级为没有结论，原结论另存，页面作为线索",
      re26["outcome"] == "not_found" and re26["finding"] is None and re26["regated_finding"]["url"] == G_URL
      and any(G_URL in l for l in step3.unanswered_leads(re26)))
ok_saved = {"outcome": "found", "steps": [], "finding": {"url": "https://x", "channel": "public_download", "access_quote": "Download all tables ZIP"}}
check("26. 有依据的保存结果不动", oc.apply_access_gate(ok_saved) is ok_saved)

# ---- 27. 一条核查出错不能拖垮整批（2026-11-18 新论文端到端：parse_error 让 summary_line 抛 KeyError，整批 not checked）----
Q_W = "Pollution readings come from the Global Weather Archive for 2010–2015."
pages27 = [f"Data. {Q_N} {Q_C} {Q_W} End."]
raw27 = copy.deepcopy(raw16)
raw27["data_sources"].append({"name": "Global Weather Archive", "role": "main", "kind": "dataset", "provider": None, "unit": None,
     "sample_period": "2010–2015", "period_evidence": {"quote": Q_W, "page": 1}, "access_category": "unknown",
     "source_evidence": {"quote": Q_W, "page": 1}, "access_evidence": None, "usage": "analyzed",
     "usage_evidence": {"quote": Q_W, "page": 1}})
rep27 = step2.verify_result(pages27, raw27)
merged27 = step3.merge_reports([("borg", rep27)])
def run27(src, web, learned, ask=None, verbose=False, **kw):
    if "Vital" in src["name"]:
        raise ConnectionResetError("Connection reset by peer")       # 第一条直接抛错
    if "Labor" in src["name"]:
        return {"outcome": "parse_error", "steps": [], "read": {}, "leads": {}}   # 第二条：模型回答两次都不是 JSON
    return {"outcome": "not_found", "steps": [], "read": {}, "leads": {}}         # 第三条正常跑完
real_run_check, oc.run_check = oc.run_check, run27
import io, contextlib
try:
    with contextlib.redirect_stdout(io.StringIO()) as out27:
        official27 = oc.check_merged(merged27, web, {"domains": []}, verbose=True, learned_path=None)   # scout 用 verbose=True
    batch_ok = True
except Exception as e:
    official27, batch_ok = {}, f"{type(e).__name__}: {e}"
finally:
    oc.run_check = real_run_check
outcomes27 = {v["name"]: v["result"]["outcome"] for v in official27.values()}
check("27. 第一条抛错、第二条 parse_error（verbose=True）→ 整批不放弃，三条都有结果", batch_ok is True and len(official27) == 3, (batch_ok, outcomes27))
check("27. 出错那条记为 check_failed 并保留错误信息；其余两条保留各自结果",
      sorted(outcomes27.values()) == ["check_failed", "not_found", "parse_error"]
      and any("ConnectionResetError" in v["result"].get("error", "") for v in official27.values()), outcomes27)
text27 = step3.report_markdown([("borg", rep27)], official=official27)
sec = lambda name: text27.split(f"## {name}", 1)[1].split("\n## ", 1)[0]
check("27. 报告：出错那条明确写“核查失败”和错误，不写成 not checked / 没找到",
      "official-site check failed (ConnectionResetError" in sec("National Vital Statistics System")
      and "not checked" not in sec("National Vital Statistics System"), sec("National Vital Statistics System"))
check("27. 报告：parse_error 那条也写“核查失败”；正常那条照常显示自己的结论",
      "official-site check failed" in sec("China Labor-force Dynamics Survey")
      and "no verified official access route found" in sec("Global Weather Archive"), text27[:3000])
check("27. 报告前面的 Main data 一行也写出核查失败", text27.count("check this yourself") >= 2, text27[:2500])

print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
