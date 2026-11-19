"""渠道一致性（2026-11-19 合入，v1）：收费 / 审核的引文本身支持该条件，才改渠道；否定句不算；
改写后与“免费”依据矛盾 → 保留已核实的渠道，条件待核。python3 test_channel_consistency.py"""
import sys
import official_check as oc

AQ_FREE = "本数据可在官网免费下载。"
CASES = [  # (名称, kind, 页面正文, access_quote, 提交渠道, payment/review_quote, 期望 v1 渠道, 期望 v1 待核)
    ("免费：页面只写免费", "payment", "数据说明。本数据可在官网免费下载。", AQ_FREE, "public_download", AQ_FREE, "public_download", False),
    ("付费：引文写机构订阅", "payment", "下载数据。本数据库需机构订阅后方可下载。", "下载数据", "public_download",
     "本数据库需机构订阅后方可下载", "subscription", False),
    ("付费：引文写购买", "payment", "数据下载。购买后可下载完整数据。", "数据下载", "public_download", "购买后可下载完整数据", "purchase", False),
    ("否定收费（本人例）", "payment", "数据说明：无需购买或订阅，本数据可无偿获取。", "本数据可无偿获取", "public_download",
     "无需购买或订阅，本数据可无偿获取", "public_download", False),
    ("否定收费（英文）", "payment", "Download the data. No subscription or fee is required.", "Download the data", "public_download",
     "No subscription or fee is required", "public_download", False),
    ("否定句 + 别处有收费", "payment", "无需购买即可下载基础表。高级会员需付费订阅。", "无需购买即可下载基础表", "public_download",
     "无需购买即可下载基础表", "public_download", True),
    ("不同子产品分别收费", "payment", "基础数据免费下载，高分辨率产品需付费购买。", "基础数据免费下载", "public_download",
     "基础数据免费下载，高分辨率产品需付费购买", "public_download", True),
    ("获取依据写免费、收费引文另一句（矛盾）", "payment", "公众可无偿获取目录所列资料。部分定制产品需购买。",
     "公众可无偿获取目录所列资料", "registration_download", "部分定制产品需购买", "registration_download", True),
    ("气象局原句（v0 被改成购买）", "payment",
     "公众可通过中国气象数据网无偿获取目录所列资料和产品。对收费的资料服务，按照规定收费。",
     "公众可通过中国气象数据网无偿获取目录所列资料和产品", "registration_download",
     "公众可通过中国气象数据网无偿获取目录所列资料和产品", "registration_download", True),
    ("审核：引文写审核通过后下载", "review", "注册后提交申请，审核通过后可下载。", "注册后提交申请", "registration_download",
     "审核通过后可下载", "apply_to_provider", False),
    ("审核：否定句", "review", "注册即可下载，无需审核。", "注册即可下载", "registration_download", "注册即可下载，无需审核",
     "registration_download", False),
]
fails = 0
for name, kind, text, aq, ch, q, exp_ch, exp_pend in CASES:
    dec = {f"{kind}_scope": "this_data", f"{kind}_quote": q}
    rej, new, note, pend = oc.condition_scope(kind, dec, text, aq, ch, None, "u", {"text": text, "title": "", "links": []})
    ok = rej is None and new == exp_ch and bool(pend) == exp_pend
    fails += not ok
    print(f"{'✓' if ok else '✗'}  {name}: {ch} → {new}，待核 {bool(pend)}")
print("\n全部通过" if not fails else f"\n{fails} 项失败")
sys.exit(1 if fails else 0)
