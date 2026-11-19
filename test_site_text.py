"""网站固定文字不能当获取依据（2026-11-19）。python3 test_site_text.py"""
import sys
import official_check as oc
CASES = [  # (引文, 是否算网站固定文字)
    ("注：建议使用IE7以上版本普通模式（“兼容性视图”），或360浏览器兼容模式浏览（非极速模式）。", True),   # 发布版历史组的实例
    ("建议使用IE8及以上浏览器，1024*768分辨率浏览本站", True),
    ("Copyright © 2024 National Bureau of Statistics. All rights reserved.", True),
    ("京ICP备10028400号-1 京公网安备11010202007625号", True),
    ("This site is best viewed with the latest version of Chrome.", True),
    ("Use the Data Browser to download tables in CSV format.", False),
    ("用户可通过浏览器访问本网站，在线查询并下载数据。", False),
    ("ERA5 data can be downloaded through the CDS either through the CDS web interface or programmatically using the CDS API service.", False),
    ("公众可通过中国气象数据网无偿获取目录所列资料和产品。", False),
    ("注册后登录即可浏览和下载数据。", False),
]
fails = 0
for q, expect in CASES:
    got = bool(oc.SITE_TEXT.search(oc.normalize(q)))
    fails += got != expect
    print(f"{'✓' if got == expect else '✗'}  {'网站固定文字' if got else '获取说明'}：{q[:60]}")
print("\n全部通过" if not fails else f"\n{fails} 项失败")
sys.exit(1 if fails else 0)
