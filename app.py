"""
HelixNova Pharma Quality & Regulatory RAG Assistant

A simple Retrieval-Augmented Generation (RAG) app for a beginner training session.

Flow:
Document Upload -> Text Extraction -> Chunking -> Embeddings -> FAISS Vector Store
-> User Question -> Similarity Search -> Relevant Context -> Claude -> Answer + Sources

Run with:  streamlit run app.py
"""

import csv
import os
import re

import anthropic
import faiss
import numpy as np
import streamlit as st
from dotenv import load_dotenv
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Settings (change these to experiment)
# ---------------------------------------------------------------------------
ALLOWED_TYPES = ["pdf", "txt"]
CHUNK_SIZE = 750          # characters per chunk
CHUNK_OVERLAP = 100       # characters shared between neighbouring chunks
TOP_K = 5                 # number of chunks to retrieve per question
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CLAUDE_MODEL = "claude-opus-5-5"
MAX_TOKENS = 4000         # room for Claude's reasoning plus a short answer
EVAL_DATASET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_dataset.csv")

FALLBACK_MESSAGE = "I could not find the answer to this question in the uploaded policy document."

SYSTEM_PROMPT = f"""You are a helpful assistant for HelixNova Pharma that answers questions \
about quality and regulatory documents.
Answer using ONLY the information in the provided context.
Do not invent information and do not use outside knowledge.
If the context does not contain enough information to answer, reply exactly with:
"{FALLBACK_MESSAGE}"
Keep answers short and clear. When helpful, mention the chunk number(s) you used.
At the very end of your reply, on its own line, list the sources you used exactly as
written in their labels (file name | Chunk number), separated by semicolons, like this:
USED_CHUNKS: policy.pdf | Chunk 2; manual.txt | Chunk 5
If you reply with the fallback message, write:
USED_CHUNKS: none"""

# Load ANTHROPIC_API_KEY from a .env file next to app.py if one exists (optional).
# Using the script's folder means it works no matter where you run streamlit from.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# On Streamlit Community Cloud the key is stored in st.secrets. Copy it into the
# environment so the Anthropic client and the key checks below can find it.
if not os.environ.get("ANTHROPIC_API_KEY"):
    try:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass  # no secrets configured -> the app shows a clear error message later


# ---------------------------------------------------------------------------
# Step 4 helper: load the embedding model once and reuse it
# ---------------------------------------------------------------------------
@st.cache_resource
def load_embedding_model():
    return SentenceTransformer(EMBEDDING_MODEL)


# ---------------------------------------------------------------------------
# Step 2: Text Extraction
# ---------------------------------------------------------------------------
def extract_text(uploaded_file):
    """Return all text from an uploaded PDF or TXT file."""
    if uploaded_file.name.lower().endswith(".pdf"):
        reader = PdfReader(uploaded_file)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()

    # TXT file
    return uploaded_file.getvalue().decode("utf-8", errors="ignore").strip()


# ---------------------------------------------------------------------------
# Step 3: Chunking
# ---------------------------------------------------------------------------
def split_into_chunks(text, filename):
    """Split text into overlapping chunks of about CHUNK_SIZE characters."""
    chunks = []
    step = CHUNK_SIZE - CHUNK_OVERLAP
    for start in range(0, len(text), step):
        chunk_text = text[start:start + CHUNK_SIZE].strip()
        if chunk_text:
            chunks.append({
                "filename": filename,
                "chunk_id": len(chunks) + 1,   # chunk numbers start at 1
                "text": chunk_text,
            })
        if start + CHUNK_SIZE >= len(text):
            break
    return chunks


# ---------------------------------------------------------------------------
# Steps 4 and 5: Embeddings + FAISS Vector Store
# ---------------------------------------------------------------------------
def build_faiss_index(chunks, model):
    """Embed every chunk and store the vectors in a FAISS index."""
    texts = [chunk["text"] for chunk in chunks]
    # normalize_embeddings=True means inner product == cosine similarity
    embeddings = model.encode(texts, normalize_embeddings=True)
    embeddings = np.array(embeddings, dtype="float32")

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return index


# ---------------------------------------------------------------------------
# Step 7: Similarity Search
# ---------------------------------------------------------------------------
def search_chunks(question, index, chunks, model, allowed_files=None):
    """Return the TOP_K chunks most similar to the question.

    allowed_files: optional list of file names to search in (document filter).
    """
    question_vector = model.encode([question], normalize_embeddings=True)
    question_vector = np.array(question_vector, dtype="float32")

    # With a document filter, rank all chunks and keep the best TOP_K from the
    # selected documents (fine for small training documents).
    k = min(TOP_K, len(chunks)) if allowed_files is None else len(chunks)
    scores, positions = index.search(question_vector, k)

    results = []
    for score, position in zip(scores[0], positions[0]):
        chunk = chunks[position]
        if allowed_files is None or chunk["filename"] in allowed_files:
            results.append({**chunk, "score": float(score)})
        if len(results) == TOP_K:
            break
    return results


# ---------------------------------------------------------------------------
# Step 8: Relevant Context
# ---------------------------------------------------------------------------
def build_context(results):
    """Join the retrieved chunks into one labeled context string."""
    parts = []
    for r in results:
        parts.append(f"[Source: {r['filename']} | Chunk {r['chunk_id']}]\n{r['text']}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Step 9: Claude
# ---------------------------------------------------------------------------
def ask_claude(context, question):
    """Send ONLY the retrieved context and the question to Claude.

    Returns the answer text and the list of (file name, chunk number) pairs
    Claude says it used.
    """
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    user_message = f"Context:\n{context}\n\nQuestion: {question}"

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    # If Claude declines to answer, use the fallback message.
    if response.stop_reason == "refusal":
        return FALLBACK_MESSAGE, []

    # The response can contain several blocks; we only want the text ones.
    answer = "".join(block.text for block in response.content if block.type == "text")

    # Read the "USED_CHUNKS: ..." line, then remove it from the answer shown to the user.
    used_chunk_ids = []
    match = re.search(r"USED_CHUNKS:\s*(.*)\s*$", answer, re.IGNORECASE)
    if match:
        # e.g. "policy.pdf | Chunk 2; manual.txt | Chunk 5" -> [("policy.pdf", 2), ("manual.txt", 5)]
        pairs = re.findall(r"([^;|]+?)\s*\|\s*Chunk\s*(\d+)", match.group(1), re.IGNORECASE)
        used_chunk_ids = [(name.strip(), int(number)) for name, number in pairs]
        answer = answer[:match.start()]

    return answer.strip() or FALLBACK_MESSAGE, used_chunk_ids


# ---------------------------------------------------------------------------
# Step 10: Answer + Sources
# ---------------------------------------------------------------------------
def show_sources(sources, used_chunk_ids):
    """Show the retrieved chunks inside an expandable section."""
    with st.expander(f"Retrieved source chunks ({len(sources)})"):
        for s in sources:
            is_used = (s["filename"], s["chunk_id"]) in used_chunk_ids
            used_label = " used in answer" if is_used else ""
            st.markdown(
                f"**{s['filename']} — Chunk {s['chunk_id']}** "
                f"(similarity: {s['score']:.2f}){used_label}"
            )
            st.text(s["text"])
            st.divider()


def show_sources_used(sources, used_chunk_ids):
    """Show the file name and chunk number of each chunk used for the answer."""
    used = [s for s in sources if (s["filename"], s["chunk_id"]) in used_chunk_ids]
    lines = ["**Sources used:**"]
    if used:
        for s in used:
            lines.append(f"- {s['filename']} — Chunk {s['chunk_id']}")
    else:
        lines.append("- None (the answer was not found in the document)")
    st.markdown("\n".join(lines))


def show_answer(item):
    """Show one answer with its retrieved chunks and the sources used."""
    st.markdown(item["answer"])
    show_sources(item["sources"], item["used_chunk_ids"])
    show_sources_used(item["sources"], item["used_chunk_ids"])


# ---------------------------------------------------------------------------
# Evaluation: run eval_dataset.csv and score the answers
# ---------------------------------------------------------------------------
def load_eval_dataset():
    """Read eval_dataset.csv (question, expected_answer, expected_keywords, expected_source)."""
    with open(EVAL_DATASET, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def keywords_found(keywords, text):
    """True if every keyword is in the text (case-insensitive).

    Keywords are separated by ';'. Alternatives for one keyword are separated by '|',
    e.g. "1 hour|one hour;Site QA".
    """
    text = text.lower()
    groups = [g for g in keywords.split(";") if g.strip()]
    return all(any(alt.strip().lower() in text for alt in g.split("|")) for g in groups)


def run_evaluation(rows, index, chunks, model):
    """Ask every eval question and check the answer, retrieval, and sources."""
    results = []
    progress = st.progress(0.0, text="Running evaluation...")
    for i, row in enumerate(rows, start=1):
        sources = search_chunks(row["question"], index, chunks, model)
        answer, used_chunk_ids = ask_claude(build_context(sources), row["question"])
        in_document = row["expected_answer"] != FALLBACK_MESSAGE

        if in_document:
            retrieved_text = " ".join(s["text"] for s in sources)
            answer_correct = keywords_found(row["expected_keywords"], answer)
            retrieval_hit = keywords_found(row["expected_keywords"], retrieved_text)
            source_correct = any(row["expected_source"] in name for name, _ in used_chunk_ids)
        else:
            # Not in the document: the only correct answer is the fallback message.
            answer_correct = answer == FALLBACK_MESSAGE
            retrieval_hit = None
            source_correct = None

        results.append({
            "question": row["question"],
            "in_document": in_document,
            "expected_answer": row["expected_answer"],
            "answer": answer,
            "answer_correct": answer_correct,
            "retrieval_hit": retrieval_hit,
            "source_correct": source_correct,
            "top_score": sources[0]["score"] if sources else 0.0,
        })
        progress.progress(i / len(rows), text=f"Evaluated {i} of {len(rows)} questions")
    progress.empty()
    return results


def percent(values):
    """Percentage of True values, ignoring None (not applicable)."""
    values = [v for v in values if v is not None]
    return f"{100 * sum(values) / len(values):.0f}%" if values else "n/a"


def show_dashboard(results):
    """Simple RAG quality dashboard: headline metrics + one row per question."""
    in_doc = [r for r in results if r["in_document"]]
    not_in_doc = [r for r in results if not r["in_document"]]

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Answer accuracy", percent([r["answer_correct"] for r in results]))
    col2.metric("Retrieval hit rate", percent([r["retrieval_hit"] for r in in_doc]))
    col3.metric("Source accuracy", percent([r["source_correct"] for r in in_doc]))
    col4.metric("Fallback accuracy", percent([r["answer_correct"] for r in not_in_doc]))
    col5.metric("Avg top similarity", f"{np.mean([r['top_score'] for r in results]):.2f}")

    mark = {True: "✅", False: "❌", None: "—"}
    st.dataframe([{
        "Question": r["question"],
        "Type": "In document" if r["in_document"] else "Not in document",
        "Expected answer": r["expected_answer"],
        "Claude answer": r["answer"],
        "Answer correct": mark[r["answer_correct"]],
        "Retrieval hit": mark[r["retrieval_hit"]],
        "Source correct": mark[r["source_correct"]],
        "Top similarity": round(r["top_score"], 2),
    } for r in results])


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="HelixNova RAG Assistant", page_icon="💊")
    st.title("HelixNova Pharma Quality & Regulatory RAG Assistant")

    # Chat history lives only in this browser session.
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # ---------------- Section 1: Upload Document ----------------
    st.header("1. Upload Document")
    uploaded_files = st.file_uploader(
        "Choose one or more PDF or TXT files", type=ALLOWED_TYPES, accept_multiple_files=True
    )

    if uploaded_files:
        # Only rebuild the index when the set of uploaded files changes.
        file_key = sorted(f"{f.name}-{f.size}" for f in uploaded_files)
        if st.session_state.get("file_key") != file_key:
            with st.spinner("Reading and indexing the document(s)..."):
                documents = []   # one summary row per document
                chunks = []      # chunks from ALL documents; each keeps its filename
                for uploaded_file in uploaded_files:
                    try:
                        text = extract_text(uploaded_file)
                    except Exception:
                        st.error(f"Sorry, {uploaded_file.name} could not be read. "
                                 "Please try another file.")
                        continue

                    if not text:
                        st.error(f"No readable text was found in {uploaded_file.name}.")
                        continue

                    doc_chunks = split_into_chunks(text, uploaded_file.name)
                    chunks.extend(doc_chunks)
                    documents.append({
                        "Document": uploaded_file.name,
                        "Extracted characters": len(text),
                        "Chunks created": len(doc_chunks),
                    })

                if not chunks:
                    st.stop()

                model = load_embedding_model()
                index = build_faiss_index(chunks, model)

            st.session_state.file_key = file_key
            st.session_state.documents = documents
            st.session_state.chunks = chunks
            st.session_state.index = index
            st.session_state.messages = []   # new document(s) -> fresh chat
            st.session_state.pop("eval_results", None)

        documents = st.session_state.documents
        names = ", ".join(d["Document"] for d in documents)
        st.success(f"Document(s) ready: **{names}**")
        col1, col2 = st.columns(2)
        col1.metric("Extracted characters",
                    f"{sum(d['Extracted characters'] for d in documents):,}")
        col2.metric("Chunks created", len(st.session_state.chunks))
        if len(documents) > 1:
            st.dataframe(documents, hide_index=True)

    # ---------------- Section 2: Document Filter ----------------
    st.header("2. Choose your Document to search")

    if "index" not in st.session_state or not uploaded_files:
        st.info("Please upload a document first.")
        return

    # Document-level filter: choose which documents to search.
    filenames = [d["Document"] for d in st.session_state.documents]
    selected_files = st.multiselect("Search in these documents", filenames, default=filenames)
    if not selected_files:
        st.warning("Please select at least one document to search.")

    if st.session_state.messages and st.button("Clear chat"):
        st.session_state.messages = []
        st.rerun()

    # Show the chat history for this session (oldest first).
    for item in st.session_state.messages:
        with st.chat_message("user"):
            st.markdown(item["question"])
        with st.chat_message("assistant"):
            show_answer(item)

    question = st.chat_input("Ask a question about your document", disabled=not selected_files)

    if question and question.strip() and selected_files:
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            if not os.environ.get("ANTHROPIC_API_KEY"):
                st.error("The ANTHROPIC_API_KEY is not set. Please add it and restart the app.")
                st.stop()

            with st.spinner("Searching the document and asking Claude..."):
                model = load_embedding_model()
                results = search_chunks(
                    question, st.session_state.index, st.session_state.chunks, model,
                    selected_files,
                )
                context = build_context(results)
                try:
                    answer, used_chunk_ids = ask_claude(context, question)
                except anthropic.AuthenticationError:
                    st.error("The API key was rejected. Please check your ANTHROPIC_API_KEY.")
                    st.stop()
                except anthropic.APIError:
                    st.error("Sorry, something went wrong while contacting Claude. Please try again.")
                    st.stop()

            item = {"question": question, "answer": answer, "sources": results,
                    "used_chunk_ids": used_chunk_ids}
            show_answer(item)

        # Save to session state so it stays visible (current session only, no database).
        st.session_state.messages.append(item)

    # ---------------- Section 3: RAG Quality Dashboard ----------------
    st.header("3. RAG Quality Dashboard")
    eval_rows = load_eval_dataset()
    st.caption(
        f"Runs the {len(eval_rows)} questions in eval_dataset.csv against all uploaded "
        f"documents and compares Claude's answers with the expected answers "
        f"({len(eval_rows)} Claude API calls)."
    )

    if st.button("Run evaluation"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.error("The ANTHROPIC_API_KEY is not set. Please add it and restart the app.")
            st.stop()
        try:
            st.session_state.eval_results = run_evaluation(
                eval_rows, st.session_state.index, st.session_state.chunks,
                load_embedding_model(),
            )
        except anthropic.AuthenticationError:
            st.error("The API key was rejected. Please check your ANTHROPIC_API_KEY.")
            st.stop()
        except anthropic.APIError:
            st.error("Sorry, something went wrong while contacting Claude. Please try again.")
            st.stop()

    if "eval_results" in st.session_state:
        show_dashboard(st.session_state.eval_results)


if __name__ == "__main__":
    main()
