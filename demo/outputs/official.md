<!-- Saved report of a real run on 2026-11-18 (LLM_PROVIDER=deepseek, deepseek-flash): `python scout.py "the effect of air pollution on labor productivity in China" --official --pdf ...`. OpenAlex selected 3 papers; Kahn (2020) downloaded automatically, Chang et al. and Chen & Zhang were refused by the publishers (HTTP 403) and downloaded by hand. The run used rules v2.5b. Offline changes to the saved results, no API call: (1) a second, hand-uploaded copy of Kahn (2020) that scout.py then analysed as a separate paper was removed (scout.py now skips such duplicates); (2) the saved model answers were re-verified with v2.5c (curly and straight quotes treated as equal), which brings back Chang et al.'s main data (Ctrip), for which the official-site check was not run ("not checked"); (3) the saved official-site findings were re-checked with v2.5d (the access quote must state how to obtain the data): the 2010 census and MERRA-2 findings did not, so they are shown as leads; in a live run the agent would have been sent back and might have found a better page; (4) the report uses the current layout (main data by paper first). Other official-site findings are those of the run and reflect the pages on the date checked. See demo/README.md for known errors. -->
# EconData Scout report

- Research direction: the effect of air pollution on labor productivity in China
- Policy: air pollution  |  Outcome: labor productivity
- Evidence Recovery Agent: not used
- Official-site check (V2): used

## Papers investigated

- **Chang2016** The Effect of Pollution on Worker Productivity: Evidence from Call Center Workers in China (American Economic Journal Applied Economics)
  - full text: uploaded by the user (automatic download had failed); version: uploaded by the user; version not checked
- **Kahn2020** Air pollution lowers high skill public sector worker productivity in China (Environmental Research Letters)
  - full text: open access (OpenAlex); version: publishedVersion - OpenAlex metadata, not verified
- **Chen2021** Impact of air pollution on labor productivity: Evidence from prison factory data (China Economic Quarterly International)
  - full text: uploaded by the user (automatic download had failed); version: uploaded by the user; version not checked

# Main data by paper

For each paper: the data the authors analysed as their main data (the model's role judgment), with the source sentence and page checked in the PDF, and where the official-site check got to. Main-data candidates whose evidence did not pass the checks are listed under **To verify**, with what is missing and where to look. Only data sources and access routes are checked; details for each data source are in the summary below.

## Chang2016

**Main data (source text checked)**
- **Ctrip call center worker productivity data** — p. 5: “Our data on worker productivity come from Ctrip International, China's largest travel agency.”
  - Official site now: not checked
- **China National Environmental Monitoring Center (CNEMC) daily API data** — p. 6: “Our daily pollution data are obtained from the China National Environmental Monitoring Center (CNEMC), which is affiliated with the Ministry of Environmental Protection of China.”
  - Official site now: official page found but could not be read — check manually

Other data used (robustness / supplementary): Beijing API data

## Kahn2020

**Main data (source text checked)**
- **Online transcripts of judicial decisions** — p. 4: “Our main data source is online transcripts of judicial decisions.11 These documents first became available online in late 2013 in a handful of courts, and cov- erage widened over time.”
  - Official site now: free download after registration (wenshu.court.gov.cn); years / version used by the paper not named on the page — pending
- **Air pollution data from China's Ministry of Environmental Protection (MEP)** — p. 4: “Air pollution data are published daily by the China’s Ministry of Environmental Protection (MEP).”
  - Official site now: no verified access route found — leads in the summary below
- **Weather data from China Meteorological Data Sharing Service System** — p. 4: “Weather data are collected from China Meteorological Data Sharing Service System (http://cdc.cma.gov.cn/).”
  - Official site now: official page found but could not be read — check manually
- **Baidu Index** — p. 4: “The Baidu Index used in this paper is a data product analogous to Google Trends.”
  - Official site now: free download after registration (index.baidu.com, distributor); years / version used by the paper not named on the page — pending

Other data used (robustness / supplementary): China Law Yearbook; China Census 2010

## Chen2021

**Main data (source text checked)**
- **Prison factory labor administrative data (Shenzhen male prison)** — p. 4: “The labor data was draw from a male prison in Shenzhen, China in 2015, where thousands of inmate laborers were forced to work in its factory during incarceration period.”
  - Official site now: no verified access route found — leads in the summary below
- **API daily report in Shenzhen (National Environmental Monitoring Center of China)** — p. 4: “The air pollution data used in this study is taken from the API daily report in Shenzhen, released by the National Environmental Monitoring Center of China.”
  - Official site now: official page found but could not be read — check manually
- **MERRA-2 satellite images (NASA)** — p. 5: “The atmospheric inversion data comes from the MERRA-2 satellite images of NASA.”
  - Official site now: no verified access route found — leads in the summary below
- **Daily data set of surface weather data in China (V3.0), China Meteorological Data Service Center** — p. 6: “The meteorological data is taken from the daily monitoring of meteorological sites provided by the China Meteorological Data Service Center.”
  - Official site now: no verified access route found — leads in the summary below

# Data source summary (merged across papers)

- **Access**: whether you can obtain this data. Direct evidence in the paper takes precedence; if the paper only makes a general statement, the conclusion is weakened; if the paper says nothing, the tool's built-in database list is used and named as the basis.
- **Historical use record**: sample years used by prior papers and statements that "the sample was narrowed for data reasons". This is a historical record only; the tool does not judge whether these years meet your research needs, and it does not represent the years, regions, or variables the database covers today. Please check these yourself.
- **Model judgments**: the usage relation (used in this paper / cites others / background), which data a period belongs to, and which part a condition applies to are all model judgments. The program only checks that quotes exist verbatim, are single sentences, name the data, and have a consistent year structure; it does not prove that these semantic judgments are correct.
- **Official site now (V2)**: for each data source, an agent searched the provider's official website for how the data can be obtained today. A finding is shown only if the program confirmed that the page is an official source and that the quoted sentences appear on it word for word. The channel, eligibility and whether the page covers the paper's version are the model's judgments on that quoted text. Official pages the program could not read are listed for manual checking and are not counted as findings.

## Air pollution data from China's Ministry of Environmental Protection　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now |
|---|---|---|
| Access channel | no channel stated (access: partly public; check on the official site whether the specific data can be downloaded) | no verified official access route found — please check this yourself |
| Eligibility | not stated | — |
| Use restrictions | none stated | — |
| Version | not stated | — |
| Source | see per-paper evidence below | — |

  - Leads from the check (not verified; open them and judge yourself):
    - https://www.cnemc.cn/jcdt/201603/t20160315_649393.shtml (submitted by the check but not confirmed: cnemc.cn is not a government / university / international-organisation domain, nor the data's own domain.)
    - https://datacenter.mee.gov.cn/websjzx/homepages/airDatas.vm (read during the check)
    - https://www.cnemc.cn/sssj/ (read during the check)
    - http://datacenter.mee.gov.cn/websjzx/homepages/airDatas.vm?ftype=day&fdevice=pc (read during the check)

- **Access: partly public; check on the official site whether the specific data can be downloaded** (basis: the tool's built-in database list; not stated in the paper — no statement found)
  - Paper evidence: no paper states an access condition
  - 🏛 Database hint: Data published by government departments; some can be queried or downloaded on the official site, some require registration or an application. Check the years and levels you need on the department's website
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
  - Sample years used by prior papers (that the period belongs to this data is a model judgment): latest year used 2017 (Kahn2020)
    - 2013–2017 (continuous range, period form consistent with the source text; Kahn2020) — p. 4: “The data for 2013 to 2017 cover 1497 nation-level monitoring stations across all 337 prefectures.”
- Per paper:
  - Kahn2020: [no statement found] Air pollution data from China's Ministry of Environmental Protection (MEP)
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 4: “Air pollution data are published daily by the China’s Ministry of Environmental Protection (MEP).”
    - Provider (extracted by the model; not an access channel): China's Ministry of Environmental Protection (MEP) (this wording does not appear verbatim in the source sentence; compare with the source text above)
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## API daily report in Shenzhen　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now (not verified) |
|---|---|---|
| Access channel | no channel stated (access: cannot determine) | official page found but the program could not read it — please check manually |
| Eligibility | not stated | — |
| Use restrictions | none stated | — |
| Version | not stated | — |
| Source | see per-paper evidence below | — |

  - Please open: https://www.cnemc.cn/gzdt/wjtz/201603/P020181010644008533922.pdf

- **Access: cannot determine** (basis: not stated in the paper, and this data is not in the tool's list — no statement found)
  - Paper evidence: no paper states an access condition
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
  - Sample years used by prior papers (that the period belongs to this data is a model judgment): latest year used 2015 (Chen2021)
    - July 2004–August 2015 (continuous range, period form consistent with the source text; Chen2021) — p. 4: “Fig. 1(A) shows the number of inmate workers and the average monthly wage for each month between July 2004 and August 2015.”
- Per paper:
  - Chen2021: [no statement found] API daily report in Shenzhen (National Environmental Monitoring Center of China)
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 6: “By combining prison factory data, API, atmospheric inversion, and meteorological data altogether, we ﬁnally construct an individual-monthly panel data set.”
    - Provider (extracted by the model; not an access channel): National Environmental Monitoring Center of China (appears verbatim in the source sentence on p. 4)
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## Baidu Index　(used by 1 paper)

| | In the papers (what prior authors used) | Distributor site now (checked 2026-11-18) |
|---|---|---|
| Access channel | no channel stated (access: cannot determine) | free download after registration — the page does not name the years / version the paper used; whether they are covered is pending |
| Eligibility | not stated | individuals can apply |
| Use restrictions | none stated | none stated on the page |
| Version | not stated | not confirmed: the page does not name the years / volumes the paper used |
| Source | see per-paper evidence below | http://index.baidu.com/Helper — found via web search |

  - Official-site text (access): “登录百度指数首页，在搜索框内输入一个关键词，按一下“查看指数”按钮，即可搜索出对应的指数数据。”
  - Official-site text (version): “搜索指数是以网民在百度的搜索量为数据基础，以关键词为统计对象，科学分析并计算出各个关键词在百度网页搜索中搜索频次的加权和。”
  - Evidence comes from: a distributor's site — not the original provider and not confirmed as official; check the original provider if you need the authoritative version
  - Why this counts as official: distributor: index.baidu.com is not the original provider and is not confirmed as official; the page names all of 'baidu', 'index'
  - Note: the page requires subscription / purchase for another version or part (加词权限/创建新词服务): “百度指数创建新词服务的费用、支付明细、有效期、权限范围等将在百度指数后台或开通权限的相关位置明示。”; the free access is tied to the data used by: “●使用方法 1. 使用入门 百度指数的使用很简单! 登录百度指数首页，在搜索框内输入一个关键词，按一下“查看指数”按钮，即可搜索出对应的指数数据。”, so registration_download is kept
  - Note: the paper used 2014–2017, but the quoted page text does not name these years or this version — whether they are covered is pending
  - Channel, eligibility and version correspondence are model judgments on the quoted official text.

- **Access: cannot determine** (basis: not stated in the paper, and this data is not in the tool's list — no statement found)
  - Paper evidence: no paper states an access condition
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
  - Sample years used by prior papers (that the period belongs to this data is a model judgment): latest year used 2017 (Kahn2020)
    - 2014–2017 (continuous range, period form consistent with the source text; Kahn2020) — p. 4: “We col- lect daily Baidu Index data on the Chinese keyword ‘kouzhao’ (mask) in the 337 matched prefectures with the judicial data in 2014–2017.”
- Per paper:
  - Kahn2020: [no statement found] Baidu Index
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 4: “We col- lect daily Baidu Index data on the Chinese keyword ‘kouzhao’ (mask) in the 337 matched prefectures with the judicial data in 2014–2017.”
    - Provider (extracted by the model; not an access channel): Baidu (appears verbatim in the source sentence on p. 4)
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## Beijing API data　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now (checked 2026-11-18) |
|---|---|---|
| Access channel | no channel stated (access: cannot determine) | apply to the data provider — for another version or product; the channel for the product the paper used is pending |
| Eligibility | not stated | an institution must apply |
| Use restrictions | none stated | 向环保系统内单位（首先向省级站和地级城市站）提供 |
| Version | not stated | only another version / the general route found; the paper's version is not confirmed on this page |
| Source | see per-paper evidence below | https://www.cnemc.cn/jcdt/201603/t20160315_649393.shtml — found via previously verified official domain |

  - Official-site text (access): “各地可依据实际需求申请下载月报数据。”
  - Evidence comes from: the official page itself
  - Why this counts as official: previously verified official domain (cnemc.cn)
  - Note: the page covers another version or product; apply_to_provider applies to that one — the channel for the product the paper used is pending
  - Note: the paper states no version or years, so version correspondence could not be checked
  - Channel, eligibility and version correspondence are model judgments on the quoted official text.

- **Access: cannot determine** (basis: not stated in the paper, and this data is not in the tool's list — no statement found)
  - Paper evidence: no paper states an access condition
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
- Per paper:
  - Chang2016: [no statement found] Beijing API data
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 17: “As an additional test of demand side factors, we also include data on the API from Beijing.”
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## China Law Yearbook　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now (checked 2026-11-18) |
|---|---|---|
| Access channel | no channel stated (access: public publication; available in libraries or on statistics bureau websites) | paid purchase — for another version or product; the channel for the product the paper used is pending |
| Eligibility | not stated | not stated on the page |
| Use restrictions | none stated | none stated on the page |
| Version | not stated | the page covers the version the paper used |
| Source | see per-paper evidence below | https://m.chinalaw.org.cn/index.php/portal/article/index.html?id=29488&cid=36 — found via web search |

  - Official-site text (access): “您可以线上预览图书的相关目录，确定心仪图书后即时在线下单，通过支付宝即可完成购买;也可通过网上打印征订单的方式，将征订单填写好后寄到我社，并根据网上提供的银行账号转账予以结算。”
  - Official-site text (version): “《中国法律年鉴》(中文版、英文版)是供读者了解和研究中国特色社会主义法治建设基本情况必备的综合性大型文献，内容全面丰富、资料翔实权威、实用性强。自1987年创刊以来，已连续出版34年，忠实地记录了我国法治建设发展情况。”
  - Evidence comes from: the official page itself
  - Why this counts as official: institutional domain; provider sentence quoted by the model found on the page (provider identity is a model judgment)
  - Note: the paper states no version or years, so version correspondence could not be checked
  - Note: the model said this is the product the paper used, but nothing in the paper pins the version, so purchase is shown for this page's product only — the channel for the paper's product is pending
  - Channel, eligibility and version correspondence are model judgments on the quoted official text.

- **Access: public publication; available in libraries or on statistics bureau websites** (basis: the tool's built-in database list; not stated in the paper — no statement found)
  - Paper evidence: no paper states an access condition
  - 📚 Database hint: Statistical yearbook publications; usually available in libraries or on statistics bureau websites. Check that the years and geographic levels you need are complete (the edition year is usually one year later than the data year)
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
- Per paper:
  - Kahn2020: [no statement found] China Law Yearbook
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 5: “Data on population size are from the China Law Yearbook in various years.”
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## China National Environmental Monitoring Center daily API data　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now (not verified) |
|---|---|---|
| Access channel | no channel stated (access: partly public; check on the official site whether the specific data can be downloaded) | official page found but the program could not read it — please check manually |
| Eligibility | not stated | — |
| Use restrictions | none stated | — |
| Version | not stated | — |
| Source | see per-paper evidence below | — |

  - Please open: https://www.cnemc.cn/gzdt/wjtz/201603/P020181010644008533922.pdf

- **Access: partly public; check on the official site whether the specific data can be downloaded** (basis: the tool's built-in database list; not stated in the paper — no statement found)
  - Paper evidence: no paper states an access condition
  - 🏛 Database hint: Data published by government departments; some can be queried or downloaded on the official site, some require registration or an application. Check the years and levels you need on the department's website
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
  - Sample years used by prior papers (that the period belongs to this data is a model judgment): 
    - 2010–2012 (continuous range, period form unverified: the period quote does not connect the start and end years as a range, not counted in "latest year used"; Chang2016) — p. 5: “Our data span the period from January 1, 2010 to December 9, 2012, with different coverage periods for the two offices.”
- Per paper:
  - Chang2016: [no statement found] China National Environmental Monitoring Center (CNEMC) daily API data
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 6: “Our daily pollution data are obtained from the China National Environmental Monitoring Center (CNEMC), which is affiliated with the Ministry of Environmental Protection of China.”
    - Provider (extracted by the model; not an access channel): China National Environmental Monitoring Center (CNEMC), affiliated with the Ministry of Environmental Protection of China (this wording does not appear verbatim in the source sentence; compare with the source text above)
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## Ctrip call center worker productivity data　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now |
|---|---|---|
| Access channel | no channel stated (access: not confirmed (initial AI judgment: restricted)) | not checked |
| Eligibility | not stated | — |
| Use restrictions | none stated | — |
| Version | not stated | — |
| Source | see per-paper evidence below | — |

- **Access: not confirmed (initial AI judgment: restricted)** (basis: the quote has no clear expression supporting this category; see the source text)
  - Paper evidence: restricted: 0 papers verified, 1 paper with only an initial AI judgment (not verified)
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
  - Sample years used by prior papers (that the period belongs to this data is a model judgment): 
    - 2010–2012 (continuous range, period form unverified: the period quote does not connect the start and end years as a range, not counted in "latest year used"; Chang2016) — p. 5: “Our data span the period from January 1, 2010 to December 9, 2012, with different coverage periods for the two offices.”
- Per paper:
  - Chang2016: [unclear wording] Ctrip call center worker productivity data — p. 5 (needs manual review: initial AI judgment was restricted, but the quote has no clear expression supporting this category): “The difference in data coverage periods is due to a combination of pollution data availability and the time coverage of the productivity data provided by the firm.”
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 5: “Our analysis is focused on Ctrip's call center workers in Shanghai and Nantong who book travel for clients throughout China.”
    - Provider (extracted by the model; not an access channel): Ctrip International (appears verbatim in the source sentence on p. 5)
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## Daily data set of surface weather data in China , China Meteorological Data Service Center　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now |
|---|---|---|
| Access channel | no channel stated (access: partly public; check on the official site whether the specific data can be downloaded) | no verified official access route found within the step budget — please check this yourself |
| Eligibility | not stated | — |
| Use restrictions | none stated | — |
| Version | daily data set of surface weather data in China (V3.0) (Chen2021) | — |
| Source | see per-paper evidence below | — |

  - Leads from the check (not verified; open them and judge yourself):
    - https://data.cma.cn/data/cdcindex/cid/6d1b5efbdcbf9a58.html (read during the check)
    - https://data.cma.cn/site/subjectdetail/id/101.html (read during the check)
    - https://data.cma.cn/data/cdcdetail/dataCode/SURF_CLI_CHN_MUL_DAY_V3.0.html (read during the check)
    - http://k.data.cma.cn/mekb/?r=dataService/cdcindex&datacode=SURF_CLI_CHN_MUL_DAY_CES_V3.0&show_value=normal (read during the check)

- **Access: partly public; check on the official site whether the specific data can be downloaded** (basis: the tool's built-in database list; not stated in the paper — no statement found)
  - Paper evidence: no paper states an access condition
  - 🏛 Database hint: Data published by government departments; some can be queried or downloaded on the official site, some require registration or an application. Check the years and levels you need on the department's website
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
  - Sample years used by prior papers (that the period belongs to this data is a model judgment): 
    - July 2004–August 2015 (continuous range, period form unverified: some years do not appear in the period quote, not counted in "latest year used"; Chen2021) — p. 6: “Fig. 2 compares the time trend of the average monthly API and cumulative times of the atmospheric inversion during our study period.”
- Per paper:
  - Chen2021: [no statement found] Daily data set of surface weather data in China (V3.0), China Meteorological Data Service Center
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 6: “By combining prison factory data, API, atmospheric inversion, and meteorological data altogether, we ﬁnally construct an individual-monthly panel data set.”
    - Version / file used in this paper: daily data set of surface weather data in China (V3.0) (source text located) — p. 6: “We use the daily data set of surface weather data in China (V3.0).”
    - Provider (extracted by the model; not an access channel): China Meteorological Data Service Center (appears verbatim in the source sentence on p. 6)
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## MERRA-2 (NASA)　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now |
|---|---|---|
| Access channel | no channel stated (access: free download (some require an account)) | no verified official access route found — please check this yourself |
| Eligibility | not stated | — |
| Use restrictions | none stated | — |
| Version | not stated | — |
| Source | see per-paper evidence below | — |

  - Leads from the check (not verified; open them and judge yourself):
    - https://disc.gsfc.nasa.gov/datasets/M2T1NXSLV_5.12.4/summary?keywords=MERRA2 (page found, but the quoted sentence does not say how to obtain the data — open it and look for a download or application page for the data the paper used)
    - https://disc.gsfc.nasa.gov/data-access (read during the check)

- **Access: free download (some require an account)** (basis: the tool's built-in database list; not stated in the paper — no statement found)
  - Paper evidence: no paper states an access condition
  - 🌐 Database hint: Data published by research institutions (e.g. NASA, climate models, satellite products); usually free to download from the official site, some require an account
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
  - Sample years used by prior papers (that the period belongs to this data is a model judgment): 
    - July 2004–August 2015 (continuous range, period form unverified: some years do not appear in the period quote, not counted in "latest year used"; Chen2021) — p. 6: “Fig. 2 compares the time trend of the average monthly API and cumulative times of the atmospheric inversion during our study period.”
- Per paper:
  - Chen2021: [no statement found] MERRA-2 satellite images (NASA)
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 5: “The atmospheric inversion (monthly times) is used as an instrumental variable of air pollution in our analysis.”
    - Provider (extracted by the model; not an access channel): NASA (appears verbatim in the source sentence on p. 5)
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## Online transcripts of judicial decisions　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now (checked 2026-11-18) |
|---|---|---|
| Access channel | no channel stated (access: cannot determine) | free download after registration — the page does not name the years / version the paper used; whether they are covered is pending |
| Eligibility | not stated | individuals can apply |
| Use restrictions | none stated | none stated on the page |
| Version | not stated | not confirmed: the page does not name the years / volumes the paper used |
| Source | see per-paper evidence below | https://wenshu.court.gov.cn/website/wenshu/181109AWZA70BFK4/index.html — found via previously verified official domain |

  - Official-site text (access): “登录的用户，在列表页点击 “下载”按钮、在全文页点击、在个人中心-我的收藏-案例包-文书列表页中点击，可以实现裁判文书下载。”
  - Official-site text (version): “中国裁判文书网，除拥有检索、查看、收藏、分享、下载的主体功能外，同时提供用户注册、登录”
  - Evidence comes from: the official page itself
  - Why this counts as official: previously verified official domain (wenshu.court.gov.cn)
  - Note: the paper used 2014–2017, but the quoted page text does not name these years or this version — whether they are covered is pending
  - Channel, eligibility and version correspondence are model judgments on the quoted official text.

- **Access: cannot determine** (basis: not stated in the paper, and this data is not in the tool's list — no statement found)
  - Paper evidence: no paper states an access condition
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
  - Sample years used by prior papers (that the period belongs to this data is a model judgment): latest year used 2017 (Kahn2020)
    - 2014–2017 (continuous range, period form consistent with the source text; Kahn2020) — p. 4: “We collect over 13 million criminal and civil cases adjudicated between 2014 and 2017 by 157 378 judges across China.”
- Per paper:
  - Kahn2020: [no statement found] Online transcripts of judicial decisions
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 4: “Our main data source is online transcripts of judicial decisions.11 These documents first became available online in late 2013 in a handful of courts, and cov- erage widened over time.”
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## Population census / 1% population sample survey　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now |
|---|---|---|
| Access channel | no channel stated (access: individual-level microdata require a formal application and are generally hard to obtain) | no verified official access route found — please check this yourself |
| Eligibility | not stated | — |
| Use restrictions | none stated | — |
| Version | not stated | — |
| Source | see per-paper evidence below | — |

  - Leads from the check (not verified; open them and judge yourself):
    - https://www.stats.gov.cn/sj/ndsj/2011/html/D0309C.HTM (page found, but the quoted sentence does not say how to obtain the data — open it and look for a download or application page for the data the paper used)
    - https://www.stats.gov.cn/sj/pcsj/rkpc/6rp/indexch.htm (read during the check)
    - https://www.stats.gov.cn/sj/pcsj/rkpc/6rp/html/fu05.htm (read during the check)
    - https://www.stats.gov.cn/sj/pcsj/rkpc/6rp/ (read during the check)
    - https://www.stats.gov.cn/zt_18555/zdtjgz/zgrkpc/d6crkpc/dlcrkpczl/index.html (read during the check)

- **Access: individual-level microdata require a formal application and are generally hard to obtain** (basis: the tool's built-in database list; not stated in the paper — no statement found)
  - Paper evidence: no paper states an access condition
  - 🔒 Database hint: Government microdata survey; individual-level data usually require a formal application or are unavailable. Aggregate figures can be found in published statistics
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
  - Sample years used by prior papers (that the period belongs to this data is a model judgment): latest year used 2010 (Kahn2020)
    - 2010 (single year, period form consistent with the source text; Kahn2020) — p. 11: “Data source: China Census 2010.”
- Per paper:
  - Kahn2020: [no statement found] China Census 2010
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 11: “All shares reported in this table are weighted by prefecture total population in the year 2010.”
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## Prison factory labor administrative data　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now |
|---|---|---|
| Access channel | no channel stated (access: cannot determine) | no verified official access route found — please check this yourself |
| Eligibility | not stated | — |
| Use restrictions | none stated | — |
| Version | not stated | — |
| Source | see per-paper evidence below | — |

  - Leads from the check (not verified; open them and judge yourself):
    - https://sf.sz.gov.cn/szjy/xxgk/cjwtdf/content/post_12054295.html (read during the check)

- **Access: cannot determine** (basis: not stated in the paper, and this data is not in the tool's list — no statement found)
  - Paper evidence: no paper states an access condition
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
  - Sample years used by prior papers (that the period belongs to this data is a model judgment): latest year used 2015 (Chen2021)
    - July 2004–August 2015 (continuous range, period form consistent with the source text; Chen2021) — p. 4: “The data we use cover all jail inmates who had ever incarcerated in this prison from July 2004 to August 2015”
- Per paper:
  - Chen2021: [no statement found] Prison factory labor administrative data (Shenzhen male prison)
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 6: “By combining prison factory data, API, atmospheric inversion, and meteorological data altogether, we ﬁnally construct an individual-monthly panel data set.”
    - Provider (extracted by the model; not an access channel): a male prison in Shenzhen, China (appears verbatim in the source sentence on p. 4)
    - Access channel recorded in the paper: not recorded in the current extraction results (this does not mean the paper does not describe one)

## Weather data from China Meteorological Data Sharing Service System　(used by 1 paper)

| | In the papers (what prior authors used) | Official site now (not verified) |
|---|---|---|
| Access channel | no channel stated (access: partly public; check on the official site whether the specific data can be downloaded) | official page found but the program could not read it — please check manually |
| Eligibility | not stated | — |
| Use restrictions | none stated | — |
| Version | not stated | — |
| Source | see per-paper evidence below | — |

  - Please open: http://cdc.cma.gov.cn/

- **Access: partly public; check on the official site whether the specific data can be downloaded** (basis: the tool's built-in database list; not stated in the paper — no statement found)
  - Paper evidence: no paper states an access condition
  - 🏛 Database hint: Data published by government departments; some can be queried or downloaded on the official site, some require registration or an application. Check the years and levels you need on the department's website
- **Historical use record:** the paper makes no statement about narrowing the sample for data reasons (this does not mean the data are complete; check the variables, years, and regions you need)
  - Sample years used by prior papers (that the period belongs to this data is a model judgment): latest year used 2017 (Kahn2020)
    - 2013–2017 (continuous range, period form consistent with the source text; Kahn2020) — p. 4: “Those data contains daily readings from 820 weather stations in China during the 2013 to 2017 period.”
- Per paper:
  - Kahn2020: [no statement found] Weather data from China Meteorological Data Sharing Service System
    - Basis for "used in this paper" (the usage relation is a model judgment; source text located): p. 4: “Weather data are collected from China Meteorological Data Sharing Service System (http://cdc.cma.gov.cn/).”
    - Provider (extracted by the model; not an access channel): China Meteorological Data Sharing Service System (appears verbatim in the source sentence on p. 4)
    - Link in the paper's text: http://cdc.cma.gov.cn/ (extracted mechanically; not claimed to be an access channel; the tool has not checked whether it is an official entry point or still works) — p. 4: “Weather data are collected from China Meteorological Data Sharing Service System (http://cdc.cma.gov.cn/).”

## Usage relation to be confirmed
The usage relation of the following records cannot be confirmed (the model judged it undeterminable, or its basis cannot be found in the source text). They are excluded from the "used in this paper" count and from the year record.

- Chang2016: Ctrip work-from-home experiment data (the basis for the usage relation cannot be found in the source text) — p. 5: “An additional feature of our data is that, during part of our study period, Ctrip performed a controlled experiment to analyze whether working from home affected worker performance.”
- Chang2016: Call quality audit data (the model judged it undeterminable) — p. 5: “Call quality was assessed based on a 1 percent sample of recorded call transcripts that were audited and scored by an external review team.”

## Excluded / candidates to check
The following entries were not counted as data sources used in the paper, for the reasons given. Source text is shown only for quotes verified in the paper.

- Chang2016: Shanghai precipitation data (the paper does not say where the data come from; possibly just a variable) — p. 19: “Columns 4 and 5 of Table 8 repeat this exercise, but focus on precipitation.”

## Paper-level sample restrictions (attribution unverified)
The following statements do not name a specific data source, so the program cannot confirm which data source they belong to. Please judge from the source text.

- Chang2016 p. 5: “The difference in data coverage periods is due to a combination of pollution data availability and the time coverage of the productivity data provided by the firm.”
- Chang2016 p. 19: “Unfortunately, such data are only available for Shanghai, so we only show results focusing on workers in that city.”
- Chang2016 p. 8: “Unfortunately, we only observe worker type for a subset of Shanghai workers.”
- Chang2016 p. 11: “Because we have "timeclock" data for only a subset of our sample, the number of observations drops to 171,713 when examining shift length.”

## Items to verify (applies to all data above)
Papers record the data and channels that prior authors used at the time. Before using the data, check each item with the data provider:

- Current version, and the latest available data year
- Whether the variables and geographic levels you need are included
- Download or application conditions (eligibility, agreements, fees, approval time)
- Official link and date checked: see "Official site now" under each source. Only pages the program could read and verify are shown as findings; official pages it could not read are listed for you to open


## Not yet confirmed

- How does China's air pollution influence its labor wage distortions? Theoretical and empirical analysis from the perspective of spatial spillover effects (2020, The Science of The Total Environment): not freely available - upload it if you can get it. https://doi.org/10.1016/j.scitotenv.2020.140843
- Is air pollution detrimental to regional innovation? Evidence from Chinese cities (2020, Growth and Change): not freely available - upload it if you can get it. https://doi.org/10.1111/grow.12445

Nothing is inferred about papers that could not be read. Access conditions are as described by the authors at the time of publication; check them with the data provider.
