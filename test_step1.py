"""
回归测试：每次修改 step1_pdf_evidence.py 之后运行，确认三篇测试论文的结果没有变差。

准备：在项目文件夹里建一个 papers 文件夹，把三篇论文按下面的文件名放进去
（论文 PDF 是学校获取的，不要上传到 GitHub，记得把 papers/ 写进 .gitignore）。
运行：
    python test_step1.py
"""
from test_support import require_materials

require_materials(['papers/deng2020.pdf', 'papers/li2015.pdf', 'papers/mobarak2021.pdf', 'papers/teng2026.pdf', 'papers/yin2025.pdf', 'papers/yu2019.pdf', 'papers/yu_zhang2021.pdf'], "test_step1")


import step1_pdf_evidence as s

# 每篇论文：候选段落里“必须出现”的内容，以及引用核查的测试（引用, 页码, 应该存在吗）
CASES = {
    "papers/deng2020.pdf": {  # Deng et al. (2020) J. Environ. Manage. 275, 111224
        "must_find": ["Urban Household Survey", "not available to the public",
                      "Meteorological Information Center"],
        "quotes": [
            ("Since the dataset is not available to the public, we can only get the data from 2002 to 2009.", 3, True),
            ("The dataset is publicly available on the NBS website.", 3, False),
        ],
    },
    "papers/yu2019.pdf": {  # Yu, Lei & Wang (2019) JEEM 96, 195-212
        "must_find": ["DSPs", "CMDSS", "WorldClim", "Energy Statistical Yearbook",
                      "National Bureau of Statistics", "Urban Household Survey"],
        "quotes": [
            # PDF 里的年份写成 '2004e2012'（短横线被存成了 e），AI 引用时会写成 2004–2012
            ("we obtained a panel of the number of ACs per 100 households for 30 provinces during 2004–2012", 5, True),
            ("we obtained a panel of the number of ACs per 100 households for 30 provinces during 2004–2015", 5, False),
        ],
    },
    "papers/yu_zhang2021.pdf": {  # Yu & Zhang (2021) Energy Economics, 低碳城市试点
        "must_find": ["NDRC", "China City Statistical Yearbook", "Due to data availability"],
        "quotes": [
            # PDF 文字层丢了空格、用了连字符号 'ﬁ'，这句曾被误判为不存在
            ("Our final sample comprises a panel dataset of 251 cities over the period 2003–2018.", 4, True),
            ("The data are mainly obtained from China City Statistical Yearbook (2004–2019).", 4, True),
            ("The data are publicly available from the NDRC website.", 4, False),
        ],
    },
    "papers/mobarak2021.pdf": {  # CEPR 工作论文：“2 Data and Measurement” 的小节、附录、粘连的脚注编号
        "must_find": ["Population Census", "CLDS", "Van Donkelaar", "Electric Power Yearbooks", "MERRA-2",
                      "Regional Statistical Yearbook", "UC Davis", "General Social Survey", "Xitai"],
        "quotes": [],
    },
    "papers/li2015.pdf": {  # 大学工作论文：每行一个块；天气数据写在附录 A.3
        "must_find": ["special agreement", "Ministry of Environmental Protection",
                      "worldweatheronline", "tianqi"],
        "must_not_find": ["data correlate tightly with those in the daily dataset. data"],
        "quotes": [],
    },
    "papers/yin2025.pdf": {  # Journal Pre-proof：每行一个块
        "must_find": ["China Stock Market and Accounting Research", "China City Statistical Yearbook (2014–2023)",
                      "Data will be made available on request"],
        "quotes": [],
    },
    "papers/teng2026.pdf": {  # Teng et al. (2026) The Energy Journal 47(2), SAGE 出版
        "must_find": ["China Health and Nutrition Survey", "publicly released",
                      "National Meteorological Information Center",
                      "available upon a reasonable request"],
        # 不应该出现在候选里的内容（之前的 bug：方法章节、参考文献被当成数据章节）
        "must_not_find": ["utility- maximizing households", "Econometrica 52"],
        "quotes": [
            ("Further information about the data is available upon a reasonable request.", 14, True),
        ],
    },
}


def run() -> bool:
    all_ok = True
    for path, case in CASES.items():
        try:
            pages, blocks = s.extract_pages(path)
        except Exception as e:
            print(f"✗ 打不开 {path}：{e}")
            all_ok = False
            continue
        passages = s.find_data_passages(blocks)
        found_text = s.normalize(" ".join(p["text"] for p in passages))
        print(f"\n{path}（候选 {len(passages)} 段）")
        for item in case["must_find"]:
            ok = item.lower() in found_text
            all_ok &= ok
            print(f"  {'✓' if ok else '✗ 没找到'}  {item}")
        for item in case.get("must_not_find", []):
            ok = item.lower() not in found_text
            all_ok &= ok
            print(f"  {'✓' if ok else '✗ 不该出现'}  不应包含：{item}")
        for quote, page, should_exist in case["quotes"]:
            ok = s.verify_quote(pages, quote, page) == should_exist
            all_ok &= ok
            label = "应存在" if should_exist else "应不存在"
            print(f"  {'✓' if ok else '✗ 判断错误'}  引用核查（{label}）：{quote[:60]}")
    all_ok &= run_quote_edge_cases()
    print("\n全部通过" if all_ok else "\n有测试失败，请检查上面的 ✗")
    return all_ok


def run_quote_edge_cases() -> bool:
    """verify_quote 的边界情况：这些引用在页面上“找得到”，但不能算作证据。
    之前的版本中，空字符串、纯年份、单个词都会核对通过。"""
    page = ("Our data come from the Urban Household Survey (UHS) since 1986. "
            "We use data over the period 2003–2018. The data are publicly available.")
    pages = [page]
    real = "Our data come from the Urban Household Survey (UHS) since 1986."
    cases = [
        ("真实的整句引用 → 通过", real, 1, True),
        ("换行、断词、大小写不同的真实引用 → 通过", "our data come from the Urban House-\nhold Survey (UHS)", 1, True),
        ("空引用 → 不通过", "", 1, False),
        ("只有空白 → 不通过", "   \n ", 1, False),
        ("只有年份 → 不通过", "2003–2018", 1, False),
        ("单个词 → 不通过", "data", 1, False),
        ("短语，压缩后不足 20 个字符 → 不通过", "publicly available", 1, False),
        ("引用不是文字（None）→ 不通过", None, 1, False),
        ("页码为 None → 不通过", real, None, False),
        ("页码是字符串 → 不通过", real, "1", False),
        ("页码是 True（Python 里 True == 1）→ 不通过", real, True, False),
        ("页码为 0 → 不通过", real, 0, False),
        ("页码超出范围 → 不通过", real, 2, False),
        ("真实的话，但页码写错 → 不通过", real, 2, False),
    ]
    ok_all = True
    print("\nverify_quote 边界情况")
    for name, quote, page_no, expected in cases:
        try:
            got = s.verify_quote(pages, quote, page_no)
        except Exception as e:   # 不允许因为异常输入而报错
            got = f"报错 {type(e).__name__}"
        ok = got == expected
        ok_all &= ok
        print(f"  {'✓' if ok else '✗'}  {name}" + ("" if ok else f"（实际：{got}）"))
    return ok_all


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
