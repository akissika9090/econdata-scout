"""
最终报告的测试（K1 适用范围未记录、G1 获取渠道与提供机构）。只检查最终报告文字，不调用 API。
只用合成文本，不需要 key、网络或论文 PDF（默认公开测试）。用真实保存结果的检查在 test_final_report_papers.py（可选）。

    python test_final_report.py
"""
import copy

import step2_ai_extract as step2
import step3_merge as step3

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("✓  " if ok else "✗  ") + name)
    if not ok:
        failures += 1
        print("     报告相关内容：" + str(detail)[:900])


def ev(quote, page=1):
    return {"quote": quote, "page": page}


def legacy(name, quote, cat="unknown", access_quote=None, provider=None, period=None):
    """旧格式记录：没有 access_applies_to、usage 等新字段。"""
    return {"name": name, "role": "main", "kind": "dataset", "provider": provider, "unit": None,
            "sample_period": period, "period_evidence": ev(quote) if period else None, "access_category": cat,
            "source_evidence": ev(quote), "access_evidence": ev(access_quote) if access_quote else None}


def report(pages, sources, paper="P"):
    rep = step2.verify_result(pages, copy.deepcopy({"data_sources": sources, "sample_limitations": [],
                                                     "availability_statement": None}))
    return step3.report_markdown([(paper, rep)]), rep


def section(text, title):
    return text.split(f"## {title}", 1)[1].split("\n## ", 1)[0] if f"## {title}" in text else ""


# ======== K1：旧记录缺少适用范围 ========
print("K1：适用范围未记录")
Q_LFS = "The present study utilizes the public-use files of the Canadian LFS (July 2001–June 2015)."
text, rep = report([f"Data. {Q_LFS} End."], [legacy("Canadian LFS", Q_LFS, "public", Q_LFS)])
src, sec = rep["data_sources"][0], section(text, "Canadian LFS")
check("K1-1. 旧记录：适用范围记为未记录；分类和核对状态保留（公开、已验证）",
      src["access_scope"] == "not_recorded" and src["access_category"] == "public" and src["verification"] == "verified",
      (src["access_scope"], src["access_category"], src["verification"]))
# 2026-11-06 英文报告：原文本身可能含 publicly available（如 WorldClim），所以检查“获取”主句和各篇论文的标签
check("K1-2. 主句不再断言整个数据公开：没有“可以公开获取”", "**Access: publicly available" not in sec and "[public]" not in sec, sec)
check("K1-3. 主句写“原记录分类：公开；适用范围未记录”", "**Access: original record category: public; scope not recorded**" in sec, sec)
check("K1-4. 结论下方显示条件原文（含 public-use files）和页码", "Source text (P p. 1): “" in sec and "public-use files" in sec, sec)
check("K1-5. 各篇论文一行也只写原记录分类，不写“【公开】”",
      "[original record category: public; scope not recorded]" in sec and "[public]" not in sec, sec)

Q_WC = "To project the cost of climate change on mortality rates in China, we employ the publicly available WorldClim-Global Climate Data."
text, _ = report([f"Data. {Q_WC} End."], [legacy("WorldClim-Global Climate Data", Q_WC, "public", Q_WC)])
sec = section(text, "WorldClim")
check("K1-6. WorldClim 同样处理，不加例外：没有“可以公开获取”，显示适用范围未记录和原文",
      "**Access: publicly available" not in sec and "[public]" not in sec and "scope not recorded" in sec
      and "publicly available WorldClim" in sec, sec)

new = legacy("Canadian LFS", Q_LFS, "public", Q_LFS)
new.update({"access_applies_to": "whole", "usage": "analyzed", "usage_evidence": ev(Q_LFS), "period_form": None, "period_years": None})
text, _ = report([f"Data. {Q_LFS} End."], [new])
check("K1-7. 对照：新结果明确给出 whole → 仍写“可以公开获取”（K1 只影响没有记录范围的旧结果）",
      "**Access: publicly available**" in section(text, "Canadian LFS"), section(text, "Canadian LFS"))

part = copy.deepcopy(new)
part["access_applies_to"] = "public-use files"
text, _ = report([f"Data. {Q_LFS} End."], [part])
check("K1-8. 对照：新结果给出部分范围 → “可以公开获取（适用于：public-use files）”",
      "publicly available (applies to: public-use files)" in text, section(text, "Canadian LFS"))

# ======== G1：获取渠道和提供机构 ========
print("\nG1：获取渠道与提供机构")
Q_URL = "Information in the figure is from the Data Center for Resources and Environmental Sciences, Chinese Academy of Sciences (RESDC; http://www.resdc.cn)."
text, _ = report([f"Data. {Q_URL} End."], [legacy("RESDC climate zones data", Q_URL,
                                                   provider="Data Center for Resources and Environmental Sciences, Chinese Academy of Sciences")])
sec = section(text, "RESDC")
# 2026-11-06：网址只是从原文机械提取，标题由“论文记载的获取渠道”改为“论文原文中的链接”，不声称是获取渠道
check("G1-1. 原文网址显示为“论文原文中的链接”（不声称是获取渠道），附原文和页码，并说明没有核实",
      "Link in the paper's text: http://www.resdc.cn" in sec and "not claimed to be an access channel" in sec and "Access channel recorded in the paper: http" not in sec and "p. 1: “Information in the figure" in sec
      and "has not checked" in sec, sec)
check("G1-2. 网址不进入获取条件结论（不再写“原文给出了网址，需要打开确认”），也不标成官方入口",
      "the paper gives a URL" not in sec and "Official entry point:" not in sec, sec)
check("G1-3. 提供机构单独一行，注明不是获取渠道", "Provider (extracted by the model; not an access channel): Data Center" in sec, sec)

Q_NB = "I merge the LFS data with three-digit industry energy intensity from NBER Productivity Database."
text, _ = report([f"Data. {Q_NB} End."], [legacy("NBER Productivity Database", Q_NB, provider="NBER")])
sec = section(text, "NBER")
check("G1-4. 只有机构名时，机构不会成为渠道：渠道写“当前提取结果未记录获取渠道”",
      "Access channel recorded in the paper: not recorded in the current extraction results" in sec and "Provider (extracted by the model; not an access channel): NBER" in sec, sec)
check("G1-5. 没有渠道时不写成论文一定没说明", "this does not mean the paper does not describe one" in sec, sec)

Q_TC = "Tabulations from the IRS's Taxpayer Compliance Measurement Program (TCMP) indicate that one-third of recipients were ineligible."
text, _ = report([f"Data. {Q_TC} End."], [legacy("IRS Taxpayer Compliance Measurement Program (TCMP)", Q_TC,
                                                  provider="Internal Revenue Service")])
sec = section(text, "IRS Taxpayer")
check("G1-6. 模型把 IRS 写成全称：机构信息保留，并附来源句原文供对照（不自动丢弃）",
      "Internal Revenue Service (this wording does not appear verbatim in the source sentence" in sec and "IRS's Taxpayer Compliance" in sec, sec)

Q_AC = "The UHS household microdata are confidential and were provided under a data use agreement with the NBS."
text, _ = report([f"Data. {Q_AC} End."], [legacy("UHS household microdata", Q_AC, "restricted", Q_AC)])
sec = text   # 显示名会按数据库清单换成中文名，这里检查整份报告
check("G1-7. 渠道信息不改变获取分类：受限条件照常（原记录分类），条件原文照常显示",
      "original record category: restricted; scope not recorded" in sec and "data use agreement" in sec, sec)

# ======== 报告整体 ========
print("\n报告整体")
text, _ = report([f"Data. {Q_URL} {Q_NB} End."], [legacy("RESDC climate zones data", Q_URL), legacy("NBER Productivity Database", Q_NB)])
check("R-1. 待核查事项只在报告末尾出现一次", text.count("## Items to verify") == 1 and text.rstrip().split("\n## ")[-1].startswith("Items to verify"),
      text[-600:])
text0, _ = report(["Data. Nothing here. End."], [])
check("R-3. 没有任何数据源时不列待核查事项", "Items to verify" not in text0, text0)
check("R-2. 不新增“数据可用性说明”章节", "availability statement" not in text and "Data availability" not in text, text)

print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
