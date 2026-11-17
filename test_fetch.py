"""
测试 PDF 下载与核对。不联网：用程序生成的小 PDF 和假的下载响应。

运行：
    python test_fetch.py
"""

import json
import os
import tempfile

import pymupdf

import fetch_fulltext as ff

failures = 0


def check(name, ok):
    global failures
    print(f"{'✓' if ok else '✗'}  {name}")
    if not ok:
        failures += 1


BODY = ("We use state-level panel data on employment and minimum wages. " * 40)


def make_pdf(first_lines: list[str], body: str = BODY) -> bytes:
    """生成一个两页的 PDF：第 1 页是 first_lines（标题等），后面是正文。"""
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in first_lines:
        page.insert_text((72, y), line, fontsize=12)
        y += 18
    page.insert_textbox(pymupdf.Rect(72, y + 20, 520, 780), body, fontsize=9)
    doc.new_page().insert_textbox(pymupdf.Rect(72, 72, 520, 780), body, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


class Resp:
    def __init__(self, status=200, content=b"", ctype="application/pdf"):
        self.status_code, self.content, self.headers = status, content, {"content-type": ctype}


def getter(resp=None, exc=None):
    def get(url):
        if exc:
            raise exc
        return resp
    return get


TITLE = "Minimum Wages and Teen Employment: A Spatial Panel Approach"
paper = {"id": "W1", "title": TITLE, "pdf_url": "https://example.org/a.pdf", "landing_url": "https://example.org/a",
         "oa_version": "publishedVersion"}

with tempfile.TemporaryDirectory() as d:
    r = ff.fetch_one(paper, d, get=getter(Resp(content=make_pdf(["Minimum Wages and Teen Employ-", "ment: A Spatial Panel Approach"]))))
    check("正常：标题被换行和断词拆开，也能核对通过，文件保存到 pdfs/",
          r["status"] == "ok" and r["path"].endswith(os.path.join("pdfs", "W1.pdf")) and os.path.exists(r["path"]))
    check("正常：记录页数、字节数，版本注明“OpenAlex 标注，未核实”",
          r["pages"] == 2 and r["bytes"] > 0 and r["version_openalex"] == "publishedVersion" and "not verified" in r["version_note"])
    r = ff.fetch_one(paper, d, get=getter(Resp(content=make_pdf(["MINIMUM WAGES AND TEEN EMPLOYMENT"]))))
    check("首页只印主标题（没有副标题）、而且是大写 → 也算找到", r["status"] == "ok")
    r = ff.fetch_one({**paper, "id": "W2"}, d, get=getter(Resp(content=make_pdf(["Household Saving in Rural Areas"]))))
    check("下载到的是别的论文 → title_mismatch，文件放到 rejected/ 供人工确认",
          r["status"] == "title_mismatch" and os.path.join("rejected", "W2.pdf") in r["path"])
    r = ff.fetch_one({**paper, "id": "W3"}, d, get=getter(Resp(content=b"<html><body>Please sign in</body></html>", ctype="text/html")))
    check("收费墙返回的登录网页 → not_pdf，不保存文件",
          r["status"] == "not_pdf" and "text/html" in r["detail"] and not os.path.exists(os.path.join(d, "pdfs", "W3.pdf")))
    r = ff.fetch_one({**paper, "id": "W4"}, d, get=getter(Resp(status=403)))
    check("HTTP 403 → http_403，保留原始链接；说明里写明“不代表论文不公开”",
          r["status"] == "http_403" and r["url"] == paper["pdf_url"] and "NOT mean" in ff.STATUS_LABELS["http_403"])
    r = ff.fetch_one({**paper, "id": "W4b"}, d, get=getter(Resp(status=500)))
    check("其他 HTTP 错误（如 500）→ http_error", r["status"] == "http_error" and r["http_status"] == 500)
    r = ff.fetch_one({**paper, "id": "W10"}, d, get=getter(Resp(content=make_pdf(["NBER WORKING PAPER SERIES", TITLE]))))
    check("标为期刊正式版、首页却写着 Working Paper → 照常下载，但给出版本不一致警告",
          r["status"] == "ok" and "Working Paper" in r.get("version_warning", ""))
    r = ff.fetch_one({**paper, "id": "W11", "oa_version": "submittedVersion"}, d,
                     get=getter(Resp(content=make_pdf(["NBER WORKING PAPER SERIES", TITLE]))))
    check("标注本来就是工作论文版 → 不警告", "version_warning" not in r)
    r = ff.fetch_one({**paper, "id": "W5"}, d, get=getter(exc=ConnectionError("timed out")))
    check("连不上 → network_error，不让程序崩溃", r["status"] == "network_error" and "timed out" in r["detail"])
    r = ff.fetch_one({**paper, "id": "W6"}, d, get=getter(Resp(content=make_pdf([TITLE], body="x"))))
    check("几乎没有文字（扫描版）→ no_text", r["status"] == "no_text")
    r = ff.fetch_one({**paper, "id": "W7"}, d, get=getter(Resp(content=b"%PDF-1.4 this is not really a pdf")))
    check("以 %PDF 开头但打不开 → unreadable", r["status"] == "unreadable")
    old = ff.MAX_BYTES
    ff.MAX_BYTES = 100
    r = ff.fetch_one({**paper, "id": "W8"}, d, get=getter(Resp(content=make_pdf([TITLE]))))
    ff.MAX_BYTES = old
    check("超过大小上限 → too_large", r["status"] == "too_large")
    r = ff.fetch_one({**paper, "pdf_url": None}, d, get=getter(exc=AssertionError("should not download")))
    check("没有 PDF 地址 → no_pdf_link，不去下载", r["status"] == "no_pdf_link")

check("标点写法不同（PDF 是弯撇号 ’、换行断词，OpenAlex 是直撇号 '）→ 也算找到（真实例子：Frontiers 2022）",
      ff.title_found("The Effect of China's Pilot Low-Carbon City Initiative on Enterprise Labor Structure",
                     ["The Effect of China\u2019s Pilot Low- Carbon City Initiative on Enterprise Labor Structure Xiaoyang Sun"]))
check("标题太短（无法可靠核对）→ 不算找到", not ff.title_found("Teens", ["Teens and work"]))
check("标题真的不在前两页 → 不算找到", not ff.title_found(TITLE, ["Some other paper", "references"]))

# --- 整批：只处理“自动调查”组；结果写进这次运行自己的文件夹 ---
with tempfile.TemporaryDirectory() as d:
    cand = os.path.join(d, "cand.json")
    json.dump({"topic": "t", "auto": [paper, {**paper, "id": "W9", "pdf_url": None}],
               "upload": [{"id": "U1", "title": "Paywalled", "doi": "https://doi.org/x"}]}, open(cand, "w"))
    out = os.path.join(d, "run1")
    rep = ff.fetch_candidates(cand, out, get=getter(Resp(content=make_pdf([TITLE]))))
    check("整批：只处理“自动调查”组，每篇一条记录", [r["status"] for r in rep["fetched"]] == ["ok", "no_pdf_link"])
    check("整批：建议上传的论文原样列出，不尝试下载", rep["upload_suggested"] == [{"id": "U1", "title": "Paywalled", "link": "https://doi.org/x"}])
    check("整批：报告和 PDF 都在这次运行的文件夹里（不写进 papers/）",
          os.path.exists(os.path.join(out, "fetch_report.json")) and rep["fetched"][0]["path"].startswith(out))

print("\n全部通过" if failures == 0 else f"\n{failures} 项失败")
raise SystemExit(1 if failures else 0)
