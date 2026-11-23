"""
测试第三步“合并”的关键：不同论文对同一个数据的叫法不同，要合并到同一组；不同的数据不能被合并。
不需要 API，也不需要论文 PDF。

运行：
    python test_step3.py
"""

import os
import tempfile

import step2_ai_extract as step2
import step3_merge as step3


def src(name, quote="", provider=None, kind="dataset"):
    s = {"name": name, "provider": provider, "kind": kind, "source_evidence": {"quote": quote}}
    s["db_hint"] = step2.database_hint(s)
    return s


# 每组里的说法都来自真实论文，应该得到同一个键
SAME = [
    ("城市统计年鉴", [
        src("China City Statistical Yearbook", "City-level controls are taken from the China City Statistical Yearbook."),
        src("City Statistical Yearbooks", "City characteristics such as population and GDP come from the City Statistical Yearbooks."),
        src("China City Statistical Yearbook", "City-level variables come from the China City Statistical Yearbook (2014–2023)."),
    ]),
    ("能源统计年鉴", [
        src("China Energy Statistical Yearbook", "Energy use figures are taken from the China Energy Statistical Yearbook."),
        src("Energy Statistical Yearbooks", "plant-level power output, taken from the Energy Statistical Yearbooks and the Electric Power Yearbooks of China."),
    ]),
    ("CFPS", [
        src("China Family Panel Studies", "Household variables come from China Family Panel Studies (CFPS), waves 2014 and 2016"),
        src("China Household Panel Survey 2016 (CFPS)", "Our source is the China Household Panel Survey 2016 (CFPS) as released."),
    ]),
    ("UHS", [
        src("Urban Household Survey", "We use Urban Household Survey (UHS) data starting in 1986"),
        src("Urban Household Survey data", "For robustness, Urban Household Survey data are used as well"),
    ]),
]

# 这些是不同的数据，不应该合并
DIFFERENT = [
    ("城市统计年鉴 vs 能源统计年鉴",
     src("China City Statistical Yearbook", "from the China City Statistical Yearbook."),
     src("China Energy Statistical Yearbook", "from the China Energy Statistical Yearbook.")),
    ("国家统计局的空调数据 vs 国家统计局的 UHS（同一机构，不同数据）",
     src("AC data", "We take the AC data from the National Bureau of Statistics (NBS) of China", provider="NBS"),
     src("Urban Household Survey", "Our data come from the Urban Household Survey (UHS) conducted by the National Bureau of Statistics")),
    ("CSMAR vs Wind（同为付费数据库）",
     src("CSMAR database", "green subsidy data are derived from the CSMAR database"),
     src("WIND database", "employee figures are taken from the WIND database")),
]


def run() -> bool:
    ok_all = True
    for label, items in SAME:
        keys = {step3.canonical_key(s)[0] for s in items}
        ok = len(keys) == 1
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  应合并：{label} → {keys}")
    for label, a, b in DIFFERENT:
        ka, kb = step3.canonical_key(a)[0], step3.canonical_key(b)[0]
        ok = ka != kb
        ok_all &= ok
        print(f"{'✓' if ok else '✗'}  不应合并：{label}（{ka} / {kb}）")
    # 2026-11-06 产品决定取消“历史年份是否满足你的研究”的自动判断：coverage_gap 和 --need 已删除（原测试检查覆盖风险提示）
    ok = not hasattr(step3, "coverage_gap") and "--need" not in open(step3.__file__, encoding="utf-8").read()
    ok_all &= ok
    print(f"{'✓' if ok else '✗'}  年份覆盖判断已取消：没有 coverage_gap，命令没有 --need")
    ok_all &= run_result_files()
    ok_all &= run_merge_choices()
    ok_all &= run_cps_series()
    ok_all &= run_census_country()
    print("\n全部通过" if ok_all else "\n有测试失败")
    return ok_all


def run_result_files() -> bool:
    """结果文件名的解析：不符合格式的文件跳过而不是报错；新格式（带年份）比旧格式新；跨年时顺序正确。"""
    ok_all = True
    print("\n结果文件")
    p = step3.parse_result_name
    cases = [
        ("旧格式能解析", p("results/deng2020_1105_093521_run1.json")["paper"] == "deng2020"),
        ("新格式能解析", p("results/deng2020_20261105_093521_run1.json")["paper"] == "deng2020"),
        ("论文名里有下划线也能解析", p("results/li_lu_li_scs_1105_105528_run1.json")["paper"] == "li_lu_li_scs"),
        ("不符合格式 → None（之前会直接报错退出）", p("results/deng2020_old_run1.json") is None),
        ("跨年：2027-01-01 晚于 2026-12-31",
         p("x_20270101_000000_run1.json")["stamp"] > p("x_20261231_235959_run1.json")["stamp"]),
        ("新格式一律晚于旧格式", p("x_20261106_000000_run1.json")["stamp"] > p("x_1231_235959_run1.json")["stamp"]),
    ]
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "results"))
        for name in ["deng2020_1105_093521_run1.json", "deng2020_20261231_120000_run1.json",
                     "deng2020_20270101_090000_run1.json", "deng2020_old_run1.json", "yu2019_1104_235400_run2.json"]:
            open(os.path.join(d, "results", name), "w").close()
        cwd = os.getcwd()
        os.chdir(d)
        try:
            latest = step3.latest_results(None)
            only = step3.latest_results(["yu2019"])
        finally:
            os.chdir(cwd)
    cases += [
        ("latest_results：混有不符合格式的文件也不报错，取最新（跨年）",
         latest.get("deng2020") == "results/deng2020_20270101_090000_run1.json"),
        ("latest_results：只取指定论文", list(only) == ["yu2019"]),
    ]
    for name, ok in cases:
        ok_all &= ok
        print(f"  {'✓' if ok else '✗'}  {name}")
    return ok_all


def report_with(sources: list[dict]) -> dict:
    """一份已核对的报告（只含合并需要的字段）。"""
    out = []
    for name, quote, period in sources:
        x = src(name, quote)
        x.update(access_category="unknown", ai_category="unknown", verification="none", evidence_scope="none",
                 sample_period=period, access_evidence=None, urls=[])
        out.append(x)
    return {"data_sources": out, "sample_limitations": []}


def run_cps_series() -> bool:
    """新功能：CPS 按调查系列合并（正例和反例）。基线里没有 CPS，所以基线不变不能证明这部分正确，要靠这些测试。"""
    ok_all = True
    print("\nCPS 调查系列（新功能）")
    cps = [src("May 1978 Current Population Survey", "We use data from the May 1978 Current Population Survey."),
           src("May Current Population Survey", "The data are from the May Current Population Survey for 1973, 1976, 1977, and 1978."),
           src("CPS Outgoing Rotation Groups", "We use the Outgoing Rotation Groups of the Current Population Survey (CPS ORG)."),
           src("CPS ASEC", "Income data come from the Annual Social and Economic Supplement of the Current Population Survey (CPS ASEC).")]
    keys = {step3.canonical_key(x)[0] for x in cps}
    cases = [("【正例】月度 CPS（带年份 / 不带年份）、ORG、ASEC → 同一个系列", len(keys) == 1)]
    k_cps = step3.canonical_key(cps[0])[0]
    others = [("American Community Survey", src("American Community Survey", "We use the 2010-2015 American Community Survey (ACS).")),
              ("Current Employment Statistics", src("Current Employment Statistics", "Payroll data come from the Current Employment Statistics (CES) program.")),
              ("美国 2010 年人口普查", src("2010 U.S. Census", "County population comes from the 2010 U.S. Census.")),
              ("另一种含义的 CPS（Child Protective Services）",
               src("CPS reports", "Child maltreatment reports to Child Protective Services (CPS) come from NCANDS.")),
              ("只写缩写 CPS、看不出是哪种 CPS → 不认定（宁可分开）", src("CPS data", "We use CPS data for the analysis."))]
    for label, x in others:
        cases.append((f"【反例】CPS ≠ {label}", step3.canonical_key(x)[0] != k_cps))
    cases.append(("【反例】Child Protective Services 不会得到 CPS 的数据库提示", step2.database_hint(others[3][1]) is None))

    merged = step3.merge_reports([
        ("PaperA", report_with([("May 1978 Current Population Survey", "We use data from the May 1978 Current Population Survey.", "1978")])),
        ("PaperB", report_with([("CPS ASEC", "Income data come from the Annual Social and Economic Supplement of the Current Population Survey (CPS ASEC).", "2010–2019"),
                                ("CPS Outgoing Rotation Groups", "We use the Outgoing Rotation Groups of the Current Population Survey (CPS ORG).", "2005–2019")])),
    ])
    g = next(m for m in merged if m["key"].startswith("gov_public_micro"))
    text = step3.format_report(merged)
    cases += [
        ("【报告】合并为一组，组名表明是“系列”", "series" in g["display"]),
        ("【报告】按论文计数：2 篇论文（PaperB 有两个部分，不算 2 篇）", g["n_papers"] == 2 and "(used by 2 papers)" in text),
        ("【报告】同一篇论文的 ASEC 和 ORG 各占一行，不被合并成一条", sorted(u["src"]["name"] for u in g["uses"] if u["paper"] == "PaperB")
         == ["CPS ASEC", "CPS Outgoing Rotation Groups"]),
        # 2026-11-06 第二阶段：期间那一行加上了形态和核实状态（“1978（单年，…；PaperA）”），改为检查年份和论文在同一行
        ("【报告】报告中保留每个部分的原始名称和年份",
         all(x in text for x in ["May 1978 Current Population Survey", "CPS ASEC", "CPS Outgoing Rotation Groups"])
         and all(any(ln.strip().startswith(f"- {y} (") and f"; {p})" in ln for ln in text.splitlines())
                 for y, p in [("1978", "PaperA"), ("2010–2019", "PaperB"), ("2005–2019", "PaperB")])),
        ("【报告】提示里写明同一系列包含多个部分、请按原始名称核对", "check each paper's original name" in text),
    ]
    for name, ok in cases:
        ok_all &= ok
        print(f"  {'✓' if ok else '✗'}  {name}")
    return ok_all


def run_census_country() -> bool:
    """人口普查跨国误合并的防护：只有原文写明中国时，才归到“人口普查（中国）”这一组。"""
    ok_all = True
    print("\n人口普查：跨国误合并的防护")
    china = "Population census / 1% population sample survey"   # 2026-11-06：清单名称改为英文
    # 基线中真实出现过的中国人口普查说法：收紧后仍要认出来
    cn = [src("2015 Population Census of China", "Internal migration is measured with the 2015 Population Census of China."),
          src("population census in China", "Two migration measures are computed from population and death counts in the population census in China.",
              provider="National Bureau of Statistics (NBS) of China"),
          src("population census in China", "the individual-level samples are random 1% and 20% draws from the 2000 and 2005 censuses respectively",
              provider="National Bureau of Statistics (NBS) of China")]
    us = [src("2010 U.S. Census", "County population comes from the 2010 U.S. Census."),
          src("Decennial Census", "Tract characteristics are from the 2000 Decennial Census of the United States."),
          src("Population Census of Indonesia", "We use the 2010 Population Census of Indonesia.")]
    hint = lambda x: (step2.database_hint(x) or {}).get("name")
    cases = [(f"中国：{x['name']} → 人口普查（中国）", hint(x) == china) for x in cn]
    cases += [(f"其他国家：{x['name']} → 不归到中国人口普查", hint(x) != china) for x in us]
    keys_cn = {step3.canonical_key(x)[0] for x in cn}
    cases += [("中国的三种说法合并为一组", len(keys_cn) == 1),
              ("美国、印尼的普查和中国的普查不在同一组", all(step3.canonical_key(x)[0] not in keys_cn for x in us)),
              ("没写国家（“the 2010 Population Census”）→ 不认定为中国普查，宁可分开（基线 li2015 因此失去提示）",
               hint(src("Population data", "Population figures come from the 2010 Population Census.")) != china)]
    for name, ok in cases:
        ok_all &= ok
        print(f"  {'✓' if ok else '✗'}  {name}")
    return ok_all


def run_merge_choices() -> bool:
    """合并时的证据选择：同一篇论文在同一组里出现多次时保留证据更强的那条；样本受限说法归到对应的数据。"""
    ok_all = True
    print("\n合并时的证据选择")

    def use(paper, cat, scope="none", period=None, name="x"):
        return {"paper": paper, "src": {"name": name, "access_category": cat, "evidence_scope": scope,
                                        "sample_period": period}}
    kept = step3.collapse_by_paper([use("a", "unknown", period="2001–2005", name="first"),
                                    use("a", "restricted", scope="direct", name="second"),
                                    use("b", "unknown", name="b")])
    by_paper = {u["paper"]: u["src"]["name"] for u in kept}
    cases = [("有已确认分类的那条优先于未确认（即使未确认那条有样本期间）", by_paper.get("a") == "second"),
             ("不同论文各保留一条", sorted(by_paper) == ["a", "b"])]
    kept = step3.collapse_by_paper([use("a", "unknown", name="first"), use("a", "unknown", name="second")])
    cases.append(("证据一样强时保留先出现的那条（结果稳定，不随机）", kept[0]["src"]["name"] == "first"))

    src = {"name": "Urban Household Survey (UHS)", "source_evidence": {"quote": "Our data come from the UHS", "page": 3},
           "access_evidence": {"quote": "the data are only available to us for 2002 to 2009", "page": 3, "verified": True}}
    lims = [{"quote": "UHS data for 2010 are missing for most cities", "page": 7},    # 点名了 UHS
            {"quote": "Weather records before 2000 are incomplete", "page": 5},       # 别的数据、别的页
            {"quote": "Some counties are dropped because of missing values", "page": 3}]  # 同一页
    rel = step3.related_limitations(src, lims)
    quotes = [x["quote"] for x in rel]
    # 2026-11-06 评审决定：样本限制不再按名称自动归属，全部留在论文级（以前点名了 UHS 的限制会归到 UHS）
    cases += [("点名了这个数据的限制 → 也不自动归到它（留在论文级）", lims[0]["quote"] not in quotes),
              ("只是和来源说明同一页、没点名 → 不归到它（2026-11-06 起，同页不能证明归属）", lims[2]["quote"] not in quotes),
              ("别的数据、别的页 → 不归到它", lims[1]["quote"] not in quotes),
              ("获取条件证据含“only … 年份”、但证据未确认针对这个数据 → 不归到它", "the data are only available to us for 2002 to 2009" not in quotes)]
    rel2 = step3.related_limitations({**src, "verification": "verified"}, lims)
    cases.append(("获取条件证据已确认针对这个数据、且含“only … 年份” → 算作它的覆盖限制",
                  "the data are only available to us for 2002 to 2009" in [x["quote"] for x in rel2]))
    for name, ok in cases:
        ok_all &= ok
        print(f"  {'✓' if ok else '✗'}  {name}")
    return ok_all


def run_main_first() -> bool:
    """2026-11-18：报告开头“按论文列出主要数据”。只改显示位置，不改核对结果。"""
    print("\n主要数据前置（main_data_markdown）")
    ok_ev = lambda q, p=3: {"quote": q, "page": p, "verified": True}
    bad_ev = lambda q, p=5: {"quote": q, "page": p, "verified": False}
    used_main = {"name": "Firm Payroll Records", "role": "main", "source_evidence": ok_ev("Our data come from Firm Payroll Records.")}
    used_rob = {"name": "Weather Station Data", "role": "robustness", "source_evidence": ok_ev("Weather data come from stations.")}
    unver = {"name": "Call Center Output", "role": "main", "mention_reason": "source_unverified",
             "source_evidence": bad_ev("Our output data come from Acme.", 5)}
    var = {"name": "Price Index", "role": "main", "mention_reason": "possible_variable",
           "source_evidence": ok_ev("We use the price index for each province.", 2)}
    usage = {"name": "Economic Census", "role": "main", "usage": "analyzed", "source_evidence": ok_ev("Based on the Economic Census.", 14),
             "usage_evidence": bad_ev("We compute averages using the Economic Census.", 29)}
    side = {"name": "Side Note Data", "role": "robustness", "mention_reason": "possible_variable", "source_evidence": ok_ev("x y z")}
    used_main["also_controls"] = True
    ctl = {"name": "City Statistical Yearbook", "role": "control", "source_evidence": ok_ev("City controls come from the City Statistical Yearbook.", 6)}
    rep = {"data_sources": [used_main, used_rob, ctl], "usage_pending": [usage], "other_mentions": [unver, var, side], "referenced": []}
    old = {"data_sources": [{"name": "Old Survey", "source_evidence": ok_ev("We use the Old Survey.")}], "other_mentions": []}
    official = {step3.canonical_key(used_main)[0]: {"result": {"outcome": "found", "finding": {
        "channel": "apply_to_provider", "url": "https://data.example.gov/apply", "pending": ["version"], "evidence_source": "official_page"}}}}
    text = step3.main_data_markdown([("P1", rep), ("Old", old)], official)
    p1 = text.split("## P1")[1].split("## Old")[0]
    main_part, todo = p1.split("To verify")[0], p1.split("To verify")[1]
    cases = [
        ("主要数据（role=main、已进入本文使用）排在论文下，附核对过的原文和页码", "**Firm Payroll Records**" in main_part and "p. 3: “Our data come from Firm Payroll Records.”" in main_part),
        ("同一份数据也提供控制变量：留在主要数据并注明", "**Firm Payroll Records** _(also provides control variables)_" in main_part),
        ("只提供控制变量的数据放进辅助数据，附原文页码，不在主要数据和其他数据里",
         "**Auxiliary data (control variables only)**\n- **City Statistical Yearbook** — p. 6: “City controls come from the City Statistical Yearbook.”" in p1
         and "City Statistical Yearbook" not in main_part and "[control variables]" not in p1),
        ("稳健性 / 补充数据不进主要数据，在下面按用途列出并附原文页码", "Weather Station Data" not in main_part
         and "- [robustness check] **Weather Station Data** — p. 3: “Weather data come from stations.”" in p1),
        ("主要数据旁写官网状态（渠道、网站、待核对项）", "apply to the data provider (data.example.gov); years / version used by the paper not named on the page — pending" in main_part),
        ("证据不足的主要数据候选放进“待核对”，三种原因各自说明缺什么", all(n in todo for n in ("Call Center Output", "Price Index", "Economic Census"))
         and "was not found in the PDF (the model pointed to p. 5)" in todo and "found no source wording" in todo
         and "analyses these data was not found in the PDF (the model pointed to p. 29)" in todo),
        ("没通过核对的引用不显示原文；通过的照常显示", "Our output data come from Acme." not in todo and "We use the price index for each province." in todo),
        ("非主要数据的其他提及不进“待核对”", "Side Note Data" not in todo),
        ("没有官网结果的主要数据写 not checked（例：待核对候选不跑官网核查）",
         step3.main_data_markdown([("P", {"data_sources": [used_main], "other_mentions": []})], {}).count("not checked") == 1),
        ("旧结果没有 role 字段：全部列为主要数据并注明", "older result without a role field" in text and "**Old Survey**" in text),
    ]
    q = "We use the restricted data files of the Panel Survey of Things."
    raw = {"data_sources": [{"name": "Panel Survey of Things", "role": "main", "kind": "dataset", "provider": None, "unit": None,
                             "sample_period": None, "period_evidence": None, "access_category": "unknown",
                             "source_evidence": {"quote": q, "page": 1}, "access_evidence": None, "access_applies_to": None,
                             "usage": "analyzed", "usage_evidence": {"quote": q, "page": 1}, "period_form": None, "period_years": None}],
           "sample_limitations": [], "availability_statement": None}
    full = step3.report_markdown([("P", step2.verify_result([f"Data. {q} End."], raw))])
    cases.append(("完整报告以主要数据一览开头，后面仍是合并摘要",
                  full.startswith("# Main data by paper") and "**Panel Survey of Things** — p. 1" in full
                  and full.index("# Main data by paper") < full.index("# Data source summary")))
    for name, ok in cases:
        print(f"  {'✓' if ok else '✗'}  {name}")
    return all(ok for _, ok in cases)


if __name__ == "__main__":
    raise SystemExit(0 if (run() & run_main_first()) else 1)
