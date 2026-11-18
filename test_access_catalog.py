"""入手経路カタログのテスト（合成データのみ、キー・ネットワーク・PDF 不要）。
目录身份规则的检查（不调模型，不联网）：名称越泛，结论越要依赖提供方、国家或版本等能确认身份的证据。
日本普查等外国数据用来检验这条通用原则，目录里没有任何“日本”专用规则。
    CATALOG=catalog_v2.json python3 experiments/catalog/test_catalog_identity.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import access_catalog as catalog

CASES = [
    # (说明, 提取出的数据源, 期望 entry_id, 期望用户结论)
    ("日本普查：提供方写明总务省统计局", {"name": "Population Census of Japan", "provider": "Statistics Bureau of Japan", "sample_period": "2015"}, None, "目录未收录"),
    ("日本普查：日文提供方", {"name": "国勢調査 (Population Census)", "provider": "総務省統計局", "sample_period": "2010"}, None, "目录未收录"),
    ("日本普查：只有泛称，没有提供方", {"name": "2015 Population Census", "provider": None, "sample_period": "2015"}, "IDENTITY-UNCONFIRMED", "线索"),
    ("Eurostat 普查（第二轮测试论文）", {"name": "Eurostat population census", "provider": "Eurostat", "sample_period": "2011"}, None, "目录未收录"),
    ("中国普查：泛称 + 统计局提供方", {"name": "population census", "provider": "National Bureau of Statistics", "sample_period": "2010"}, "CN-NBS-CENSUS", "线索"),   # 提供方即身份证据；没写汇总表 → 只给线索
    ("中国普查：第六次全国人口普查汇总表", {"name": "Tabulation on the Sixth National Population Census", "provider": None, "sample_period": "2010"}, "CN-NBS-CENSUS", "可获取（已核实）"),
    ("中国普查：名称带 China，但没说是汇总表", {"name": "China Census 2010", "provider": None, "sample_period": "2010"}, "CN-NBS-CENSUS", "线索"),
    ("日本气象厅数据（JMA）", {"name": "JMA meteorological observation data", "provider": "Japan Meteorological Agency", "sample_period": None}, None, "目录未收录"),
    ("韩国环境部空气质量", {"name": "air pollution data", "provider": "Ministry of Environment, Korea", "sample_period": None}, None, "目录未收录"),
    ("日本工业统计（泛称 industrial firm database）", {"name": "industrial firm database", "provider": "METI", "sample_period": "2010"}, None, "目录未收录"),
    ("中国工业企业数据库", {"name": "China Industrial Enterprise Database", "provider": None, "sample_period": "1998–2007"}, "CN-NBS-ASIE", "该版本获取方式未确认"),
    ("CSMAR", {"name": "CSMAR database", "provider": "CSMAR", "sample_period": "2010–2016"}, "CN-CSMAR", "订阅受限"),
    ("CGSS 2010（入口已核实）", {"name": "Chinese General Social Survey (CGSS)", "provider": None, "sample_period": "2010"}, "CN-CGSS", "受限获取（已核实入口）"),
]

fails = 0
for desc, src, want_id, want_out in CASES:
    m = catalog.match(src)
    got_id, got_out = m.get("entry_id"), catalog.outcome(m)
    ok = got_id == want_id and (want_out is None or got_out == want_out)
    fails += not ok
    print(f"{'✓' if ok else '✗'} {desc}: {got_id} / {got_out}" + ("" if ok else f"   （期望 {want_id} / {want_out}）"))
# 結果表：主要データだけを 1 行ずつ、制限と未確認の条件を書く
rep = {"data_sources": [
    {"name": "CSMAR database", "provider": "CSMAR", "role": "main", "sample_period": "2010–2016", "source_evidence": {"page": 4}},
    {"name": "China City Statistical Yearbook", "role": "control"},
    {"name": "Population Census of Japan", "provider": "Statistics Bureau of Japan", "role": "main"}]}
table = catalog.render_table_ja([("Test paper", rep)])
rows = [l for l in table.splitlines() if l.startswith("| Test paper")]
for desc, ok in [("主要データだけ 2 行", len(rows) == 2),
                 ("CSMAR は契約が必要・図書館で確認", "契約が必要" in rows[0] and "図書館" in rows[0] and "p.4" in rows[0]),
                 ("日本のセンサスはカタログ未収録", "カタログ未収録" in rows[1]),
                 ("表に中国統計局の入口を出さない", "stats.gov.cn" not in rows[1])]:
    fails += not ok
    print(f"{'✓' if ok else '✗'} 結果表：{desc}")
print(f"{len(CASES) + 4 - fails}/{len(CASES) + 4} 通过")
sys.exit(1 if fails else 0)
