"""V3 展示ページ（2026-11-23）：保存済みの実行結果から代表例を取り出し、docs/index.html を作る（GitHub Pages は main の docs/ から公開）。API・ネットワーク不要。
    python3 site/build_site.py          # docs/index.html を書き出す
    python3 site/build_site.py --check  # 書き出さずに、各代表例の文言が保存結果にそのまま存在するかだけ確認

方針（本人、2026-11-23）：ページには代表例だけを載せる。評価の数字は載せず、リポジトリの評価文書へリンクする。
代表例はツールの実際の出力をそのまま使い、手を加えない（合字 ﬁ→fi の表示正規化と、引用の 1 文目で切る場合の「…」のみ）。
出典：demo/outputs/access_table_ja.md（第 3・4 号 13 本、2026-11-18 の抽出）、demo/outputs/vertical_integration_report.md
（2026-11-19 の実行）、demo/outputs/official.md（公式サイト確認、2026-11-18 の実行）。"""
import html
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "demo", "outputs")
REPO = "https://github.com/akissika9090/econdata-scout"
# 公式サイト確認の入手経路コード → 日本語（step3 の英語ラベルと 1 対 1）
CHANNEL_JA = {"free download after registration": "登録後に無料でダウンロード", "free public download": "公開されていて無料でダウンロード"}


# 公式サイトの原文（中国語）に添える英語の参考訳（2026-11-23 本人要望）。ツールの出力ではないので、ページでもそう明記する
REFERENCE_EN = {
    "登录的用户，在列表页点击 “下载”按钮、在全文页点击、在个人中心-我的收藏-案例包-文书列表页中点击，可以实现裁判文书下载。":
        "Logged-in users can download judgment documents by clicking the “Download” button on the list page, on the full-text "
        "page, or on the document list page under Personal Center > My Favorites > Case Packages.",
}


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


def read(name: str) -> str:
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        return f.read()


def table_rows(text: str) -> list[dict]:
    rows, head = [], None
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if head is None:
            head = cells
        else:
            rows.append(dict(zip(head, cells)))
    return rows


def catalog_example(rows, paper_prefix, data_name, quote=None):
    r = next(r for r in rows if r["論文"].startswith(paper_prefix) and data_name in r["論文が使ったデータ"])
    used = r["論文が使ったデータ"]
    m = re.match(r"\*\*(.+?)\*\*(?:（(.+?)）)?、p\.(\d+)", used)
    entry = r["入口"]
    url = re.search(r"https?://\S+", entry)
    return {"kind": "catalog", "paper": r["論文"], "data": m.group(1), "years": m.group(2), "page": m.group(3),
            "quote": quote, "verdict": r["結論（入手の条件と理由）"], "entry_label": entry.split("：")[0] if url else entry,
            "entry_url": url.group(0) if url else None, "next": r["次にやること"], "pending": r["未確認の条件"],
            "source": "demo/outputs/access_table_ja.md", "run": "2026-11-18 の抽出（第 3・4 号 13 本）・凍結版カタログ"}


def official_example(text):
    sec = text.split("## Online transcripts of judicial decisions")[1].split("\n## ")[0]
    title = re.search(r"- \*\*Kahn2020\*\* (.+?) \((.+?)\)\n", text)
    q = re.search(r"\*\*Online transcripts of judicial decisions\*\* — p\. (\d+): “(.+?)”", text)
    first = re.match(r"(.+?decisions\.)", q.group(2)).group(1)
    channel = re.search(r"\| Access channel \| .+? \| (.+?) —", sec).group(1)
    return {"kind": "official", "paper": title.group(1), "venue": title.group(2), "data": "Online transcripts of judicial decisions",
            "years": re.search(r"between (\d{4}) and (\d{4})", text).expand(r"\1–\2"), "page": q.group(1), "quote": first + " …",
            "channel": CHANNEL_JA[channel], "channel_en": channel,
            "access_quote": re.search(r"Official-site text \(access\): “(.+)”\s*$", sec, re.M).group(1),   # 原文里有嵌套的引号，取到行末
            "entry_url": re.search(r"\| Source \| .+? \| (https://\S+)", sec).group(1),
            "checked": re.search(r"checked (\d{4}-\d{2}-\d{2})", sec).group(1),
            "pending": "論文が使った年（2014–2017）が含まれるか：公式サイトの文面には年の記載がない",
            "source": "demo/outputs/official.md", "run": "2026-11-18 の実行（--official、公式サイト確認）"}


def examples():
    rows = table_rows(read("access_table_ja.md"))
    rep = read("vertical_integration_report.md")
    q = re.search(r"\*\*CSMAR\*\* — p\. 4: “(.+?)”", rep).group(1)
    return [catalog_example(rows, "Vertical integration", "CSMAR", q),
            catalog_example(rows, "On foreign-invested", "China Industrial Enterprise Database"),
            official_example(read("official.md"))]


def check(exs) -> list[str]:
    """代表例の文言が出典ファイルにそのまま存在するか（表示用の NFKC 正規化と末尾の「…」を除いて）。"""
    srcs = {n: nfkc(read(n)) for n in ("access_table_ja.md", "vertical_integration_report.md", "official.md")}
    bad = []
    for e in exs:
        for k in ("paper", "data", "verdict", "next", "quote", "access_quote", "entry_url"):
            v = e.get(k)
            if not v:
                continue
            v = nfkc(v.removesuffix(" …"))
            if not any(v in s for s in srcs.values()):
                bad.append(f"{e['data']}: {k} not found verbatim in the saved results")
    return bad


def card(e, i):
    esc = html.escape
    quote = f"<blockquote>“{esc(nfkc(e['quote']))}”</blockquote>" if e.get("quote") else ""
    years = f"（{esc(e['years'])}）" if e.get("years") else ""
    if e["kind"] == "catalog":
        verdict = esc(e["verdict"])
        entry = (f"{esc(e['entry_label'])}：<a href=\"{esc(e['entry_url'])}\">{esc(e['entry_url'])}</a>" if e["entry_url"] else esc(e["entry_label"]))
        rows = [("結論（入手の条件と理由）", f"<strong>{verdict}</strong>"), ("入口", entry), ("次にやること", esc(e["next"])),
                ("未確認の条件", esc(e["pending"]))]
        how = "カタログ照合（中国経済データ 9 種）"
    else:
        rows = [("結論（入手の条件と理由）", f"<strong>✅ 公式サイトで確認：{esc(e['channel'])}</strong>"),
                ("公式サイトの記載（原文）", f"<span lang=\"zh\">“{esc(e['access_quote'])}”</span>"
                 + (f"<span class=\"tr\" lang=\"en\">{esc(REFERENCE_EN[e['access_quote']])}"
                    f"<small>英語の参考訳（ツールの出力ではありません）</small></span>" if e["access_quote"] in REFERENCE_EN else "")),
                ("入口", f"<a href=\"{esc(e['entry_url'])}\">{esc(e['entry_url'])}</a>（{esc(e['checked'])} に確認）"),
                ("未確認の条件", esc(e["pending"]))]
        how = "公式サイト確認エージェント（--official）"
    body = "".join(f"<tr><th scope=\"row\">{k}</th><td>{v}</td></tr>" for k, v in rows)
    return (f"<article class=\"slip\" id=\"ex{i}\"><header><span class=\"how\">{how}</span><h3>{esc(e['data'])}</h3>"
            f"<p class=\"paper\">{esc(nfkc(e['paper']))}</p></header>"
            f"<div class=\"evid\"><span class=\"pg\">p.{esc(e['page'])}</span>{years}{quote}</div>"
            f"<table>{body}</table><footer>出典：<a href=\"{REPO}/blob/main/{e['source']}\">{e['source']}</a>　{esc(e['run'])}"
            + ("・ツールの出力を加工せずに掲載" if e["kind"] == "catalog" else
               f"・英語の出力（{esc(e['channel_en'])}）を日本語の項目名で掲載、引用は原文のまま") + "</footer></article>")


def page(exs) -> str:
    csmar = exs[0]
    route = [("論文の記述", f"p.{csmar['page']}「{nfkc(csmar['quote'])}」"), ("論文が使ったデータ", csmar["data"]),
             ("入手の条件", csmar["verdict"].split("：")[0].lstrip("🔐 ")), ("次にやること", csmar["next"].split("。")[0])]
    stations = "".join(f"<li><span class=\"k\">{html.escape(k)}</span><span class=\"v\">{html.escape(v)}</span></li>" for k, v in route)
    cards = "".join(card(e, i + 1) for i, e in enumerate(exs))
    return TEMPLATE.replace("{{STATIONS}}", stations).replace("{{CARDS}}", cards).replace("{{REPO}}", REPO)


TEMPLATE = open(os.path.join(HERE, "template.html"), encoding="utf-8").read() if os.path.exists(os.path.join(HERE, "template.html")) else ""

if __name__ == "__main__":
    exs = examples()
    bad = check(exs)
    for b in bad:
        print("✗", b)
    if bad:
        sys.exit(1)
    print(f"代表例 {len(exs)} 件：すべての文言が保存結果にそのまま存在")
    if "--check" not in sys.argv:
        with open(os.path.join(ROOT, "docs", "index.html"), "w", encoding="utf-8") as f:
            f.write(page(exs))
        print("docs/index.html を書き出しました")
