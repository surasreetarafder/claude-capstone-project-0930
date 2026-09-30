# Specification: Simple Enterprise RAG Application

This document defines **how** the app works, step by step.
It builds on `requirements.md` (what to build) and `CLAUDE.md` (development rules).

> **Note:** The defaults in this specification (chunk size 750, top 5 chunks) replace the
> earlier values in `requirements.md` (800 and 3).

---

## 1. Default Settings

All settings are constants at the top of `app.py`.

| Setting           | Default              | Meaning                                    |
| ----------------- | -------------------- | ------------------------------------------ |
| `ALLOWED_TYPES`   | `["pdf", "txt"]`     | File types the user can upload             |
| `CHUNK_SIZE`      | `750`                | Characters per chunk (approximate)         |
| `CHUNK_OVERLAP`   | `100`                | Characters shared between adjacent chunks  |
| `TOP_K`           | `5`                  | Number of chunks retrieved per question    |
| `EMBEDDING_MODEL` | `"all-MiniLM-L6-v2"` | sentence-transformers model                |
| `CLAUDE_MODEL`    | `"claude-opus-5-5"`  | Claude model used to answer                |
| `MAX_TOKENS`      | `1024`               | Maximum length of Claude's answer          |

**Fallback message** (used whenever the answer is not in the document):

> "I could not find the answer to this question in the uploaded policy document."

---

## 2. The Flow

```
 1. Document Upload
        ↓
 2. Text Extraction
        ↓
 3. Chunking
        ↓
 4. Embeddings
        ↓
 5. FAISS Vector Store
        ↓
 6. User Question
        ↓
 7. Similarity Search
        ↓
 8. Relevant Context
        ↓
 9. Claude
        ↓
10. Answer + Sources
```

Steps 1–5 run **once per uploaded document** (indexing).
Steps 6–10 run **once per question** (answering).

---

## 3. Step-by-Step Specification

### Step 1 — Document Upload
- **Input:** a file chosen by the user in the sidebar (`st.file_uploader`).
- **Rules:** only one file at a time; only `.pdf` or `.txt`.
- **Output:** the file's name and raw bytes.
- **Error:** unsupported type → *"Please upload a PDF or TXT file."*
- Uploading a new file clears the old index and the chat history.

### Step 2 — Text Extraction
- **Input:** file bytes and file type.
- **PDF:** read every page with `pypdf.PdfReader` and join the page text with newlines.
- **TXT:** decode the bytes as UTF-8.
- **Output:** one string containing the full document text.
- **Error:** empty text → *"No readable text was found in this document."*

### Step 3 — Chunking
- **Input:** the full document text.
- **Method:** simple character-based sliding window.
  - Each chunk is about `CHUNK_SIZE` (750) characters.
  - Each new chunk starts `CHUNK_SIZE − CHUNK_OVERLAP` (650) characters after the previous one,
    so neighbouring chunks share about 100 characters.
  - Skip chunks that are empty or only whitespace.
- **Output:** a list of chunks. Each chunk is a dictionary:

  ```
  {
    "filename": "leave_policy.pdf",
    "chunk_id": 1,          # starts at 1
    "text": "..."
  }
  ```

### Step 4 — Embeddings
- **Input:** the list of chunk texts.
- **Method:** encode all chunk texts with the `sentence-transformers` model `EMBEDDING_MODEL`,
  with normalization turned on.
- The model is loaded once and cached (`@st.cache_resource`).
- **Output:** a 2-D array of vectors (one row per chunk, 384 numbers each for MiniLM).

### Step 5 — FAISS Vector Store
- **Input:** the embedding vectors.
- **Method:** create a `faiss.IndexFlatIP` index (inner product = cosine similarity on
  normalized vectors) and add all vectors.
- **Storage:** keep the index and the chunk list in `st.session_state`
  (in memory only, nothing saved to disk).
- **Output:** a ready-to-search index. The sidebar shows the filename and number of chunks.

### Step 6 — User Question
- **Input:** text typed into `st.chat_input`.
- **Rule:** if no document has been indexed yet, show *"Please upload a document first."*
- The question is added to the chat history and shown on screen.

### Step 7 — Similarity Search
- **Input:** the question.
- **Method:**
  1. Embed the question with the same model (normalized).
  2. Search the FAISS index for the `TOP_K` (5) closest chunks.
  3. If the document has fewer than 5 chunks, return all of them.
- **Output:** a list of chunk positions and their similarity scores.

### Step 8 — Relevant Context
- **Input:** the search results.
- **Method:** look up each result's chunk and build a context block, labeling every chunk:

  ```
  [Source: leave_policy.pdf | Chunk 4]
  <chunk text>

  [Source: leave_policy.pdf | Chunk 9]
  <chunk text>
  ```
- **Output:** the context string plus the list of source chunks (kept for display in Step 10).

### Step 9 — Claude
- **Input:** the context string and the question.
- **Method:** one call to `client.messages.create` using the `anthropic` SDK.
  - The API key comes from the `ANTHROPIC_API_KEY` environment variable.
  - Only the **system prompt**, **retrieved context**, and **question** are sent — never the whole
    document and never earlier chat turns.
- **System prompt:**

  ```
  You are a helpful assistant that answers questions about a company policy document.
  Answer using ONLY the information in the provided context.
  If the context does not contain the answer, reply exactly with:
  "I could not find the answer to this question in the uploaded policy document."
  Do not use outside knowledge. Keep answers short and clear.
  ```

- **User message:**

  ```
  Context:
  <context string from Step 8>

  Question: <user question>
  ```

- **Output:** Claude's answer text.
- **Errors:**
  - Missing API key → *"The ANTHROPIC_API_KEY is not set. Please add it and restart the app."*
  - API or network problem → *"Sorry, something went wrong while contacting Claude. Please try again."*
  - Claude declines to answer (`stop_reason == "refusal"`) → show the fallback message.

### Step 10 — Answer + Sources
- **Display:** Claude's answer in an assistant chat bubble.
- **Sources:** below the answer, an expander titled **"Sources"** lists each retrieved chunk:
  - Filename
  - Chunk number
  - Similarity score (2 decimals)
  - Chunk text
- If the answer is the fallback message, the sources are still shown so learners can see
  what was retrieved.
- The question, answer, and sources are saved to `st.session_state.messages`
  (current session only).

---

## 4. Session State

| Key          | Contents                                         |
| ------------ | ------------------------------------------------ |
| `filename`   | Name of the currently indexed file               |
| `chunks`     | List of chunk dictionaries                       |
| `index`      | The FAISS index                                  |
| `messages`   | Chat history: role, text, and sources            |

A **"Clear chat"** button in the sidebar empties `messages`.

---

## 5. Planned Functions in `app.py`

| Function                                   | Step  |
| ------------------------------------------ | ----- |
| `load_embedding_model()`                   | 4     |
| `extract_text(uploaded_file)`              | 2     |
| `split_into_chunks(text, filename)`        | 3     |
| `build_faiss_index(chunks, model)`         | 4–5   |
| `search_chunks(question, index, chunks, model)` | 7–8 |
| `build_context(results)`                   | 8     |
| `ask_claude(context, question)`            | 9     |
| `show_sources(sources)`                    | 10    |
| `main()`                                   | UI and flow |

---

## 6. Test Scenarios

| # | Action                                             | Expected result                                   |
| - | -------------------------------------------------- | ------------------------------------------------- |
| 1 | Upload a TXT policy                                | Sidebar shows filename and chunk count            |
| 2 | Upload a text-based PDF policy                     | Sidebar shows filename and chunk count            |
| 3 | Upload a `.docx` file                              | Uploader does not accept it                       |
| 4 | Ask a question answered in the policy              | Correct answer + 5 sources with chunk numbers     |
| 5 | Ask a question not in the policy                   | Exact fallback message + sources shown            |
| 6 | Ask several questions                              | All previous Q&A stay visible in the chat         |
| 7 | Click "Clear chat"                                 | Chat history is empty; document stays indexed     |
| 8 | Run without `ANTHROPIC_API_KEY`                    | Simple, clear error message; no crash             |
