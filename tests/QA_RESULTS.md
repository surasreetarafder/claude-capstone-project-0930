# QA Results — HelixNova Pharma Quality & Regulatory RAG Assistant

**Date:** 2026-09-29
**Version tested:** `app.py` with advanced extensions (multi-document retrieval, document filters, evaluation dataset, RAG quality dashboard)
**Overall result:** ✅ **PASS — 15 / 15 tests passed, no defects found, no code changes needed**

## Summary

### Core RAG tests (regression)

| # | Test | Result |
|---|------|--------|
| 1 | PDF upload works | ✅ PASS |
| 2 | TXT upload works | ✅ PASS |
| 3 | Text extraction works | ✅ PASS |
| 4 | Chunking works | ✅ PASS |
| 5 | Embeddings are created | ✅ PASS |
| 6 | FAISS retrieval works | ✅ PASS |
| 7 | Relevant chunks are sent to Claude | ✅ PASS |
| 8 | Claude answers from document context | ✅ PASS |
| 9 | Unsupported questions return the fallback response | ✅ PASS |
| 10 | API keys are not hardcoded | ✅ PASS |

### Advanced extensions

| # | Test | Result |
|---|------|--------|
| 11 | Multi-document retrieval with source attribution | ✅ PASS |
| 12 | Similarity score display | ✅ PASS |
| 13 | Document-level filters | ✅ PASS |
| 14 | Evaluation dataset with expected answers | ✅ PASS |
| 15 | Simple RAG quality dashboard | ✅ PASS |

## Evidence

### Core RAG tests

| # | Evidence |
|---|----------|
| 1 | `helixnova_pharma_quality_policy_dataset.pdf` (15,310 chars, 24 chunks) and `tests/quality_manual.pdf` (2 pages, 8 chunks) processed with no errors |
| 2 | `helixnova_pharma_quality_policy_dataset.txt` (15,459 chars, 24 chunks) and `tests/quality_manual.txt` (8 chunks) processed with no errors |
| 3 | Extracted text matches the source text; key policy facts ("within 30 minutes of discovery", "Global Recall Committee", etc.) present |
| 4 | All chunks ≤ 750 characters, 100-character overlap, numbered 1..n, each tagged with its filename |
| 5 | One 384-dimension vector per chunk stored in FAISS (e.g. 24 / 24) |
| 6 | Exactly 5 chunks returned, sorted by similarity; the chunk containing the answer is retrieved (top score 0.55–0.59) |
| 7 | One Claude request per question containing only the 5 retrieved chunks + the question; the full document and chat history are not sent |
| 8 | "How quickly must a Critical deviation be reported?" → "Site Quality Head within 30 minutes of discovery (Chunk 3)", matching the policy |
| 9 | "Recommended dose of ibuprofen for children?" and "Maximum dosage of paracetamol?" → exactly *"I could not find the answer to this question in the uploaded policy document."* with Sources used: none |
| 10 | No keys in any project file; the key is read from `ANTHROPIC_API_KEY` (environment or `.env`); `.env` is in `.gitignore` |

### Advanced extensions

Tested with two documents uploaded together: `helixnova_pharma_quality_policy_dataset.txt` and `tests/quality_manual.txt`.

| # | Evidence |
|---|----------|
| 11 | Both documents indexed together (24 + 8 = 32 chunks, 20,280 characters) with a per-document summary table. A batch-records question was answered from both files, and "Sources used" listed `quality_manual.txt — Chunk 3` and `helixnova_pharma_quality_policy_dataset.txt — Chunk 21`. Both chunks contain batch-record retention rules, and every cited source was among the retrieved chunks. |
| 12 | Every retrieved chunk shows its similarity score (2 decimals) in the "Retrieved source chunks" section; the dashboard also shows the top similarity per question and the average (0.56) |
| 13 | "Search in these documents" defaults to all documents. With only `quality_manual.txt` selected, all retrieved chunks came from that file. With only the policy selected, "How quickly must a Critical deviation be reported?" → "30 minutes", cited from the policy. The question box is disabled with a warning when no document is selected. |
| 14 | `eval_dataset.csv` loads 17 rows: 14 questions with expected answers, expected keywords and expected source, plus 3 questions not in the policy whose expected answer is the fallback message |
| 15 | "Run evaluation" ran all 17 questions with no errors and showed 5 metrics — Answer accuracy **100%**, Retrieval hit rate **100%**, Source accuracy **100%**, Fallback accuracy **100%**, Avg top similarity **0.56** — plus a 17-row ✅/❌ results table |

Chat history was also re-checked: all 3 questions and answers stayed visible across the filter changes.

## Test Runs

| Run | Documents | Checks | Result |
|-----|-----------|--------|--------|
| `py tests/qa.py` (regression, current version) | `tests/quality_manual.txt`, `tests/quality_manual.pdf` | 38 | 38 PASS, 0 FAIL |
| Advanced-extensions check (current version) | policy dataset `.txt` + `tests/quality_manual.txt` | 13 | 13 PASS, 0 FAIL* |
| Real-dataset check (previous version, before the extensions) | `helixnova_pharma_quality_policy_dataset.pdf` / `.txt` | 16 | 16 PASS, 0 FAIL |

\* One check first reported FAIL because the test expected every cited source to come from `quality_manual.txt`. Claude also cited the policy's Chunk 21, which does contain batch-record retention rules. The citation was correct and the test expectation was too strict, so this is recorded as PASS.

## Notes and Limitations

- Uploads were tested by passing each file directly to the app in Streamlit's test runner (`tests/driver.py`), because the runner cannot use a browser upload box. Streamlit's own PDF/TXT-only restriction on the upload box and clicking through the page in a browser were not tested.
- The real-dataset PDF/TXT check was run before the extensions were added and has not been re-run on the current version; the core pipeline is covered by the current regression run above.
- The dashboard scores answers by keyword matching against `eval_dataset.csv` (e.g. "30 minutes", "Site Quality Head"). It is a simple check, not a full judgement of answer quality.
- The evaluation run used both documents together; results may differ with other document combinations.
- Tests 7–9, 11, 13 and 15 use real Claude API calls (`claude-opus-5-5`), so the exact wording of answers can vary between runs.

## How to Re-run

```
py tests/qa.py
```
Needs `ANTHROPIC_API_KEY`; makes 4 Claude API calls.

To re-run the quality dashboard, open the app, upload `helixnova_pharma_quality_policy_dataset` (PDF or TXT) and click **Run evaluation** in Section 3 (17 Claude API calls).
