"""
Pakistan Law Assistant – Professional Edition v6.4
Now with improved hybrid weighting, relevance filtering, and clean citations.
"""
import os, json, faiss, numpy as np, datetime, re
from openai import OpenAI
from rank_bm25 import BM25Okapi

INDEX_PATH = "../pakistan_law_faiss.index"
META_PATH  = "../pakistan_law_metadata.json"
BM25_PATH  = "../pakistan_law_bm25.json"
LOG_PATH   = "../logs/query_log.jsonl"
CONTEXT_LOG = "../logs/last_context.txt"

MODEL_EMB  = "text-embedding-3-large"
MODEL_CHAT = "gpt-4o-mini"
TOP_K      = 20
BASE_URL   = "http://127.0.0.1:5002/view"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

idx = faiss.read_index(INDEX_PATH)
meta = json.load(open(META_PATH, encoding="utf-8"))
corpus = json.load(open(BM25_PATH, encoding="utf-8"))["corpus"]
bm25 = BM25Okapi([c.split() for c in corpus])

def emb(txt):
    e = client.embeddings.create(model=MODEL_EMB, input=txt[:8000]).data[0].embedding
    v = np.array(e, dtype="float32").reshape(1, -1)
    faiss.normalize_L2(v)
    return v

def safe_json(o):
    if isinstance(o, np.generic): return o.item()
    raise TypeError(f"Type {type(o).__name__} not serializable")

def link(law, sec):
    """
    Builds a valid, file-safe URL to the viewer for a given law and section.
    Automatically normalizes naming and skips missing JSONs.
    """
    # Clean law name — remove underscores before parentheses, normalize everything
    law_clean = re.sub(r'_*\((\d{4})\)', r'_\1', law)
    law_clean = re.sub(r'[()]+', '', law_clean)
    law_clean = re.sub(r'[^A-Za-z0-9_]+', '_', law_clean)
    law_clean = re.sub(r'_+', '_', law_clean).strip('_')

    # Check if corresponding JSON exists
    structured_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../pakistan_code_structured"))
    json_path = os.path.join(structured_dir, f"{law_clean}.json")

    # Only build link if the file exists
    if os.path.exists(json_path):
        return f"{BASE_URL}?law={law_clean}&section={sec}"
    else:
        # Skip dead link, return plain text fallback (no hyperlink)
        return f"{law} §{sec}"

def ask(query, urdu=False, return_hits=False):
    qv = emb(query)
    D, I = idx.search(qv, TOP_K)

    # --- Hybrid Weighted Merge (FAISS 0.7 + BM25 0.3) ---
    faiss_hits = {i: float(1 / (1 + D[0][k])) for k, i in enumerate(I[0]) if i < len(meta)}
    bm25_scores = bm25.get_scores(query.split())
    bm25_norm = np.interp(bm25_scores, (bm25_scores.min(), bm25_scores.max()), (0, 1))

    combined = {}
    for i, m in enumerate(meta):
        s = 0.0
        if i in faiss_hits:
            s += 0.7 * faiss_hits[i]
        s += 0.3 * bm25_norm[i]
        if s > 0:
            combined[m["law"] + "_" + m["section_no"]] = {"meta": m, "score": s}

    # --- Boost for keyword overlaps ---
    qwords = set(re.findall(r"\w+", query.lower()))
    for v in combined.values():
        law_words = set(v["meta"]["law"].lower().split())
        if len(qwords & law_words) > 0:
            v["score"] *= 1.3

    # --- Filter & sort ---
    hits = [v for v in combined.values() if v["score"] > 0.15]
    hits = sorted(hits, key=lambda x: x["score"], reverse=True)[:5]
    conf = float(np.mean([h["score"] for h in hits])) if hits else 0.0

    # --- Context for LLM ---
    context = "\n\n".join([
        f"[{h['meta']['law']} §{h['meta']['section_no']}] {h['meta']['text']}"
        for h in hits
    ])
    os.makedirs(os.path.dirname(CONTEXT_LOG), exist_ok=True)
    open(CONTEXT_LOG, "w", encoding="utf-8").write(context)

    # --- GPT reasoning ---
    sys = ("You are a Pakistani legal assistant. Use only the provided context. "
           "Respond clearly and structured:\n"
           "1️⃣ Summary Answer\n2️⃣ Relevant Acts or Sections\n3️⃣ Legal Interpretation")
    ans = client.chat.completions.create(
        model=MODEL_CHAT,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": f"Q: {query}\n\nContext:\n{context}"}
        ],
        temperature=0.3
    ).choices[0].message.content

    if urdu:
        ur = client.chat.completions.create(
            model=MODEL_CHAT,
            messages=[{"role": "user", "content": f"Translate to Urdu:\n{ans}"}]
        ).choices[0].message.content
        ans += f"\n\n🇵🇰 **Urdu Translation:**\n{ur}"

    # --- Citations ---
    cites = "<br>".join([
        f"• <a href='{link(h['meta']['law'], h['meta']['section_no'])}' target='_blank' "
        f"style='color:#41b97a;font-weight:600;text-decoration:none;'>"
        f"{h['meta']['law']} §{h['meta']['section_no']}</a> — {h['meta'].get('section_title','')}"
        for h in hits
    ])
    output = f"### 🧠 Legal Response\n{ans}\n\n---\n**Confidence:** {conf:.2f}\n\n📚 <b>Top Retrieved Sections:</b><br>{cites}"

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "time": datetime.datetime.now().isoformat(timespec='seconds'),
            "query": query, "confidence": round(conf, 3),
            "laws": [h['meta']['law'] for h in hits]
        }, ensure_ascii=False, default=safe_json) + "\n")

    return (output, conf, hits) if return_hits else (output, conf)