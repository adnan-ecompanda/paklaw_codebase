"""
extract_texts.py
------------------------------------------------------------
Purpose:
    Extract readable, normalized plain text from Pakistan legal PDFs
    to feed into LLM-based structural parsing.

Output:
    pakistan_code_texts/<lawname>.txt
------------------------------------------------------------
"""

import os
import re
import fitz
from tqdm import tqdm

# ---------- PATHS ----------
PDF_DIR = "../pakistan_code_pdfs"
OUT_DIR = "../pakistan_code_texts"
os.makedirs(OUT_DIR, exist_ok=True)

# ---------- CLEANER ----------
def clean_text(text: str) -> str:
    text = re.sub(r"Page\s*\d+\s*of\s*\d+", " ", text)
    text = re.sub(r"–|—", "-", text)
    text = re.sub(r"_{2,}", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"UNDER REVIEW|DRAFT", "", text, flags=re.I)
    text = re.sub(r"Date:.*?\d{4}", "", text)
    return text.strip()

# ---------- BLOCK EXTRACTION ----------
def extract_blocks(pdf_path):
    text_blocks = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            blocks = page.get_text("blocks")
            blocks = sorted(blocks, key=lambda b: (b[1], b[0]))  # sort top→bottom
            for b in blocks:
                text_blocks.append(b[4])
    return "\n".join(text_blocks)

def normalize_all():
    for pdf in tqdm(os.listdir(PDF_DIR)):
        if not pdf.lower().endswith(".pdf"):
            continue
        pdf_path = os.path.join(PDF_DIR, pdf)
        try:
            text = clean_text(extract_blocks(pdf_path))
            out_path = os.path.join(OUT_DIR, pdf.replace(".pdf", ".txt"))
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            print(f"⚠️ Error processing {pdf}: {e}")

if __name__ == "__main__":
    print("🧹 Extracting and cleaning text from PDFs...")
    normalize_all()
    print(f"✅ Normalized texts saved to {OUT_DIR}")