"""
V2 官网核查 Agent：论文没写清楚怎么获取时，由模型去数据提供方的官网查“现在怎么拿”，程序决定能不能写成结论。

一个数据源的核查过程（循环，每一步写进行动日志）：
    1. 模型看到：数据名、提供方、论文所用的版本和年份、论文怎么写的获取条件、论文里的网址、以前核对通过的官方域名
    2. 模型选一个动作：search_web / read_page / submit_finding / give_up
    3. 程序执行，把结果交回模型
    4. 停止：提交的结果通过程序核对（found）；模型判断找不到（not_found）；步数用完；模型调用失败

找入口的顺序（需求文档，2026-11-17）：论文里的网址 → 以前核对通过的官方域名 → 搜索 → 模型凭记忆的网址（最后的备选）。
每个读过的网址都记下是怎么发现的（paper / learned / search / link / model），用来评估搜索是否值得。

程序核对（submit_finding 时）：
    1. 网页由程序自己读取（web_tools），读不到 → 拒绝（网页未能核对）
    2. 官方来源：政府、大学等机构域名，且页面写到这个数据或提供方；或以前核对通过的域名；或由官方页面链接过去的平台
    3. 获取说明原文必须逐字存在于程序读到的页面
    4. 版本：说“同一版本已找到”时，必须引用写到论文所用版本或年份的官网原文，且原文存在；否则降为“仅找到其他版本”
    5. 使用限制每条必须逐字出现在页面中，否则丢弃
    渠道、资格、版本是否对应，是模型对官网原文的语义判断，报告中如实标注
"""

import json
import os
import re
from datetime import date
from urllib.parse import urlparse

import gemini_client
from web_tools import Web, host, normalize, quote_in_text

# 待核对的种类（报告和评分共用）
PENDING_ZH = {"review": "是否需要审核", "payment": "是否需要订阅或购买", "free_quota": "该产品是否包含在免费额度内",
              "current": "当前渠道（只找到发布公告）", "product": "目标产品的渠道（只找到其他版本或产品）",
              "version": "论文所用年份 / 版本是否包含在内（页面没写到）"}

MAX_STEPS = 12   # 2026-11-17 试点：8 步时 CSMAR、SEDAC 在读不到的网页上用完了步数
MAX_SEARCHES = 6   # v2.4：第二轮 WDI 已读到世界银行页面，却把步数花在搜索上，没来得及提交
MAX_OBSERVATION = 2500
LEARNED_FILE = "official_domains.json"
ACTIONS = ["search_web", "read_page", "submit_finding", "give_up"]
CHANNELS = ["public_download", "registration_download", "subscription", "purchase", "apply_to_provider", "request_from_author"]
ELIGIBILITY = ["researchers", "individuals", "institution_must_apply", "not_stated"]
CHECK_RESULTS = ["same_version_found", "other_version_only", "discontinued"]
VERSION_UNCONFIRMED = "version_unconfirmed"   # 程序给的结论（模型不能选）：页面没写到论文用的年份 / 卷册
# 机构域名（政府、大学、国际组织）。只靠域名不够：页面还必须写到这个数据或提供方
# 页面上提到订阅、购买、付费：免费渠道（公开下载、注册下载）不能直接成立，先退回让模型确认
# 英文按整词匹配（“fee” 不匹配 “feedback”）；不用 “subscribe”，政府网站页脚常见“订阅邮件”按钮
PAYMENT_CUES = ("订阅", "购买", "付费", "收费", "开通", "subscription", "purchase", "paid access", "fee", "fees",
                # 2026-11-17 WWO 回归：商业网站写的是价格和套餐，不一定出现上面的词
                "pricing", "/month", "per month", "pro plan", "pro plans", "premium plan", "价格", "元/年", "元/月")
FREE_CHANNELS = ("public_download", "registration_download")
# 页面上提到审核、审批：免费渠道先退回，第二次提交必须指出审核针对哪份数据，并附审核原文（逐字）
# 英文不用单独的 “review”（政府页面常见 “review the documentation”），只用 approval / approved 和固定搭配
REVIEW_CUES = ("审核", "审批", "approval", "approved", "subject to review", "application review", "reviewed and approved")
INSTITUTIONAL = (".gov", ".gov.cn", ".gc.ca", ".go.jp", ".gov.uk", ".gov.au", ".gouv.fr", ".europa.eu", ".int",
                 ".edu", ".edu.cn", ".ac.uk", ".ac.jp", ".ac.cn", ".edu.au", ".edu.hk", ".org.cn")

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "action": {"type": "string", "enum": ACTIONS},
        "query": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
        "near": {"type": ["string", "null"]},
        "channel": {"type": ["string", "null"]},
        "eligibility": {"type": ["string", "null"]},
        "restrictions": {"type": ["array", "null"], "items": {"type": "string"}},
        "check_result": {"type": ["string", "null"]},
        "access_quote": {"type": ["string", "null"]},
        "version_quote": {"type": ["string", "null"]},
        "provider_quote": {"type": ["string", "null"]},
        "review_scope": {"type": ["string", "null"]},
        "payment_scope": {"type": ["string", "null"]},
        "payment_quote": {"type": ["string", "null"]},
        "other_part_name": {"type": ["string", "null"]},
        "scope_evidence": {"type": ["string", "null"]},
        "review_quote": {"type": ["string", "null"]},
        "reason": {"type": ["string", "null"]},
    },
    "required": ["thought", "action"],
}

SYSTEM_PROMPT = """You check how ONE data source used in an economics paper can be obtained TODAY, using the data provider's official website.
The paper tells you which data and which version/file/years the authors used. You must find the official page that explains how to get THAT version.

Where to look, in this order:
  1. URLs written in the paper (listed in the task), if any
  2. official domains already verified for this provider (listed in the task), if any
  3. search_web (you may use site:example.gov to stay on one domain)
  4. a URL you know from memory — only as a last resort; memory URLs may be outdated
Only official pages count: the provider's own site (government, university, research center) or an application/download
platform that the official site links to. Third-party blogs, library guides and data catalogs are clues only.

Actions (choose exactly one per step):
  search_web     query = search words (max 128 characters)
  read_page      url = a URL from the task or from a previous result; near = optional word to jump to
  submit_finding url = the official page; channel, eligibility, restrictions, check_result, access_quote, version_quote, provider_quote
  give_up        reason = why no official access route could be found

Fields for submit_finding:
  channel       public_download | registration_download (free after creating an account) | subscription | purchase |
                apply_to_provider | request_from_author
  eligibility   researchers | individuals | institution_must_apply | not_stated
  restrictions  conditions on USING the data after access is granted, copied word-for-word (e.g. "only at a Research Data Center",
                "must not be shared with third parties"); [] if none. The application requirement itself is NOT a restriction.
  check_result  same_version_found  = the page clearly covers the version/file/years the paper used (the same PRODUCT:
                                      e.g. historical baseline climate data is not the same product as future projections)
                other_version_only  = the page covers another version (e.g. public files while the paper used restricted files)
                discontinued        = the page explicitly says this version is no longer provided
  access_quote   ONE sentence copied word-for-word from the page that states how to obtain the data
  version_quote  ONE sentence copied word-for-word from the page that names the version, file type or years the paper used
                 (required for same_version_found). A general sentence about the website or the survey does NOT count.
  provider_quote ONE sentence from the page that shows it is this data's or provider's official page
  review_scope / review_quote  only when the page mentions review or approval (审核, 审批, approval, approved) and your channel
                 is public_download or registration_download:
                 review_scope = this_data   (the review applies to the data/version the paper used)
                              | other_part  (it applies to another version or part, e.g. restricted files or community-level data)
                              | unclear
                 review_quote = the sentence about review/approval, copied word-for-word from the page
  payment_scope / payment_quote  the same, when the page mentions subscription / purchase / fees (订阅, 购买, 付费, 开通)
  other_part_name  required with scope other_part: name the other product / version / part that the fee or review applies to
  scope_evidence   required with scope other_part: what ties the FREE access to the data the paper used — the page title or a
                   heading naming that product, the pricing-table row for that product, or the direct download link (URL) for it.
                   A site-wide free quota ("500 free calls/day", "free plan", "no credit card") does not show that the paper's
                   product is free.
Rules:
  - Copy quotes exactly from read_page results of THAT url. Quotes from search snippets or other pages are rejected.
  - If a page could not be read, do not submit it; read another page or give_up.
  - Copy quotes exactly from read_page results. The program re-reads the page and rejects quotes it cannot find.
  - Do not use background knowledge as evidence. If the page does not say it, it is not evidence.
  - If the paper used a restricted or special version and the page only describes public files, use other_version_only.
  - "Register, then apply, and download after review" is apply_to_provider, not registration_download.
  - Registering or logging in is not the whole channel. If the page says what you can access depends on an institution's
    subscription, or that more data must be bought, the channel is subscription (or purchase), not registration_download.
Answer with one JSON object."""


# ============ 官方域名名单（使用中增长） ============

def load_learned(path: str = LEARNED_FILE) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"domains": []}


def save_learned(learned: dict, path: str = LEARNED_FILE) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(learned, f, ensure_ascii=False, indent=1)


def learned_domains_for(src: dict, learned: dict) -> list[str]:
    terms = [t.lower() for t in source_terms(src)]
    return [d["domain"] for d in learned["domains"] if any(t in d.get("label", "").lower() for t in terms)]


# ============ 数据和提供方的识别词 ============

def source_terms(src: dict) -> list[str]:
    """页面上用来识别“这是这个数据 / 提供方的页面”的词：数据名（去括号）、提供方、名称里的大写缩写。"""
    terms = []
    for field in (src.get("name"), src.get("provider")):
        if field:
            core = re.sub(r"\s*\(.*?\)\s*", " ", field).strip()
            if len(core) >= 6:
                terms.append(core)
            terms += re.findall(r"\b[A-Z][A-Z0-9]{2,7}\b", field)
    seen, out = set(), []
    for t in terms:
        if t.lower() not in seen and t.upper() not in {"THE", "AND", "DATA"}:
            seen.add(t.lower())
            out.append(t)
    return out


def own_domain_term(h: str, src: dict) -> str | None:
    """数据自己的域名：主域名的第一段就是数据名的缩写（如 csmar.com 对应 CSMAR）。商业数据库的官网通常是公司网站，不是机构域名。
    只接受完全相同（csmar-guide.net 不算）。"""
    labels = h.split(".")
    base = labels[-3] if len(labels) >= 3 and labels[-2] in ("com", "net", "org", "edu", "gov", "ac") else (labels[-2] if len(labels) >= 2 else "")
    for t in source_terms(src):
        if re.fullmatch(r"[A-Za-z0-9]{3,10}", t) and t.lower() == base:
            return t
    return None


DOMAIN_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})\b", re.I)


def provider_domain(src: dict) -> str | None:
    """论文写明的提供方本身就是一个网站域名时（如 provider = "worldweatheronline.com"），返回去掉 www 的域名。
    依据是论文：作者说数据来自这个网站。只看提供方字段，不看论文里的其他网址（论文网址可能是第三方转载站）。"""
    prov = (src.get("provider") or "").strip().lower()
    m = DOMAIN_RE.fullmatch(prov) or DOMAIN_RE.fullmatch(re.sub(r"^https?://", "", prov).split("/")[0])
    return m.group(1).removeprefix("www.") if m else None


# ============ 研究地区（v2.4） ============
# 第二轮：提取名 "National Population Census (2010)" 没写国家，核查按名称搜到了日本 e-Stat 的普查。
# 论文研究国家明确时，交给模型，并拒绝属于另一个国家的政府域名（.org/.com/.edu/.int 等通用域名不受影响）。
COUNTRY_WORDS = {"China": ("china", "chinese"), "Japan": ("japan", "japanese"), "United States": ("united states", "u.s.", "american"),
                 "United Kingdom": ("united kingdom", "britain", "british", "england"), "Canada": ("canada", "canadian"),
                 "Australia": ("australia", "australian"), "Germany": ("germany", "german"), "France": ("france", "french"),
                 "Korea": ("korea", "korean"), "India": ("india", "indian")}
COUNTRY_TLD = {".cn": "China", ".jp": "Japan", ".gov": "United States", ".uk": "United Kingdom", ".ca": "Canada",
               ".au": "Australia", ".de": "Germany", ".fr": "France", ".kr": "Korea", ".in": "India"}


def country_in(text: str) -> str | None:
    """文本里只出现一个国家时返回它；没有或多个都返回 None（不做国家核对）。"""
    t = f" {(text or '').lower()} "
    hits = [c for c, words in COUNTRY_WORDS.items() if any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t) for w in words)]
    return hits[0] if len(hits) == 1 else None


def paper_country(paper: dict) -> str | None:
    """Use the paper's classified study area, or its title when no area was recorded."""
    area = (paper.get("study_area") or "").strip()
    if area and area.lower() != "not stated":
        return country_in(area)
    if paper.get("origin") != "uploaded by the user":
        return country_in(paper.get("title") or "")
    return None


def host_country(h: str) -> str | None:
    return next((c for tld, c in COUNTRY_TLD.items() if h.endswith(tld)), None)


INTL_ORGS = ("worldbank.org", "imf.org", "oecd.org", "un.org")   # v2.4b：用 .org 的国际组织（第二轮 WDI 被拒）


def is_institutional(h: str) -> bool:
    return (any(h.endswith(sfx) or h == sfx.lstrip(".") for sfx in INSTITUTIONAL)
            or any(h == d or h.endswith("." + d) for d in INTL_ORGS))


DISTRIBUTOR = "distributor"   # v2.5：非官方的分发方网站（如 NBER 的 CPS 整理版），可以回答“数据从哪里来”，报告注明不是原始提供方
NAME_STOPWORDS = {"data", "database", "databases", "dataset", "datasets", "file", "files", "series", "table", "tables", "the", "and",
                  "for", "from", "with", "statistics", "statistical", "survey", "national", "annual", "monthly"}


def names_data(src: dict, text: str) -> str | None:
    """页面是否点名了这个数据（只看数据名，不看提供方）：完整名称逐字出现；或名称中有区分度的词（≥2 个）全部出现。
    返回命中的说明，没有返回 None。"""
    name = re.sub(r"\s*\(.*?\)\s*", " ", src.get("name") or "").strip()
    t = f" {normalize(text)} "
    if len(name) >= 6 and normalize(name) in t:
        return repr(name)
    words = [w for w in re.findall(r"[a-z][a-z0-9]{2,}", normalize(name)) if w not in NAME_STOPWORDS and not w.isdigit()]
    if len(words) >= 2 and all(re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", t) for w in words):
        return "all of " + ", ".join(repr(w) for w in words)
    return None


def official_status(url: str, page: dict, src: dict, learned: dict, linked_from_official: set,
                    provider_quote: str | None = None) -> tuple[bool, str]:
    """返回 (是否算官方来源, 依据)。"""
    h = host(page.get("final_url") or url)
    if any(h == d or h.endswith("." + d) for d in learned_domains_for(src, learned)):
        return True, f"previously verified official domain ({h})"
    if url in linked_from_official:
        return True, "linked from an official page"
    text = page.get("text", "")
    own = own_domain_term(h, src)
    if own and normalize(own) in normalize(text):
        return True, f"the data's own domain ({h} = {own}); the page names {own!r}"
    pd = provider_domain(src)
    if pd and (h == pd or h.endswith("." + pd)):
        return True, f"the provider's own site: the paper names {pd} as the provider"
    if not is_institutional(h):
        why = f"{h} is not a government / university / international-organisation domain, nor the data's own domain"
        named = names_data(src, text)
        if named:   # 不是官方，但页面点名了这个数据：作为分发方接受，报告注明
            return True, (f"{DISTRIBUTOR}: {h} is not the original provider and is not confirmed as official; "
                          f"the page names {named}")
        if not src.get("provider"):
            why += "; provider not confirmed from the paper (only a data description is available)"
        return False, why
    named = [t for t in source_terms(src) if normalize(t) in normalize(text)]
    if named:
        return True, f"institutional domain; the page names {named[0]!r}"
    if provider_quote and quote_in_text(provider_quote, text):
        return True, "institutional domain; provider sentence quoted by the model found on the page (provider identity is a model judgment)"
    return False, f"{h} is institutional, but the page does not name this data or provider"


# ============ 程序核对一条提交 ============

UNREADABLE = "Rejected: the program could not read the page"

# v2.5d（2026-11-18）获取依据门槛：获取原文必须写明对应的获取方式，否则不能给出下载 / 申请 / 购买 / 订阅结论。
# 以前程序只核对原文在页面上存在：“本表是2010年第六次全国人口普查初步汇总的……”“向社会公开发布实时监测数据”
# “If you have a question, please read …” 都被当成了下载依据。只看获取原文这一句，不看页面其他地方。
_DOWNLOAD = (r"download|下载|获取|导出|浏览|查询|查看|在线|免费|\bexport|\bzip\b|\bcsv\b|\bxlsx?\b|\bftp\b|index of /"
             r"|\bfiles? (?:are|is) (?:on|available)|available (?:for|to) (?:download|the public)|\bonline\b|public use|\bfree\b"
             r"|\bbrowse|\bview\b|\bquery|\bretriev|\baccess(?:ing)? (?:\w+ ){0,2}(?:data|dataset|files?|tables?)\b")
ACCESS_WORDS = {
    "public_download": _DOWNLOAD,
    "registration_download": _DOWNLOAD + r"|注册|登录|\bregist|sign[- ]?up|log ?in",
    "apply_to_provider": (r"appl(?:y|ies|ied|ication)|request|申请|审核|审批|提交|填写|许可|授权|submit|\bform\b|approv|proposal"
                          r"|permission|查阅|阅览|on[- ]site|reading room"),   # 到馆查阅也是向提供方获取
    "purchase": r"purchas|\bbuy|\border|price|购买|订购|征订|下单|售价|定价|书店|bookstore|\d\s*元|[$€£]\s?\d",
    "subscription": r"subscri|licen[cs]|订阅|订购|会员|开通|权限|access rights",   # “享有和学校相同的数据权限”＝机构订阅
    "request_from_author": r"author|contact|request|联系|索取",
}
ACCESS_NOT_STATED = "Rejected: the access quote does not say how to obtain the data"


def access_stated(channel: str, quote: str) -> bool:
    """获取原文是否写明了这个渠道的获取方式（下载、申请、购买、订阅、向作者索取）。只做字面检查：
    写了不代表渠道判断一定对（那仍是模型对原文的判断），没写则一定不能下这个结论。"""
    pattern = ACCESS_WORDS.get(channel)
    return bool(pattern and re.search(pattern, normalize(quote or ""), re.I))


def access_gate_message(channel: str) -> str:
    return (f"{ACCESS_NOT_STATED} — the quoted sentence has no {channel.replace('_', ' ')} wording; the page is a lead only: "
            f"find the page on this site that states how to download or apply, or give_up")


def apply_access_gate(result: dict) -> dict:
    """离线复核保存的结果用（不调用 API）：found 结论的获取原文没写获取方式 → 改为没有结论，页面作为附原因的线索保留。
    实时运行时同一检查在 verify_finding 里，模型会被退回、可以换页面再交；离线复核无法知道它会不会找到更好的页面。"""
    f = result.get("finding") if result.get("outcome") == "found" else None
    if not f or access_stated(f["channel"], f.get("access_quote") or ""):
        return result
    step = {"step": len(result.get("steps") or []) + 1, "action": "submit_finding", "args": {"url": f["url"]},
            "observation": access_gate_message(f["channel"]), "offline_regate": "v2.5d"}
    return {**result, "outcome": "not_found", "finding": None, "regated_finding": f,
            "steps": list(result.get("steps") or []) + [step]}

# ============ 产品与时效：只找到其他产品，或只找到发布当时的公告 ============
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                       "october", "november", "december"], 1)}
ANNOUNCE = re.compile(r"(?i)now available|is available today|starting today|is released|now released|正式向|正式开放|向学术界开放"
                      r"|正式上线|现已发布|现正式")
HISTORICAL_YEARS = 3   # 发布日期早于核查日期 3 年以上的公告，只能说明发布当时的获取条件


def page_date(page: dict, url: str) -> date | None:
    """页面的发布日期：标题里的日期、“发布日期 / 发布时间 / Release date”标签、或网址里的日期。
    不用“Date modified / 更新日期”（页面改版也会更新，不代表内容是新的）。"""
    title, text = page.get("title") or "", (page.get("text") or "")[:1500]
    m = re.search(r"(?i)\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),\s+((?:19|20)\d{2})", title)
    if m:
        return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
    m = re.search(r"(?:发布日期|发布时间|Release date|Published|Posted)\s*[:：]?\s*((?:19|20)\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"/daily-quotidien/(\d{2})(\d{2})(\d{2})/", url)
    if m:
        return date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"/t((?:19|20)\d{2})(\d{2})(\d{2})_", url)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def historical_announcement(page: dict, url: str, aq: str, checked: date) -> date | None:
    """发布日期早于核查日期 3 年以上、而且是发布公告（标题或获取依据里有“现已发布 / 正式开放”之类）→ 返回发布日期。"""
    d = page_date(page, url)
    if not d or (checked - d).days < 365 * HISTORICAL_YEARS:
        return None
    if ANNOUNCE.search(page.get("title") or "") or ANNOUNCE.search(aq or ""):
        return d
    return None


SENTENCE_MARK = re.compile(r"[。，；：！？,.;:!?]")


def is_menu_hit(text: str, i: int, cue: str) -> bool:
    """命中是不是在导航栏 / 菜单里：
    中文词：前后 20 个字符内被空格切成 3 段以上的短词、又没有中文标点（如“政策解读 行政审批 气象信息服务企业备案”）；
    英文词：前后 40 个字符内没有任何标点。"""
    if cue.isascii():
        return not SENTENCE_MARK.search(text[max(0, i - 40): i + 40])
    win = text[max(0, i - 20): i + len(cue) + 20]
    return len(win.split()) >= 3 and not re.search(r"[。，；：！？]", win)


def payment_cues(text: str, cues=PAYMENT_CUES) -> list[str]:
    """页面上提到订阅/购买/付费（或审核，cues=REVIEW_CUES）的句子片段（最多 3 处）。
    审核词只在正文句子里算：前后 40 个字符内没有任何标点的命中（导航栏、菜单，如“规章库 政策文件 … 行政审批 …”）跳过。"""
    low, out = text.lower(), []
    for cue in cues:
        pat = re.escape(cue) if not cue.isascii() else r"\b" + re.escape(cue) + r"\b"
        for m in re.finditer(pat, low):
            i = m.start()
            if cues is REVIEW_CUES and is_menu_hit(text, i, cue):
                continue
            out.append(re.sub(r"\s+", " ", text[max(0, i - 60): i + 60]).strip())
            break
    return out[:3]


# ---- v1（2026-11-19，本人要求）：渠道改写要有对应条件的依据；否定句（无需购买、不收费、no fee）不算收费 / 审核依据 ----
NEGATOR_BEFORE = re.compile(r"(?:无需|无须|不需要?|不必|不用|免于?|免除|毋需|不收取?|没有|无)[^，,。；;：:]{0,8}$"
                            r"|(?i:\b(?:no|without|not|never|free of)\b[^,.;:]{0,25}$)")
NEGATOR_AFTER = re.compile(r"^[^，,。；;：:]{0,6}(?:不需要|不必|免除|(?i:\s*(?:is|are)?\s*(?:not required|not needed|unnecessary|waived)))")
CLAUSE_END = re.compile(r"[，,。；;：:!?！？\n]")


def cue_hits(text: str, cues) -> list[tuple[int, str, bool]]:
    """页面上每一处条件词：(位置, 词, 是否被否定)。否定 = 同一分句里紧挨着“无需 / 不 / no / without”等。"""
    low, out = text.lower(), []
    for cue in cues:
        pat = re.escape(cue) if not cue.isascii() else r"\b" + re.escape(cue) + r"\b"
        for m in re.finditer(pat, low):
            i = m.start()
            if cues is REVIEW_CUES and is_menu_hit(text, i, cue):
                continue
            before = CLAUSE_END.split(text[max(0, i - 40):i])[-1]
            after = CLAUSE_END.split(text[m.end():m.end() + 30])[0]
            out.append((i, cue, bool(NEGATOR_BEFORE.search(before) or NEGATOR_AFTER.search(after))))
    return sorted(out)


def affirmed_cues(text: str, cues=PAYMENT_CUES) -> list[str]:
    """没有被否定的条件词所在片段（最多 3 处）。“无需购买或订阅，本数据可无偿获取”→ 空。"""
    out = []
    for i, cue, neg in cue_hits(text, cues):
        if not neg:
            out.append(re.sub(r"\s+", " ", text[max(0, i - 60): i + 60]).strip())
    return list(dict.fromkeys(out))[:3]


FREE_WORDS = re.compile(r"无偿|免费|free of charge|at no (?:cost|charge)|\bfree\b(?! (?:quota|trial|plan|calls?|tier|account))", re.I)
FREE_NEGATED = re.compile(r"(?:不|非|并非|不是)\s*(?:免费|无偿)|(?i:\bnot\s+(?:free|available free))")


def states_free(sentence: str) -> bool:
    """句子明确写了免费 / 无偿（且没有被否定：“不免费”“not free”不算）。"""
    return bool(FREE_WORDS.search(sentence or "")) and not FREE_NEGATED.search(sentence or "")


# 引文不出现“订阅 / 审核”字样、但写明了同一条件的说法（发布版回归测试 14：CSMAR“享有和学校图书馆相同的数据权限”＝机构订阅）
SUPPORT_EXTRA = {"payment": ("权限", "会员", "license", "licence", "licensed", "access rights"),
                 "review": ("申请", "许可", "授权", "apply", "application", "permission")}


def condition_support(kind: str, q: str) -> str:
    """该条件（收费 / 审核）的引文本身是否支持“这份数据需要它”：
    affirmed = 写了条件且没被否定；negated = 只有被否定的写法（无需购买…）；mixed = 同一句既写免费又写收费（多为不同子产品分别收费）；
    none = 没写这个条件。"""
    hits = cue_hits(q, tuple(CONDITION[kind]["cues"]) + SUPPORT_EXTRA[kind])
    pos = [h for h in hits if not h[2]]
    if kind == "payment" and pos and states_free(q):
        return "mixed"
    if pos:
        return "affirmed"
    return "negated" if hits else "none"


CONDITION = {
    "payment": {"cues": PAYMENT_CUES, "what": "subscription / purchase",
                "pending": "whether a subscription or purchase is required for the data used is unclear — please check"},
    "review": {"cues": REVIEW_CUES, "what": "review / approval",
               "pending": "whether review / approval is required for the data used is unclear — please check"},
}
# 全站通用的免费额度说法：不能单凭它说明论文所用的产品免费
GENERIC_FREE = re.compile(r"(?i)free\s+(?:api\s+)?(?:calls|requests|tier|plan|account|trial)|(?:calls|requests)\s*(?:/|per)\s*day"
                          r"|no credit card|免费额度|免费试用|每天\s*\d+\s*次")
FREE_CUE = re.compile(r"(?i)\bfree\b|免费|\bincluded\b|✓|\$0\b|0元")
NOT_FREE = re.compile(r"(?i)not included|not available|✗|×|不含|不包括|仅限付费|paid only|premium only")
SUBSCRIPTION_WORDS = ("订阅", "开通", "机构", "学校", "图书馆", "subscription", "subscrib", "institution", "library")


YEAR_RE = re.compile(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)")
YEAR_SPAN = re.compile(r"(?<!\d)(1[89]\d\d|20\d\d)\s*(?:-|–|—|~|至|到|to)\s*(1[89]\d\d|20\d\d)(?!\d)")


def covers_paper(src: dict, evidence: str) -> bool:
    """论文写了版本：证据要写到版本号；写了年份：证据里要有落在论文年份范围内的年份。都没写 → 不在这里判断。"""
    version = src.get("version") or ""
    tokens = re.findall(r"\d+(?:\.\d+)+", version) or re.findall(r"\bv\d+\b", version, re.I)
    if tokens:
        return any(normalize(tk) in normalize(evidence) for tk in tokens)
    years = [int(y) for y in YEAR_RE.findall(src.get("sample_period") or "")]
    if not years:
        return True
    if len(years) > 1 and not YEAR_SPAN.search(src.get("sample_period") or ""):
        # 分开的几卷（如 2000、2010）：每一卷都要写到
        return all(str(y) in evidence for y in years)
    lo, hi = min(years), max(years)
    spans = [(int(a), int(b)) for a, b in YEAR_SPAN.findall(evidence)]          # “1960-2023”这类范围：和论文年份有重叠就算
    return (any(a <= hi and b >= lo for a, b in spans)
            or any(lo <= int(y) <= hi for y in YEAR_RE.findall(evidence)))


def scope_evidence_ok(ev: str, page: dict) -> bool:
    """“保留免费渠道”的对应依据：页面标题、页面上逐字存在的一句（标题、套餐表行等），或页面上的直接下载链接。"""
    ev = (ev or "").strip()
    if not ev:
        return False
    if ev.startswith("http"):
        return any(ev.rstrip("/") == (l.get("url") or "").rstrip("/") for l in page.get("links", []))
    return normalize(ev) in normalize(page.get("title") or "") or quote_in_text(ev, page.get("text", ""))


def condition_scope(kind: str, decision: dict, text: str, aq: str, channel: str, warned: set | None,
                    url: str, page: dict | None = None) -> tuple[str | None, str, str | None, bool | str]:
    """订阅/购买（kind=payment）或审核（kind=review）：页面提到这些条件、模型交的是免费渠道时，
    模型要说明条件针对哪份数据（this_data / other_part / unclear）并附原文。返回 (退回原因, 渠道, 说明, 是否待核对)。
    - 第一次提交没带齐依据 → 退回复查（带齐了就直接核对，省一次调用）
    - this_data：原文逐字在页面上 → 渠道改为“向提供方申请”（审核）或“机构订阅 / 付费购买”（按原文）
    - other_part：原文逐字在页面上，且下载依据本身不提这类条件 → 保留原渠道，注明另一版本需要
    - 其他（看不清、没说明、下载依据本身提到条件）→ 保留入口，标“待核对”，不写成免费渠道的结论"""
    c = CONDITION[kind]
    found = affirmed_cues(text, c["cues"])   # v1：只被否定提到（无需购买、不收费）不算页面提到条件，不退回、不追问
    if not found:
        return None, channel, None, False
    scope, q = decision.get(f"{kind}_scope"), (decision.get(f"{kind}_quote") or "").strip()
    if warned is not None and url not in warned and not (scope and q):
        warned.add(url)
        return (f"Rejected for now: the page mentions {c['what']}: " + " | ".join(f'"…{x}…"' for x in found)
                + f". Submit again with {kind}_scope (this_data / other_part / unclear) and {kind}_quote (that sentence "
                  "copied word-for-word). this_data = it applies to the data/version the paper used; other_part = it applies "
                  "only to another version or part. With other_part also give other_part_name (what that other part is) and "
                  "scope_evidence: the page title, a heading or pricing-table row copied word-for-word, or the direct "
                  "download URL, that ties the free access to the data the paper used."), channel, None, False
    if scope in ("this_data", "other_part") and not (q and quote_in_text(q, text)):
        return f"Rejected: {kind}_quote was not found word-for-word on that page. Copy that sentence exactly.", channel, None, False
    if scope == "this_data":
        support = condition_support(kind, q)
        if support != "affirmed":
            # v1：引文不支持“需要该条件” → 不改渠道。否定句 = 引文本身说不需要；其余情况（没写、同句免费与收费并存）→ 条件待核
            if support == "negated" and not affirmed_cues(text.replace(q, " "), c["cues"]):
                return None, channel, (f"the model said {c['what']} applies, but its quote says it is not needed (“{q}”), and the "
                                       f"page states it nowhere else — {channel} is kept"), False
            why = {"negated": f"its quote says it is not needed (“{q}”), but the page mentions it elsewhere: {found[0]}",
                   "mixed": f"its quote states both free access and {c['what']} (“{q}”) — probably different sub-products",
                   "none": f"its quote does not state {c['what']} (“{q}”)"}[support]
            return None, channel, (c["pending"] + f"; the model said it applies to this data, but {why}. {channel} is kept "
                                   "as the verified fact; the condition is pending"), True
        if kind == "payment" and states_free(aq) and normalize(aq) != normalize(q):
            # 改写后复查：获取依据明确写免费，收费依据又说这份数据要付费 → 证据矛盾，保留已核实的事实，条件待核
            return None, channel, (c["pending"] + f"; the access quote says it is free (“{aq}”) but the payment quote says "
                                   f"{c['what']} is needed (“{q}”) — the evidence conflicts, so {channel} is kept and the "
                                   "condition is pending"), True
        if kind == "review":
            note = ("registration required; download after review approval" if channel == "registration_download"
                    else "download after review approval")
            new = "apply_to_provider"
        else:
            new = "subscription" if any(w in q.lower() for w in SUBSCRIPTION_WORDS) else "purchase"
            note = "institutional subscription required" if new == "subscription" else "paid purchase required"
        return None, new, f"{note} (channel changed from {channel} to {new}): “{q}”", False
    if scope == "other_part" and not affirmed_cues(aq, c["cues"]):
        # 2026-11-17 回归（WWO）后的规则：保留免费渠道要说清“另一部分”是什么，并给出免费说明对应论文所用数据的依据
        other = (decision.get("other_part_name") or "").strip()
        ev = (decision.get("scope_evidence") or "").strip()
        page = page or {"text": text}
        generic = bool(GENERIC_FREE.search(aq))
        if generic and not (scope_evidence_ok(ev, page) and FREE_CUE.search(ev) and not NOT_FREE.search(ev)
                            and normalize(ev) != normalize(aq)):
            # 证据只有全站免费额度：不判免费，保留入口，标“该产品是否包含在免费额度内，待核对”
            return None, channel, (f"the access quote is a site-wide free quota (“{aq}”); whether the product the paper used is "
                                   f"included in it is unclear — please check"), "free_quota"
        if ev and not scope_evidence_ok(ev, page):
            # 依据写错格式（转述、拼接）和其他引文一样退回重交，不直接定成待核对
            return ("Rejected: scope_evidence was not found on that page. Copy ONE heading, title or pricing-table row "
                    "word-for-word (no paraphrase, no combining), or give the direct download URL."), channel, None, False
        if not other or not ev:
            return None, channel, (c["pending"] + "; the model did not name the other product or did not show what ties the "
                                   "free access to the data used"), True
        return None, channel, (f"the page requires {c['what']} for another version or part ({other}): “{q}”; the free access "
                               f"is tied to the data used by: “{ev}”, so {channel} is kept"), False
    return None, channel, c["pending"] + (f": “{q}”" if q else f"; the page says: {found[0]}"), True


def verify_finding(web: Web, src: dict, decision: dict, learned: dict, linked_from_official: set,
                   timeout: int = 25, payment_warned: set | None = None, deepseek_retry: bool = True,
                   review_warned: set | None = None) -> tuple[bool, str, dict | None]:
    url = (decision.get("url") or "").strip()
    page = web.fetch(url, timeout=timeout, deepseek_retry=deepseek_retry) if url else {"error": "no url"}
    if page.get("error"):
        return False, f"{UNREADABLE} ({page['error']}).", None
    ok, why = official_status(url, page, src, learned, linked_from_official, decision.get("provider_quote"))
    if not ok:
        return False, f"Rejected: not an official source — {why}.", None
    area, site_country = src.get("study_area"), host_country(host(page.get("final_url") or url))
    if area and site_country and site_country != area:
        return False, (f"Rejected: the paper studies {area}, but this is a {site_country} government site — it describes "
                       f"{site_country}'s data, not the data the paper used. Look for {area}'s own data."), None
    channel, elig, result = decision.get("channel"), decision.get("eligibility") or "not_stated", decision.get("check_result")
    if channel not in CHANNELS:
        return False, f"Rejected: channel must be one of {', '.join(CHANNELS)}.", None
    if elig not in ELIGIBILITY:
        return False, f"Rejected: eligibility must be one of {', '.join(ELIGIBILITY)}.", None
    if result not in CHECK_RESULTS:
        return False, f"Rejected: check_result must be one of {', '.join(CHECK_RESULTS)}.", None
    aq = decision.get("access_quote") or ""
    if not quote_in_text(aq, page["text"]):
        return False, "Rejected: the access_quote was not found word-for-word on that page. Copy it exactly from read_page.", None
    if not access_stated(channel, aq):
        return False, access_gate_message(channel) + ".", None
    notes, pending, cond_note = [], [], None
    if channel in FREE_CHANNELS and GENERIC_FREE.search(aq) and not affirmed_cues(page["text"]):
        ev = (decision.get("scope_evidence") or "").strip()
        if not (scope_evidence_ok(ev, page) and FREE_CUE.search(ev) and not NOT_FREE.search(ev) and normalize(ev) != normalize(aq)):
            notes.append(f"the access quote is a site-wide free quota (“{aq}”); whether the product the paper used is included "
                         f"in it is unclear — please check")
            pending.append("free_quota")
    # 页面上提到订阅/购买、审核：免费渠道要说明这些条件针对哪份数据（两条规则共用同一套处理）
    for kind in ("payment", "review"):
        if channel not in FREE_CHANNELS:
            break
        warned = payment_warned if kind == "payment" else review_warned
        reject, channel, note, is_pending = condition_scope(kind, decision, page["text"], aq, channel, warned, url, page)
        if reject:
            return False, reject, None
        if note:
            notes.append(note)
        if is_pending:
            pending.append(is_pending if isinstance(is_pending, str) else kind)
        elif channel not in FREE_CHANNELS:
            cond_note = note.split(" (channel changed")[0]
    vq = decision.get("version_quote") or ""
    version_ok = bool(vq) and quote_in_text(vq, page["text"])
    if result == "same_version_found" and not version_ok:
        result = "other_version_only"
        notes.append("same version claimed, but no version sentence from the page was located → recorded as other version only")
    if result == "same_version_found" and not covers_paper(src, f"{vq} {page.get('title') or ''}"):
        # v2.4b：论文写了年份或版本，官网引文（或页面标题）却没写到 → 不能说是同一版本，标待核对
        notes.append(f"the paper used {src.get('version') or src.get('sample_period')}, but the quoted page text does not name "
                     f"these years or this version — whether they are covered is pending")
        result = VERSION_UNCONFIRMED   # 报告和评分都按“版本待核对”处理，不显示“覆盖论文所用版本”
        pending.append("version")
    checked = date.fromisoformat(page.get("fetched_on")) if page.get("fetched_on") else date.today()
    as_of = historical_announcement(page, url, aq, checked)
    if as_of:
        # 只找到发布当时的公告：保留链接和它能证明的内容（发行时的获取条件），当前渠道待核对
        notes.append(f"this is an announcement dated {as_of.isoformat()}: it shows how the data could be obtained when released "
                     f"({channel}), not how to obtain it now — current channel pending")
        pending.append("current")
    if result == "other_version_only":
        # 只找到其他版本或产品：渠道只说明那个版本 / 产品，论文所用产品的当前渠道待核对
        notes.append(f"the page covers another version or product; {channel} applies to that one — the channel for the product "
                     f"the paper used is pending")
        pending.append("product")
    kept, dropped = [], []
    for r in decision.get("restrictions") or []:
        (kept if r and normalize(r) in normalize(page["text"]) else dropped).append(r)
    if dropped:
        notes.append(f"restrictions not found on the page were dropped: {dropped}")
    if not src.get("version") and not src.get("sample_period"):
        notes.append("the paper states no version or years, so version correspondence could not be checked")
        if result == "same_version_found":
            # 2026-11-17 WorldClim 回归：论文没写版本和年份，程序无法核对“同一产品”（历史基线 vs 未来预测）→ 目标产品渠道待核对
            notes.append(f"the model said this is the product the paper used, but nothing in the paper pins the version, so "
                         f"{channel} is shown for this page's product only — the channel for the paper's product is pending")
            if "product" not in pending:
                pending.append("product")
    finding = {
        "url": url, "final_url": page.get("final_url"), "page_title": page.get("title"), "read_by": page.get("method"),
        "official_basis": why,
        # 依据来自哪里（和标准答案的“依据来自哪里”一列对应）：官网本身，或官网链接过去的平台。第三方资料不会被接受为依据
        "evidence_source": (DISTRIBUTOR if why.startswith(DISTRIBUTOR)
                            else "linked_platform" if why == "linked from an official page" else "official_page"),
        "channel": channel, "eligibility": elig, "restrictions": kept, "check_result": result,
        "access_quote": aq, "version_quote": vq if version_ok else None, "checked_on": page.get("fetched_on") or date.today().isoformat(),
        "notes": notes, "judgment": "channel, eligibility and version correspondence are model judgments on the quoted page text",
        "pending": pending, "review_pending": "review" in pending, "payment_pending": "payment" in pending,
        "review_note": cond_note, "as_of": as_of.isoformat() if as_of else None,
    }
    where = "a distributor page (not the original provider)" if why.startswith(DISTRIBUTOR) else "the official page"
    return True, f"Accepted: verified against {where}." + (f" Notes: {'; '.join(notes)}" if notes else ""), finding


# ============ Agent 循环 ============

def describe_source(src: dict, learned: dict) -> str:
    ev = src.get("access_evidence") or {}
    lines = [f"Data source: {src.get('name')}",
             f"Provider (from the paper, model-extracted): {src.get('provider') or 'not stated'}",
             f"Version / file used in the paper: {src.get('version') or 'not stated'}"
             + (" (located in the paper text)" if src.get("version_verified") else ""),
             f"Years used in the paper: {src.get('sample_period') or 'not stated'}",
             f"How the paper describes this data (source sentence): "
             + (f'"{(src.get("source_evidence") or {}).get("quote")}"' if (src.get("source_evidence") or {}).get("quote") else "not available"),
             f"What the paper says about access: {src.get('access_category', 'unknown')}"
             + (f' — "{ev.get("quote")}" (p. {ev.get("page")})' if ev.get("quote") else ""),
             f"URLs written in the paper: {', '.join(src.get('urls') or []) or 'none'}",
             f"Country the research is about: {src.get('study_area') or 'not stated'}"
             + (" — the data is that country's data; include the country in searches" if src.get("study_area") else ""),
             f"Official domains already verified for this provider: {', '.join(learned_domains_for(src, learned)) or 'none'}"]
    if china_print_stats(src):   # v2.4a：纸质资料也可能有官方在线版（如国家统计局网站上的年鉴、普查资料），先查
        lines.append("This is a printed statistical publication. FIRST search whether an official online or electronic version of "
                     "the editions the paper used exists (e.g. on stats.gov.cn or a provincial statistics bureau site) and read it. "
                     "Copies on third-party sites do not count.")
    return "\n".join(lines)


def ask_model(system: str, content: str) -> tuple[dict, str]:
    """官网核查 Agent 默认用 DeepSeek（有 DEEPSEEK_API_KEY 时），避开 Gemini 免费层的排队；
    设置环境变量 OFFICIAL_MODEL=gemini 可改回 Gemini。论文提取不受影响，仍用 Gemini。"""
    if os.environ.get("DEEPSEEK_API_KEY") and os.environ.get("OFFICIAL_MODEL", "deepseek") != "gemini":
        import deepseek_client
        return deepseek_client.generate_json(system, content, ACTION_SCHEMA)
    return gemini_client.generate_json(system, content, ACTION_SCHEMA)


def _same_page(a: str, b: str) -> bool:
    """同一网站（后两段域名相同，如 www.cdc.gov 与 portugues.cdc.gov）、同一路径，视为同一页面。"""
    pa, pb = urlparse(a), urlparse(b)
    base = lambda h: ".".join((h or "").lower().split(".")[-2:])
    return base(pa.hostname) == base(pb.hostname) and pa.path.rstrip("/") == pb.path.rstrip("/")


def _origin(url: str, src: dict, learned: dict, search_urls: set, link_urls: set) -> str:
    if any(_same_page(url, u) for u in (src.get("urls") or [])):
        return "paper"
    if any(host(url) == d or host(url).endswith("." + d) for d in learned_domains_for(src, learned)):
        return "learned"
    if any(_same_page(url, u) for u in search_urls):
        return "search"
    if any(_same_page(url, u) for u in link_urls):
        return "link"
    return "model"


def _page_excerpt(page: dict, near: str | None) -> str:
    text = page.get("text", "")
    start = 0
    if near:
        i = normalize(text).find(normalize(near))
        start = max(0, i - 300) if i >= 0 else 0
    excerpt = text[start:start + 1800]
    links = "\n".join(f"  - {l['text'] or '(no text)'} → {l['url']}" for l in page.get("links", [])[:30])
    return f"Title: {page.get('title')}\nRead by: {page.get('method')}\nText (from char {start}):\n{excerpt}\nLinks:\n{links}"


def _log(verbose: bool, step: dict) -> None:
    """每一步在终端打印一行，方便看进度（测试时关闭）。"""
    if verbose:
        args = {k: (v[:60] + "…" if isinstance(v, str) and len(v) > 60 else v) for k, v in step["args"].items()}
        obs = " ".join(step.get("observation", "").split())[:140]
        print(f"    step {step['step']} [{step.get('model')}] {step['action']} {json.dumps(args, ensure_ascii=False)}\n      → {obs}", flush=True)


# ============ 已知渠道：中国的纸质统计资料（v2.4，本人定） ============
# 统计年鉴、普查资料汇编多数只有纸质版：官方渠道是买书，或到国家统计局的中国统计资料馆免费查阅。
# Agent 没找到这份资料可用的获取说明（或只找到别的年份）时，归为 apply_to_provider（到馆查阅），依据由程序逐字核对。
CN_LIBRARY = {"url": "https://www.stats.gov.cn/zs/tjwh/tjzlg/202406/t20240627_1955213.html",
              "access_quote": "资料馆设立了网站查询、电子邮件、电话咨询、现场查阅多种渠道",
              "version_quote": "不仅囊括国家统计局编印的所有统计资料"}
PRINT_STATS = re.compile(r"(?i)yearbook|tabulation|年鉴|普查资料|统计资料")


def china_print_stats(src: dict) -> bool:
    return src.get("study_area") == "China" and bool(PRINT_STATS.search(f"{src.get('name') or ''} {src.get('provider') or ''}"))


def library_finding(web: Web) -> dict | None:
    page = web.fetch(CN_LIBRARY["url"])
    if page.get("error") or not all(quote_in_text(CN_LIBRARY[k], page["text"]) for k in ("access_quote", "version_quote")):
        return None
    # v2.4b：资料馆的通用说明只能支持“可以到馆查阅”这条线索；具体卷册是否可查，页面没写 → 待核对
    return {"url": CN_LIBRARY["url"], "final_url": page.get("final_url"), "page_title": page.get("title"), "read_by": page.get("method"),
            "official_basis": "known channel for Chinese statistical publications (National Bureau of Statistics library)",
            "evidence_source": "official_page", "channel": "apply_to_provider", "eligibility": "individuals", "restrictions": [],
            "check_result": VERSION_UNCONFIRMED, "access_quote": CN_LIBRARY["access_quote"],
            "version_quote": CN_LIBRARY["version_quote"], "checked_on": page.get("fetched_on") or date.today().isoformat(),
            "notes": ["print publication: the library page describes its holdings in general (all NBS publications); "
                      "whether the specific volumes the paper used are held is not stated — please check"],
            "judgment": "known-channel rule; quotes checked by the program", "pending": ["version"], "review_pending": False,
            "payment_pending": False, "review_note": None, "as_of": None, "discovered_via": "known_channel"}


def online_edition_hits(src: dict, web: Web, learned: dict) -> list[str] | None:
    """归到统计资料馆之前，程序按出版物名称 + 卷次检索官方在线版（Agent 的检索不算：它可能搜的是别的卷或别的年鉴）。
    返回结果里的官方域名网址；检索失败（出错、离线未缓存）返回 None —— 没查成不能当作“没有在线版”。"""
    core = re.sub(r"\s*\(.*?\)\s*", " ", src.get("name") or "").strip()
    years = YEAR_RE.findall(" ".join(re.findall(r"\((.*?)\)", src.get("name") or ""))) or YEAR_RE.findall(src.get("sample_period") or "")
    res = web.search(f"{core} {' '.join(years)} 电子版 在线")
    if res.get("error"):
        return None
    return [r["url"] for r in res.get("results", [])
            if is_institutional(host(r["url"])) or any(host(r["url"]).endswith(d) for d in learned_domains_for(src, learned))]


def run_check(src: dict, web: Web, learned: dict, max_steps: int = MAX_STEPS, ask=ask_model, verbose: bool = False) -> dict:
    """核查一个数据源：Agent 先查；中国的纸质统计资料确认没有官方在线版后，补上统计资料馆这个已知渠道。"""
    result = agent_check(src, web, learned, max_steps, ask, verbose)
    f = result.get("finding")
    if china_print_stats(src) and (not f or "product" in f["pending"]):
        hits = online_edition_hits(src, web, learned)
        if hits is None:   # 在线版没查成 → 不归档，结果保持原样
            return dict(result, online_search="failed")
        if hits:   # 可能有官方在线版，没核对过 → 不归档，列入手动核对
            for u in hits[:3]:
                result["leads"].setdefault(u, {"decision": None, "discovered_via": "search",
                                               "reason": "possible official online edition of this publication — not checked"})
            return result
        lib = library_finding(web)
        if lib:
            if f:
                lib["notes"].append(f"the agent also found: {f['channel']} at {f['url']} (for another edition)")
            result = dict(result, outcome="found", finding=lib, agent_outcome=result["outcome"])
    return result


def agent_check(src: dict, web: Web, learned: dict, max_steps: int = MAX_STEPS, ask=ask_model, verbose: bool = False) -> dict:
    """Agent 循环。返回 {outcome, finding?, steps, discovery}。ask 只在测试时替换。"""
    task = describe_source(src, learned)
    steps, seen = [], set()
    search_urls, link_urls, official_pages, read_origins = set(), set(), set(), {}
    last_results = None
    leads = {}   # 提交了、但页面读不到的网址：主流程结束后再试一次，仍读不到就请用户手动核对
    payment_warned = set()   # 已经因为页面提到订阅/购买退回过一次的网址
    review_warned = set()    # 已经因为页面提到审核退回过一次的网址
    official_sites = set()   # 读到过、程序认定为官方的页面（找到官方站点 ≠ 找到获取说明）

    def end(outcome: str, **extra) -> dict:
        return {"outcome": outcome, **extra, "steps": steps, "read": read_origins, "leads": leads,
                "official_sites": sorted(official_sites)}
    for n in range(1, max_steps + 1):
        history = "\n\n".join(f"Step {s['step']}: {s['action']} {json.dumps(s['args'], ensure_ascii=False)}\n"
                              f"Result: {s['observation'][:MAX_OBSERVATION]}" for s in steps)
        left = max_steps - n + 1
        content = f"{task}\n\n{history or '(no steps yet)'}\n\nSteps left (including this one): {left}"
        if left <= 2:   # v2.4：WDI 读到了页面却没提交
            content += "\nFew steps left: if a page you already read states how to obtain the data, submit_finding now."
        if verbose:
            print(f"    step {n}: asking the model…", flush=True)
        try:
            decision, model = ask(SYSTEM_PROMPT, content)
        except (Exception, SystemExit) as e:
            if verbose:
                print(f"    model call failed: {str(e)[:200]}", flush=True)
            if hasattr(e, "raw"):   # deepseek_client.ParseError：两次都不是可解析的 JSON
                return end("parse_error", error=str(e)[:300], raw_response=e.raw[:4000])
            return end("agent_error", error=str(e)[:300])
        if not isinstance(decision, dict):
            return end("agent_error", error="model did not return a JSON object")
        action = decision.get("action")
        args = {k: v for k, v in decision.items() if k not in ("thought", "action") and v not in (None, [], "")}
        step = {"step": n, "model": model, "thought": decision.get("thought", ""), "action": action, "args": args}
        steps.append(step)
        key = json.dumps([action, args], sort_keys=True, ensure_ascii=False)
        if action == "give_up":
            step["observation"] = "Stopped: no official access route was found."
            _log(verbose, step)
            return end("not_found", reason=decision.get("reason"))
        resubmit = action == "submit_finding" and (decision.get("url") or "").strip() in (payment_warned | review_warned)
        if key in seen and not resubmit:   # 订阅/购买提醒后原样再提交是允许的（模型确认那些说明与此无关）
            step["observation"] = "Not executed: you already did exactly this. Try something different, or give_up."
            _log(verbose, step)
            continue
        seen.add(key)
        try:
            if action == "search_web" and sum(s["action"] == "search_web" for s in steps) > MAX_SEARCHES:
                step["observation"] = (f"Not executed: search limit ({MAX_SEARCHES}) reached. Read a page from the results above, "
                                       f"submit_finding, or give_up.")
            elif action == "search_web":
                res = web.search(decision.get("query") or "")
                urls = [r["url"] for r in res.get("results", [])]
                search_urls.update(urls)
                step["observation"] = res.get("error") or "\n".join(
                    f"[{i}] {r['title']} — {r['url']}\n    {(r.get('snippet') or '')[:200]}"
                    for i, r in enumerate(res["results"], 1)) or "No results."
                if urls and urls[:3] == (last_results or [])[:3]:
                    # 2026-11-17 试点：SEDAC 换了 4 次检索词，前几条结果完全相同，步数白白用掉
                    step["observation"] = ("Same top results as your previous search — searching again will not help. "
                                           "Read one of these pages, or try a different site.\n") + step["observation"]
                last_results = urls
            elif action == "read_page":
                url = (decision.get("url") or "").strip()
                page = web.fetch(url)
                read_origins.setdefault(url, _origin(url, src, learned, search_urls, link_urls))
                if page.get("error"):
                    step["observation"] = f"Could not read the page: {page['error']}"
                    h = host(url)
                    if url and (is_institutional(h) or own_domain_term(h, src)
                                or any(h == d or h.endswith("." + d) for d in learned_domains_for(src, learned))):
                        # 像官方入口、但读不到：模型没提交也记下来，主流程后再试一次，仍读不到就请用户手动核对
                        leads.setdefault(url, {"decision": None, "reason": step["observation"],
                                               "discovered_via": read_origins.get(url)})
                else:
                    links = {l["url"] for l in page.get("links", [])}
                    link_urls.update(links)
                    st_ok, st_why = official_status(url, page, src, learned, official_pages)
                    if st_ok and not st_why.startswith(DISTRIBUTOR):   # 分发方不把“官方”传给它链接出去的页面
                        official_pages.update(links)   # 官方页面链接出去的平台也算官方
                        official_sites.add(url)
                    step["observation"] = _page_excerpt(page, decision.get("near"))
            elif action == "submit_finding":
                ok, message, finding = verify_finding(web, src, decision, learned, official_pages,
                                                      payment_warned=payment_warned, review_warned=review_warned)
                step["observation"] = message
                if not ok and message.startswith(UNREADABLE):
                    u = (decision.get("url") or "").strip()
                    leads[u] = {"decision": {k: v for k, v in decision.items() if k != "thought"}, "reason": message,
                                "discovered_via": read_origins.get(u) or _origin(u, src, learned, search_urls, link_urls)}
                _log(verbose, step)
                if ok:
                    url = finding["url"]
                    finding["discovered_via"] = read_origins.get(url) or _origin(url, src, learned, search_urls, link_urls)
                    if not finding["official_basis"].startswith(("previously verified", DISTRIBUTOR)):   # 分发方不记为已核实官方域名
                        learned["domains"].append({"domain": host(finding["final_url"] or url),
                                                   "label": f"{src.get('name')} | {src.get('provider') or ''}",
                                                   "first_verified": finding["checked_on"]})
                    return end("found", finding=finding)
            else:
                step["observation"] = f"Error: unknown action {action!r}. Use one of {', '.join(ACTIONS)}."
        except Exception as e:
            step["observation"] = f"Error: the tool failed ({type(e).__name__}: {str(e)[:120]}). Try a different action."
        if action != "submit_finding":
            _log(verbose, step)
    return end("budget_exhausted")


# ============ 报告用：对合并后的每个数据源做官网核查 ============

def source_for_merged(m: dict) -> dict:
    """合并后的一个数据源（step3.merge_reports 的一项）→ 交给 Agent 的描述。
    选版本信息最完整的那条论文记录；论文中的网址合并所有论文的。"""
    def rank(u):
        s = u["src"]
        return (bool(s.get("version_verified")), bool(s.get("version")), bool(s.get("provider")), bool(s.get("sample_period")))
    best = max(m["uses"], key=rank)["src"]
    src = dict(best)
    areas = {u["src"].get("study_area") for u in m["uses"]}
    src["study_area"] = areas.pop() if len(areas) == 1 else None
    src["urls"] = list(dict.fromkeys(url for u in m["uses"] for url in (u["src"].get("urls") or [])))
    return src


def check_merged(merged: list[dict], web: Web, learned: dict, ask=ask_model, verbose: bool = False,
                 learned_path: str | None = LEARNED_FILE) -> dict:
    """对每个合并后的数据源跑一次官网核查。返回 {合并键: {name, checked_source, result}}，可直接存成 JSON。
    读不到的官方页面直接列入手动核对（mark_manual）。"""
    out = {}
    for i, m in enumerate(merged, 1):
        src = source_for_merged(m)
        if verbose:
            print(f"  [{i}/{len(merged)}] {m['display']}", flush=True)
        try:
            res = mark_manual(run_check(src, web, learned, ask=ask, verbose=verbose))
        except Exception as e:   # 2026-11-18：一条出错只记这一条（以前会让整批官网核查放弃，报告全部 not checked）
            res = {"outcome": "check_failed", "error": f"{type(e).__name__}: {str(e)[:300]}", "steps": [], "read": {}, "leads": {}}
        out[m["key"]] = {"name": m["display"],
                         "checked_source": {k: src.get(k) for k in ("name", "provider", "version", "sample_period", "urls", "study_area")},
                         "result": res}
        if verbose:
            print("    " + summary_line(src, res), flush=True)
    if learned_path:   # 测试时传 None，不改动真实的域名名单
        save_learned(learned, learned_path)
    return out


def mark_manual(result: dict, max_urls: int = 3) -> dict:
    """主流程没得到核对通过的结果、但有读不到的官方页面 → 直接记为 manual_check（不再重试）。
    网址去重：同一网站同一栏目只留一个；模型提交过的排在前面；最多 max_urls 个。"""
    if result.get("outcome") == "found" or not result.get("leads"):
        return result
    ordered = sorted(result["leads"].items(), key=lambda kv: kv[1]["decision"] is None)
    kept, seen = {}, set()
    for url, lead in ordered:
        h = host(url)
        first = urlparse(url).path.strip("/").split("/")[0] if urlparse(url).path.strip("/") else ""
        if (h, first) in seen:
            continue
        seen.add((h, first))
        kept[url] = lead
        if len(kept) >= max_urls:
            break
    result["all_unreadable"] = list(result["leads"])
    result["leads"] = kept
    result["outcome_before_manual"] = result.get("outcome")
    result["outcome"] = "manual_check"
    return result


def summary_line(src: dict, result: dict) -> str:
    """一行结论（报告和终端用）。"""
    if result["outcome"] == "manual_check":
        urls = ", ".join(result["leads"])
        return f"{src.get('name')}: official entry found but the page could not be read — please check manually: {urls}"
    if result["outcome"] != "found":
        why = {"not_found": "no official access route found", "budget_exhausted": "step budget used up before a verified finding",
               "agent_error": "model call failed", "parse_error": "the model's answer could not be read (invalid JSON twice)",
               "check_failed": f"the check failed ({result.get('error', 'unknown error')})"}.get(
                   result["outcome"], f"no result ({result['outcome']})")   # 不认识的结果也只影响这一行（以前 parse_error 会抛 KeyError）
        return f"{src.get('name')}: official check — {why}"
    f = result["finding"]
    parts = [f["channel"], f["eligibility"]] + [f"restriction: {r}" for r in f["restrictions"]] + [f["check_result"]]
    return f"{src.get('name')}: " + " | ".join(parts) + f" — {f['url']} (checked {f['checked_on']}, found via {f['discovered_via']})"
