# Requirements: Simple Enterprise RAG Application

## 1. Purpose

Build a small **Retrieval-Augmented Generation (RAG)** web app for a beginner training session.
A user uploads a policy document (PDF or TXT) and asks questions about it. The app finds the most
relevant parts of the document and asks Claude to answer **using only those parts**.

The goal is to teach the core RAG steps clearly, not to build a production system.

---

## 2. Technology Stack

| Purpose            | Tool                                   |
| ------------------ | -------------------------------------- |
| Language           | Python 3.10+                           |
| User interface     | Streamlit                              |
| LLM                | Anthropic Claude API (`anthropic` SDK) |
| Embeddings         | `sentence-transformers`                |
| Vector store       | FAISS (`faiss-cpu`)                    |
| PDF text extraction| `pypdf`                                |

No other frameworks (e.g. LangChain, LlamaIndex) should be used, so learners can see every step.

---

## 3. High-Level Flow

```
Upload file ──► Extract text ──► Split into chunks ──► Embed chunks ──► Store in FAISS
                                                                            │
User question ──► Embed question ──► Search FAISS (top-k) ◄─────────────────┘
                                            │
                                            ▼
                        Build prompt (retrieved chunks + question)
                                            │
                                            ▼
                                    Claude API call
                                            │
                                            ▼
                   Show answer + sources (filename, chunk number, text)
```

---

## 4. Functional Requirements

### FR-1: Upload a document
- The user can upload **one** file using `st.file_uploader`.
- Allowed types: `.pdf` and `.txt`.
- Any other file type is rejected with a clear error message.
- The app shows the uploaded filename after a successful upload.

### FR-2: Extract text
- **PDF:** use `pypdf.PdfReader` and join the text of all pages.
- **TXT:** decode the file as UTF-8 text.
- If no text can be extracted (e.g. a scanned image PDF or empty file), show an error:
  *"No readable text was found in this document."* and stop processing.

### FR-3: Split into chunks
- Split the extracted text into chunks using a simple **character-based** splitter.
- Default settings (defined as constants at the top of the file):
  - `CHUNK_SIZE = 800` characters
  - `CHUNK_OVERLAP = 100` characters
- Each chunk keeps simple metadata:
  - `filename` – name of the uploaded file
  - `chunk_id` – chunk number, starting at 1
  - `text` – the chunk text
- The app displays how many chunks were created.

### FR-4: Create embeddings
- Use `sentence-transformers` with the model **`all-MiniLM-L6-v2`** (small, fast, runs on CPU).
- The embedding model is loaded once and cached with `@st.cache_resource`.
- Embeddings are normalized so that inner product equals cosine similarity.

### FR-5: Store embeddings in FAISS
- Use an in-memory `faiss.IndexFlatIP` index.
- The index and the chunk metadata list are stored in `st.session_state`.
- The index is rebuilt only when a **new** file is uploaded (not on every Streamlit rerun).
- Nothing is saved to disk.

### FR-6: Ask a question
- The user types a question using `st.chat_input`.
- The question box is available only after a document has been processed.

### FR-7: Retrieve relevant chunks
- Embed the question with the same embedding model.
- Search the FAISS index for the **top-k** most similar chunks.
- Default: `TOP_K = 3`.
- (Optional, simple) Ignore chunks below a minimum similarity score, e.g. `MIN_SCORE = 0.25`.
  If no chunk passes the threshold, skip the Claude call and return the fallback message (FR-10).

### FR-8: Send only retrieved context and question to Claude
- Call Claude with the official `anthropic` Python SDK (`client.messages.create`).
- Model: **`claude-opus-5-5`**, stored in a constant `CLAUDE_MODEL` so it is easy to change.
- The request contains **only**:
  1. A system prompt with grounding rules (see Section 6).
  2. The retrieved chunks, each labeled with its filename and chunk number.
  3. The user's question.
- The full document and earlier chat turns are **not** sent to Claude.
- The API key is read from the `ANTHROPIC_API_KEY` environment variable (or a `.env` file).
  It must never be hard-coded or shown in the UI.

### FR-9: Display grounded answer with sources
- Show Claude's answer in the chat area.
- Below the answer, show a **"Sources"** section (e.g. inside `st.expander`) listing each
  retrieved chunk with:
  - Filename
  - Chunk number
  - Similarity score (rounded to 2 decimals)
  - The chunk text

### FR-10: Clear fallback when the answer is not in the policy
- If the retrieved context does not contain the answer, Claude must reply with exactly:

  > **"I could not find the answer to this question in the uploaded policy document."**

- The same message is shown if no chunks pass the similarity threshold (FR-7).
- Claude must not guess or use outside knowledge.

### FR-11: Session-only chat history
- Chat history (questions, answers, sources) is stored in `st.session_state.messages`.
- The history is shown on screen each time the page reruns.
- History is lost when the browser tab is closed or the session ends — nothing is persisted.
- A **"Clear chat"** button in the sidebar resets the history.
- Uploading a new document also clears the history.

---

## 5. User Interface Layout

- **Title:** "Enterprise Policy Assistant (RAG Demo)"
- **Sidebar:**
  - File uploader (PDF / TXT)
  - Document status: filename and number of chunks
  - "Clear chat" button
- **Main area:**
  - Chat history (user and assistant messages using `st.chat_message`)
  - Each assistant message has a collapsible "Sources" section
  - Chat input box at the bottom
- Show a spinner (`st.spinner`) while processing the document and while waiting for Claude.

---

## 6. Prompt Requirements

**System prompt (example):**

```
You are a helpful assistant that answers questions about a company policy document.
Answer using ONLY the information in the provided context.
If the context does not contain the answer, reply exactly with:
"I could not find the answer to this question in the uploaded policy document."
Do not use outside knowledge. Keep answers short and clear.
When helpful, mention which chunk number(s) your answer came from.
```

**User message format (example):**

```
Context:
[Source: policy.pdf | Chunk 4]
<chunk text>

[Source: policy.pdf | Chunk 7]
<chunk text>

Question: <user question>
```

---

## 7. Error Handling

| Situation                         | Behaviour                                                  |
| --------------------------------- | ---------------------------------------------------------- |
| `ANTHROPIC_API_KEY` not set       | Show an error in the UI explaining how to set it.          |
| Unsupported file type             | Show an error; do not process the file.                    |
| No text extracted                 | Show an error; do not build the index.                     |
| Question asked with no document   | Chat input is disabled / show an info message.             |
| Claude API error (network, 429, etc.) | Show a friendly error message; the app must not crash. |
| Claude declines to answer (`stop_reason == "refusal"`) | Show the fallback message.            |

---

## 8. Non-Functional Requirements

- **Simplicity:** a single file `app.py` (roughly 150–250 lines), with small, well-named functions
  and short comments explaining each RAG step.
- **Beginner-friendly:** no classes or advanced patterns required; readable top-to-bottom.
- **Configuration:** all tunable values (`CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `MIN_SCORE`,
  `EMBEDDING_MODEL`, `CLAUDE_MODEL`, `MAX_TOKENS`) are constants at the top of `app.py`.
- **Performance:** processing a typical 20-page policy PDF should take under ~30 seconds on a laptop CPU.
- **Security:** API key only from environment; uploaded files are kept in memory only.
- **Runs locally** with: `streamlit run app.py`

---

## 9. Planned Project Files

| File               | Description                                   |
| ------------------ | --------------------------------------------- |
| `app.py`           | The Streamlit application (to be written later) |
| `requirements.txt` | Python dependencies                           |
| `.env.example`     | Template showing `ANTHROPIC_API_KEY=`          |
| `README.md`        | Setup and run instructions                    |
| `sample_policy.txt`| Small sample policy document for the demo     |

**Planned `requirements.txt` contents:**

```
streamlit
anthropic
faiss-cpu
sentence-transformers
pypdf
python-dotenv
```

---

## 10. Out of Scope

- Multiple documents at once
- User login / authentication
- Saving the FAISS index or chat history to disk or a database
- OCR for scanned PDFs
- Streaming responses, advanced chunking (by sentence/heading), re-ranking, or hybrid search
- Deployment to a cloud server

---

## 11. Acceptance Criteria

1. A user can upload a PDF or TXT file and see the number of chunks created.
2. Asking a question that **is** answered in the document returns a correct answer plus sources
   showing filename, chunk number, and chunk text.
3. Asking a question that is **not** in the document returns the exact fallback message.
4. Only the top-k retrieved chunks and the question are sent to Claude (verifiable by reading the code).
5. Chat history remains visible during the session and is cleared by "Clear chat",
   uploading a new file, or starting a new session.
6. The app starts with `streamlit run app.py` after installing `requirements.txt` and setting
   `ANTHROPIC_API_KEY`.
