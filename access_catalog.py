"""入手経路カタログ（中国経済データ 9 種）の照合と、利用者向け日本語の結果表（不调模型，不联网）。
与 DataPilot experiments/catalog/catalog.py（v2.1 冻结）判定一致，另加 render_table_ja。先认准论文用的那份数据，再给获取方式。
级别：
  product_version  认出产品，版本也对上目录里核实过的入口 → 给渠道、入口、依据
  product          认出产品，但版本没写、靠数据年份推断、或目录没核实这一版 → 给该产品的渠道，注明版本要核对
  lead             只认出提供方或数据系列 → 只给入口线索和要核对什么，不给获取方式
  none             目录里没有 → 交给 Agent
只用数据名（和版本字段）认产品，不用论文原句：同一句话里常并列几份数据。"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_FILE = os.environ.get("ACCESS_CATALOG", "access_catalog.json")
CATALOG = json.load(open(os.path.join(HERE, CATALOG_FILE), encoding="utf-8"))
YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


def _norm(s):
    return " ".join((s or "").lower().replace("—", "-").replace("–", "-").split())


def _years(s):
    out = []
    for a, b in re.findall(r"((?:19|20)\d{2})\s*[-–—~至到]\s*((?:19|20)\d{2})", s or ""):
        out += list(range(int(a), int(b) + 1))
    return sorted(set(out + [int(y) for y in YEAR.findall(s or "")]))


def _product_hit(entry, src):
    m = entry["match"]
    name = _norm(src.get("name"))
    n = name if m.get("fields") is None else _norm(" ".join(src.get(f) or "" for f in m["fields"]))
    if m.get("require_any_in_name") and not any(w in name for w in m["require_any_in_name"]):
        return None
    for alias in m["names"]:
        i = n.find(alias)
        if i < 0:
            continue
        j = i + len(alias)
        if alias.isascii() and (re.search(r"[a-z0-9]", n[i - 1:i] if i else "") or (len(alias) <= 5 and re.search(r"[a-z0-9]", n[j:j + 1]))):
            continue   # 英文别名要按词对齐（cma 不匹配 cmaq，cfps 不匹配 cfpsx）
        rest = n[j:].lstrip()
        if any(rest.startswith(w) for w in m.get("not_if_followed_by", [])):
            continue
        if any(x in name for x in m.get("exclude", [])):
            return None
        return alias
    return None


def _versions(entry, src):
    """返回 (级别, 入口列表, 版本说明)。"""
    v = entry["versions"]
    kind = v["kind"]
    explicit = _years(f"{src.get('version') or ''} {src.get('name') or ''}")
    data_years = _years(src.get("sample_period") or "")
    if kind == "any":
        return "product_version", [entry["entry_template"]], "目录条目不分版本"
    if kind == "unversioned":   # 目录条目没有可核对的版本清单（CSMAR 子库、工业企业数据库年份）：只能给到 product
        return "product", [entry["entry_template"]], v.get("note", "目录没有版本清单")
    if kind == "platform":
        if any(w in _norm(src.get("name")) for w in v["dataset_words"]):
            return "product_version", [entry["entry_template"]], "数据名写到了具体数据（站点 / 日值）"
        return "product", [entry["entry_template"]], "只认出发布平台，没认出具体数据集"
    if kind == "census_round":
        nm = _norm(src.get("name"))
        rounds = sorted({y for k, y in v["aliases"].items() if k in nm} | {y for y in explicit + data_years if str(y) in v["online"] or y == 2020})
        tables = any(w in nm for w in v["needs_name_words"])
        urls = [v["online"][str(y)] for y in rounds if str(y) in v["online"]]
        if rounds and len(urls) == len(rounds) and tables:
            return "product_version", urls, f"普查年份 {rounds}，数据名说明是汇总资料"
        if not rounds:   # 没认出哪一次普查：只能给线索，不能给获取方式
            return "lead", [], "认出是人口普查，但没认出是哪一次"
        if not tables:   # 2026-11-18：数据名没写明是汇总资料 → 可能是微观数据、分县/分省资料或抽样，只给线索（CEQI liang2022 分县资料被给成在线入口）
            return "lead", [], f"认出是人口普查（{rounds}），但数据名没说明是汇总资料，可能是微观数据、分县 / 分省资料或抽样"
        why = "数据名没说明是汇总表还是微观数据" if not tables else ""
        if not rounds:
            why = (why + "；" if why else "") + "没认出是哪一次普查"
        elif len(urls) < len(rounds):
            why = (why + "；" if why else "") + f"目录只核实了 {sorted(v['online'])} 年的在线资料"
        return "product", urls, f"普查年份 {rounds or '未知'}：{why}"
    if kind == "fixed":
        words = v.get("needs_name_words")
        if words and not any(w in _norm(src.get("name")) for w in words):
            return "product", [entry["entry_template"]], f"版本 {v['value']}，但数据名没说明是汇总表还是微观数据"
        return "product_version", [entry["entry_template"]], f"固定版本 {v['value']}"
    if kind == "edition_year":
        if explicit:
            eds, how = explicit, "论文写明的版本年份"
        elif data_years:
            eds, how = [y + v.get("data_year_offset", 0) for y in data_years], f"由数据年份推断（数据年份 + {v.get('data_year_offset', 0)}）"
        else:
            return "product", [], "论文没写版本或年份"
        if "online" in v:
            lo, hi = v["online"]
            urls = [entry["entry_template"].format(Y=y) for y in eds if lo <= y <= hi]
            if explicit and len(urls) == len(eds):
                return "product_version", urls, f"{how}：{eds}"
            return "product", urls, f"{how}：{eds}；目录核实在线入口的是 {lo}–{hi} 年版" + ("（版本靠推断，请核对卷册）" if not explicit else "")
        known = v.get("known", {})
        urls = [known[str(y)] for y in eds if str(y) in known]
        if explicit and len(urls) == len(eds):
            return "product_version", urls, f"{how}：{eds}"
        return "product", urls, f"{how}：{eds}；目录只核实了 {sorted(known)} 年版"
    if kind in ("report_year", "survey_year"):
        ys = explicit or data_years
        if not ys:
            return "product", [], "论文没写年份"
        known = v.get("known", {})
        urls = [known[str(y)] for y in ys if str(y) in known]
        if len(urls) == len(ys):
            return "product_version", urls, f"年份 {ys}"
        return "product", urls, f"年份 {ys}；目录只核实了 {sorted(known)} 年的入口"
    return "product", [], "未知版本规则"


def _identity(entry, src, alias):
    """名称越泛，越要靠提供方、国家、版本等证据确认身份。
    返回 "ok"（别名不泛，或找到证据）/ "conflict"（提供方写明了却不是该机构）/ "unconfirmed"（没有证据）。"""
    idt = entry.get("identity")
    if not idt or alias not in idt["generic_names"]:
        return "ok"
    ev = idt["evidence_any"]
    has = lambda t: any(w in _norm(t) for w in ev)
    if has(src.get("name")) or has(src.get("version")) or has(src.get("provider")):
        return "ok"
    prov = _norm(src.get("provider"))
    if prov and not any(g in prov for g in idt["generic_names"]):
        return "conflict"      # 提供方写明了另一家机构（Eurostat、Statistics Bureau of Japan…）
    return "unconfirmed"       # 没写提供方，或提供方本身也是泛称（Ministry of Environmental Protection）


def outcome(m):
    """报告结论（本人定的口径 v2）：访问限制和核实程度分开。
    已核实（版本对上）：可获取 / 受限获取（附入口与资格）/ 获取受限（无研究者入口）
    限制已确认、细节待查：订阅受限（问图书馆子库和年份）等——限制对整个产品成立时
    该版本获取方式未确认：只有产品的一般说明，没确认适用于论文所用版本
    线索 / 目录未收录"""
    lv, a = m["level"], m.get("access") or {}
    r = a.get("restriction")
    if lv == "product_version":
        if r in ("open", "registration"):
            return "可获取（已核实）"
        if r == "no_public":
            return "获取受限（已核实）"
        return "受限获取（已核实入口）"
    if lv == "product":
        if a.get("whole_product"):
            return "订阅受限" if r == "subscription" else "获取受限（已核实）"
        return "该版本获取方式未确认"
    return "线索" if lv == "lead" else "目录未收录"


def match(src):
    name = src.get("name") or ""
    for e in CATALOG["products"]:
        alias = _product_hit(e, src)
        if alias:
            idt = _identity(e, src, alias)
            if idt == "conflict":
                continue   # 例：Eurostat 的 population census 不是中国普查
            if idt == "unconfirmed":
                return {"level": "lead", "entry_id": "IDENTITY-UNCONFIRMED", "matched_on": f"数据名只有泛称“{alias}”，没有国家、机构或版本证据",
                        "entries": [], "channel": None,
                        "still_check": f"先确认这份数据的国家和提供机构；若是{e['product']}，再按该条目核对"}
            level, urls, vnote = _versions(e, src)
            if level == "lead":
                return {"level": "lead", "entry_id": e["id"], "matched_on": f"数据名含“{alias}”；{vnote}", "entries": urls,   # 线索不给产品入口（例：普查分县资料不能指向在线汇总表）
                        "still_check": e["still_check"], "channel": None}
            return {"level": level, "entry_id": e["id"], "product": e["product"], "matched_on": f"数据名含“{alias}”",
                    "channel": e["channel"], "channel_label": e["channel_label"], "entries": urls,
                    "version_note": vnote, "evidence": e["evidence"], "not_for": e["not_for"],
                    "still_check": e["still_check"] + ("" if level == "product_version" else "；论文所用版本"),
                    "verified_by": e["verified_by"], "next_step": e.get("next_step"), "access": e.get("access")}
    n, prov = _norm(name), _norm(src.get("provider"))
    for r in CATALOG["leads"]:
        m = r["match"]
        # 提供方只看第一个写的机构（“BNU and ANU with the support of NBS” 不算统计局的数据）
        hit = ("name_regex" in m and re.search(m["name_regex"], n)) or \
              any(re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", n) or prov.startswith(k) for k in m.get("provider_or_name", []))
        if hit:
            return {"level": "lead", "entry_id": r["id"], "matched_on": r["when"], "entries": r["entries"],
                    "still_check": r["still_check"], "channel": None}
    return {"level": "none"}


# ---------- 利用者向けの日本語結果表 ----------
VERDICT_JA = {"可获取（已核实）": "✅ 入手可能（確認済み）", "受限获取（已核实入口）": "🔐 制限付き入手（入口確認済み）",
              "获取受限（已核实）": "⛔ 入手制限あり（確認済み）", "订阅受限": "🔐 契約が必要（範囲は要確認）",
              "该版本获取方式未确认": "❓ この版の入手方法は未確認", "线索": "🔎 手がかりのみ", "目录未收录": "— カタログ未収録"}
_BY_ID = {e["id"]: e for e in CATALOG["products"] + CATALOG["leads"]}


def _cell(s):
    return (s or "—").replace("|", "／").replace("\n", " ")


def row_ja(label: str, src: dict) -> list[str]:
    """1 つのデータ源 → [論文, 論文が使ったデータ, 結論, 入口, 次にやること, 未確認の条件]"""
    m = match(src)
    verdict = VERDICT_JA[outcome(m)]
    ev = src.get("source_evidence") or {}
    used = f"**{src.get('name')}**" + (f"（{src['sample_period']}）" if src.get("sample_period") else "") + \
           (f"、p.{ev['page']}" if ev.get("page") else "") + ("；統制変数にも使用" if src.get("also_controls") else "")
    e = _BY_ID.get(m.get("entry_id")) or {}
    ja = e.get("ja") or {}
    if m["level"] == "none":
        return [label, used, verdict, "—", "カタログ未収録：論文本文のデータ説明から提供元を探す（V2 公式サイト確認も利用可）", "—"]
    if m.get("entry_id") == "IDENTITY-UNCONFIRMED":
        return [label, used, verdict, "—", "名称が一般的で国・機関・版を確認できない。まずデータの国と提供機関を確認する", "データの国と提供機関"]
    if m["level"] == "lead":
        if m.get("entry_id") in {x["id"] for x in CATALOG["products"]}:
            return [label, used, verdict, "—", f"{ja.get('product')} の可能性。どの回・どの資料（集計表かミクロデータか）か確認する", ja.get("still_check")]
        urls = re.findall(r"https?://[^\s（）()]+", "；".join(m.get("entries") or []))   # 入口欄は URL だけ（説明文は中国語のため）
        return [label, used, verdict, "；".join(urls) or "—", ja.get("next_step"), ja.get("when")]
    # 製品を特定できた行：結論欄に入手の条件と理由、版の確認は未確認欄へ
    urls = m.get("entries") or [x["url"] for x in (m.get("evidence") or [])[:1]]
    verdict = ja.get("verdict_version") if m["level"] == "product_version" else ja.get("verdict")
    entry = f"{ja.get('entry_label')}：{'；'.join(urls)}" if urls else (ja.get("entry_label") or "—")
    return [label, used, verdict, entry, ja.get("next_step"), ja.get("still_check")]


def render_table_ja(reports: list[tuple[str, dict]], main_only: bool = True) -> str:
    """reports = [(論文ラベル, step2/step3 のレポート)]。主要データ（role=main）を 1 行ずつ表にする。"""
    lines = ["# データ入手経路（中国経済データ・カタログ照合）", "",
             "読み方：「結論」はそのデータを手に入れるための条件と理由（📖 既知の経路 / 🔐 制限あり / ⛔ 公開なし / ✅ 確認済み）。"
             "「次にやること」は誰に何を確認するか。論文が使った版・年が入っているかは「未確認の条件」に書く。"
             "カタログ未収録のデータは論文本文の説明を参照。", "",
             "| 論文 | 論文が使ったデータ | 結論（入手の条件と理由） | 入口 | 次にやること | 未確認の条件 |", "|---|---|---|---|---|---|"]
    for label, rep in reports:
        for src in (rep or {}).get("data_sources", []):
            if main_only and src.get("role") != "main":
                continue
            lines.append("| " + " | ".join(_cell(x) for x in row_ja(label, src)) + " |")
    return "\n".join(lines) + "\n"
