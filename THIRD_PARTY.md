# Third-party material

The MIT License in `LICENSE` covers the code and documentation written for this project. It does **not** cover the third-party material listed below. That material belongs to its original authors and publishers. It is included only to show what the program reads and reports. No permission has been obtained from the rights holders, and this note does not grant any right to reuse the material.

## Short quotations from published papers

The program's output consists of short verbatim quotations from papers, each with its page number. Such quotations appear in the demo files and in some test files.

| Where | Papers quoted |
|---|---|
| `demo/outputs/normal.md`, `demo/data/yip2018_1105_105410_run1.json` | Yip (2018). *Journal of Environmental Economics and Management*, 89, 136–152 |
| `demo/outputs/review.md`, `demo/data/A_Liebman1998.json` | Liebman (1998). The Impact of the Earned Income Tax Credit on Incentives and Income Distribution. *Tax Policy and the Economy*, 12. https://doi.org/10.1086/tpe.12.20061856 |
| `demo/outputs/official.md` | Chang, Graff Zivin, Gross & Neidell (2019). The Effect of Pollution on Worker Productivity: Evidence from Call Center Workers in China. *AEJ: Applied Economics* 11(1), 151–172. https://doi.org/10.1257/app.20160436; Kahn & Li (2020). Air pollution lowers high skill public sector worker productivity in China. *Environmental Research Letters* 15, 084003. https://doi.org/10.1088/1748-9326/ab8b8c; Chen & Zhang (2021). Impact of air pollution on labor productivity: Evidence from prison factory data. *China Economic Quarterly International* 1, 148–159. https://doi.org/10.1016/j.ceqi.2021.04.004 |
| `test_final_report.py` (synthetic tests reusing single sentences) | Yip (2018); Yu, Lei & Wang (2019), *JEEM* 96, 195–212; Teng et al. (2026), *The Energy Journal* 47(2), 31–49; Liebman (1998) (a shortened sentence) |
| Default tests `test_step3.py` (single sentences) and `test_official.py` (one sentence) | `test_step3.py`: Deng et al. (2020); Yu, Lei & Wang (2019); Li, Liu & Salvo (2015); Khanna, Liang, Mobarak & Song (2021); Yin, Meng, Dong & Li (2025); Zhou, Zhong & Yang (2022); Wei, Jiang & Chen (2023); Chen, Oliva & Zhang (2022). `test_official.py`: Yu, Lei & Wang (2019) |
| Optional paper tests (`test_step1.py`, `test_step2.py`, `test_contract.py`, `test_agent.py`, `test_phase2.py`, `test_final_report_papers.py`) and comments in `step1_pdf_evidence.py`, `step2_ai_extract.py`, `step3_merge.py` | Yip (2018); Chen, Oliva & Zhang (2022), *Journal of Development Economics* 156, 102833; Deng et al. (2020), *J. Environ. Manage.* 275, 111224; Yu, Lei & Wang (2019); Li, Liu & Salvo (2015), NUS working paper; Khanna, Liang, Mobarak & Song (2021), CEPR DP15994; Borgschulte, Molitor & Zou (2022), NBER WP 29952; Teng et al. (2026); Yin, Meng, Dong & Li (2025), *Economic Analysis and Policy*; Yu & Zhang (2021), *Energy Economics*; Zhou, Zhong & Yang (2022), *Frontiers in Public Health* 9, 798780; Wei, Jiang & Chen (2023), *Energy Economics* 125, 106862; Beck, Rivers, Wigle & Yonezawa (2015), *Resource and Energy Economics* 41, 40–69; Li, Lu & Li (2020), *Sustainable Cities and Society* 56, 102092; Li, Du & Zhang (2020), *Risk Management and Healthcare Policy* 13; Liebman (1998); Bowen et al. (2011), *Climatic Change* |

Checked sentence by sentence on 2026-11-18: every quotation of eight or more words in the released files was searched for in the local copies of the papers. 59 were found and are attributed above; for Liebman (1998) there is no local PDF, so its 9 quotations were checked against the saved extraction: 8 were verified against the PDF when that extraction was made, 1 was marked unverified at the time (model output, shown as unconfirmed). The remaining strings are synthetic test sentences or the program's own text.

`demo/outputs/official.md` (added 2026-11-18): its 33 paper quotations were checked against local copies of the three papers above (all found; one is interrupted by a footnote in the PDF; recounted after the v2.5c re-verification).

## Quotations from websites

`demo/outputs/official.md` also quotes short passages (one to two sentences each, 10 in total) from the web pages the official-site check read on 2026-11-18, with their URLs: National Bureau of Statistics of China (stats.gov.cn), China Judgements Online (wenshu.court.gov.cn), the China Law Yearbook publisher (chinalaw.org.cn), Baidu Index help pages (index.baidu.com) and NASA GES DISC (disc.gsfc.nasa.gov). They remain the property of the site owners.

## Bibliographic metadata

`demo/data/fallback/candidates.json` and `demo/data/fallback/run.json` contain search results from [OpenAlex](https://openalex.org): titles, authors, venues, DOIs and links. They are copies of a real run, kept so that the fallback demo replays real data; the paper abstracts were removed before release (2026-11-17), everything else is unchanged.

## Paper PDFs

Paper PDFs are not included.

## Model output

The saved extraction outputs in `demo/data/` were produced by Google Gemini models. Their quoted sentences are text from the papers listed above.
