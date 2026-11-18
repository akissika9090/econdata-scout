"""
第二步：让 AI 从候选段落中提取数据信息，再由程序核对 AI 给出的每一条引用。

分工：
    step1（规则）：从 PDF 中筛出候选段落，宁多勿漏
    AI          ：判断每段在说什么，提取数据名称、样本期间、获取条件，并给出原文引用和页码
    程序         ：用 verify_quote 核对引用是否真的出现在那一页；核对不通过的证据不采用

获取条件的四个分类：
    public        公开       原文写明公开可得（publicly available / publicly released 等）
    subscription  订阅       原文写明需要订阅、购买或机构授权
    restricted    受限       原文写明不公开、保密、需申请或仅向作者索取
    unknown       未确认     原文没有说明，或说明不足以判断  ← 没写就是未确认，不能默认为公开

准备（二选一）：
    免费：Google Gemini
        pip install google-genai pymupdf
        export GEMINI_API_KEY="你的key"
    付费：Claude
        pip install anthropic pymupdf
        export ANTHROPIC_API_KEY="你的key"
    两个都设置时优先用 Gemini。可用 export GEMINI_MODEL=... 更换 Gemini 模型。
运行：
    python step2_ai_extract.py papers/deng2020.pdf

注意：这一步会把候选段落（不是整个 PDF 文件）发送给外部 API。
Gemini 免费层的条款规定，提交的内容可能被用于改进 Google 的产品，并可能有人工审核。
学校渠道获取的论文，请自己确认这样使用是否符合使用条件。
"""

import json
import os
import unicodedata
import re
import sys

import gemini_client
import step1_pdf_evidence as step1

MODEL = "claude-sonnet-5-5"
ACCESS_LABELS = {"public": "public", "subscription": "subscription", "restricted": "restricted", "unknown": "not stated in the paper"}


# ============ 1. 准备发给 AI 的文字 ============

def find_reference_page(blocks) -> int | None:
    """找到参考文献开始的那一页，保底方案不发送参考文献部分。"""
    for page_no, page_blocks in enumerate(blocks, start=1):
        for text, _ in page_blocks:
            if re.match(r"^(references|bibliography)\.?$", text.strip(), re.IGNORECASE):
                return page_no
    return None


def build_context(pages, blocks) -> tuple[str, str]:
    """返回 (发给 AI 的文字, 使用的模式)。
    有数据章节：只发候选段落（更省钱、更聚焦）
    没有数据章节：发除参考文献以外的全文（保底，规则失效时也不会漏）"""
    passages = step1.find_data_passages(blocks)
    has_data_section = any("数据章节" in p["reason"] for p in passages)
    if has_data_section:
        parts = [f"[第{p['page']}页]\n{p['text']}" for p in passages]
        return "\n\n".join(parts), "候选段落"
    ref_page = find_reference_page(blocks) or len(pages) + 1
    parts = [f"[第{i}页]\n{pages[i - 1]}" for i in range(1, ref_page)]
    return "\n\n".join(parts), "全文（未找到数据章节）"


# ============ 2. 让 AI 按固定格式回答 ============
# 用“工具调用”强制 AI 按下面的 JSON 结构输出，程序就不用去猜它的回答格式。

USAGE_VALUES = ["analyzed", "cited", "described", "unclear"]
PERIOD_FORMS = ["single", "discrete", "range", "unclear"]
# V2（2026-11-17）：论文侧获取说明的细分字段。渠道与资格是模型对“已核对的条件原文”的语义判断；
# V1 的四个分类（access_category）保留不变，细分字段只作为补充显示，必须和已核对的分类一致才显示
ACCESS_CHANNELS = ["public_download", "registration_download", "subscription", "purchase",
                   "apply_to_provider", "request_from_author", "special_agreement", "not_stated"]
ELIGIBILITY_VALUES = ["researchers", "individuals", "institution_must_apply", "not_stated"]
# 渠道与 V1 分类的对应关系（只做一致性检查，不新增语义规则）
CHANNEL_CATEGORY = {"public_download": "public", "registration_download": "public",
                    "subscription": "subscription", "purchase": "subscription",
                    "apply_to_provider": "restricted", "request_from_author": "restricted",
                    "special_agreement": "restricted", "not_stated": None}

EVIDENCE = {
    "type": "object",
    "description": "原文证据",
    "properties": {
        "quote": {"type": "string", "description": "从原文逐字复制的一句话，不要改写、不要拼接多句"},
        "page": {"type": "integer", "description": "这句话所在的页码，即文字前面 [第N页] 标记的 N"},
    },
    "required": ["quote", "page"],
}

EXTRACT_TOOL = {
    "name": "record_data_sources",
    "description": "记录论文中使用的数据来源及其获取条件",
    "input_schema": {
        "type": "object",
        "properties": {
            "data_sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "数据名称，如 Urban Household Survey"},
                        "role": {"type": "string", "enum": ["main", "robustness", "supplementary"],
                                 "description": "main：主要分析；robustness：稳健性检验；supplementary：情景预测等补充分析"},
                        "kind": {"type": "string", "enum": ["dataset", "policy_info"],
                                 "description": "dataset：统计、调查、行政等数据；policy_info：政策名单、实施时间等用于构造处理组的信息"},
                        "provider": {"type": ["string", "null"], "description": "提供机构，原文没写则为 null"},
                        "sample_period": {"type": ["string", "null"], "description": "论文实际使用的数据年份范围，如 2002–2009；原文没写则为 null"},
                        "period_evidence": {
                            "anyOf": [EVIDENCE, {"type": "null"}],
                            "description": "写明样本期间的原文；sample_period 为 null 时为 null",
                        },
                        "unit": {"type": ["string", "null"], "description": "观察单位或地区层级，如 household、county、city"},
                        "access_category": {"type": "string", "enum": list(ACCESS_LABELS)},
                        "source_evidence": EVIDENCE,
                        "access_evidence": {
                            "anyOf": [EVIDENCE, {"type": "null"}],
                            "description": "支持获取条件分类的原文；分类为 unknown 时为 null",
                        },
                        "access_applies_to": {"type": ["string", "null"],
                                              "description": "获取条件适用的对象：整个数据源写 whole；只适用于某个部分或版本时，从条件原文中逐字复制那个部分的名称；分类为 unknown 时为 null"},
                        "usage": {"type": "string", "enum": USAGE_VALUES,
                                  "description": "这一条记录中，本文与这个数据的关系：analyzed 本文自己分析使用；cited 引用他人研究的数据或结果；described 只介绍、背景或比较；unclear 无法判断"},
                        "usage_evidence": {"anyOf": [EVIDENCE, {"type": "null"}],
                                           "description": "表明这条使用关系的原文（一句话）"},
                        "period_form": {"anyOf": [{"type": "string", "enum": PERIOD_FORMS}, {"type": "null"}],
                                        "description": "样本期间的形态：single 单年；discrete 几个不连续的年份；range 连续区间；unclear 无法判断；没有样本期间时为 null"},
                        "period_years": {"anyOf": [{"type": "array", "items": {"type": "integer"}}, {"type": "null"}],
                                         "description": "single：一个年份；discrete：列出的各个年份；range：[起始年, 结束年]；没有样本期间时为 null"},
                        "version": {"type": ["string", "null"],
                                    "description": "本文实际使用的版本、文件或匹配方式，从 version_evidence 原文逐字复制（如 public use files、restricted data files、1% sample）；原文没写为 null"},
                        "version_evidence": {"anyOf": [EVIDENCE, {"type": "null"}],
                                             "description": "写明版本、文件或匹配方式的原文；version 为 null 时为 null"},
                        "access_channel": {"type": "string", "enum": ACCESS_CHANNELS,
                                           "description": "按 access_evidence 原文判断的获取渠道；原文没写渠道为 not_stated"},
                        "eligibility": {"type": "string", "enum": ELIGIBILITY_VALUES,
                                        "description": "原文写明谁可以申请或获取；没写为 not_stated"},
                        "use_restrictions": {"type": "array", "items": {"type": "string"},
                                             "description": "使用限制（如只能在指定场所使用、需要签署协议），每条从 access_evidence 原文逐字复制；没有则为空数组"},
                    },
                    "required": ["name", "role", "kind", "sample_period", "period_evidence",
                                 "access_category", "source_evidence", "access_evidence",
                                 "access_applies_to", "usage", "usage_evidence", "period_form", "period_years",
                                 "version", "version_evidence", "access_channel", "eligibility", "use_restrictions"],
                },
            },
            "sample_limitations": {
                "type": "array",
                "description": "因为数据拿不到或覆盖不全，作者缩小样本、缺少年份或缺少变量的说法",
                "items": EVIDENCE,
            },
            "availability_statement": {
                "anyOf": [EVIDENCE, {"type": "null"}],
                "description": "针对整篇论文的数据可用性声明（如 Data Availability Statement），没有则为 null",
            },
        },
        "required": ["data_sources", "sample_limitations", "availability_statement"],
    },
}

SYSTEM_PROMPT = """你是经济学研究的数据审查助手。你的任务是从论文片段中找出作者使用了哪些数据，以及作者如何描述这些数据的获取条件。

规则：
1. 只依据给出的文字判断，不要使用你对这些数据库的背景知识。即使你知道某个数据库通常是公开的，只要原文没写，就必须分类为 unknown。
2. 获取条件分类：
   - public：原文明确写了公开可得
   - subscription：原文明确写了需要订阅、购买或机构授权
   - restricted：原文明确写了不公开、保密、需申请，或只能向作者索取
   - unknown：原文没有说明，或说明不足以判断
3. 只有网址、下载链接或数据介绍，不等于公开；必须有“publicly available”这类明确说法才能判为 public。
   区分“数据本身”和“附加结果”：例如 “summary statistics are available upon request” 说的是统计表，不是数据的获取条件。
4. 引用必须从原文逐字复制一句话，页码以文字前面的 [第N页] 为准。程序会逐条核对，编造或改写的引用会被拒绝。
5. 记录作者自己用到的所有数据，包括稳健性检验、情景预测等补充分析用到的数据（role 分别记为 robustness、supplementary）；
   即使相关结果“可应要求提供”而没有放在正文，只要作者说用了这份数据，也要记录。
   文献综述里提到的、其他研究所用的数据或结果，可以记录，但 usage 必须记为 cited。
6. 政策信息也算数据源：例如试点城市名单、政策实施时间、处理组定义的来源（如“从国家发改委收集”），kind 记为 policy_info。
7. 样本期间指论文实际使用的数据年份，必须附上写明年份的原文（period_evidence）。
   注意统计年鉴的出版年份不等于数据年份：例如“2004–2019 年《中国城市统计年鉴》”通常记录的是 2003–2018 年的数据。
   如果原文另有一句写明样本期间（如 “over the period 2003–2018”），以那一句为准并引用它。
8. “样本受限的说法”只记录因为数据拿不到或覆盖不全而造成的限制（如缺少某些年份、地区、变量）；
   删除缺失值、剔除异常值等常规数据清洗步骤不要记录。
9. 如果论文有针对整篇论文的数据可用性声明（如 “Data Availability Statement” 一节），记录在 availability_statement。
10. usage 针对每一条记录判断本文与这个数据的关系，并在 usage_evidence 中引用依据：
    analyzed 本文自己分析使用；cited 引用他人研究的数据或结果（如 “Smith (2010) finds …”）；described 只介绍、背景或比较；unclear 无法判断。
    同一个数据如果既被引用、又被本文使用，分成两条记录分别记录。
11. access_applies_to：获取条件适用于整个数据源写 whole；只适用于某个部分或版本（如 public-use files、county identifiers）时，
    从 access_evidence 原文中逐字复制那个部分的名称。
12. period_form 和 period_years：原文写的是一个年份记 single；几个不连续的年份（如 “1977 and 1997”）记 discrete 并列出各年；
    连续区间（如 “2003–2018”“from 2003 to 2018”）记 range，period_years 为 [起始年, 结束年]；无法判断记 unclear。不要把不连续的年份写成区间。
13. version：作者实际用的是哪个版本、文件或匹配方式（如 public use files、restricted data files、1% sample、与税务记录匹配的数据），
    从原文逐字复制，并在 version_evidence 中引用那一句；原文没写就为 null，不要用背景知识补。
14. access_channel、eligibility、use_restrictions 只依据 access_evidence 那一句判断：
    public_download 公开下载；registration_download 注册后免费下载；subscription 订阅；purchase 付费购买；
    apply_to_provider 向数据提供方申请；request_from_author 向作者索取（只有作者承诺提供本文使用的这份数据时才算）；
    special_agreement 与数据提供方的特别协议（如与企业管理层的协议）；not_stated 原文没写渠道（例如只写了“不公开”）。
    eligibility：researchers 研究者可申请；individuals 个人可申请；institution_must_apply 须由机构提交；not_stated 没写。
    use_restrictions 每条从 access_evidence 原文逐字复制（如 only at a Research Data Center）；没有则为空数组。"""


def ask_ai(context: str) -> tuple[dict, str]:
    """根据设置了哪个 API key 选择模型，返回 (结构化结果, 使用的模型)。
    两个都设置了时优先用 Gemini（免费）。"""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_PROVIDER", "").lower() == "deepseek":   # 2026-11-18：只设 DeepSeek 时也走这条
        result, model = ask_gemini(context)
        return result, (f"DeepSeek ({model})" if model.startswith("deepseek") else f"Gemini ({model})")
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ask_claude(context), f"Claude ({MODEL})"
    raise SystemExit("没有找到 API key。请设置 GEMINI_API_KEY 或 ANTHROPIC_API_KEY。")


def ask_gemini(context: str) -> tuple[dict, str]:
    """调用 Google Gemini API，返回 (结构化结果, 实际使用的模型)。
    用 JSON Schema 约束输出格式，和 Claude 用的是同一份格式定义。
    重试、换备用模型的做法在 gemini_client 里，和检索步骤共用。"""
    return gemini_client.generate_json(SYSTEM_PROMPT, f"以下是论文片段：\n\n{context}", EXTRACT_TOOL["input_schema"])


def ask_claude(context: str) -> dict:
    """调用 Claude API，返回 AI 填好的结构化结果。"""
    import anthropic  # 放在这里导入，这样没装 anthropic 也能运行下面的核查测试
    client = anthropic.Anthropic()  # 自动读取环境变量 ANTHROPIC_API_KEY
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "record_data_sources"},  # 强制使用这个工具，也就是强制按格式回答
        messages=[{"role": "user", "content": f"以下是论文片段：\n\n{context}"}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("AI 没有按要求返回结构化结果")


# ============ 3. 程序核对 AI 的回答 ============

def check_evidence(pages, evidence, tolerant: bool = False) -> dict | None:
    """核对一条证据，在原有内容上加上 verified 字段（只表示“这句话逐字出现在原文这一页”）。
    给定页找不到、但逐字出现在另一页时（常见原因：模型写了期刊印刷页码，而不是 [第N页] 标记），
    把页码改成实际所在的页，并在 page_given 里保留模型原来写的页码。这是机械核对，不改变引用的内容。"""
    if not evidence:
        return None
    quote, page = evidence.get("quote", ""), evidence.get("page", 0)
    if step1.verify_quote(pages, quote, page):
        return {**evidence, "verified": True}
    found = [i for i in range(1, len(pages) + 1) if step1.verify_quote(pages, quote, i)]
    if found:
        return {**evidence, "page": found[0], "page_given": page, "verified": True}
    if tolerant:   # 只用于“本文用了这个数据”的证据：PDF 噪声打断了句子（公式符号、脚注、跨页），词序完整才通过
        pages_to_try = [page] if isinstance(page, int) and not isinstance(page, bool) else []
        pages_to_try += [i for i in range(1, len(pages) + 1) if i != page]
        hit = next((i for i in pages_to_try if step1.verify_quote_tolerant(pages, quote, i)), None)
        if hit is not None:
            extra = {"page": hit, "page_given": page} if hit != page else {}
            return {**evidence, **extra, "verified": True, "pdf_interrupted": True}
    return {**evidence, "verified": False}


def tidy_years(text: str | None) -> str | None:
    """显示用：把 PDF 里的 '2004e2012' 还原为 '2004–2012'。"""
    return re.sub(r"(\d{4})e(\d{4})", r"\1–\2", text) if text else text


def period_supported(period: str, evidence: dict | None) -> bool:
    """样本期间里的每个四位数年份，都必须出现在核对通过的证据原文中。"""
    if not evidence or not evidence.get("verified"):
        return False
    years = re.findall(r"\d{4}", tidy_years(period))
    quote = tidy_years(evidence["quote"])
    return bool(years) and all(y in quote for y in years)



# ---------- 期间形态（第二阶段）：模型判断形态和年份，程序只做结构检查和转换一致性 ----------
RANGE_SEP = r"\s*(?:–|-|—|~|to|through|until)\s*"


def flat_years_text(text: str | None) -> str:
    """检查年份写法用：还原 '2004e2012'、压缩空白、小写。不合并连字符断词（会把 '1985-\n1997' 粘成一个数）。"""
    return re.sub(r"\s+", " ", tidy_years(text or "")).lower()


def range_written(start: int, end: int, text: str | None) -> bool:
    """原文是否有把起止年连起来的区间写法：A–B、A-B、A to B、from A to / through B、between A and B。“A and B” 不算区间。"""
    t = flat_years_text(text)
    # 结束年前面允许一个月份之类的词（“from January 2006 through December 2014”）
    return bool(re.search(rf"\b{start}{RANGE_SEP}(?:[a-z]+\.?\s+)?{end}\b", t)
                or re.search(rf"\bbetween (?:[a-z]+\.?\s+)?{start} and (?:[a-z]+\.?\s+)?{end}\b", t))


def parse_period(src: dict) -> tuple[str | None, list[int] | None, bool]:
    """返回 (形态, 年份, 是否从字符串推断)。新提示词的结果用模型给的 period_form / period_years；
    旧结果（或新结果里形态为空）按 sample_period 的写法推断：一个年份 → 单年；“A–B” → 区间；其他 → 离散。"""
    if src.get("period_form"):
        return src["period_form"], src.get("period_years"), False
    period = tidy_years(src.get("sample_period"))
    years = [int(y) for y in re.findall(r"\b(?:1[89]|20)\d{2}\b", period or "")]
    if not years:
        return None, None, True
    if len(years) == 1:
        return "single", years, True
    if len(years) == 2 and years[0] < years[1] and range_written(years[0], years[1], period):
        # 与期间形态检查用同一个区间写法判断（允许结束年前有月份词，如 “July 2001–June 2015”）
        return "range", years, True
    return "discrete", years, True


def check_period_form(src: dict) -> None:
    """期间形态的结构检查（在 check_evidence 之后调用）。不符合 → period_form_unverified：年份照常显示，不计入“最晚用到”。
    程序不替模型改判形态。区间写法只支持“形态与原文一致”，期间属于哪个数据仍是模型的判断。"""
    form, years, inferred = parse_period(src)
    src["period_form"], src["period_years"], src["period_form_inferred"] = form, years, inferred
    if not src.get("sample_period") and not years:
        return
    problem = None
    ev = src.get("period_evidence") or {}
    quote = flat_years_text(ev.get("quote")) if ev.get("verified") else ""
    if form in (None, "unclear"):
        problem = "the model did not determine the period form"
    elif not years or not all(isinstance(y, int) and not isinstance(y, bool) for y in years):
        problem = "no usable years"
    elif form == "single" and len(years) != 1:
        problem = "a single year must have exactly one year"
    elif form == "discrete" and len(set(years)) < 2:
        problem = "discrete years need at least two years"
    elif form == "range" and not (len(years) == 2 and years[0] < years[1]):
        problem = "a range needs two ordered endpoints"
    elif not quote:
        problem = "no verified period quote"
    elif not all(re.search(rf"\b{y}\b", quote) for y in years):
        problem = "some years do not appear in the period quote"
    elif form == "range" and not range_written(years[0], years[1], quote):
        problem = "the period quote does not connect the start and end years as a range"
    else:
        shown = {int(y) for y in re.findall(r"\b(?:1[89]|20)\d{2}\b", tidy_years(src.get("sample_period")) or "")}
        if shown and shown != set(years):
            problem = "the displayed period and the year field disagree"
    if form == "discrete" and years and not problem:
        src["period_years"] = sorted(set(years))
    if problem:
        src["period_form_unverified"] = True
        src["period_unverified"] = True
        src["period_form_note"] = f"period form unverified: {problem}"
        src["rule_notes"].append(src["period_form_note"])


def period_year_set(src: dict) -> set[int] | None:
    """“最晚用到”用的年份集合：区间展开为其中每一年，离散年份只算列出的年份。期间未核实的不参与（返回 None）。"""
    if src.get("period_unverified") or src.get("period_form") not in ("single", "discrete", "range"):
        return None
    years = src.get("period_years") or []
    if src["period_form"] == "range":
        return set(range(years[0], years[1] + 1))
    return set(years)


# 每种获取条件分类，证据原文里至少要出现一个对应的说法，程序才接受这个分类。
# 引用“存在”还不够，还要能“支持”分类。例：脚注里只有一个下载网址，引用是真的，但不能说明数据公开。
# ---------- 引用能否支持获取条件分类：词组 + 组合规则 ----------
# 不再逐句列短语（publicly available、not publicly available、no ... publicly available ……），
# 而是把说法拆成几组“零件”，用三条组合规则判断。遇到没见过的说法，通常只需要往某组里加一个词，规则不变。
WORDS = {
    "open":      r"publicly|freely|openly",                                   # 公开（副词）
    "avail":     r"availab\w*|accessib\w*|access\w*|released|downloadable|provided|shared|distributed|obtain\w*",
    "public_np": r"public[- ](use|access|domain|release)\w*|open[- ](access|data|source)|available to the public"
                 r"|free of charge|free(ly)? download\w*|\bpumf\b",              # 本身就表示公开的名词短语
    "negator":   r"no|not|none|neither|nor|never|cannot|can't|unable|without",
    "restrict":  r"unavailable|inaccessible|confidential\w*|restricted|proprietary|permission|non-disclosure|approv\w*|agreement"
                 r"|upon (a )?(reasonable )?request|secure (facility|data|room|cent\w+)",
    "subscribe": r"subscri\w*|purchas\w*|licen[cs]\w*|commercial|paid|fees?",
}
W = {k: rf"\b(?:{v})\b" for k, v in WORDS.items()}
GAP = r"[^.;]{0,80}?"   # 同一句（同一分句）内的间隔


# 双重否定：“没有限制”“不收费”本身是公开的说法，先识别出来再从句子里拿掉，免得 no / restrictions 被当成否定和限制
UNRESTRICTED = re.compile(
    r"\b(?:no|without(?: any)?|not subject to(?: any)?|free (?:of|from)(?: any)?)\s+(?:access |use |usage |legal |ethical )?"
    r"(?:restrictions?|limitations?|fees?|charges?|costs?|permissions? (?:is |are )?(?:needed|required))\b"
    r"|\bunrestricted\b")
# 一句话里有多个分句（A, but B / A; B / A whereas B），每个分句可能在说不同的对象或不同的时间
CLAUSE_SPLIT = re.compile(r",?\s*\b(?:but|whereas|while|although|though|however|yet)\b,?|;")
# 不是数据本身的对象：说明文档公开不等于数据公开
NON_DATA_OBJECT = re.compile(r"\b(?:documentation|codebooks?|questionnaires?|user guides?|manuals?|metadata|"
                             r"(?:replication |source |analysis )?code|programs?|scripts?|summary statistics)\b")


def clause_signals(clause: str) -> set[str]:
    """一个分句能支持哪些获取条件分类。三条组合规则：
    公开 = 公开副词紧挨可获得词（publicly available）或公开名词短语（public-use files）或“没有限制”，且同一分句没有否定和限制
    受限 = 否定词出现在公开/可获得词之前（not available、no ... publicly available、cannot be accessed），或出现限制词
    订阅 = 出现订阅/购买/许可类词"""
    unrestricted = bool(UNRESTRICTED.search(clause))
    q = UNRESTRICTED.sub(" ", clause)
    negated = bool(re.search(rf"{W['negator']}{GAP}(?:{W['open']}|{W['avail']}|\bpublic\b)", q))
    restricted_word = bool(re.search(W["restrict"], q))
    public_claim = unrestricted or bool(re.search(rf"{W['open']}(?:\s+\w+)?\s+{W['avail']}", q) or re.search(W["public_np"], q))
    signals = set()
    if public_claim and not negated and not restricted_word:
        signals.add("public")
    if negated or restricted_word:
        signals.add("restricted")
    if re.search(W["subscribe"], q) and not unrestricted:
        signals.add("subscription")
    return signals


def analyze_access(quote: str, src: dict | None = None) -> dict:
    """分析一句获取条件的证据，返回 {signals, conflict, attributed}。
    1. 切成分句，逐句判断；
    2. 数据对象归属：有分句点名了这个数据、而别的分句没点名，就只看点名的分句；
       有分句说的是文档、代码等非数据对象，就去掉这些分句；
    3. 剩下的分句里同时出现“公开”和“受限”，记为冲突：规则不替任何一方做决定，交给人看原文。"""
    q = step1.normalize(quote)
    clauses = [c.strip() for c in CLAUSE_SPLIT.split(q) if c and c.strip()]
    per = [(c, clause_signals(c)) for c in clauses]
    per = [(c, sig) for c, sig in per if sig] or per
    attributed = "none"
    if len(per) > 1 and src is not None:
        named = [x for x in per if names_source(x[0], src)]
        if named and len(named) < len(per):
            per, attributed = named, "named"
    if len(per) > 1:
        data_clauses = [x for x in per if not NON_DATA_OBJECT.search(x[0])]
        if data_clauses and len(data_clauses) < len(per):
            per, attributed = data_clauses, "non_data_removed"
    signals = set().union(*(sig for _, sig in per)) if per else set()
    return {"signals": signals, "conflict": "public" in signals and "restricted" in signals, "attributed": attributed}


def access_signals(quote: str, src: dict | None = None) -> set[str]:
    return analyze_access(quote, src)["signals"]


def supports_category(category: str, quote: str, src: dict | None = None) -> bool:
    """证据原文是否含有支持该分类的说法（有冲突时不算支持）。"""
    a = analyze_access(quote, src)
    return category in a["signals"] and not a["conflict"]


def find_urls(src: dict) -> list[str]:
    """从核对通过的证据原文中找出网址。原文只给了网址、没写“公开”时分类仍是未确认，
    但网址本身对用户有用：知道该去哪里确认。"""
    urls = []
    for key in ("source_evidence", "access_evidence"):
        ev = src.get(key) or {}
        if ev.get("verified"):
            urls += re.findall(r"(?:https?://|www\.)[^\s,;)]+[^\s,;).]", ev.get("quote", ""))
    return list(dict.fromkeys(urls))


def load_known_databases(path: str = "known_databases.json") -> dict:
    """读取数据库知识清单；文件不存在时返回空清单（不影响其他功能）。"""
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(base, path), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"types": {}, "databases": []}


KNOWN_DATABASES = load_known_databases()


def match_database(db: dict, text: str) -> dict | None:
    """清单中的一个数据库是否出现在这段文字里；出现则返回提示 {type, name, icon, message}。"""
    flags = 0 if db.get("case_sensitive") else re.IGNORECASE
    if not re.search(db["pattern"], text, flags):
        return None
    info = KNOWN_DATABASES["types"].get(db["type"], {})
    return {"type": db["type"], "name": db["name"], "icon": info.get("icon", ""), "message": info.get("message", "")}


def database_hint(src: dict) -> dict | None:
    """数据名称、提供机构或来源原文中出现清单里的数据库时，返回 {type, name, icon, message}（清单中第一个匹配的）。
    这是“数据库常识提示”，不是论文证据，不改变获取条件分类。"""
    ev = src.get("source_evidence") or {}
    text = " ".join(str(x) for x in [src.get("name"), src.get("provider"), ev.get("quote")] if x)
    for db in KNOWN_DATABASES["databases"]:
        hint = match_database(db, text)
        if hint:
            return hint
    if src.get("kind") == "policy_info":   # 清单里没有、但 AI 标为政策信息的
        info = KNOWN_DATABASES["types"].get("policy_doc", {})
        return {"type": "policy_doc", "name": "policy information", "icon": info.get("icon", ""), "message": info.get("message", "")}
    return None


SPECIFIC_HINT_TYPES = {"paid", "gov_micro", "academic_survey", "open_science", "public_disclosure"}


def all_specific_hints(text: str) -> list[dict]:
    """找出一段文字中提到的所有“名称具体”的数据库（付费数据库、学术调查等），用于拆分联合来源。"""
    found = []
    for db in KNOWN_DATABASES["databases"]:
        if db["type"] in SPECIFIC_HINT_TYPES:
            hint = match_database(db, text)
            if hint:
                found.append(hint)
    return found


EVIDENCE_RANK = {"direct": 3, "general": 2, "unclear": 1, "none": 0}


def scope_key(scope: str | None) -> str:
    """比较用的适用范围：whole / undetermined / not_recorded（旧结果没有记录）原样；具体部分名称只比较字母和数字。"""
    if scope in (None, "undetermined"):
        return "undetermined"
    if scope in ("whole", "not_recorded"):
        return scope
    return letters(scope)


def stated_condition(src: dict) -> tuple[str, str] | None:
    """这条记录带有的获取条件信息 (分类, 适用范围)：已验证的分类；或需要人工复核时模型的判断。
    都没有则为 None。范围参与比较：分类相同、范围不同（如 public use 版本和整个数据源）不是同一个条件。"""
    if src.get("access_category", "unknown") != "unknown":
        return src["access_category"], scope_key(src.get("access_scope"))
    if src.get("needs_review") and src.get("ai_category", "unknown") != "unknown":
        return src["ai_category"], scope_key(src.get("access_applies_to") if "access_applies_to" in src else "not_recorded")
    return None   # 条件词面线索（candidate）不是条件信息，不参与合并时的条件比较


def conditions_compatible(a: dict, b: dict) -> bool:
    """两条记录能否合并成一条：条件（分类和适用范围）相同，或其中一条没有任何条件信息。
    两条都有条件、而且不同 → 不能合并（不静默去掉冲突，也不把某一部分的条件并到整个数据源上）。"""
    ca, cb = stated_condition(a), stated_condition(b)
    return ca is None or cb is None or ca == cb


def evidence_rank(src: dict) -> tuple:
    """同一个数据有多条记录时，比较哪条证据更强：
    先看有没有确认的获取条件，再看证据归属（直接 > 总体声明 > 无法确认），最后看有没有样本期间。
    step2（同一论文内去重）和 step3（同一组内每篇论文只留一条）用同一个标准。"""
    return (src["access_category"] != "unknown", EVIDENCE_RANK.get(src.get("evidence_scope", "none"), 0),
            bool(src.get("sample_period")))


def split_joint_sources(sources: list[dict]) -> list[dict]:
    """拆分联合来源（在核对之前）：名称里同时提到两个以上具体数据库（如 “CSMAR and WIND databases”）→ 拆成多条。
    每一部分之后用自己的名称单独核对，不继承原联合记录的核对结论
    （以前先核对再拆分，Wind 会继承只点名了 CSMAR 的“订阅”证据）。"""
    expanded = []
    for src in sources:
        hits = all_specific_hints(src.get("name") or "")
        if len(hits) >= 2:
            expanded += [{**src, "name": h["name"], "_split_from": src.get("name"), "_split_hint": h} for h in hits]
        else:
            expanded.append(src)
    return expanded


PERIOD_FIELDS = ("sample_period", "period_evidence", "period_unverified", "period_note",
                 "period_form", "period_years", "period_form_inferred", "period_form_unverified", "period_form_note")


def dedupe_sources(sources: list[dict]) -> list[dict]:
    """同一篇论文中重复的同一个数据库（已核对过的记录）：条件不冲突的合并为一条，保留证据更强的那条；
    条件不同（如公开版本和受限的识别码）分别保留。
    合并时如果保留的那条没有样本期间，就把另一条的期间连同证据、核实状态、说明一起搬过来——
    只搬期间而丢掉“未核实”标记，会把未核实的年份变成覆盖依据。"""
    kept, index = [], {}
    for src in sources:
        hint = src.get("db_hint") or {}
        key = hint.get("name") if hint.get("type") in SPECIFIC_HINT_TYPES else None
        pos = next((i for i in index.get(key, []) if conditions_compatible(kept[i], src)), None) if key else None
        if pos is None:
            if key:
                if index.get(key):
                    src = {**src, "rule_notes": src["rule_notes"] + [f"与同一论文中“{kept[index[key][0]]['name']}”的获取条件不同，分别保留"]}
                index.setdefault(key, []).append(len(kept))
            kept.append(src)
            continue
        old = kept[pos]
        better, worse = (src, old) if evidence_rank(src) > evidence_rank(old) else (old, src)
        better = dict(better)
        if not better.get("sample_period") and worse.get("sample_period"):
            for f in PERIOD_FIELDS:
                better[f] = worse.get(f)
        better["rule_notes"] = better["rule_notes"] + [f"与同一论文中重复的“{worse['name']}”合并为一条"]
        kept[pos] = better
    return kept


# 来源说明里通常会出现的词：说明“数据从哪里来”。来源证据里一个都没有的，很可能只是变量或研究对象，而不是数据来源。
# 例：li2020 “This paper evaluated the effect of PM10 and AQI on health-care expenditure” —— PM10、AQI 是变量
PROVENANCE = re.compile(
    r"\b(from|obtained|obtain|provided|provides|provide|collected|collect|derived|drawn|sources?|sourced|released|published|"
    r"publishes|downloaded|download|purchased|issued|compiled|recorded|records|reported|database|dataset|datasets|data ?set|"
    r"survey|surveys|yearbooks?|census|archive|repository|files?|website|monitoring|monitored|measured|retrieved|acquired?|"
    r"available|developed|produced|readings|agreement)\b",
    re.IGNORECASE)
# 没有具体名称的笼统说法：“many other statistical yearbooks”“various sources”
VAGUE_NAME = re.compile(r"^\s*(many|other|various|several|some|additional|further|numerous)\b", re.IGNORECASE)


TABLE_CELL_WORDS = 15   # 表格单元格一样短的来源引用
SOURCE_TABLE_WINDOW = 2500   # 引用前多少字符内要有提到来源的表格（标题或表头），可以从上一页接过来
TABLE_WORD = re.compile(r"\btable\b", re.IGNORECASE)
SOURCE_WORD = re.compile(r"\bsources?\b", re.IGNORECASE)


def in_source_table(pages: list[str] | None, evidence: dict) -> bool:
    """v2.5b：来源引用像表格单元格（≤ TABLE_CELL_WORDS 个词），且所在位置之前（同页或接上一页）不远处有
    提到来源的表格（同时出现 “table” 和 “source(s)”）→ 这是数据来源表里列出的数据，不是变量。
    例：Abdelkader 2017 表 1 “Variable | Source”中的 “The World Bank: World Development Indicator (WDI).”"""
    if not pages or not evidence or not evidence.get("verified"):
        return False
    quote, page = evidence.get("quote") or "", evidence.get("page")
    if len(quote.split()) > TABLE_CELL_WORDS or not isinstance(page, int) or not (1 <= page <= len(pages)):
        return False
    here = step1.normalize(pages[page - 1])
    before = (step1.normalize(pages[page - 2]) + " " if page >= 2 else "")
    pos = here.find(step1.normalize(quote)[:40])
    if pos < 0:
        return False
    window = (before + here[:pos])[-SOURCE_TABLE_WINDOW:]
    return bool(TABLE_WORD.search(window) and SOURCE_WORD.search(window))


def classify_mention(src: dict, pages: list[str] | None = None) -> str | None:
    """不像独立数据来源的条目返回原因（不删除，移到“其他提及”）：
       source_unverified  来源引用缺失或在原文中找不到
       unspecified        笼统说法，没有具体名称
       possible_variable  来源证据里没有任何“数据从哪里来”的说法，可能只是变量
    在数据库清单里的（如 CFPS、Wind）或 AI 标为政策信息的，不做这个判断。"""
    se = src.get("source_evidence") or {}
    if not se.get("verified"):
        return "source_unverified"   # 来源引用缺失或在原文中找不到：不能确认本文使用了这个数据
    if VAGUE_NAME.search(src.get("name", "")):
        return "unspecified"
    if src.get("db_hint") and src["db_hint"].get("type") != "policy_doc":
        return None
    if src.get("kind") == "policy_info":
        return None
    quote = (src.get("source_evidence") or {}).get("quote", "")
    if quote and not PROVENANCE.search(step1.normalize(quote)) and not in_source_table(pages, se):
        return "possible_variable"
    return None


MENTION_LABELS = {"unspecified": "a general phrase without a specific name",
                  "possible_variable": "the paper does not say where the data come from; possibly just a variable",
                  "source_unverified": "the source quote cannot be found in the paper, so use in this paper cannot be confirmed"}


def paid_database_hint(src: dict) -> str | None:
    """兼容旧接口：只返回付费数据库的名字。"""
    hint = database_hint(src)
    return hint["name"] if hint and hint["type"] == "paid" else None


YEARBOOK_EDITION = re.compile(r"(Yearbooks?|Year Books?|年鉴)[^.]{0,40}?\(?\s*(\d{4})\s*(?:–|-|—|~|to)\s*(\d{4})", re.IGNORECASE)


def check_yearbook_period(pages, src: dict) -> None:
    """统计年鉴的出版年份通常比数据年份晚一年（2004–2019 年版记录 2003–2018 年的数据）。
    如果模型给的样本期间正好是期间证据里年鉴版次的年份，只加提示，并把期间标为未核实（不计入“最晚用到”）。
    不自动替换：原文中“早一年”的年份范围可能属于别的数据（之前的自动替换会借用天气数据的期间），程序无法可靠判断归属。"""
    ev = src.get("period_evidence") or {}
    period = src.get("sample_period")
    m = YEARBOOK_EDITION.search(tidy_years(ev.get("quote", "")))
    if not (period and m):
        return
    y1, y2 = int(m.group(2)), int(m.group(3))
    if year_span(period) != (y1, y2):
        return
    src["period_unverified"] = True
    src["period_note"] = f"{y1}–{y2} 可能是年鉴的出版年份，实际数据年份可能是 {y1 - 1}–{y2 - 1}，请核对原文"


def year_span(period: str | None) -> tuple[int, int] | None:
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", tidy_years(period) or "")]
    return (min(years), max(years)) if years else None


# ---------- 证据是否针对这个数据：直接证据 / 总体声明 / 无法确认 ----------
# 引用真实存在、也含有“公开”等说法，还不够：还要看这句话是不是在说这个数据。
# 例：Zhou 2022 “Publicly available datasets were analyzed in this study.” 是整篇论文的总体声明，
#     没有点名 CFPS，不能直接证明 CFPS 公开。

GENERIC_STATEMENT = re.compile(
    r"datasets? (were|was) (analy[sz]ed|used)|all (the )?data|data (used|analy[sz]ed) in this (study|paper|article)"
    r"|data that support|data supporting|data availability|further information about the data"
    r"|replication (files|package)|(publicly|freely) available datasets?", re.IGNORECASE)
# 句首的指代：“This dataset ...”“The data ...”“These data ...”“It ...”，需要看前文指的是什么
ANAPHOR = re.compile(r"^\W*(since |because |however, |therefore, |as )?(this|the|these|such|that|its|it|data)\b", re.IGNORECASE)
NAME_STOPWORDS = {"data", "dataset", "datasets", "database", "databases", "survey", "surveys", "china", "chinese",
                  "national", "statistics", "statistical", "information", "center", "centre", "bureau", "the", "and",
                  "from", "level", "daily", "annual", "yearly", "monthly", "household", "households", "city", "cities"}


def letters(text: str | None) -> str:
    """只保留字母和数字（先合并换行断词、统一大小写），用于逐字比较名称。"""
    return re.sub(r"[^a-z0-9]", "", step1.squash(text or ""))


def source_names(src: dict) -> dict:
    """可以识别这个数据源的名称信息：缩写（名称中和匹配到的清单名称中的大写缩写）、完整名称、数据库清单中的名称模式。
    不含提供机构字段；不用“名称中的若干个词同时出现”来推断点名（2026-11-06 评审决定，未经约定的启发式已移除）。
    已知局限：名称本身含有机构缩写时（如 “IRS Statistics of Income”），这个缩写也会被当作点名依据；程序不猜测它是不是机构。"""
    name = src.get("name") or ""
    core = re.sub(r"\s*\(.*?\)\s*|（.*?）", " ", name).strip()
    # 数据库清单条目只按“数据名称”匹配（db_hint 可能来自机构名或来源原文，不能拿来证明点名）
    db = next((d for d in KNOWN_DATABASES["databases"] if match_database(d, name)), None)
    acronyms = {a for a in re.findall(r"\b[A-Z][A-Z0-9]{1,6}\b", f"{name} {db['name'] if db else ''}") if a not in {"AND", "OF", "THE"}}
    full = {letters(core)} if len(letters(core)) >= 8 else set()
    return {"acronyms": acronyms, "full": full, "db": db}


def names_source(text: str, src: dict, exclude: dict | None = None) -> bool:
    """这段文字是否点名了这个数据源。成立的条件（任一）：缩写出现；完整名称逐字出现；数据库清单中的名称模式匹配。
    exclude：要排除的名称信息（判断“是否还点名了其他数据”时，去掉和目标共有的缩写、名称和清单条目）。"""
    n = source_names(src)
    if exclude:
        n = {"acronyms": n["acronyms"] - exclude["acronyms"], "full": n["full"] - exclude["full"],
             "db": None if n["db"] is exclude["db"] else n["db"]}
    if any(re.search(rf"\b{re.escape(a)}\b", text or "") for a in n["acronyms"]):
        return True
    lt = letters(text)
    if any(f and f in lt for f in n["full"]):
        return True
    return bool(n["db"] and match_database(n["db"], text or ""))


def preceding_context(pages, evidence: dict, max_chars: int = 900) -> str:
    """证据句之前的上下文（同一页，最多 max_chars 个字符），用来判断 “this dataset” 指的是什么。"""
    page_no = evidence.get("page", 0)
    if not 1 <= page_no <= len(pages):
        return ""
    flat = re.sub(r"\s+", " ", pages[page_no - 1])
    head = step1.squash(evidence.get("quote", ""))[:40]
    # 用去掉空白后的文字定位，再换算回原文位置（逐字符做简单统一，速度快）
    squashed, index_map = [], []
    for i, ch in enumerate(flat):
        sq = unicodedata.normalize("NFKC", ch).lower()
        if sq.strip() and ch not in "-‐‑–—\u00ad":
            squashed.append(sq)
            index_map.extend([i] * len(sq))
    pos = "".join(squashed).find(head)
    if pos == -1:
        return ""
    start = index_map[pos]
    return flat[max(0, start - max_chars):start]


def evidence_scope(pages, src: dict, evidence: dict | None, statement: dict | None = None) -> str:
    """判断获取条件的证据是否针对这个数据：
       direct   直接证据：证据原文点名了这个数据
       anaphor  指代句：以 “This dataset / The data” 开头、前文提到了这个数据——只是线索，不确认归属
       general  总体声明：只说本文使用了公开数据等，没有归属到某个数据（或就是论文的数据可用性声明）
       unclear  无法确认：既没点名，也不像总体声明"""
    if not evidence:
        return "none"
    quote = evidence.get("quote", "")
    if names_source(quote, src):
        return "direct"
    if statement and step1.squash(statement.get("quote", "")) == step1.squash(quote):
        return "general"
    if GENERIC_STATEMENT.search(quote):
        return "general"
    # 证据句以 “This dataset / The data” 等指代开头、前文提到了这个数据：保留这条线索，但不据此确认归属。
    # 前文出现过名称，不能证明指代的就是它（中间可能已经换成了别的数据）→ 交给人工复核（2026-11-06 起）
    if ANAPHOR.search(quote) and names_source(preceding_context(pages, evidence), src):
        return "anaphor"
    return "unclear"


SCOPE_LABELS = {"direct": "direct evidence", "general": "general statement of the paper",
                "unclear": "the evidence does not clearly refer to this data",
                "anaphor": "anaphoric sentence; attribution needs manual confirmation", "none": ""}
VERIFICATION_LABELS = {
    "verified": "verified",
    "quote_not_found": "the quote cannot be found in the paper",
    "no_signal": "the quote has no clear expression supporting this category",
    "general_statement": "the evidence is only a general statement of the paper, not about this data",
    "unclear_reference": "the evidence does not clearly refer to this data",
    "conflict": "the quote contains both public and restricted expressions",
    "multi_sentence": "the evidence is a multi-sentence quote; the program does not judge attribution across sentences, so it needs manual review",
    "multiple_sources": "the evidence sentence also names other data sources of this paper; the program does not judge which one the condition belongs to",
    "anaphor_reference": "the evidence sentence starts with a reference (e.g. The data); this data is mentioned earlier, but the sentences in between do not form an unbroken chain of references to it, so the program does not confirm that it refers to it",
    "scope_unverified": "the model says the condition applies only to a part, but that part's name does not appear in the condition sentence (scope unverified)",
}
# 冻结的 Agent 提示词引用的是中文原文：保留一份，Agent 发给模型的内容保持不变
VERIFICATION_LABELS_ZH = {
    "verified": "已验证",
    "quote_not_found": "引用无法在原文中找到",
    "no_signal": "引用中没有支持该分类的明确说法",
    "general_statement": "证据只是论文的总体声明，没有针对这个数据",
    "unclear_reference": "证据没有明确指向这个数据",
    "conflict": "引用里同时有公开和受限的说法",
    "multi_sentence": "证据是多句引用，程序不判断跨句的归属，需要人工复核",
    "multiple_sources": "证据句里还提到了本论文的其他数据，程序不判断条件属于哪一个",
    "anaphor_reference": "证据句以指代开头（如 The data），前文提到了这个数据，但程序不据此确认指的就是它",
    "scope_unverified": "模型说条件只适用于某一部分，但这个部分名称没有出现在条件句中（适用范围未核实）",
    "none": "",
}


# 论文没有写获取条件时，根据数据库提示类型给出的结论（依据是工具内置清单，不是论文）。
# 清单里的事实就直接说（例如 CSMAR 收费是事实，不用“很可能”）；只有确实因数据而异的才写“需要确认”。
# 真正不确定的往往是“你自己能不能拿到”（学校有没有订阅），那是下一步的行动建议，不是数据本身的属性。
HINT_CONCLUSIONS = {
    "paid": "paid subscription required (check whether your university subscribes)",
    "gov_micro": "individual-level microdata require a formal application and are generally hard to obtain",
    "gov_public_micro": "public-use versions can usually be downloaded free of charge (more detailed variables may require a restricted version)",
    "academic_survey": "register and apply on the official site; students can generally obtain it",
    "open_science": "free download (some require an account)",
    "public_disclosure": "freely available, but you need to compile the data yourself",
    "yearbook": "public publication; available in libraries or on statistics bureau websites",
    "gov_portal": "partly public; check on the official site whether the specific data can be downloaded",
    "policy_doc": "policy documents are publicly available, but you need to code the variables yourself",
}
EVIDENCE_CONCLUSIONS = {"public": "publicly available", "subscription": "subscription or purchase required",
                        "restricted": "restricted: the paper states the data are not public or need a special channel; generally hard to obtain"}


def conclusion(category: str, hint: dict | None, urls: list[str] | None, n_evidence: int = 1,
               scope: str = "direct", ai_category: str | None = None, verification: str | None = None) -> tuple[str, str]:
    """把“论文证据”和“数据库提示”合成一句结论，并说明依据。返回 (结论, 依据)。
    规则：论文有直接证据就以论文为准；只有总体声明时，结论减弱并说明；论文没写，才用清单的常识；都没有就如实说明。"""
    if category == "unknown" and ai_category in EVIDENCE_CONCLUSIONS and verification not in (None, "none", "verified"):
        if verification == "general_statement":
            text = f"the paper makes a general statement that the data are {ACCESS_LABELS[ai_category]}, but not for this data specifically"
        else:
            text = f"not confirmed (initial AI judgment: {ACCESS_LABELS[ai_category]})"
        if hint and hint.get("type") in HINT_CONCLUSIONS:
            text += f"; database list reference: {HINT_CONCLUSIONS[hint['type']]}"
        return text, f"{VERIFICATION_LABELS[verification]}; see the source text"
    if category in EVIDENCE_CONCLUSIONS and scope in ("general", "unclear"):
        text = {"general": f"the paper makes a general statement that the data are {ACCESS_LABELS[category]}, but not for this data specifically",
                "unclear": f"the paper has a \"{ACCESS_LABELS[category]}\" statement, but it is unclear whether it refers to this data"}[scope]
        if hint and hint.get("type") in HINT_CONCLUSIONS:
            text += f"; database list reference: {HINT_CONCLUSIONS[hint['type']]}"
        return text, SCOPE_LABELS[scope] + " (check the source text)"
    if category in EVIDENCE_CONCLUSIONS:
        basis = "source text of the paper" if n_evidence <= 1 else f"source text of {n_evidence} papers"
        return EVIDENCE_CONCLUSIONS[category], basis
    if hint and hint.get("type") in HINT_CONCLUSIONS:
        return HINT_CONCLUSIONS[hint["type"]], "the tool's built-in database list; not stated in the paper"
    if urls:
        return "the paper gives a URL; open it to check", "source text of the paper (URL only, no condition stated)"
    return "cannot determine", "not stated in the paper, and this data is not in the tool's list"


# 句子分界：句号 / 问号 / 感叹号后面跟着空白，再接任何字母（大小写都算）、数字或括号。常见缩写里的句号不算。
SENTENCE_BREAK = re.compile(r"[.!?]\s+(?=[A-Za-z0-9(])")
ABBREVIATION = re.compile(r"\b(?:U\.S|U\.K|e\.g|i\.e|et al|etc|No|Fig|Vol|pp|Dr|Inc|Ltd|Co|vs)\.", re.IGNORECASE)


def sentence_count(quote: str) -> int:
    """引用里有几句话（分界数 + 1）。先去掉缩写里的句号，免得 “U.S. Census” 被当成两句。
    不确定是不是分界的地方一律当作分界：结果是“多句引用，需要人工复核”，而不是让多句引用按整段关键词通过。"""
    text = ABBREVIATION.sub(lambda m: m.group(0).replace(".", ""), (quote or "").strip())
    return len(SENTENCE_BREAK.findall(text)) + 1


def other_sources_named(quote: str, src: dict, others: list[dict]) -> list[str]:
    """证据句里还点名了本论文的哪些其他数据源。和目标共用的词（如同名的重复条目）不算。"""
    target = source_names(src)
    key = lambda x: re.sub(r"\s*\(.*?\)\s*", " ", x.get("name") or "").strip().lower()
    named = []
    for o in others or []:
        if o is src or key(o) == key(src):
            continue
        # 同一个数据库的另一条记录：只按名称判断（database_hint 还会看来源原文，原文里提到别的数据库时会误认为同一个）
        other = source_names(o)
        if target["db"] and other["db"] is target["db"]:
            continue
        if names_source(quote, o, exclude=target):
            named.append(o.get("name"))
    return named


def anaphor_resolved(pages, src: dict, evidence: dict, others: list[dict] | None) -> bool:
    """指代句能否确认指向这个数据（2026-11-17 起，见 DEVLOG）。
    从证据句往前（同一页、preceding_context 的范围内）逐句找最近一次点名这个数据的句子，三个条件都满足才确认：
      1. 找到了点名句；
      2. 点名句和证据句之间的每一句本身也是指代句（以 The / This / It 等开头），即指代链没有被另起话题的句子打断；
      3. 从点名句到证据句，没有点名本论文的其他数据源。
    条件 2 防止中间出现了模型没有抽取的数据（例：“We obtain weather data from NOAA.” 夹在中间时不确认）。
    诊断依据：受限 0/15 中 7 次是 deng2020 UHS 的指代句被拦下，模型判断正确；规则按一般原则写，没有针对具体论文。"""
    text = ABBREVIATION.sub(lambda m: m.group(0).replace(".", ""), preceding_context(pages, evidence).strip())
    sentences = [x.strip() for x in SENTENCE_BREAK.split(text) if x and x.strip()]
    chain = [evidence.get("quote", "")]
    for sentence in reversed(sentences):
        if names_source(sentence, src):
            if any(not ANAPHOR.search(x) for x in chain[1:]):
                return False
            return not any(other_sources_named(x, src, others) for x in chain + [sentence])
        chain.append(sentence)
    return False


def access_status(pages, src: dict, category: str, evidence: dict | None, statement: dict | None = None,
                  others: list[dict] | None = None) -> tuple[str, str]:
    """核对一条获取条件的证据能否支持这个分类，返回 (验证状态, 证据归属)。
    evidence 必须已经过 check_evidence（带 verified 字段）。三个条件都满足才是 "verified"：
    引用真实存在且是单句、引用里有支持该分类的说法（且没有冲突）、引用针对这个数据。
    基础流程（verify_result）和 Agent（agent_tools.submit_evidence）用的是这同一个函数，规则完全一样。"""
    if category == "unknown":
        return "none", "none"
    if not evidence or not evidence["verified"]:
        return "quote_not_found", "none"
    # 输入契约：获取条件的证据必须是单句。多句引用中，一句的“受限 / 公开”可能和另一句点名的数据被凑在一起，
    # 整段按关键词判断归属并不可靠（例：A 数据的名称 + 相邻句中 B 数据的受限条件）。
    # 不判断跨句的归属，交给人工复核；最终分类“未确认”，AI 的判断和原文引用都保留。提示词要求“一句话”不等于模型一定遵守
    if sentence_count(evidence["quote"]) > 1:
        return "multi_sentence", "none"
    if analyze_access(evidence["quote"], src)["conflict"]:
        return "conflict", "none"
    if not supports_category(category, evidence["quote"], src):
        return "no_signal", "none"
    scope = evidence_scope(pages, src, evidence, statement)
    if scope == "anaphor" and anaphor_resolved(pages, src, evidence, others):
        scope = "direct"
    # 同一句里还点名了本论文的其他数据源：可能是共同条件，也可能是分别描述，V1 不区分，交给人工复核（2026-11-06 起）
    if scope == "direct" and other_sources_named(evidence["quote"], src, others):
        return "multiple_sources", "none"
    return {"direct": "verified", "general": "general_statement", "unclear": "unclear_reference",
            "anaphor": "anaphor_reference"}[scope], scope


def check_source(pages, raw: dict, statement: dict | None, others: list[dict]) -> dict:
    """从模型的原始记录出发，完整核对一个数据源（证据、期间、数据库提示、获取条件）。
    每条记录都从头计算，不沿用任何之前的核对结果。"""
    src = {k: v for k, v in raw.items() if not k.startswith("_")}
    src["rule_notes"] = []   # 规则对 AI 原始结果做的修改，逐条记录，方便统计纠正与误改
    if raw.get("_split_from"):
        src["rule_notes"].append(f"由联合来源“{raw['_split_from']}”拆分，单独核对")
    src["source_evidence"] = check_evidence(pages, src.get("source_evidence"), tolerant=True)
    src["access_evidence"] = check_evidence(pages, src.get("access_evidence"))
    src["period_evidence"] = check_evidence(pages, src.get("period_evidence"), tolerant=True)
    for key in ("source_evidence", "access_evidence", "period_evidence"):
        ev = src.get(key)
        if ev and ev.get("page_given") is not None:
            src["rule_notes"].append(f"{key}：引用逐字出现在第{ev['page']}页（模型写的是第{ev['page_given']}页），已更正页码")
    src["sample_period"] = tidy_years(src.get("sample_period"))
    # 样本期间没有可核对的证据，或证据里找不到这些年份：保留 AI 的说法，但标出来，提醒用户自己确认
    if src["sample_period"] and not period_supported(src["sample_period"], src["period_evidence"]):
        src["period_unverified"] = True
    check_yearbook_period(pages, src)
    check_period_form(src)
    if src.get("period_note"):
        src["rule_notes"].append(src["period_note"])
    src["db_hint"] = raw.get("_split_hint") or database_hint(src)
    src["paid_hint"] = src["db_hint"]["name"] if src["db_hint"] and src["db_hint"]["type"] == "paid" else None
    src["urls"] = find_urls(src)
    src["ai_category"] = src["access_category"]   # AI 初步判断，始终保留
    # 三个字段分开保存：AI 初步判断（ai_category）、验证状态（verification）、最终分类（access_category）。
    # 只有通过 access_status 的全部检查，AI 的判断才成为最终分类；否则最终分类“未确认”，AI 的判断和未通过的原因都保留
    ai_cat = src["access_category"]
    status, src["evidence_scope"] = access_status(pages, src, ai_cat, src["access_evidence"], statement, others=others)
    # 适用范围：旧提示词没有这个字段 → 记为“未记录”（not_recorded），不默认针对整个数据源。
    # 分类和核对状态不变；报告只显示“原记录分类 + 适用范围未记录 + 原文”，不写成整个数据的结论
    applies = raw.get("access_applies_to") if "access_applies_to" in raw else "not_recorded"
    src["access_applies_to"] = applies
    if status == "verified" and applies not in ("whole", "not_recorded"):
        # 模型说条件只适用于某一部分：这个部分名称必须逐字出现在条件句中（没给范围也算未核实）
        if not applies or step1.squash(applies) not in step1.squash(src["access_evidence"]["quote"]):
            status = "scope_unverified"
    src["verification"] = status
    # “论文未说明”（none：AI 也说原文没写）和“需要人工复核”（AI 给了判断但没通过核对）分开
    src["needs_review"] = status not in ("verified", "none")
    src["access_scope"] = applies if status == "verified" else None
    src["access_origin"] = "paper" if status == "verified" else None
    if status not in ("verified", "none"):
        src["access_category"] = "unknown"
        src["downgraded"] = f"AI 初步判断为“{ACCESS_LABELS[ai_cat]}”，但{VERIFICATION_LABELS[status]}，最终记为“未确认”"
        src["rule_notes"].append(src["downgraded"])
    if status == "none":
        condition_candidate(pages, src, statement, others)
    check_usage(pages, raw, src)
    check_version_and_details(pages, raw, src)
    return src


def check_version_and_details(pages, raw: dict, src: dict) -> None:
    """V2（2026-11-17）：核对版本与获取细分字段。旧结果没有这些字段 → 记为未记录（None），不推断。
    - 版本：version_evidence 必须逐字存在于原文，且 version 的写法逐字出现在这句里，才算 version_verified
    - 渠道 / 资格：只在获取条件已核对通过（verification == verified）时显示；渠道还必须和已核对的分类一致
      （CHANNEL_CATEGORY），不一致时不显示渠道，并记一条 rule_note
    - 使用限制：每条都必须逐字出现在已核对的条件原文里，否则丢弃并记 rule_note"""
    if "version" not in raw:
        src["version"], src["version_verified"] = None, None
    else:
        src["version_evidence"] = check_evidence(pages, src.get("version_evidence"))
        ev = src.get("version_evidence") or {}
        v = src.get("version")
        # 没写版本 → None（不适用），不记为“未通过”
        src["version_verified"] = (bool(ev.get("verified") and step1.squash(v) in step1.squash(ev["quote"]))
                                   if v else None)
        if v and not src["version_verified"]:
            src["rule_notes"].append(f"版本“{v}”没有在核对通过的原文中逐字出现，报告中标为未核实")
    channel = raw.get("access_channel")
    src["access_channel_shown"] = None
    src["eligibility_shown"] = None
    src["use_restrictions_shown"] = []
    if channel is None or src.get("verification") != "verified":
        return
    quote = src["access_evidence"]["quote"]
    expected = CHANNEL_CATEGORY.get(channel)
    if channel != "not_stated" and expected != src["access_category"]:
        src["rule_notes"].append(f"模型给的渠道“{channel}”与已核对的分类“{src['access_category']}”不一致，不显示渠道")
    elif channel != "not_stated":
        src["access_channel_shown"] = channel
    if raw.get("eligibility") and raw["eligibility"] != "not_stated":
        src["eligibility_shown"] = raw["eligibility"]
    for r in raw.get("use_restrictions") or []:
        if r and step1.squash(r) in step1.squash(quote):
            src["use_restrictions_shown"].append(r)
        else:
            src["rule_notes"].append(f"使用限制“{r}”没有在条件原文中逐字出现，不显示")


# 候选的适用对象：只有说法本身带有对象时才记录（如 “public use sample”）；否则“适用范围未确定”，从不默认为整个数据源
CANDIDATE_SCOPE = re.compile(r"public[- ]use(?:\s+[a-z]+)?", re.IGNORECASE)


def condition_candidate(pages, src: dict, statement: dict | None, others: list[dict]) -> None:
    """模型判 unknown 时：记录这个数据源已核对通过的来源句、期间句里的条件词面线索（沿用现有词组）。
    **只是线索，不升级为最终分类**（2026-11-06 评审决定）：词组只能说明出现了某个词，不能证明它描述的是数据的获取条件
    （例：“the impact of temperature on AC purchases” 里的 purchases 是研究内容，不是购买数据）。
    获取对象和适用范围要由模型在提取请求中判断。最终分类保持 unknown，报告中显示线索和原文，需要人工复核。"""
    found = []
    for key in ("source_evidence", "period_evidence"):
        ev = src.get(key)
        if not ev or not ev.get("verified"):
            continue
        a = analyze_access(ev["quote"], src)
        if a["signals"]:
            found.append((key, ev, a))
    if not found:
        return
    cats = set().union(*(a["signals"] for _, _, a in found))
    key, ev, _ = found[0]
    m = CANDIDATE_SCOPE.search(step1.normalize(ev["quote"]))
    src["candidate"] = {"categories": sorted(cats), "evidence": ev, "from": key,
                        "scope": m.group(0) if m else "undetermined",
                        "conflict": len(cats) > 1 or any(x[2]["conflict"] for x in found)}
    src["needs_review"] = True
    src["rule_notes"].append(f"{'来源句' if key == 'source_evidence' else '期间句'}中有“{'、'.join(ACCESS_LABELS[c] for c in sorted(cats))}”类词语"
                             "（模型未判断；程序不能确认它描述的是数据的获取条件），需要人工复核")


def check_usage(pages, raw: dict, src: dict) -> None:
    """使用关系（每条记录各自的）：模型的判断，程序只核对依据原文存在。
    analyzed 且依据核对通过 → 本文使用；cited / described → 引用或介绍；unclear 或依据核对失败 → 使用关系待确认。
    旧提示词没有这个字段：旧提示词要求“只记录作者自己用到的数据”，按 analyzed、以来源句为依据（只用于回归对比）。"""
    if "usage" in raw:
        usage = raw.get("usage") if raw.get("usage") in USAGE_VALUES else "unclear"
        uev = check_evidence(pages, raw.get("usage_evidence"), tolerant=True)
        src["usage_legacy"] = False
    else:
        usage, uev = "analyzed", src.get("source_evidence")
        src["usage_legacy"] = True
    src["usage"], src["usage_evidence"] = usage, uev
    if usage in ("cited", "described"):
        src["usage_group"] = "referenced"
    elif usage == "analyzed" and uev and uev.get("verified"):
        src["usage_group"] = "analyzed"
    else:
        src["usage_group"] = "pending"
        src["rule_notes"].append("使用关系待确认：" + ("模型判断为无法确定" if usage == "unclear" else "使用关系的依据无法在原文中找到"))


UNKNOWN_REASONS = {"none": "no statement found", "no_signal": "unclear wording", "conflict": "conflicting evidence",
                   "quote_not_found": "quote cannot be checked", "lexical_clue": "lexical clue, unconfirmed"}


def unknown_reason(src: dict) -> str | None:
    """最终分类为 unknown 时，说明是哪一种 unknown（报告中不再统一写成“论文没写”）。提取失败是论文级的，不在这里。"""
    if src.get("access_category", "unknown") != "unknown":
        return None
    status = src.get("verification", "none")
    if status == "none" and src.get("candidate"):
        status = "lexical_clue"   # 模型判 unknown，但来源句 / 期间句中有条件类词语：不是“未找到说明”
    return UNKNOWN_REASONS.get(status, "attribution unclear")


def verify_result(pages, result: dict) -> dict:
    """核对模型的提取结果。顺序很重要：先拆分联合来源 → 再逐条从头核对 → 分流出“其他提及” → 最后去重。
    这样每条记录的核对结果都对应它自己的名称和证据；去重只合并已经核对好的记录，期间连同核实状态整体搬运。"""
    statement = check_evidence(pages, result.get("availability_statement"))
    statement = statement if statement and statement["verified"] else None
    raw_sources = split_joint_sources(result.get("data_sources", []))
    checked = [check_source(pages, raw, statement, raw_sources) for raw in raw_sources]
    limitations = [check_evidence(pages, ev) for ev in result.get("sample_limitations", [])]
    # 先分流、再去重：来源引用无效（或不像独立数据来源）的记录先移到“其他提及”，不参加去重时的比较——
    # 否则一条来源无效但条件更强的记录会先淘汰来源有效的那条，然后自己也被移走，结果有效来源一起消失
    candidates, others = [], []
    for src in checked:
        reason = classify_mention(src, pages)
        if reason:
            src["mention_reason"] = reason
            src["rule_notes"].append(f"移到“其他提及”：{MENTION_LABELS[reason]}")
            others.append(src)
        else:
            candidates.append(src)
    # 按使用关系分流：只有“模型判断为本文使用、且依据核对通过”的记录参与去重、本文使用计数和年份记录
    analyzed = [x for x in candidates if x["usage_group"] == "analyzed"]
    kept = dedupe_sources(analyzed)
    return {
        "data_sources": kept,
        "referenced": [x for x in candidates if x["usage_group"] == "referenced"],
        "usage_pending": [x for x in candidates if x["usage_group"] == "pending"],
        "other_mentions": others,
        "availability_statement": statement,
        "sample_limitations": [ev for ev in limitations if ev and ev["verified"]],
        "rejected_limitations": [ev for ev in limitations if ev and not ev["verified"]],
    }


# ============ 4. 打印报告 ============

def print_report(report: dict, mode: str) -> None:
    print(f"（AI 读取的内容：{mode}）\n")
    print("=== 数据来源 ===")
    for i, src in enumerate(report["data_sources"], start=1):
        se, ae = src["source_evidence"], src["access_evidence"]
        pe = src.get("period_evidence")
        kind = "（政策信息）" if src.get("kind") == "policy_info" else ""
        kind += {"robustness": "（稳健性检验）", "supplementary": "（补充分析）"}.get(src.get("role"), "")
        period = src.get("sample_period") or "原文未写"
        if src.get("period_unverified"):
            period += "  ⚠ 未能用原文核对，请自行确认"
        if src.get("period_note"):
            period += f"  ⚠ {src['period_note']}"
        print(f"\n{i}. {src['name']}{kind}")
        print(f"   提供机构：{src.get('provider') or '原文未写'}")
        print(f"   样本期间：{period}    单位：{src.get('unit') or '原文未写'}")
        text, basis = conclusion(src["access_category"], src.get("db_hint"), src.get("urls"),
                                 scope=src.get("evidence_scope", "direct"), ai_category=src.get("ai_category"),
                                 verification=src.get("verification"))
        print(f"   ▶ 结论：{text}（依据：{basis}）")
        print(f"   论文证据：【{ACCESS_LABELS[src['access_category']]}】")
        if src.get("downgraded"):
            print(f"   ⚠ 需要人工复核：{src['downgraded']}")
        if src.get("urls"):
            print(f"   🔗 原文给出的网址：{'  '.join(src['urls'])}（有网址不等于公开，请打开确认获取条件）")
        if src.get("db_hint"):
            h = src["db_hint"]
            print(f"   {h['icon']} 数据库提示（{h['name']}）：{h['message']}（工具内置清单的提示，不是论文中的说法）")
        if se:
            print(f"   来源证据 第{se['page']}页 {'✓' if se['verified'] else '✗ 核对失败'}：{se['quote']}")
        if ae:
            print(f"   条件证据 第{ae['page']}页 {'✓' if ae['verified'] else '✗ 核对失败'}：{ae['quote']}")
        if pe:
            print(f"   期间证据 第{pe['page']}页 {'✓' if pe['verified'] else '✗ 核对失败'}：{tidy_years(pe['quote'])}")
    if report.get("other_mentions"):
        print("\n=== 其他提及（不像独立的数据来源，供参考）===")
        for src in report["other_mentions"]:
            print(f"   - {src['name']}：{MENTION_LABELS[src['mention_reason']]}")
    print("\n=== 数据可用性声明 ===")
    st = report.get("availability_statement")
    print(f"   第{st['page']}页 ✓：{st['quote']}" if st else "（论文中没有找到）")
    print("\n=== 样本受限的说法 ===")
    if not report["sample_limitations"]:
        print("（无）")
    for ev in report["sample_limitations"]:
        print(f"   第{ev['page']}页 ✓：{ev['quote']}")
    if report["rejected_limitations"]:
        print(f"\n（另有 {len(report['rejected_limitations'])} 条 AI 给出的引用核对失败，已丢弃）")
    print("\n说明：以上是论文作者发表时的描述，不代表数据库现在的获取条件，请自行核实。")


def extract(pdf_path: str) -> dict:
    """完整流程：读取 PDF → 筛选段落 → AI 提取 → 程序核对。评估脚本也调用这个函数。"""
    pages, blocks = step1.extract_pages(pdf_path)
    context, mode = build_context(pages, blocks)
    raw, model_used = ask_ai(context)
    return {"model": model_used, "mode": mode, "ai_raw": raw, "report": verify_result(pages, raw)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python step2_ai_extract.py 论文.pdf")
        raise SystemExit(1)
    pdf_path = sys.argv[1]
    result = extract(pdf_path)
    print(f"使用的模型：{result['model']}")
    print_report(result["report"], result["mode"])

    # 把 AI 的原始回答和核对后的报告都存下来，方便之后对照标准答案评估
    out = re.sub(r"\.pdf$", "", pdf_path, flags=re.IGNORECASE) + "_result.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到 {out}")
