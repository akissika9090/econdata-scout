"""V3 展示ページのテスト（2026-11-23）。API・ネットワーク不要。
① 代表例の文言が保存済みの実行結果（demo/outputs/）にそのまま存在する（ツールの出力を加工していない）
② site/index.html が build_site.py の出力と一致する（ページを手で書き換えていない）
③ ページに評価の数字を載せていない（本人の方針：評価はリポジトリの文書へリンク）
    python3 test_site.py"""
import os, re, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "site"))
import build_site as bs

fails = 0
def check(name, ok, info=""):
    global fails
    fails += not ok
    print(("✓ " if ok else "✗ ") + name + ("" if ok else f"\n    {info}"))

exs = bs.examples()
check("代表例は 3 件（カタログ 2、公式サイト確認 1）", [e["kind"] for e in exs] == ["catalog", "catalog", "official"], [e["kind"] for e in exs])
bad = bs.check(exs)
check("① 代表例の文言（論文名、データ名、引用、結論、次にやること、公式サイトの原文、入口）が保存結果にそのまま存在", not bad, bad)
check("① 公式サイトの原文は入れ子の引用符を含めて全文（行末まで）", exs[2]["access_quote"].endswith("可以实现裁判文书下载。"), exs[2]["access_quote"])
built = bs.page(exs)
check("公式サイトの原文はそのまま残し、英語の参考訳はツールの出力ではないと明記して添える",
      exs[2]["access_quote"] in bs.REFERENCE_EN and "英語の参考訳（ツールの出力ではありません）" in built
      and bs.html.escape(exs[2]["access_quote"]) in built)
current = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
check("② site/index.html は build_site.py の出力と一致（python3 site/build_site.py で再生成）", built == current)
text = re.sub(r"<[^>]+>", " ", built)
check("③ 評価の数字（○/○ 件・達成・誤り○件）をページに載せていない", not re.search(r"\d+\s*/\s*\d+|達成|誤り\s*\d", text),
      re.findall(r".{0,20}(?:\d+\s*/\s*\d+|達成|誤り\s*\d).{0,20}", text)[:3])
check("ページの <title> と、評価文書へのリンクがある", "<title>EconData Scout</title>" in built and "docs/access_catalog_ja.md" in built)
print("\n全部通过" if not fails else f"\n{fails} 项失败")
sys.exit(1 if fails else 0)
