# build_index_pro.py
"""
Professional Hybrid Index Builder for Pakistan Law Assistant.
- Extracts section-level text from all JSON laws
- Generates batched OpenAI embeddings (text-embedding-3-large)
- Normalizes vectors for cosine similarity (FAISS IndexFlatIP)
- Builds BM25 lexical index for hybrid retrieval
- Saves FAISS index, metadata, and corpus
"""

import os, json, faiss, numpy as np
from openai import OpenAI
from rank_bm25 import BM25Okapi
from tqdm import tqdm

# ------------------ CONFIG ------------------
MODEL_EMB = "text-embedding-3-large"
DATA_DIR = "../pakistan_code_structured"
INDEX_PATH = "../pakistan_law_faiss.index"
META_PATH = "../pakistan_law_metadata.json"
BM25_PATH = "../pakistan_law_bm25.json"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ------------------ EXTRACT ------------------
def extract_sections(json_path):
    """Load each law JSON and extract its sections with metadata."""
    try:
        data = json.load(open(json_path, encoding="utf-8"))
        law = data.get("law_name", "Unknown Law")
        year = data.get("year", "")
        for ch in data.get("chapters", []):
            for sec in ch.get("sections", []):
                text = sec.get("body", "").strip()
                if len(text) < 20:
                    continue
                yield {
                    "law": f"{law} ({year})",
                    "section_no": sec.get("section_no", "?"),
                    "section_title": sec.get("section_title", ""),
                    "text": text
                }
    except Exception as e:
        print(f"⚠️ Skipped {json_path}: {e}")
        return []

# ------------------ BUILD ------------------
print("🔧 Building FAISS + BM25 hybrid index...")
all_sections = []
for fname in tqdm(os.listdir(DATA_DIR)):
    if fname.endswith(".json"):
        fpath = os.path.join(DATA_DIR, fname)
        all_sections.extend(list(extract_sections(fpath)))

if not all_sections:
    print("❌ No valid law sections found.")
    exit()

texts = [s["text"] for s in all_sections]

# ------------------ EMBEDDINGS ------------------
print(f"🔹 Generating embeddings for {len(texts)} sections...")
embeddings = []
BATCH = 50
for i in tqdm(range(0, len(texts), BATCH)):
    batch = texts[i:i + BATCH]
    emb = client.embeddings.create(model=MODEL_EMB, input=batch)
    for e in emb.data:
        embeddings.append(e.embedding)

embeddings = np.array(embeddings, dtype="float32")
faiss.normalize_L2(embeddings)  # cosine similarity

# ------------------ FAISS INDEX ------------------
print("🧠 Creating FAISS cosine-similarity index...")
index = faiss.IndexFlatIP(embeddings.shape[1])
index.add(embeddings)

# ------------------ BM25 INDEX ------------------
print("📚 Building BM25 lexical index...")
tokenized = [t.split() for t in texts]
bm25 = BM25Okapi(tokenized)

# ------------------ SAVE ------------------
print("💾 Saving index files...")
faiss.write_index(index, INDEX_PATH)
json.dump(all_sections, open(META_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump({"corpus": texts}, open(BM25_PATH, "w", encoding="utf-8"), ensure_ascii=False)

print("\n✅ Build complete!")
print(f"• FAISS index  → {INDEX_PATH}")
print(f"• Metadata     → {META_PATH}")
print(f"• BM25 corpus  → {BM25_PATH}")
print(f"Total sections → {len(texts)}")