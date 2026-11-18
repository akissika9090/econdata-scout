"""
V2 官网核查用的网页工具：搜索（DeepSeek Search API）和读网页（先直接读取，读不到再用 DeepSeek Fetch API）。

- 每个读过的页面和每次搜索都存进 web_cache/，同一网址不重复读取，结果可复查；离线模式（offline=True）只读缓存，用于测试和回放
- 读到的页面统一变成“纯文字 + 链接列表”，程序用这份文字核对 AI 引用的官网原文
- 只发送检索词和公开网址，不发送论文 PDF

需要 DEEPSEEK_API_KEY 才能搜索或用 Fetch API；没有 key 时只能直接读取网页（搜索返回空结果并说明原因）。
"""

import hashlib
import json
import os
import re
import time
import unicodedata
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

DEEPSEEK_TOOLS = "https://api.deepseek.com/v1/tools"
CACHE_DIR = "web_cache"
USER_AGENT = "Mozilla/5.0 (compatible; EconDataScout/2.0; research tool)"
MIN_TEXT = 200            # 直接读取得到的文字少于这个长度，多半是靠 JavaScript 加载的页面，改用 Fetch API
RETRY_WAITS = [0, 5, 15]  # 429 / 5xx 时的等待秒数
CACHE_VERSION = 2         # 2026-11-17：修正中文网页编码后，旧缓存（可能是乱码）不再使用
META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([A-Za-z0-9_-]+)""", re.IGNORECASE)


def decode_html(raw: bytes, header_ctype: str, apparent: str | None) -> str:
    """网页编码：先看响应头，再看页面里的 <meta charset>，最后用自动检测。
    很多中文网站不在响应头里写 charset，按 ISO-8859-1 解码就会变成乱码（2026-11-17 试点中国家统计局页面的问题）。"""
    m = re.search(r"charset=([A-Za-z0-9_-]+)", header_ctype or "", re.IGNORECASE)
    enc = m.group(1) if m else None
    if not enc:
        mm = META_CHARSET.search(raw[:4000])
        enc = mm.group(1).decode() if mm else (apparent or "utf-8")
    try:
        return raw.decode(enc, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


# ============ 页面文字与链接 ============

class _TextAndLinks(HTMLParser):
    """从 HTML 中取出可见文字和链接（跳过 script / style）。"""

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base, self.parts, self.links = base_url, [], []
        self._skip, self._href, self._anchor = 0, None, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "a":
            href = dict(attrs).get("href")
            if href and not href.startswith(("javascript:", "mailto:", "#")):
                self._href, self._anchor = urljoin(self.base, href), []
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section", "td"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "a" and self._href:
            self.links.append({"url": self._href, "text": " ".join("".join(self._anchor).split())[:120]})
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        if self._href:
            self._anchor.append(data)


def html_to_text(html: str, base_url: str) -> tuple[str, list[dict]]:
    p = _TextAndLinks(base_url)
    p.feed(html)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.parts))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text, p.links


MD_LINK = re.compile(r"\[([^\]]{0,200})\]\((https?://[^)\s]+)\)")


def markdown_links(md: str) -> list[dict]:
    return [{"url": u, "text": " ".join(t.split())[:120]} for t, u in MD_LINK.findall(md or "")]


def normalize(text: str) -> str:
    """核对引文用：统一全角半角、引号、破折号，合并空白，忽略大小写。"""
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = t.replace("­", "")
    t = re.sub(r"[‘’´`]", "'", t)
    t = re.sub(r"[“”]", '"', t)
    t = re.sub(r"[‐‑‒–—−]", "-", t)
    return re.sub(r"\s+", " ", t).strip()


def quote_in_text(quote: str, text: str) -> bool:
    q = normalize(quote)
    return bool(q) and len(q) >= 8 and q in normalize(text)


def host(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


# ============ 网页读取与搜索 ============

class Web:
    """offline=True：只用 web_cache/ 里的内容（测试、回放）；session / sleep 只在测试时替换。"""

    def __init__(self, cache_dir: str = CACHE_DIR, offline: bool = False, session=None,
                 deepseek_key: str | None = None, sleep=time.sleep):
        self.cache_dir, self.offline, self.sleep = cache_dir, offline, sleep
        self.key = deepseek_key if deepseek_key is not None else os.environ.get("DEEPSEEK_API_KEY")
        self._session = session
        self.calls = {"search": 0, "fetch_direct": 0, "fetch_deepseek": 0}
        os.makedirs(cache_dir, exist_ok=True)

    @property
    def session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers["User-Agent"] = USER_AGENT
        return self._session

    def _cache_path(self, kind: str, key: str) -> str:
        return os.path.join(self.cache_dir, f"{kind}_{hashlib.sha1(key.encode()).hexdigest()[:16]}.json")

    def _load(self, kind, key):
        path = self._cache_path(kind, key)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if kind == "page" and data.get("cache_v") != CACHE_VERSION:
                return None   # 旧格式（可能是编码错误的页面）→ 重新读取
            return data
        return None

    def _save(self, kind, key, value):
        with open(self._cache_path(kind, key), "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=1)

    def _deepseek(self, endpoint: str, payload: dict, retry: bool = True) -> dict:
        last = None
        for wait in (RETRY_WAITS if retry else [0]):
            if wait:
                self.sleep(wait)
            r = self.session.post(f"{DEEPSEEK_TOOLS}/{endpoint}", json=payload, timeout=60,
                                  headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
            if r.status_code not in (408, 429) and r.status_code < 500:
                break   # 其他 4xx（如 402 余额不足）不重试
        raise RuntimeError(f"DeepSeek {endpoint} failed: {last}")

    def search(self, query: str, count: int = 8) -> dict:
        """返回 {"results": [{title, url, snippet, authority}], "error"?}。"""
        cached = self._load("search", f"{query}|{count}")
        if cached is not None:
            return cached
        if self.offline:
            return {"results": [], "error": "offline: this search is not in the cache"}
        if not self.key:
            return {"results": [], "error": "no DEEPSEEK_API_KEY: web search is unavailable"}
        try:
            data = self._deepseek("search", {"query": query[:128], "count": count})
        except Exception as e:
            return {"results": [], "error": str(e)[:200]}
        self.calls["search"] += 1
        out = {"query": query, "searched_on": date.today().isoformat(),
               "results": [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("snippet") or r.get("summary"),
                            "authority": r.get("authority")} for r in data.get("results", []) if r.get("url")]}
        self._save("search", f"{query}|{count}", out)
        return out

    def _direct(self, url: str, errors: list, timeout: int = 25) -> dict | None:
        """直接读取网页（requests）。成功返回页面；失败把原因加进 errors，返回 None。"""
        try:
            r = self.session.get(url, timeout=timeout, allow_redirects=True)
        except Exception as e:
            errors.append(f"direct ({url.split(':')[0]}): {type(e).__name__}")
            return None
        ctype = r.headers.get("Content-Type", "")
        if r.status_code != 200 or "html" not in ctype:
            errors.append(f"direct: HTTP {r.status_code} {ctype.split(';')[0]}")
            return None
        html = decode_html(r.content, ctype, getattr(r, "apparent_encoding", None))
        text, links = html_to_text(html, r.url)
        if len(text) < MIN_TEXT:
            errors.append("direct: page text too short (probably loaded by JavaScript)")
            return None
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        self.calls["fetch_direct"] += 1
        return {"url": url, "final_url": r.url, "title": " ".join((title.group(1) if title else "").split()),
                "text": text, "links": links, "method": "direct"}

    def fetch(self, url: str, timeout: int = 25, deepseek_retry: bool = True) -> dict:
        """返回 {url, title, text, links, method, fetched_on} 或 {url, error}。先直接读取，读不到再用 Fetch API。"""
        cached = self._load("page", url)
        if cached is not None:
            return cached
        if self.offline:
            return {"url": url, "error": "offline: this page is not in the cache"}
        errors = []
        page = self._direct(url, errors, timeout)
        if page is None and url.startswith("https://") and any("SSLError" in e for e in errors):
            # 不少中文网站证书链不完整：浏览器能打开，Python 验证失败。不关闭证书验证，改用 http 读同一地址，并在结果中注明
            page = self._direct("http://" + url[len("https://"):], errors, timeout)
            if page:
                page["url"], page["method"] = url, "direct_http_fallback"
        if page is None and self.key:
            try:
                data = self._deepseek("fetch", {"url": url}, retry=deepseek_retry)
                content = data.get("content") or ""
                if content.strip():
                    page = {"url": url, "final_url": url, "title": data.get("title") or "", "text": content,
                            "links": markdown_links(content), "method": "deepseek_fetch"}
                    self.calls["fetch_deepseek"] += 1
                else:
                    errors.append("deepseek_fetch: empty content")
            except Exception as e:
                errors.append(f"deepseek_fetch: {str(e)[:120]}")
        if page is None:
            return {"url": url, "error": "; ".join(errors) or "could not read the page"}
        page["fetched_on"] = date.today().isoformat()
        page["cache_v"] = CACHE_VERSION
        self._save("page", url, page)
        return page
