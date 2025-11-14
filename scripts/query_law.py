"""
Pakistan Law RAG Assistant – v4 (Universal)
--------------------------------------------
Retrieves and synthesizes grounded answers across ALL Pakistan Code laws.
Intelligently weights domain relevance instead of restricting categories.
"""

import os, json, faiss, numpy as np, re
from openai import OpenAI
from numpy.linalg import norm

# ==== CONFIG ====
INDEX_PATH = "../pakistan_law_faiss.index"
META_PATH  = "../pakistan_law_metadata.json"
EMBED_MODEL = "text-embedding-3-large"
TOP_K = 25
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ==== HELPERS ====
def get_embedding(text):
    """Get vector embedding for text."""
    resp = client.embeddings.create(model=EMBED_MODEL, input=text[:8000])
    return np.array(resp.data[0].embedding, dtype="float32")

def cosine(a, b):
    """Compute cosine similarity."""
    return float(np.dot(a, b) / (norm(a) * norm(b)))

# ==== LOAD INDEX ====
index = faiss.read_index(INDEX_PATH)
metas = json.load(open(META_PATH, encoding="utf-8"))

# ==== AUTO DOMAIN WEIGHTING ====
def get_domain_boosts(query):
    """Return regex-based domain boosts depending on topic."""
    domain_boosts = []
    mapping = {
        "motor|vehicle|insurance|road|traffic": 1.3,
        "bank|loan|finance|currency|securities": 1.25,
        "marriage|divorce|inheritance|family": 1.2,
        "tax|duty|import|customs": 1.25,
        "crime|penal|theft|murder|offence": 1.3,
        "education|university|school|college": 1.15,
        "health|epidemic|disease|drug|hospital": 1.15
    }
    for pattern, weight in mapping.items():
        if re.search(pattern, query, re.I):
            domain_boosts.append((re.compile(pattern, re.I), weight))
    return domain_boosts

# ==== MAIN PIPELINE ====
def ask_question(query):
    print(f"\n🔎 Query: {query}")
    query_vec = get_embedding(query)
    D, I = index.search(np.array([query_vec]), TOP_K)
    hits = [metas[i] for i in I[0] if i < len(metas)]

    # Rerank by cosine similarity
    for h in hits:
        h["similarity"] = cosine(get_embedding(h["text"]), query_vec)

    # Apply domain-based weighting (boost relevance)
    boosts = get_domain_boosts(query)
    if boosts:
        for h in hits:
            for pattern, weight in boosts:
                if pattern.search(h["law"]) or pattern.search(h["text"]):
                    h["similarity"] *= weight

    # Sort and select top hits
    hits = sorted(hits, key=lambda x: x["similarity"], reverse=True)[:5]

    # Display hits
    print("\n📚 Top Retrieved Sections:")
    for i, h in enumerate(hits, 1):
        print(f"{i}. {h['law']} ({h.get('year', '')}) – {h['file']}")
        print(f"   Excerpt: {h['text'][:180]}...\n")

    # Build context for GPT
    context = "\n\n".join([f"[{h['law']}]\n{h['text']}" for h in hits])

    # GPT synthesis
    prompt = f"""
You are a Pakistani legal AI assistant.
Answer using only the context below. Always cite Act names and section numbers when possible.

Question: {query}

Context:
{context}
"""
    answer = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "You are an expert in Pakistani law."},
                  {"role": "user", "content": prompt}],
        temperature=0.3
    )

    print("\n🧠", answer.choices[0].message.content.strip())
    return {"query": query, "answer": answer.choices[0].message.content.strip(), "sources": hits}

if __name__ == "__main__":
    q = input("Ask a legal question: ")
    ask_question(q)