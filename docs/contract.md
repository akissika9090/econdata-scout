# Contract: what each part may decide

The model's output is a candidate. The program checks it, and a check that fails never deletes information: the record stays visible with the reason.

## Fields of a data source

| Field | Meaning | Written by |
|---|---|---|
| `ai_category` | The model's original access category (public / subscription / restricted / unknown). Never changed afterwards | Extraction |
| `access_evidence` | The quote and page the model gave. `verified` only means the quote appears verbatim on that page | Extraction (Agent may replace it) |
| `verification` | Result of the access check: `verified`, or the reason it failed (quote not found, multi-sentence, no supporting expression, conflict, general statement, unclear reference, anaphoric sentence, another source named, scope unverified) | `step2.access_status()` (shared by extraction and Agent) |
| `access_category` | The current conclusion. Equals the submitted category only when `verification == verified`; otherwise "unknown" (unconfirmed) | Same |
| `access_scope` | Which part a verified condition applies to: `whole`, a part name found verbatim in the condition sentence, or `not_recorded` for older results that have no scope field | Same |
| `usage` / `usage_evidence` | Used in this paper / cites others / background, with its quote. Only "used in this paper" with a verified quote counts as used | Extraction; checked in step2 |
| `sample_period`, `period_form`, `period_years` | Sample years with their form (single / discrete / range); the form is checked against the period quote | Extraction; checked in step2 |

## When an access condition is accepted

The checks run in order, and the first failure stops them:

1. The quote appears verbatim on the stated page. If it is on another page, the page is corrected and the model's page is kept.
2. The quote is a single sentence.
3. It contains an expression that supports the category, and not both public and restricted expressions.
4. The sentence itself names this data.
5. The sentence does not name another data source of the same paper.
6. If the model says the condition applies only to a part, that part's name appears in the sentence.

Steps 2, 4 and 5 are deliberately conservative: when the program cannot decide, the record goes to manual review instead of becoming a conclusion. A lexical clue (for example "public use" inside a source sentence that the model did not classify) is shown as a clue and never becomes a conclusion.

## Report rules

- Every conclusion shows its basis. A failed check shows its reason and is not shown as "the paper does not say".
- Older results without a scope field show "original record category: X; scope not recorded" with the quote. They are not stated as a condition of the whole dataset.
- URLs are extracted mechanically from verified quotes and shown as "links in the paper's text". They are not claimed to be access channels, and they are not verified. Providers are shown separately and are not channels either. Records with no link say "not recorded in the current extraction results".
- Sample years are a historical record. The tool does not judge whether they meet the user's needs.
- Paper-level sample restrictions are not attributed to a data source automatically.
- The checklist of items to verify with the data provider appears once, at the end.
