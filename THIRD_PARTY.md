# Third-party material

The MIT License in `LICENSE` covers the code and documentation written for this project. It does **not** cover the third-party material listed below. That material belongs to its original authors and publishers. It is included only to show what the program reads and reports. No permission has been obtained from the rights holders, and this note does not grant any right to reuse the material.

## Short quotations from published papers

The program's output consists of short verbatim quotations from papers, each with its page number. Such quotations appear in the demo files and in some test files.

| Where | Papers quoted |
|---|---|
| `demo/outputs/normal.md`, `demo/data/yip2018_1105_105410_run1.json` | Yip (2018). *Journal of Environmental Economics and Management*, 89, 136–152 |
| `demo/outputs/review.md`, `demo/data/A_Liebman1998.json` | Liebman (1998). The Impact of the Earned Income Tax Credit on Incentives and Income Distribution. *Tax Policy and the Economy*, 12. https://doi.org/10.1086/tpe.12.20061856 |
| `demo/outputs/vertical_integration_report.md`, `docs/index.html` (one sentence, p. 4) | Yuan, Geng, Sun & Cui (2022). Vertical integration and corporate value under uncertainty shock: Evidence from the COVID-19 pandemic. *China Economic Quarterly International* 2, 239–251. https://doi.org/10.1016/j.ceqi.2022.11.002 (open access, CC BY-NC-ND) |
| `docs/index.html` (one sentence, p. 4, shortened with “…”) | Kahn & Li (2020), listed in the next row |
| `demo/outputs/official.md` | Chang, Graff Zivin, Gross & Neidell (2019). The Effect of Pollution on Worker Productivity: Evidence from Call Center Workers in China. *AEJ: Applied Economics* 11(1), 151–172. https://doi.org/10.1257/app.20160436; Kahn & Li (2020). Air pollution lowers high skill public sector worker productivity in China. *Environmental Research Letters* 15, 084003. https://doi.org/10.1088/1748-9326/ab8b8c; Chen & Zhang (2021). Impact of air pollution on labor productivity: Evidence from prison factory data. *China Economic Quarterly International* 1, 148–159. https://doi.org/10.1016/j.ceqi.2021.04.004 |

**Tests and code comments (since 2026-11-23):** the public tests and the code comments use synthetic sentences written for this project. Earlier versions reused single sentences from papers there (Yip 2018; Yu, Lei & Wang 2019; Teng et al. 2026; Deng et al. 2020; Li, Liu & Salvo 2015; Khanna, Liang, Mobarak & Song 2021; Yin, Meng, Dong & Li 2025; Zhou, Zhong & Yang 2022; Wei, Jiang & Chen 2023; Chen, Oliva & Zhang 2022; Li, Lu & Li 2020; Liebman 1998); those sentences were replaced. Tests that read real paper PDFs are not distributed. Institution and dataset names (for example "Data Center for Resources and Environmental Sciences, Chinese Academy of Sciences") are kept.

Checked sentence by sentence on 2026-11-18 (for the files distributed at that time): every quotation of eight or more words in the released files was searched for in the local copies of the papers. 59 were found and are attributed above; for Liebman (1998) there is no local PDF, so its 9 quotations were checked against the saved extraction: 8 were verified against the PDF when that extraction was made, 1 was marked unverified at the time (model output, shown as unconfirmed). The remaining strings are synthetic test sentences or the program's own text.

Added on 2026-11-23: the Yuan et al. (2022) sentence was found word for word in the local PDF (PDF page 4, journal page 242); the Kahn & Li (2020) sentence in `docs/index.html` is the first sentence of a quotation already in `demo/outputs/official.md`. `site/build_site.py` takes every quotation on the page from the saved results unchanged, and `test_site.py` checks this.

`demo/outputs/official.md` (added 2026-11-18): its 33 paper quotations were checked against local copies of the three papers above (all found; one is interrupted by a footnote in the PDF; recounted after the v2.5c re-verification).

## Quotations from websites

`demo/outputs/official.md` also quotes short passages (one to two sentences each, 10 in total) from the web pages the official-site check read on 2026-11-18, with their URLs: National Bureau of Statistics of China (stats.gov.cn), China Judgements Online (wenshu.court.gov.cn), the China Law Yearbook publisher (chinalaw.org.cn), Baidu Index help pages (index.baidu.com) and NASA GES DISC (disc.gsfc.nasa.gov). They remain the property of the site owners.

`docs/index.html` repeats one of them (China Judgements Online, wenshu.court.gov.cn) unchanged, with an English reference translation written for this project and marked on the page as not part of the tool's output.

## Bibliographic metadata

`demo/outputs/access_table_ja.md` and `demo/outputs/access_table_round3_replay_ja.md` list the titles of 13 papers in *China Economic Quarterly International* vol. 2 (2022), issues 3–4 (open access, CC BY-NC-ND), with the names of the data they used, sample years and page numbers. They contain no quotations from the papers. The titles are taken from the PDFs' metadata (since 2026-11-23). `docs/index.html` also shows the title of one of them: Xiong, Wan & Liang (2022). On foreign-invested enterprises’ exit: Economic development or labor market price regulation? *China Economic Quarterly International* 2, 215–226. https://doi.org/10.1016/j.ceqi.2022.08.006

`demo/data/fallback/candidates.json` and `demo/data/fallback/run.json` contain search results from [OpenAlex](https://openalex.org): titles, authors, venues, DOIs and links. They are copies of a real run, kept so that the fallback demo replays real data; the paper abstracts were removed before release (2026-11-17), everything else is unchanged.

## Paper PDFs

Paper PDFs are not included.

## Model output

The saved extraction outputs in `demo/data/` were produced by Google Gemini models. Their quoted sentences are text from the papers listed above.
