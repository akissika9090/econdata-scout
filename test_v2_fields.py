"""
V2（2026-11-17）论文侧新字段的测试：版本（version）与获取细分（渠道｜资格｜使用限制）。
检查最终报告文字和核对后的字段。不联网、不调用 AI：模型的提取结果是固定内容，只用合成文本。

要点：
- 旧结果没有新字段 → 不显示、不推断（与 V1 报告相同）
- 版本必须逐字出现在核对通过的原文里，才显示为“已定位”
- 渠道 / 资格只在获取条件核对通过时显示；渠道必须与已核对的分类一致
- 使用限制必须逐字出现在条件原文里

运行：
    python test_v2_fields.py
"""

import copy

import step2_ai_extract as step2
import step3_merge as step3

failures = 0


def check(name, ok, detail=""):
    global failures
    print(f"{'✓' if ok else '✗'}  {name}" + ("" if ok else f"\n     相关内容：{str(detail)[:500]}"))
    if not ok:
        failures += 1


def ev(quote, page=1):
    return {"quote": quote, "page": page}


def source(name, source_quote, cat="unknown", access_quote=None, **v2):
    s = {"name": name, "role": "main", "kind": "dataset", "provider": None, "unit": None,
         "sample_period": None, "period_evidence": None,
         "access_category": cat, "source_evidence": ev(source_quote),
         "access_evidence": ev(access_quote) if access_quote else None,
         "access_applies_to": "whole" if cat != "unknown" else None,
         "usage": "analyzed", "usage_evidence": ev(source_quote), "period_form": None, "period_years": None}
    s.update(v2)
    return s


def run(pages, sources):
    raw = {"data_sources": sources, "sample_limitations": [], "availability_statement": None}
    rep = step2.verify_result(pages, copy.deepcopy(raw))
    return step3.report_markdown([("P", rep)]), rep


def section(text, name):
    return next((p for p in text.split("\n## ") if p.startswith(name)), "")


SRC = "We use the restricted data files of the Panel Survey of Things."
ACC = "The Panel Survey of Things restricted data files are available to approved researchers only at a Research Data Center."
PAGES = [f"Data. {SRC} {ACC} End."]

# ---- 1. 完整的新字段：版本已定位；渠道、资格、限制都显示 ----
text, rep = run(PAGES, [source("Panel Survey of Things", SRC, "restricted", ACC,
                               version="restricted data files", version_evidence=ev(SRC),
                               access_channel="apply_to_provider", eligibility="researchers",
                               use_restrictions=["only at a Research Data Center"])])
sec = section(text, "Panel Survey of Things")
x = rep["data_sources"][0]
check("1. 版本逐字出现在核对通过的原文中 → 显示为已定位，附页码和原文",
      x["version_verified"] is True and "Version / file used in this paper: restricted data files (source text located)" in sec, sec)
check("1. 渠道与已核对的分类（受限）一致 → 显示“apply to the data provider”；资格显示“researchers can apply”",
      "apply to the data provider" in sec and "researchers can apply" in sec, sec)
check("1. 使用限制逐字出现在条件原文 → 显示", "restriction: only at a Research Data Center" in sec, sec)
check("1. 原有的 V1 分类不变（受限，已验证）", x["access_category"] == "restricted" and x["verification"] == "verified", x["verification"])

# ---- 2. 版本写法不在原文里 → 标为未核实，不当作已定位 ----
text, rep = run(PAGES, [source("Panel Survey of Things", SRC, "restricted", ACC,
                               version="confidential microdata", version_evidence=ev(SRC),
                               access_channel="apply_to_provider", eligibility="not_stated", use_restrictions=[])])
sec = section(text, "Panel Survey of Things")
check("2. 版本写法没有逐字出现 → 显示为“模型的写法，未定位”",
      rep["data_sources"][0]["version_verified"] is False and "model's wording; not found verbatim" in sec, sec)

# ---- 3. 渠道与已核对的分类不一致 → 不显示渠道，记 rule_note ----
text, rep = run(PAGES, [source("Panel Survey of Things", SRC, "restricted", ACC,
                               version=None, version_evidence=None,
                               access_channel="public_download", eligibility="not_stated", use_restrictions=[])])
sec = section(text, "Panel Survey of Things")
x = rep["data_sources"][0]
check("3. 渠道“公开下载”与已核对的“受限”不一致 → 不显示渠道，留下说明",
      x["access_channel_shown"] is None and "public download" not in sec
      and any("不一致" in n for n in x["rule_notes"]), (sec, x["rule_notes"]))

# ---- 4. 条件核对没通过 → 渠道、资格、限制都不显示（不能借细分字段绕过核对） ----
UNNAMED = "These files are available only at a Research Data Center."
pages4 = [f"Data. {SRC} We thank the survey team. {UNNAMED} End."]
text, rep = run(pages4, [source("Panel Survey of Things", SRC, "restricted", UNNAMED,
                                version=None, version_evidence=None, access_channel="apply_to_provider",
                                eligibility="researchers", use_restrictions=["only at a Research Data Center"])])
sec = section(text, "Panel Survey of Things")
x = rep["data_sources"][0]
check("4. 条件句没通过核对（指代链被打断）→ 细分字段都不显示，最终分类未确认",
      x["verification"] != "verified" and x["access_category"] == "unknown"
      and "Access details in the paper" not in sec, (x["verification"], sec))

# ---- 5. 使用限制不在条件原文里 → 丢弃 ----
text, rep = run(PAGES, [source("Panel Survey of Things", SRC, "restricted", ACC,
                               version=None, version_evidence=None, access_channel="apply_to_provider",
                               eligibility="not_stated", use_restrictions=["requires a signed confidentiality agreement"])])
sec = section(text, "Panel Survey of Things")
x = rep["data_sources"][0]
check("5. 编造的使用限制（原文没有）→ 不显示，留下说明",
      x["use_restrictions_shown"] == [] and "confidentiality agreement" not in sec
      and any("使用限制" in n for n in x["rule_notes"]), (sec, x["rule_notes"]))

# ---- 6. 渠道写 not_stated（例如只写了“不公开”）→ 不显示渠道，分类照常 ----
NOTPUB = "The Panel Survey of Things data are not available to the public."
pages6 = [f"Data. {SRC} {NOTPUB} End."]
text, rep = run(pages6, [source("Panel Survey of Things", SRC, "restricted", NOTPUB,
                                version=None, version_evidence=None, access_channel="not_stated",
                                eligibility="not_stated", use_restrictions=[])])
sec = section(text, "Panel Survey of Things")
x = rep["data_sources"][0]
check("6. 原文只写“不公开”、没写渠道 → 分类受限已验证，不显示细分",
      x["verification"] == "verified" and x["access_channel_shown"] is None and "Access details in the paper" not in sec, sec)

# ---- 6b. 新结果但原文没写版本 → version_verified 为 None（不适用），不是 False ----
text, rep = run(PAGES, [source("Panel Survey of Things", SRC, "restricted", ACC,
                               version=None, version_evidence=None, access_channel="not_stated",
                               eligibility="not_stated", use_restrictions=[])])
check("6b. 原文没写版本 → 版本核对记为不适用（None），不显示版本",
      rep["data_sources"][0]["version_verified"] is None and "Version / file used" not in section(text, "Panel Survey of Things"),
      rep["data_sources"][0]["version_verified"])

# ---- 7. 旧结果（没有新字段）→ 不显示新内容，不推断 ----
old = source("Panel Survey of Things", SRC, "restricted", ACC)
text, rep = run(PAGES, [old])
sec = section(text, "Panel Survey of Things")
x = rep["data_sources"][0]
check("7. 旧结果没有新字段 → 版本为空、不显示版本和细分",
      x["version"] is None and x["version_verified"] is None
      and "Version / file used" not in sec and "Access details in the paper" not in sec, sec)

# ---- 9. 弯引号 / 撇号（v2.5c，2026-11-18）：PDF 存 ’ “ ”、模型抄成 ' " 时仍算同一句；改了字的仍不通过 ----
import step1_pdf_evidence as step1
CURLY = "Our data on worker productivity come from Acme International, China\u2019s largest travel agency, and we call it \u201ctimeclock\u201d data."
STRAIGHT = "Our data on worker productivity come from Acme International, China's largest travel agency, and we call it \"timeclock\" data."
check("9a. 原文弯引号、引文直引号 → 严格核对和宽松核对都通过",
      step1.verify_quote([CURLY], STRAIGHT, 1) and step1.verify_quote_tolerant([CURLY], STRAIGHT, 1))
check("9b. 反过来（原文直引号、引文弯引号）也通过", step1.verify_quote([STRAIGHT], CURLY, 1))
check("9c. 只是引号相同、改了一个词 → 仍不通过",
      not step1.verify_quote([CURLY], STRAIGHT.replace("largest", "smallest"), 1))
check("9d. 撇号不能被省略：原文 China’s、引文 Chinas → 不通过", not step1.verify_quote([CURLY], STRAIGHT.replace("China's", "Chinas"), 1))
text, rep = run([f"Data. {CURLY} End."], [source("Acme worker productivity data", STRAIGHT)])
used9 = [d["name"] for d in rep["data_sources"]]
other9 = [d["name"] for d in rep["other_mentions"]]
check("9e. 端到端：来源引文只差撇号写法 → 进入“本文使用”，不再移到其他提及",
      used9 == ["Acme worker productivity data"] and not other9, (used9, other9))

print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
