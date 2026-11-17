# Third-party material

The MIT License in `LICENSE` covers the code and documentation written for this project. It does **not** cover the third-party material listed below. That material belongs to its original authors and publishers. It is included only to show what the program reads and reports. No permission has been obtained from the rights holders, and this note does not grant any right to reuse the material.

## Short quotations from published papers

The program's output consists of short verbatim quotations from papers, each with its page number. Such quotations appear in the demo files and in some test files.

| Where | Papers quoted |
|---|---|
| `demo/outputs/normal.md`, `demo/data/yip2018_1105_105410_run1.json` | Yip (2018). *Journal of Environmental Economics and Management*, 89, 136–152 |
| `demo/outputs/review.md`, `demo/data/A_Liebman1998.json` | Liebman (1998). The Impact of the Earned Income Tax Credit on Incentives and Income Distribution. *Tax Policy and the Economy*, 12. https://doi.org/10.1086/tpe.12.20061856 |
| `test_final_report.py` (synthetic tests reusing single sentences) | Yip (2018); Yu, Lei & Wang (2019), *JEEM* 96, 195–212; Teng et al. (2026), *The Energy Journal* 47(2), 31–49 |
| Optional paper tests (`test_step1.py`, `test_step2.py`, `test_contract.py`, `test_agent.py`, `test_phase2.py`, `test_final_report_papers.py`) and comments in `step2_ai_extract.py`, `step3_merge.py` | Deng et al. (2020), *J. Environ. Manage.* 275, 111224; Yu, Lei & Wang (2019); Li, Liu & Salvo (2015), NUS working paper; Khanna, Liang, Mobarak & Song (2021), CEPR DP15994; Borgschulte, Molitor & Zou (2022), NBER WP 29952; Teng et al. (2026); Yin, Meng, Dong & Li (2025), *Economic Analysis and Policy*; Yu & Zhang (2021), *Energy Economics*; Zhou, Zhong & Yang (2022), *Frontiers in Public Health* 9, 798780; Wei, Jiang & Chen (2023), *Energy Economics* 125, 106862; Beck, Rivers, Wigle & Yonezawa (2015), *Resource and Energy Economics* 41, 40–69; Li, Lu & Li (2020), *Sustainable Cities and Society* 56, 102092; Li, Du & Zhang (2020), *Risk Management and Healthcare Policy* 13; Liebman (1998); Bowen et al. (2011), *Climatic Change* |

This list was compiled from paper identifiers found in the released files. A sentence-by-sentence check that every quotation is attributed has not been done yet.

## Bibliographic metadata

`demo/data/fallback/candidates.json` and `demo/data/fallback/run.json` contain search results from [OpenAlex](https://openalex.org): titles, authors, venues, DOIs and links. They are copies of a real run, kept so that the fallback demo replays real data. The paper abstracts that OpenAlex returned were removed before publication (the `abstract` fields are set to `null`); the demo does not use them.

## Paper PDFs

Paper PDFs are not included.

## Model output

The saved extraction outputs in `demo/data/` were produced by Google Gemini models. Their quoted sentences are text from the papers listed above.
