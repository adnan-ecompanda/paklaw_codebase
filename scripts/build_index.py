import os, json, faiss, numpy as np
from tqdm import tqdm
from openai import OpenAI

# ===== CONFIG =====
DATA_DIR   = "../pakistan_code_structured"
INDEX_PATH = "../pakistan_law_faiss.index"
META_PATH  = "../pakistan_law_metadata.json"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== HELPERS =====
def extract_sections(data):
    """Flatten all section bodies from chapters."""
    texts = []
    if "chapters" in data:
        for chap in data["chapters"]:
            for sec in chap.get("sections", []):
                body = sec.get("body", "")
                if body and len(body.strip()) > 20:
                    title = f"{sec.get('section_no', '')}. {sec.get('section_title', '')}".strip()
                    combined = f"{title}\n{body.strip()}"
                    texts.append(combined)
    return texts

def get_embedding(text):
    resp = client.embeddings.create(
       model="text-embedding-3-large",
        input=text[:8000]
    )
    return np.array(resp.data[0].embedding, dtype="float32")

# ===== MAIN =====
def main():
    print("🔧 Building FAISS index from structured Pakistan Code JSONs...")
    vectors, metas = [], []

    for fname in tqdm(os.listdir(DATA_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(DATA_DIR, fname)

        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            print(f"❌ {fname}: {e}")
            continue

        law_name = data.get("law_name", fname)
        year = data.get("year", "")
        sections = extract_sections(data)

        for i, section_text in enumerate(sections):
            try:
                emb = get_embedding(section_text)
                vectors.append(emb)
                metas.append({
                    "law": law_name,
                    "year": year,
                    "file": fname,
                    "chunk": i,
                    "text": section_text[:400]
                })
            except Exception as e:
                print(f"⚠️ Embedding error in {fname}, section {i}: {e}")

    if not vectors:
        print("❌ No valid chunks found. Make sure your JSONs have section bodies.")
        return

    # Build FAISS index
    vectors = np.vstack(vectors)
    dim = vectors.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(vectors)

    faiss.write_index(index, INDEX_PATH)
    json.dump(metas, open(META_PATH, "w", encoding="utf-8"), indent=2)

    print(f"\n✅ Built FAISS index with {len(vectors)} chunks")
    print(f"📦 Saved index to: {INDEX_PATH}")
    print(f"🧾 Metadata saved to: {META_PATH}")

if __name__ == "__main__":
    main()