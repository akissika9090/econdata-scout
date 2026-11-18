"""
测试 step2 的“核对”部分，不需要 API key。
用一份模拟的 AI 回答（其中故意放了编造的引用和错误的分类），检查程序能否把它们拦下来。

运行：
    python test_step2.py
"""
from test_support import require_materials

require_materials(['papers/deng2020.pdf', 'papers/mobarak2021.pdf', 'papers/yu_zhang2021.pdf', 'papers/zhou2022.pdf'], "test_step2")


import step1_pdf_evidence as step1
import step2_ai_extract as step2

PDF = "papers/deng2020.pdf"

# 模拟 AI 的回答：前两条是正确的，后两条故意出错
FAKE_AI_ANSWER = {
    "data_sources": [
        {   # 引用真实存在、原文写明不公开；证据句是指代句，但指代链连续指向前文点名的 UHS → 受限已验证（2026-11-17 起；11-06 至 11-16 为需要人工复核）
            "name": "Urban Household Survey", "provider": "National Bureau of Statistics of China",
            "kind": "dataset", "sample_period": "2002–2009", "unit": "household", "access_category": "restricted",
            "period_evidence": {"quote": "Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", "page": 3},  # 期间有证据，年份都在原文里 → 通过
            "source_evidence": {"quote": "Our data come from the Urban Household Survey (UHS) since 1986 conducted by the National Bureau of Statistics of China.", "page": 3},
            "access_evidence": {"quote": "Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", "page": 3},
        },
        {   # 正确：原文没写获取条件，所以是未确认
            "name": "Daily meteorological data", "provider": "Chinese National Meteorological Information Center",
            "kind": "dataset", "sample_period": "2002–2010", "unit": "county", "access_category": "unknown",
            "period_evidence": {"quote": "Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", "page": 3},  # 原文是 2002 到 2009，AI 写成 2010 → 期间应标为未核对
            "source_evidence": {"quote": "The daily meteorological data of China comes from the Chinese National Meteorological Information Center.", "page": 3},
            "access_evidence": None,
        },
        {   # 错误1：AI 凭背景知识说是公开的，并编造了一句引用 → 应降级为未确认
            "name": "Daily meteorological data (duplicate)", "provider": None,
            "kind": "dataset", "sample_period": "2002–2009", "unit": None, "access_category": "public",
            "period_evidence": None,  # 有期间但没给证据 → 期间应标为未核对
            "source_evidence": {"quote": "The daily meteorological data of China comes from the Chinese National Meteorological Information Center.", "page": 3},
            "access_evidence": {"quote": "The meteorological data are publicly available online.", "page": 3},
        },
        {   # 错误2：引用是真的，但页码写错了（第5页）→ 应降级为未确认
            "name": "Urban Household Survey (wrong page)", "provider": None,
            "kind": "dataset", "sample_period": None, "unit": None, "access_category": "restricted",
            "period_evidence": None,
            "source_evidence": {"quote": "Our data come from the Urban Household Survey (UHS) since 1986 conducted by the National Bureau of Statistics of China.", "page": 3},
            "access_evidence": {"quote": "Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", "page": 5},
        },
        {   # 错误3：引用真实存在（脚注里的下载网址），但不能说明数据公开 → 应降级为未确认
            # 这是 Yu 2019 实际出现过的错误，这里用论文1里同样“只是数据介绍”的一句来模拟
            "name": "Daily meteorological data (url only)", "provider": None,
            "kind": "dataset", "sample_period": None, "unit": None, "access_category": "public",
            "period_evidence": None,
            "source_evidence": {"quote": "The daily meteorological data of China comes from the Chinese National Meteorological Information Center.", "page": 3},
            "access_evidence": {"quote": "The daily meteorological data of China comes from the Chinese National Meteorological Information Center.", "page": 3},
        },
    ],
    "sample_limitations": [
        {"quote": "Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", "page": 3},
        {"quote": "Data for 2010 onward were missing for most provinces.", "page": 3},  # 编造 → 应被丢弃
    ],
    # 这篇论文没有数据可用性声明，AI 编造了一句 → 应被丢弃
    "availability_statement": {"quote": "All data used in this study are available from the authors upon request.", "page": 8},
}

# 第一条（UHS）的证据是指代句 “Since the dataset ...”：2026-11-06 起不据此确认归属 → 未确认（需要人工复核），以前是受限
EXPECTED_CATEGORIES = ["restricted", "unknown", "unknown", "unknown", "unknown"]
EXPECTED_PERIOD_UNVERIFIED = [False, True, True, False, False]


def run() -> bool:
    pages, blocks = step1.extract_pages(PDF)
    report = step2.verify_result(pages, FAKE_AI_ANSWER)
    ok_all = True
    for src, expected in zip(report["data_sources"], EXPECTED_CATEGORIES):
        ok = src["access_category"] == expected
        ok_all &= ok
        note = f"（AI 原判断 {src['ai_category']}，已降级）" if src.get("downgraded") else ""
        print(f"{'✓' if ok else '✗'}  {src['name']}：{src['access_category']} {note}")
    for src, expected in zip(report["data_sources"], EXPECTED_PERIOD_UNVERIFIED):
        flagged = bool(src.get("period_unverified"))
        ok = flagged == expected
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  {src['name']}：样本期间 {src['sample_period']} "
              f"{'标为未核对' if flagged else '核对通过' if src['sample_period'] else '（无）'}")
    ok = report["availability_statement"] is None
    ok_all &= ok
    print(f"{'✓' if ok else '✗'}  编造的数据可用性声明被丢弃")
    # 分类信号检查：真实论文里出现过的句子
    signal_cases = [
        ("public", "Data have been publicly released for the following ten years: 1989, 1991, 2015.", True),
        ("public", "we employ the publicly available WorldClim-Global Climate Data.", True),
        ("public", "http://data.cma.cn/data/cdcdetail/dataCode/SURF_CLI_CHN_MUL_DAY_V3.0.html.", False),
        ("public", "Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", False),
        ("restricted", "Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", True),
        ("restricted", "Further information about the data is available upon a reasonable request.", True),
        # li2015：通过与企业管理层的特别协议取得的数据（第一版规则把这句判为“不支持”，导致正确的“受限”被降级）
        ("restricted", "Our data on worker output is made available thanks to a special agreement with management at a textile operation in a city in the northern province of Hebei, China.", True),
        ("public", "Our data on worker output is made available thanks to a special agreement with management at a textile operation.", False),
        ("restricted", "GDP data for 2013 was obtained from the National Bureau of Statistics of China, available at http://data.stats.gov.cn/workspace/index?m=fsjd.", False),
    ]
    for cat, quote, expected in signal_cases:
        ok = step2.supports_category(cat, quote) == expected
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  “{quote[:50]}…” {'支持' if expected else '不支持'} {cat}")
    # 商业数据库提示：真实论文里出现过的说法
    hint_cases = [
        ({"name": "Wind database", "source_evidence": {"quote": "employee data are derived from the WIND database"}}, "Wind"),   # 2026-11-06：清单名称改为英文
        ({"name": "CSMAR", "source_evidence": {"quote": "firm-level data is drawn from the China Stock Market and Accounting Research (CSMAR) database"}}, "CSMAR"),
        ({"name": "weather data", "source_evidence": {"quote": "readings for ground temperature, humidity, wind speed and wind direction are available at www.worldweatheronline.com"}}, None),
        ({"name": "China City Statistical Yearbook", "source_evidence": {"quote": "City-level data is obtained from the China City Statistical Yearbook"}}, None),
    ]
    # 其他类型的提示（真实论文中的说法）
    type_cases = [
        ({"name": "Urban Household Survey", "source_evidence": {"quote": "Our data come from the Urban Household Survey (UHS) since 1986"}}, "gov_micro"),
        ({"name": "Census", "source_evidence": {"quote": "We measure internal migration using the 2015 Population Census of China."}}, "gov_micro"),
        ({"name": "CFPS", "source_evidence": {"quote": "Household-level data is from China Family Panel Studies (CFPS) in 2014 and 2016"}}, "academic_survey"),
        ({"name": "CHNS", "source_evidence": {"quote": "We obtained household-level data on AC ownership from the China Health and Nutrition Survey (CHNS)"}}, "academic_survey"),
        ({"name": "City yearbook", "source_evidence": {"quote": "City-level data is obtained from the China City Statistical Yearbook (2014–2023)."}}, "yearbook"),
        # 国家统计局的省级汇总数据，不应该被当成“微观调查数据”，而是政府部门发布的数据
        ({"name": "AC data", "source_evidence": {"quote": "The AC data come from the National Bureau of Statistics (NBS) of China, which conducts household surveys in urban and rural areas"}}, "gov_portal"),
        # 国家统计局编的年鉴：应提示为年鉴，而不是“政府部门”
        ({"name": "energy data", "source_evidence": {"quote": "The energy consumption data are from the China Energy Statistical Yearbook."}}, "yearbook"),
        ({"name": "EIU", "source_evidence": {"quote": "We use the expected annual income growth rate from the Economist Intelligence Unit (EIU)"}}, "paid"),
        ({"name": "MERRA-2", "source_evidence": {"quote": "We collect data on thermal inversions from the Modern-Era Retrospective Analysis for Research and Applications, Version 2 (MERRA-2)"}}, "open_science"),
        ({"name": "mortality data", "provider": "China's DSPs", "source_evidence": {"quote": "The mortality data come from China's DSPs."}}, "gov_micro"),
        ({"name": "LCCP policy", "kind": "policy_info", "source_evidence": {"quote": "Information about the LCCP policy is manually collected from the National Development and Reform Commission (NDRC)."}}, "gov_portal"),
        ({"name": "pilot list", "kind": "policy_info", "source_evidence": {"quote": "The pilot cities were announced in 2010."}}, "policy_doc"),
        ({"name": "weather data", "source_evidence": {"quote": "wind speed and wind direction are available at www.worldweatheronline.com"}}, None),
    ]
    for src, expected in type_cases:
        h = step2.database_hint(src)
        got = h["type"] if h else None
        ok = got == expected
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  数据库提示类型：{src['name']} → {got or '无'}")
    for src, expected in hint_cases:
        got = step2.paid_database_hint(src)
        ok = got == expected
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  数据库提示：{src['name']} → {got or '无'}")
    urls = step2.find_urls({"access_evidence": {"verified": True, "quote": "readings are available at www.worldweatheronline.com and http://data.stats.gov.cn/workspace/index?m=fsjd."}})
    ok = urls == ["www.worldweatheronline.com", "http://data.stats.gov.cn/workspace/index?m=fsjd"]
    ok_all &= ok
    print(f"{'✓' if ok else '✗'}  从原文提取网址：{urls}")
    # 年鉴出版年份被当成样本期间：只提示、标为未核实，不自动替换（2026-11-06 起）。
    # yu_zhang2021 原文第 4 页另有 “over the period 2003–2018”，以前会自动改成那一句；但“早一年”的年份范围可能属于别的数据，不再自动替换
    pages_yz, _ = step1.extract_pages("papers/yu_zhang2021.pdf")
    for label, pg in [("原文另有早一年的期间（yu_zhang2021）", pages_yz), ("原文没有早一年的期间（deng2020）", pages)]:
        src = {"sample_period": "2004–2019", "period_evidence": {"quote": "The data are mainly obtained from China City Statistical Yearbook (2004–2019).", "page": 4, "verified": True}}
        step2.check_yearbook_period(pg, src)
        ok = (src["sample_period"] == "2004–2019" and src["period_evidence"]["page"] == 4 and src.get("period_unverified") is True
              and "可能是年鉴的出版年份" in src.get("period_note", ""))
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  年鉴年份：{label} → 不替换，只提示并标为未核实")
    # 结论：论文证据优先，其次数据库清单，最后网址
    concl_cases = [
        # 2026-11-06：报告改为英文，期望文字随之翻译（原为 需要付费订阅/清单、受限/论文原文、网址/只有网址、无法判断/清单中也没有）
        (("unknown", {"type": "paid"}, []), "paid subscription", "database list"),
        (("restricted", {"type": "gov_micro"}, []), "restricted", "source text of the paper"),
        (("public", {"type": "paid"}, []), "publicly available", "source text of the paper"),   # 论文说公开时以论文为准
        (("unknown", None, ["www.example.com"]), "URL", "URL only"),
        (("unknown", None, []), "cannot determine", "not in the tool's list"),
    ]
    for (cat, hint, urls), want_text, want_basis in concl_cases:
        text, basis = step2.conclusion(cat, hint, urls)
        ok = want_text in text and want_basis in basis
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  结论：{cat} + {hint and hint['type']} → {text}（{basis}）")
    # 证据是否针对这个数据（真实论文中的句子）
    scope_cases = [
        # “Since the dataset ...” 没有点名，前文点名了 UHS → 指代句：只是线索，不确认归属（2026-11-06 起；以前判为直接证据）
        ("papers/deng2020.pdf", {"name": "Urban Household Survey", "provider": "National Bureau of Statistics"},
         {"quote": "Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", "page": 3}, "anaphor"),
        # 同一句话，安到气象数据头上：前文没有点名气象数据 → 无法确认（不能过度归属）
        ("papers/deng2020.pdf", {"name": "daily meteorological data", "provider": "Chinese National Meteorological Information Center"},
         {"quote": "Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", "page": 3}, "unclear"),
        # 只出现名称中的一个普通词 Census（名称是 2015 Population Census of China）→ 不能确认点名，按指代句处理（需要人工复核）。
        # 2026-11-06 第二阶段“点名收紧”后的预期；以前是 direct。这是收紧带来的有效信息减少，记入回归报告，不是修好
        ("papers/mobarak2021.pdf", {"name": "2015 Population Census of China"},
         {"quote": "The 2015 Census is the latest census with restricted public access.", "page": 9}, "anaphor"),
        # 整篇论文的总体声明 → 总体声明
        ("papers/zhou2022.pdf", {"name": "China Family Panel Studies", "provider": "Peking University"},
         {"quote": "Publicly available datasets were analyzed in this study.", "page": 8}, "general"),
    ]
    for pdf, src, ev, expected in scope_cases:
        pg, _ = step1.extract_pages(pdf)
        got = step2.evidence_scope(pg, src, ev)
        ok = got == expected
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  证据归属：{src['name'][:30]} ← “{ev['quote'][:40]}…” → {got}")
    text, basis = step2.conclusion("public", {"type": "academic_survey"}, [], scope="general")
    ok = "general statement" in text and "not for this data specifically" in text
    ok_all &= ok
    print(f"{'✓' if ok else '✗'}  总体声明时结论减弱：{text}")
    # 联合来源拆分 + 同一论文去重（wei2023 实际出现的情况）：走完整的 verify_result（先拆分、再逐条核对、再去重）
    jt = ["Data. Employee data are derived from the WIND database. Subsidy data come from the CSMAR database. "
          "Firm data are drawn from the CSMAR and WIND databases. City data come from the China City Statistical Yearbook. End."]
    js = lambda n, q: {"name": n, "role": "main", "kind": "dataset", "provider": None, "unit": None, "sample_period": None,
                       "period_evidence": None, "access_category": "unknown", "source_evidence": {"quote": q, "page": 1},
                       "access_evidence": None}
    out = step2.verify_result(jt, {"data_sources": [js("WIND database", "Employee data are derived from the WIND database."),
                                                    js("CSMAR database", "Subsidy data come from the CSMAR database."),
                                                    js("CSMAR and WIND databases", "Firm data are drawn from the CSMAR and WIND databases."),
                                                    js("China City Statistical Yearbook", "City data come from the China City Statistical Yearbook.")],
                                   "sample_limitations": [], "availability_statement": None})["data_sources"]
    hints = sorted((x.get("db_hint") or {}).get("name", x["name"]) for x in out)
    ok = len(out) == 3 and sum(1 for h in hints if "Wind" in h) == 1 and sum(1 for h in hints if "CSMAR" in h) == 1
    ok_all &= ok
    print(f"{'✓' if ok else '✗'}  拆分并去重：4 条 → {len(out)} 条 {hints}")
    # 换一种说法的句子（不是从任何测试论文里抄来的），检查规则能否泛化，而不是只记住见过的句子
    paraphrase_cases = [
        ("public", "We rely on the public use microdata files released by the statistical office.", True),
        ("public", "The survey is publicly accessible through the project website.", True),
        ("public", "None of these records are publicly accessible.", False),
        ("restricted", "None of these records are publicly accessible.", True),
        ("restricted", "Individual-level files cannot be accessed outside the secure facility.", True),
        ("restricted", "Access is subject to a confidentiality agreement with the ministry.", True),
        ("restricted", "The tax records are not public.", True),
        ("public", "The tax records are not public.", False),
        # 句子里有 public，但说的是“公共支出”，不是数据公开
        ("public", "We use data on public expenditure from the yearbook.", False),
        # 测试集里出现过的两句（用来确认修复）
        ("public", "The present study utilizes the public-use files of the Canadian LFS (July 2001–June 2015).", True),
        ("restricted", "To the best of our knowledge, no individual-level census data in 1995 and 2010 are publicly available.", True),
    ]
    # 第二批换说法的句子：先写好再运行，用来比较“短语清单”和“词组+规则”的泛化能力
    # （旧版 10/15，新版 14/15；唯一的错误是 “unavailable” 放错了词组，移到限制词组后 15/15）
    for q, truth in [
        ("The microdata are openly accessible on the project website.", {"public"}),
        ("These data can be freely obtained from the ministry.", {"public"}),
        ("The census tables are freely distributed by the statistics office.", {"public"}),
        ("Access to the data requires approval from the ethics committee.", {"restricted"}),
        ("The registry is not publicly released.", {"restricted"}),
        ("None of the files are released to the public.", {"restricted"}),
        ("Readers may download the data free of charge.", {"public"}),
        ("The firm-level records were provided under a confidentiality agreement.", {"restricted"}),
        ("These records are unavailable to outside researchers.", {"restricted"}),
        ("We purchased the transaction data from a commercial vendor.", {"subscription"}),
        ("The dataset is accessible only within the secure data center.", {"restricted"}),
        ("We use public spending data from the yearbook.", set()),
        ("Data on public health expenditure come from the yearbook.", set()),
        ("The data are available at www.example.org.", set()),
        ("We thank the bureau for providing access to its archives.", set()),
    ]:
        got = step2.access_signals(q)
        ok = got == truth
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  换说法2：“{q[:55]}…” → {sorted(got) or '无'}")
    for cat, quote, expected in paraphrase_cases:
        ok = step2.supports_category(cat, quote) == expected
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  换说法：“{quote[:55]}…” {'支持' if expected else '不支持'} {cat}")
    # 证据状态（冲突）、双重否定、数据对象归属（G 师傅的例句 + 两个对象例句）
    cfps = {"name": "China Family Panel Studies (CFPS)"}
    census = {"name": "Population census microdata"}
    for q, src, truth, conflict in [
        ("No restrictions apply to these publicly available data.", None, {"public"}, False),
        ("The data are available without restriction from the website.", None, {"public"}, False),
        ("Data are not freely available but can be obtained upon request.", None, {"restricted"}, False),
        ("Public documentation is available, but the microdata are restricted.", None, {"restricted"}, False),
        ("The documentation is publicly available, but access to the household-level records requires approval.", None, {"restricted"}, False),
        ("The data were previously confidential but are now publicly released.", None, {"public", "restricted"}, True),
        ("Province-level tables are publicly available, but the county-level data are confidential.", None, {"public", "restricted"}, True),
        ("The CFPS data are publicly available, whereas the census microdata require approval.", cfps, {"public"}, False),
        # 2026-11-06 评审决定移除“名称中两个词同时出现即点名”：分句里只有 “census microdata”，不是完整名称
        # “Population census microdata”，不能确认点名 → 两个分句都保留 → 冲突（交人工）。以前靠两词共现判为受限
        ("The CFPS data are publicly available, whereas the census microdata require approval.", census, {"public", "restricted"}, True),
    ]:
        a = step2.analyze_access(q, src)
        ok = a["signals"] == truth and a["conflict"] == conflict
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  证据状态：“{q[:50]}…”{'（' + src['name'][:12] + '）' if src else ''} → "
              f"{sorted(a['signals']) or '无'}{' 冲突' if a['conflict'] else ''}")
    ok = not step2.supports_category("public", "The data were previously confidential but are now publicly released.")
    ok_all &= ok
    print(f"{'✓' if ok else '✗'}  有冲突时不支持任何一方")
    # 三个字段：AI 初步判断、验证状态、最终分类
    pg, _ = step1.extract_pages("papers/zhou2022.pdf")
    fake = {"data_sources": [{"name": "China Family Panel Studies", "kind": "dataset", "access_category": "public",
                              "sample_period": None, "period_evidence": None,
                              "source_evidence": {"quote": "Household-level data is from China Family Panel Studies (CFPS) in 2014 and 2016", "page": 2},
                              "access_evidence": {"quote": "Publicly available datasets were analyzed in this study.", "page": 8}}],
            "sample_limitations": [], "availability_statement": None}
    v = step2.verify_result(pg, fake)["data_sources"][0]
    ok = v["ai_category"] == "public" and v["verification"] == "general_statement" and v["access_category"] == "unknown"
    ok_all &= ok
    print(f"{'✓' if ok else '✗'}  三字段：AI={v['ai_category']} 验证={v['verification']} 最终={v['access_category']}")
    text, basis = step2.conclusion(v["access_category"], v.get("db_hint"), v.get("urls"), ai_category=v["ai_category"], verification=v["verification"])
    ok = "general statement" in text
    ok_all &= ok
    print(f"{'✓' if ok else '✗'}  结论：{text}（{basis}）")
    # 变量、笼统说法不当作数据来源
    var = {"name": "PM10", "kind": "dataset", "source_evidence": {"quote": "This paper evaluated the effect of PM10 and AQI on health-care expenditure", "verified": True}}
    vague = {"name": "many other statistical yearbooks of China", "kind": "dataset", "source_evidence": {"quote": "The data sources are the China Environmental Yearbook and many other statistical yearbooks of China.", "verified": True}}
    real = {"name": "worker output data", "kind": "dataset", "source_evidence": {"quote": "Our data on worker output is made available thanks to a special agreement with management", "verified": True}}
    for src, expected in [(var, "possible_variable"), (vague, "unspecified"), (real, None)]:
        got = step2.classify_mention(src)
        ok = got == expected
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  是否独立数据来源：{src['name'][:30]} → {got or '是数据来源'}")
    ok = step2.tidy_years("2004e2012") == "2004–2012"
    ok_all &= ok
    print(f"{'✓' if ok else '✗'}  显示时 2004e2012 还原为 2004–2012")
    ok = len(report["sample_limitations"]) == 1 and len(report["rejected_limitations"]) == 1
    ok_all &= ok
    print(f"{'✓' if ok else '✗'}  样本受限：保留 {len(report['sample_limitations'])} 条，丢弃编造的 {len(report['rejected_limitations'])} 条")

    # 空引用、过短引用、页码为空：verify_quote 拒绝后，不能作为样本受限说法、数据可用性声明或期间证据进入报告
    # （之前空引用会核对通过，被当成一条“样本受限的说法”列进报告）
    junk = {"data_sources": [{"name": "Urban Household Survey", "kind": "dataset", "access_category": "unknown",
                              "sample_period": "2002–2009", "period_evidence": {"quote": "2002 to 2009", "page": 3},
                              "source_evidence": {"quote": "Our data come from the Urban Household Survey (UHS) since 1986 conducted by the National Bureau of Statistics of China.", "page": 3},
                              "access_evidence": None}],
            "sample_limitations": [{"quote": "", "page": 3}, {"quote": "the data", "page": 3},
                                   {"quote": "Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", "page": None}],
            "availability_statement": {"quote": "", "page": 3}}
    r = step2.verify_result(pages, junk)
    # 页码为空、但原文逐字存在的那条限制：程序在全文中找到它（第 3 页），改正页码后保留（2026-11-06 起）；
    # 空引用、过短引用仍然拒绝
    kept_lims = r["sample_limitations"]
    ok = (len(kept_lims) == 1 and kept_lims[0]["page"] == 3 and kept_lims[0].get("page_given") is None
          and len(r["rejected_limitations"]) == 2 and r["availability_statement"] is None
          and r["data_sources"][0].get("period_unverified") is True)
    ok_all &= ok
    print(f"{'✓' if ok else '✗'}  空引用、过短引用被拒绝；页码为空但原文存在的限制改正页码后保留；期间标为未核对")

    context, mode = step2.build_context(pages, blocks)
    print(f"\n发给 AI 的内容：{mode}，约 {len(context.split())} 个英文词")
    print("\n全部通过" if ok_all else "\n有测试失败")
    return ok_all


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
