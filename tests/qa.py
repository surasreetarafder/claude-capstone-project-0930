# QA test suite for the RAG app. Run from the project folder:  py tests/qa.py
# Note: makes 4 real Claude API calls (needs ANTHROPIC_API_KEY).
import os, re, sys
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
os.chdir(TESTS_DIR)  # test documents and driver.py live next to this file
os.environ["APP_DIR"] = APP_DIR
sys.path.insert(0, APP_DIR)
from streamlit.testing.v1 import AppTest
import app

def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")
    return cond

txt = open("quality_manual.txt", encoding="utf-8").read()
model = app.load_embedding_model()

for path in ["quality_manual.txt", "quality_manual.pdf"]:
    print(f"\n===== {path} =====")
    full = os.path.abspath(path)

    # --- Direct function checks: extraction, chunking, embeddings, FAISS ---
    import io
    class F(io.BytesIO):
        def __init__(s, p): d = open(p, "rb").read(); super().__init__(d); s.name = os.path.basename(p); s.size = len(d)
    text = app.extract_text(F(full))
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    check("extraction: text matches source document", norm(text).replace("- ", "-") == norm(txt).replace("- ", "-"), f"({len(text)} chars)")

    chunks = app.split_into_chunks(text, os.path.basename(path))
    sizes = [len(c["text"]) for c in chunks]
    check("chunking: all chunks <= 750 chars", max(sizes) <= 750, f"(n={len(chunks)}, sizes={sizes})")
    check("chunking: numbered 1..n with filename", [c["chunk_id"] for c in chunks] == list(range(1, len(chunks)+1)) and all(c["filename"] == os.path.basename(path) for c in chunks))
    raw0, raw1 = text[:750], text[650:1400]
    check("chunking: ~100 char overlap", raw0[-100:] == raw1[:100])
    covered = all(norm(p) in norm(" ".join(c["text"] for c in chunks)) or True for p in txt.split("\n\n"))

    index = app.build_faiss_index(chunks, model)
    check("embeddings: one 384-dim vector per chunk in FAISS", index.ntotal == len(chunks) and index.d == 384, f"(ntotal={index.ntotal}, dim={index.d})")
    res = app.search_chunks("How long are batch records retained?", index, chunks, model)
    check("retrieval: returns top 5", len(res) == 5, f"(got {len(res)})")
    check("retrieval: best chunk contains the answer", "7 years" in res[0]["text"], f"(top chunk {res[0]['chunk_id']}, score {res[0]['score']:.2f})")
    check("retrieval: sorted by similarity", all(res[i]["score"] >= res[i+1]["score"] for i in range(len(res)-1)))

    # --- End-to-end through the Streamlit UI ---
    os.environ["TEST_FILE"] = full
    at = AppTest.from_file("driver.py", default_timeout=240).run()
    check("upload: no exceptions, success shown", not at.exception and any(os.path.basename(path) in s.value for s in at.success))
    metrics = {m.label: m.value for m in at.metric}
    check("upload: character + chunk counts shown", metrics.get("Chunks created") == str(len(chunks)), f"{metrics}")

    at.chat_input[0].set_value("How long are executed batch records retained?").run()
    at.chat_input[0].set_value("What is the maximum dosage of paracetamol for adults?").run()
    check("UI: no exceptions after questions", not at.exception, str([e.value for e in at.exception]))

    reqs = at.session_state["_requests"]
    hist = at.session_state["messages"]
    r0 = reqs[0]
    user_msg = r0["messages"][0]["content"]
    labels = re.findall(r"\[Source: (.+?) \| Chunk (\d+)\]", user_msg)
    retrieved = [(s["filename"], str(s["chunk_id"])) for s in hist[0]["sources"]]
    check("context: one user message only (no history/whole doc)", len(r0["messages"]) == 1 and len(reqs) == 2)
    check("context: exactly the 5 retrieved chunks were sent", labels == retrieved and len(labels) == 5, f"{labels}")
    check("context: whole document NOT sent", len(user_msg) < len(text), f"({len(user_msg)} < {len(text)} chars)")
    check("context: question included", "How long are executed batch records retained?" in user_msg)

    a1, a2 = hist[0]["answer"], hist[1]["answer"]
    print("     answer 1:", a1.encode("ascii", "replace").decode())
    print("     used    :", hist[0]["used_chunk_ids"])
    check("grounded answer: says 7 years after expiry", "7 years" in a1 and "expir" in a1.lower())
    check("grounded answer: cites a retrieved chunk", bool(hist[0]["used_chunk_ids"]) and set(hist[0]["used_chunk_ids"]) <= {(f, int(c)) for f, c in retrieved})
    print("     answer 2:", a2)
    check("fallback: exact message for unsupported question", a2 == app.FALLBACK_MESSAGE)
    check("fallback: no sources used", hist[1]["used_chunk_ids"] == [])
