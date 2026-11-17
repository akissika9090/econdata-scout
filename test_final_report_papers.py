"""
最终报告的可选论文测试：用真实保存结果和论文 PDF 检查最终报告（从 test_final_report.py 拆出）。
材料不随仓库发布；缺材料时报告 SKIPPED（退出码 77）。

    python test_final_report_papers.py
"""
import json

from test_support import require_materials

MATERIALS = ["results/yip2018_1105_105410_run1.json", "papers/yip2018.pdf",
             "results/teng2026_1104_235531_run1.json", "papers/teng2026.pdf"]
require_materials(MATERIALS, "test_final_report_papers")

import step1_pdf_evidence as step1   # noqa: E402
import step2_ai_extract as step2     # noqa: E402
import step3_merge as step3          # noqa: E402

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("✓  " if ok else "✗  ") + name)
    if not ok:
        failures += 1
        print("     报告相关内容：" + str(detail)[:900])


def section(text, title):
    return text.split(f"## {title}", 1)[1].split("\n## ", 1)[0] if f"## {title}" in text else ""


# ======== 真实保存结果 ========
print("\n真实保存结果")
j = json.load(open("results/yip2018_1105_105410_run1.json", encoding="utf-8"))
rep = step2.verify_result(step1.extract_pages("papers/yip2018.pdf")[0], j["ai_raw"])
text = step3.report_markdown([("yip2018", rep)])
sec = section(text, "Canadian LFS")
check("T-1. yip2018：Canadian LFS 不再写“可以公开获取”，显示原记录分类和 public-use files 原文",
      "**Access: publicly available" not in sec and "original record category: public; scope not recorded" in sec and "public-use" in sec, sec)
j = json.load(open("results/teng2026_1104_235531_run1.json", encoding="utf-8"))
rep = step2.verify_result(step1.extract_pages("papers/teng2026.pdf")[0], j["ai_raw"])
text = step3.report_markdown([("teng2026", rep)])
check("T-2. teng2026：已有的 RESDC 网址和原文显示为论文原文中的链接",
      "Link in the paper's text: http://www.resdc.cn" in text and "p. 17" in text, text[:1500])

print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
