"""
llm_parse.py
------------------------------------------------------------
Purpose:
    Convert normalized Pakistan law text files into structured JSON
    using GPT-4o / local LLM.

Output:
    pakistan_code_structured/<lawname>.json
------------------------------------------------------------
"""

import os
import json
from tqdm import tqdm
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

IN_DIR = "../pakistan_code_texts"
OUT_DIR = "../pakistan_code_structured"
os.makedirs(OUT_DIR, exist_ok=True)

SYSTEM_PROMPT = """You are a legal text parser for Pakistan's laws.
Return strict JSON only (no explanations).
Schema:
{
  "law_name": string,
  "year": number | null,
  "chapters": [
    {
      "chapter_title": string,
      "sections": [
        {"section_no": string, "section_title": string, "body": string}
      ]
    }
  ]
}
"""

def parse_text_with_llm(text):
    user_prompt = f"Parse this act into structured JSON:\n{text[:12000]}"
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        return {"error": str(e), "raw": text[:2000]}

def process_all():
    for file in tqdm(os.listdir(IN_DIR)):
        if not file.endswith(".txt"):
            continue
        with open(os.path.join(IN_DIR, file), "r", encoding="utf-8") as f:
            text = f.read()
        data = parse_text_with_llm(text)
        data["source_file"] = file
        out_path = os.path.join(OUT_DIR, file.replace(".txt", ".json"))
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    print("🤖 Parsing normalized texts into structured JSON...")
    process_all()
    print(f"✅ Structured JSONs saved to {OUT_DIR}")