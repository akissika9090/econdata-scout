"""
第一步（修订版）：从用户上传的论文 PDF 中，按页提取文字，找出可能描述“数据来源和获取条件”的段落。
这一步完全不用 AI，结果是确定的、可复查的。之后 AI 只会看到这里筛出来的段落。

另外提供 verify_quote()：以后 AI 提取信息时必须给出“原文引用 + 页码”，
程序用它检查这句话是不是真的出现在那一页上，防止 AI 编造证据。

准备：
    pip install pymupdf
运行：
    python step1_pdf_evidence.py 你的论文.pdf
"""

import re
import sys
import unicodedata
import pymupdf  # PyMuPDF


# 和“数据来源/获取条件”相关的关键词。命中越多，段落越可能是我们要找的。
DATA_KEYWORDS = [
    "data", "dataset", "survey", "database", "census", "statistics",
    "obtained", "provided by", "collected", "source",
    "come from", "comes from", "conducted by", "drawn from",
]
# “某某数据来自某处”这种句式，是数据来源最直接的信号，出现在任何章节都应该被找到
# （例：Teng 2026 第5章 “Data on residential electricity use are from the China Electricity Council”）
SOURCE_SENTENCE = re.compile(
    r"\b(data|dataset|statistics|information)\b[^.]{0,80}?\b(are|is|were|was|come|comes|came)\s+"
    r"(mainly |primarily |largely )?(obtained |collected |drawn |taken |derived )?from\b"
    r"|\bwe (use|employ|obtain|collect|draw)\b[^.]{0,80}?\b(data|dataset|survey|statistics|rate|projections?)\b[^.]{0,40}?\bfrom\b"
    r"|\b(using|uses|used) (\w+ ){0,3}data from\b"          # “using data from the CGSS”（文献综述中也会命中，交给 AI 区分）
    r"|\bdata sources? (is|are|was|were)\b"                 # “The data source is the CFPS”
    r"|\b(are|is) (publicly |freely )?available (at|from|on)\b")  # “readings ... are available at www....”
ACCESS_KEYWORDS = [
    "not available to the public", "publicly available", "publicly released", "available upon request",
    "upon reasonable request", "upon a reasonable request",
    "confidential", "restricted", "proprietary", "license", "subscription",
    "permission", "agreement", "access", "public",
    # 样本覆盖受限的信号：作者因为数据原因缩小了样本
    "data availability", "data limitation", "data limitations", "not included due to",
    "missing", "unavailable",
]


def normalize(text: str) -> str:
    """统一格式，用于关键词匹配：
    - NFKC 把连字符号还原成普通字母（'ﬁ' → 'fi'）
    - 合并 PDF 换行造成的断词（如 'avail-\\nable'、'Com- mission'）
    - 压缩空白、转小写"""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("­", "")  # 软连字符
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def squash(text: str) -> str:
    """用于引用核查的更严格的统一：在 normalize 基础上去掉所有空白和连字符。
    因为有的 PDF 文字层丢了空格（'Ourﬁnalsamplecomprises'），或保留了排版断词（'em- ployees'），
    只比较字母和数字的顺序，才不会把真实引用误判为不存在。"""
    text = normalize(text)
    # 有的 PDF（如 Elsevier 部分期刊）把年份之间的“–”存成字母 e：'2004e2012' 实为 '2004–2012'
    text = re.sub(r"(\d{4})e(\d{4})", r"\1–\2", text)
    return re.sub(r"[\s\-‐‑–—]", "", text)


def extract_pages(pdf_path: str) -> tuple[list[str], list[list[tuple[str, float]]]]:
    """返回两样东西：每页的完整文字（用于引用核查），以及每页的文字块（用于找段落）。
    用“文字块”而不是按换行切分，是因为论文常是双栏排版，按块读取才能保持段落完整。
    每个块同时记下字号，用来区分正文和脚注（脚注字号更小）。
    扫描版 PDF 没有文字层，会得到空字符串。"""
    pages, blocks = [], []
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            pages.append(page.get_text())
            page_blocks = []
            for b in page.get_text("dict")["blocks"]:
                if b["type"] != 0 or not b["lines"]:
                    continue  # 跳过图片块
                spans = [sp for line in b["lines"] for sp in line["spans"]]
                text = re.sub(r"\s+", " ", " ".join(
                    "".join(sp["text"] for sp in line["spans"]) for line in b["lines"])).strip()
                # 块的字号：取块内字符最多的那个字号
                sizes: dict[float, int] = {}
                for sp in spans:
                    sizes[round(sp["size"], 1)] = sizes.get(round(sp["size"], 1), 0) + len(sp["text"])
                size = max(sizes, key=sizes.get) if sizes else 0.0
                # 脚注编号和正文粘在一起时（如 “24We use ...”）补一个空格，否则认不出脚注，也认不出 “We use”
                text = re.sub(r"^(\d{1,3})(?=[A-Z][a-z])", r"\1 ", text)
                page_blocks.append((text, size))
            blocks.append(merge_line_blocks(page_blocks))
    return pages, blocks


def merge_line_blocks(page_blocks: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """有些 PDF（工作论文、Journal Pre-proof）每一行都是一个独立的块，段落被切碎。
    把属于同一段的连续行重新拼成段落：上一块没有以句号等结尾、字号相同、且两块都不是标题时，合并。"""
    merged: list[tuple[str, float]] = []
    for text, size in page_blocks:
        if merged:
            prev, prev_size = merged[-1]
            if (abs(prev_size - size) < 0.2 and not re.search(r"[.!?:]$", prev)
                    and not parse_heading(prev)[0] and not parse_heading(text)[0]):
                joined = prev[:-1] + text if prev.endswith("-") else prev + " " + text
                merged[-1] = (joined, size)
                continue
        merged.append((text, size))
    return merged


def body_font_size(blocks: list[list[tuple[str, float]]]) -> float:
    """正文字号 = 全文中字符数最多的字号。"""
    counts: dict[float, int] = {}
    for page_blocks in blocks:
        for text, size in page_blocks:
            counts[size] = counts.get(size, 0) + len(text)
    return max(counts, key=counts.get) if counts else 0.0


def score_passage(passage: str) -> tuple[int, list[str]]:
    """给段落打分：数据类关键词 1 分，获取条件类关键词 2 分（更重要）。"""
    p = normalize(passage)
    # 用 \b 匹配整词，避免 "public" 误命中 "publication"
    hits = [k for k in DATA_KEYWORDS if re.search(rf"\b{re.escape(k)}\b", p)]
    access_hits = [k for k in ACCESS_KEYWORDS if re.search(rf"\b{re.escape(k)}\b", p)]
    score = len(hits) + 2 * len(access_hits)
    if SOURCE_SENTENCE.search(p):
        score += 3
        hits = hits + ["“数据来自……”句式"]
    return score, hits + access_hits


# 编号标题：编号后带点，例如 "2. Data sources"、"3.2. Data"
DOTTED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.\s+[A-Z][^.]{0,90}$")
# 编号后不带点的标题，例如 "2 Data"（有些期刊这样写）。和脚注 "12 We thank ..." 长得很像，
# 所以额外要求：词数少、不以句号结尾、编号后面没有数字（排除公式碎片 "3 PRECj 00"）
UNDOTTED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\s+[A-Z][^\d.]{0,60}$")
# 不带编号、但明显是数据章节的标题，例如 "Data" 或 "Data Availability Statement"
# 必须以大写的 Data / DATA 开头、不以句号结尾、词数少，才算标题。
# 否则正文里刚好以 “data ...” 开头的一行（如 “data correlate tightly with ...”）会被误认为标题
UNNUMBERED_DATA_HEADING = re.compile(r"^(Data|DATA)\b[^.]{0,50}$")
DATA_HEADING_WORDS = re.compile(r"\b(data|dataset|datasets|data sources?|data availability)\b", re.IGNORECASE)
# 论文末尾常见的、不带编号的章节标题。认出它们，数据声明这类无编号章节才知道在哪里结束
OTHER_UNNUMBERED_HEADINGS = re.compile(
    r"^(references|bibliography|acknowledge?ments?|funding|declarations?( of [\w\s]+)?|"
    r"conflicts? of interest|competing interests?|orcid ids?|appendix( [a-z0-9]+)?|"
    r"supplementary (material|data)|supplemental material|notes|author biograph(y|ies)|"
    r"credit authorship contribution statement)\.?$", re.IGNORECASE)
# “纯数据章节”标题里只允许出现这些词，例如 'Data sources'、'Data and sample'、'Data and variables'。
# 'Data and Method'、'Methodology and data' 含有其他主题词，属于混合章节，小节不继承。
PURE_DATA_TITLE_WORDS = {"data", "dataset", "datasets", "source", "sources", "and", "the", "sample",
                         "samples", "variables", "variable", "description", "descriptions",
                         "collection", "construction", "summary", "statistics", "descriptive",
                         "measurement", "measurements", "measures"}
# 附录标题：如 “A.3 Air pollution and meteorology”、“B Data appendix”、“Appendix C. Data sources”
APPENDIX_HEADING = re.compile(r"^(appendix\s+)?[A-H](\.\d+)*\.?\s+[A-Z][^.]{0,80}$", re.IGNORECASE)
# 脚注：以 1–3 位数字加空格开头的块，例如 "13 http://data.cma.cn/..."
FOOTNOTE = re.compile(r"^\d{1,3}\s+\S")


def parse_heading(block: str) -> tuple[bool, str | None]:
    """判断一个文字块是不是章节标题。返回 (是否标题, 编号)，没有编号的标题编号为 None。"""
    if len(block) > 100:
        return False, None
    m = DOTTED_HEADING.match(block)
    if m:
        return True, m.group(1)
    m = UNDOTTED_HEADING.match(block)
    if m and len(block.split()) <= 8:
        return True, m.group(1)
    m = APPENDIX_HEADING.match(block)
    if m and len(block.split()) <= 8 and not re.match(r"^[A-H]\s+[a-z]", block):
        return True, None   # 附录标题，编号不参与“小节继承”
    if UNNUMBERED_DATA_HEADING.match(block) and len(block.split()) <= 6:
        return True, None
    if OTHER_UNNUMBERED_HEADINGS.match(block):
        return True, None
    return False, None


def is_pure_data_title(heading: str) -> bool:
    """去掉编号后，标题里的词是否全部属于“数据类”词汇。"""
    title = re.sub(r"^[\d.\s]+", "", heading).lower()
    words = re.findall(r"[a-z]+", title)
    return "data" in words and all(w in PURE_DATA_TITLE_WORDS for w in words)


def find_repeated_blocks(blocks: list[list[tuple[str, float]]], min_pages: int = 3) -> set[str]:
    """找出在很多页重复出现的块（页眉页脚，如 'X. Yu et al. / Journal ... 197'）。
    比较时去掉数字，因为页码每页不同。"""
    seen: dict[str, set[int]] = {}
    for page_no, page_blocks in enumerate(blocks, start=1):
        for b, _ in page_blocks:
            key = re.sub(r"\d+", "", b).strip().lower()
            seen.setdefault(key, set()).add(page_no)
    return {k for k, pages in seen.items() if len(pages) >= min_pages}


def find_data_passages(blocks: list[list[tuple[str, float]]], min_score: int = 4, max_others: int = 15) -> list[dict]:
    """找出候选段落，来源有两种：
    1. 位于“数据章节”内的段落：不看关键词得分，全部收进来，按原文顺序排列。
       数据章节的小节也算，例如 '2. Data sources' 下的 '2.4. Residential energy consumption'，
       即使小节标题里没有 data 这个词。章节可以跨页，直到遇到不属于它的下一个标题为止。
    2. 其他位置的段落：关键词得分达到 min_score 才收进来，最多 max_others 段。
    脚注单独标出，因为 PDF 里脚注的位置不一定属于它所在的章节。页码从 1 开始。"""
    repeated = find_repeated_blocks(blocks)
    body_size = body_font_size(blocks)
    section_results, other_results = [], []
    data_section_number = None   # 数据章节的编号，例如 "2"；无编号的 Data 章节用 ""
    current_heading = None
    inherit_number = None        # 哪个章节的小节可以继承“数据章节”身份
    in_references = False        # 参考文献部分：文献条目里满是 data、survey 等词，不能当候选
    unnumbered_count = 0         # 无编号数据章节已收集的段落数
    for page_no, page_blocks in enumerate(blocks, start=1):
        for passage, size in page_blocks:
            if re.sub(r"\d+", "", passage).strip().lower() in repeated:
                continue  # 页眉页脚
            heading, number = parse_heading(passage)
            if heading:
                in_references = bool(re.match(r"^(references|bibliography)\.?$", passage.strip(), re.IGNORECASE))
                inside_parent = (inherit_number and number
                                 and number.startswith(inherit_number + "."))
                if inside_parent:
                    current_heading = passage          # 纯数据章节下的小节，即使标题没有 data 也继续收集
                elif DATA_HEADING_WORDS.search(passage):
                    data_section_number = number or ""  # 进入新的数据章节
                    current_heading = passage
                    # 只有标题以 Data 开头的“纯数据章节”（如 '2. Data sources'），小节才继承。
                    # '3. Methodology, data and summary statistics' 是混合章节，3.1 计量模型不应算进来。
                    inherit_number = number if (number and is_pure_data_title(passage)) else None
                    unnumbered_count = 0
                else:
                    data_section_number = None          # 离开数据章节
                    current_heading = None
                    inherit_number = None
                continue
            score, hits = score_passage(passage)
            in_section = data_section_number is not None
            # 太短的块（页码、图注、表格碎片）通常跳过。但数据章节里的短句如果含相关词也要保留：
            # 数据声明经常只有一句话，如 'Further information about the data is available upon a reasonable request.'
            if len(passage) < 30 or (len(passage) < 80 and not (in_section and score >= 1)):
                continue
            # 安全上限：无编号的数据章节（如 Data Availability Statement）最多收 8 段，
            # 防止后面的章节标题没被认出时一路收到文末
            if in_section and data_section_number == "":
                unnumbered_count += 1
                if unnumbered_count > 8:
                    data_section_number = None
                    continue
            # 脚注 = 数字开头 + 字号明显小于正文。
            # 只看“数字开头”不够：上一页正文的接续段落也可能以数字开头（如 '28 other cities in 2012'）
            is_footnote = bool(FOOTNOTE.match(passage)) and size < body_size * 0.9
            item = {"page": page_no, "score": score, "keywords": hits, "text": passage}
            if data_section_number is not None:
                where = "数据章节中的脚注" if is_footnote else "位于数据章节"
                item["reason"] = f"{where}「{current_heading}」"
                section_results.append(item)
            elif score >= min_score and not in_references:
                item["reason"] = "脚注，关键词得分达到阈值" if is_footnote else "关键词得分达到阈值"
                other_results.append(item)
    other_results.sort(key=lambda r: r["score"], reverse=True)
    return section_results + other_results[:max_others]


# 引用压缩（去掉空白和连字符）后至少要有这么多字符。
# 太短的引用（空字符串、“2003–2018”、“data”）几乎在任何一页都能“找到”，核对通过也说明不了什么。
# 已保存的真实 AI 引用压缩后最短也有 25 个字符以上，所以这个下限不影响正常引用。
MIN_QUOTE_CHARS = 20


def verify_quote(pages: list[str], quote: str, page_no: int) -> bool:
    """检查一句引用是否真的出现在指定页。忽略换行、断词和大小写差异。
    只核对“原文里有没有这句话”，不判断这句话说了什么（那是 step2 的规则的事）。
    以下情况一律不通过：引用不是文字或太短；页码不是整数或超出范围。"""
    if not isinstance(quote, str) or len(squash(quote)) < MIN_QUOTE_CHARS:
        return False
    # bool 是 int 的子类（True == 1），要单独排除
    if not isinstance(page_no, int) or isinstance(page_no, bool) or not (1 <= page_no <= len(pages)):
        return False
    return squash(quote) in squash(pages[page_no - 1])


MAX_GAPS, MAX_GAP_CHARS = 3, 900   # 被打断最多 3 处；每处插入的噪声（去空白后）不超过 900 字符（脚注 + 页眉页脚）


def _in_order(words: list[str], text: str) -> int:
    """words 依次出现在 text 中：连续的词组成一段，段与段之间允许插入噪声。
    从每个可能的起点贪心地取最长连续段；段数 ≤ MAX_GAPS + 1，每处插入 ≤ MAX_GAP_CHARS。返回起点，找不到返回 -1。"""
    first = words[0]
    start = text.find(first)
    while start >= 0:
        pos, i, gaps, ok = start, 0, 0, True
        while i < len(words):
            j = i + 1   # 从 pos 开始，最长能连续匹配到第几个词
            while j < len(words) and text.startswith("".join(words[i:j + 1]), pos):
                j += 1
            if not text.startswith("".join(words[i:j]), pos):
                ok = False
                break
            pos += len("".join(words[i:j]))
            i = j
            if i == len(words):
                break
            nxt = text.find(words[i], pos, pos + MAX_GAP_CHARS + len(words[i]))
            gaps += 1
            if nxt < 0 or gaps > MAX_GAPS:
                ok = False
                break
            pos = nxt
        if ok and i == len(words):
            return start
        start = text.find(first, start + 1)
    return -1


def verify_quote_tolerant(pages: list[str], quote: str, page_no: int) -> bool:
    """宽松核对，只用于“本文用了这个数据”类的证据（来源句、使用关系、期间），不用于获取条件。
    PDF 文字层常把一句话打断：公式符号混进句子、脚注插在句子中间、句子跨到下一页。
    要求引用的每个词按顺序出现在这一页（或这一页接下一页），最多被打断 MAX_GAPS 处；先要通过严格核对的长度和页码检查。"""
    if not isinstance(quote, str) or len(squash(quote)) < MIN_QUOTE_CHARS:
        return False
    if not isinstance(page_no, int) or isinstance(page_no, bool) or not (1 <= page_no <= len(pages)):
        return False
    words = [w for w in (squash(x) for x in normalize(quote).split(" ")) if w]
    if len(words) < 4:
        return False
    text = squash(pages[page_no - 1])
    if _in_order(words, text) >= 0:
        return True
    if page_no < len(pages):   # 跨页：匹配必须从这一页开始
        return 0 <= _in_order(words, text + squash(pages[page_no])) < len(text)
    return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python step1_pdf_evidence.py 论文.pdf")
        raise SystemExit(1)

    pages, blocks = extract_pages(sys.argv[1])
    empty = sum(1 for p in pages if not p.strip())
    print(f"共 {len(pages)} 页，其中 {empty} 页没有可提取的文字")
    if empty == len(pages):
        print("这可能是扫描版 PDF，第一版暂不支持。")
        raise SystemExit(1)

    print("\n=== 可能描述数据来源/获取条件的段落 ===")
    passages = find_data_passages(blocks)
    if not passages:
        print("没有找到数据章节，也没有关键词得分足够高的段落。")
    for r in passages:
        print(f"\n[第 {r['page']} 页 | {r['reason']} | 得分 {r['score']} | 命中：{', '.join(r['keywords']) or '无'}]")
        print(r["text"][:800])

    # 演示引用核查：取第一个候选段落的第一句（应该存在），再造一句假话（应该不存在）
    if passages:
        print("\n=== 引用核查演示 ===")
        first = passages[0]
        real_sentence = re.split(r"(?<=\.)\s", first["text"])[0]
        tests = [
            (real_sentence, first["page"]),
            ("All data used in this paper are publicly available on the authors' website.", first["page"]),
        ]
        for quote, page in tests:
            print(f"{'✓ 存在' if verify_quote(pages, quote, page) else '✗ 不存在'}  第{page}页：{quote[:120]}")
