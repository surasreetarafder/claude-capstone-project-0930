# CLAUDE.md

## Project Overview

A simple enterprise RAG (Retrieval-Augmented Generation) app for a beginner training session.
Users upload a policy document (PDF or TXT), ask questions, and get answers from Claude that are
grounded only in the retrieved document chunks.

Full specification: see `requirements.md`.

## Tech Stack

- Python 3.10+
- Streamlit (UI)
- Anthropic Claude API (`anthropic` SDK)
- FAISS (`faiss-cpu`) for the vector store
- `sentence-transformers` for embeddings
- `pypdf` for PDF text extraction

## Commands

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Development Rules

1. **Keep it beginner friendly.** Write simple, readable code with short comments that explain each RAG step.
2. **Keep most logic in `app.py`.** Use small, well-named functions. Do not split into many modules.
3. **Never hardcode API keys.** Do not put keys in code, comments, or example output.
4. **Use `ANTHROPIC_API_KEY` from environment variables** (a `.env` file is fine for local use).
5. **Support PDF and TXT uploads only.**
6. **Chunk before embedding.** Split the extracted text into chunks, then embed each chunk.
7. **Retrieve before calling Claude.** Search FAISS for the most relevant chunks first.
8. **Claude answers only from retrieved context.** Send only the retrieved chunks and the question, never the whole document.
9. **Use the fallback when the answer is not found.** Reply with:
   "I could not find the answer to this question in the uploaded policy document."
10. **Keep error messages simple and understandable** for non-technical users.
11. **No unnecessary frameworks or complexity.** No LangChain, LlamaIndex, databases, or extra services.

## RAG Pipeline (in order)

Upload → Extract text → Chunk → Embed → Store in FAISS → Embed question → Retrieve top-k → Ask Claude → Show answer + sources (filename, chunk number)

## Conventions

- Tunable settings (`CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `EMBEDDING_MODEL`, `CLAUDE_MODEL`) are constants at the top of `app.py`.
- Chat history lives only in `st.session_state` for the current session.
- Cache the embedding model with `@st.cache_resource`.
