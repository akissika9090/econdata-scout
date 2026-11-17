"""
Evidence Recovery Agent 可以使用的工具。

每个工具都是普通的 Python 函数：输入简单的参数，返回一段给模型看的文字（observation）。
工具只做“查”和“核对”，不做判断——最终能不能接受一条证据，由 submit_evidence 用和基础流程完全相同的规则决定。

    search_pdf(query)                    在全文中按关键词找句子，返回最多 5 句（附页码）
    read_page(page, near)                阅读某一页；给了 near 时，只返回这个词附近的一段
    submit_evidence(category, quote, page)
                                         提交“获取条件分类 + 原文引用 + 页码”，由程序核对：
                                         引用存在、引用支持该分类、引用针对这个数据，三项都满足才接受
"""

import re

import step1_pdf_evidence as step1
import step2_ai_extract as step2

MAX_RESULTS = 5          # search_pdf 最多返回几句
MAX_SENTENCE = 400       # 每句最多显示多少字符
MAX_PAGE_TEXT = 2500     # read_page 最多返回多少字符
STOPWORDS = {"the", "and", "for", "are", "was", "were", "this", "that", "with", "from", "data", "dataset"}

# 提交失败时告诉模型原因，方便它决定下一步（换一句、再找，或者放弃）
REJECT_REASONS = {
    "quote_not_found": "the quote was not found word-for-word on that page (copy it exactly, and check the page number)",
    "no_signal": "the quote does not explicitly state that access condition",
    "conflict": "the quote states both public and restricted conditions; it cannot be used alone",
    "multiple_sources": "the quote also names another data source of this paper; it is left for manual review",
    "anaphor_reference": ("the quote starts with a reference such as 'The data' and does not name this data source itself; "
                          "it is left for manual review"),
    "multi_sentence": ("the quote has more than one sentence; evidence must be a single sentence "
                       "(multi-sentence evidence is left for manual review)"),
    "general_statement": "the quote is a general statement about the paper's data, not about this specific data source",
    "unclear_reference": "the quote does not clearly refer to this data source",
    "none": "category 'unknown' cannot be submitted; use give_up instead",
}


def split_sentences(pages: list[str]) -> list[tuple[int, str]]:
    """把每页文字切成句子，返回 [(页码, 句子)]。只用于搜索，不改动原文。"""
    result = []
    for page_no, text in enumerate(pages, start=1):
        flat = re.sub(r"\s+", " ", text)
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", flat):
            sentence = sentence.strip()
            if len(sentence) >= 20:
                result.append((page_no, sentence))
    return result


def search_pdf(pages: list[str], query: str) -> str:
    """按关键词搜索：句子里出现的关键词越多排得越前；关键词一个都没出现的句子不返回。"""
    terms = [t for t in re.findall(r"[a-z0-9]+", step1.normalize(query or "")) if len(t) >= 3 and t not in STOPWORDS]
    if not terms:
        return "Error: the query has no usable keywords. Use 1-5 specific words, e.g. 'publicly available' or the dataset name."
    scored = []
    for page_no, sentence in split_sentences(pages):
        low = step1.normalize(sentence)
        hits = sum(1 for t in terms if re.search(rf"\b{re.escape(t)}", low))
        if hits:
            scored.append((-hits, page_no, sentence))
    if not scored:
        return f"No sentence contains any of: {', '.join(terms)}."
    scored.sort()
    lines = [f"[page {p}] {s[:MAX_SENTENCE]}" for _, p, s in scored[:MAX_RESULTS]]
    more = f" (showing {MAX_RESULTS} of {len(scored)})" if len(scored) > MAX_RESULTS else ""
    return f"Sentences matching {', '.join(terms)}{more}:\n" + "\n".join(lines)


def read_page(pages: list[str], page: int, near: str | None = None) -> str:
    """返回某一页的文字。给了 near 时，返回这个词附近的一段（找不到就返回页首）。"""
    if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= len(pages):
        return f"Error: page must be a number from 1 to {len(pages)}."
    flat = re.sub(r"\s+", " ", pages[page - 1]).strip()
    if not flat:
        return f"Page {page} has no extractable text."
    start = 0
    if near:
        pos = flat.lower().find(near.lower())
        start = max(0, pos - MAX_PAGE_TEXT // 3) if pos != -1 else 0
    text = flat[start:start + MAX_PAGE_TEXT]
    cut = " [...]" if start + MAX_PAGE_TEXT < len(flat) else ""
    return f"[page {page}{', from character ' + str(start) if start else ''}]\n{text}{cut}"


def submit_evidence(pages: list[str], src: dict, category: str, quote: str, page: int,
                    statement: dict | None = None, others: list[dict] | None = None) -> tuple[bool, str, dict | None]:
    """核对 Agent 提交的证据。返回 (是否接受, 给模型看的说明, 核对后的证据)。
    规则和基础流程完全相同（step2.access_status）：Agent 不能用比基础流程更宽松的标准改变分类。"""
    if category not in ("public", "subscription", "restricted"):
        return False, "Rejected: category must be public, subscription or restricted.", None
    evidence = step2.check_evidence(pages, {"quote": quote or "", "page": page})
    status, scope = step2.access_status(pages, src, category, evidence, statement, others=others)
    if status == "verified":
        return True, "Accepted: the quote was verified against the PDF.", evidence
    return False, f"Rejected: {REJECT_REASONS.get(status, status)}.", evidence
