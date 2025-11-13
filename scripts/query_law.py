import faiss, numpy as np, json, os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
INDEX_PATH = "../pakistan_law_faiss.index"
META_PATH = "../pakistan_law_metadata.json"

index = faiss.read_index(INDEX_PATH)
metas = json.load(open(META_PATH, encoding="utf-8"))

def embed(q):
    emb = client.embeddings.create(
        model="text-embedding-3-small",
        input=q
    ).data[0].embedding
    return np.array(emb, dtype="float32").reshape(1, -1)

def search(query, top_k=5):
    qvec = embed(query)
    D, I = index.search(qvec, top_k)
    results = []
    for dist, idx in zip(D[0], I[0]):
        meta = metas[idx]
        results.append({"distance": float(dist), **meta})
    return results

query = input("Ask a legal question: ")
hits = search(query)

context = "\n\n".join([open(os.path.join("../pakistan_code_structured", h["file"])).read() for h in hits])
prompt = f"Answer using Pakistani law context below:\n{context}\n\nQuestion: {query}\nAnswer:"

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": prompt}],
    max_tokens=500
)

print("🧠", resp.choices[0].message.content)