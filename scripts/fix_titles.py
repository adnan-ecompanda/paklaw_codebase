import os, json, csv
from tqdm import tqdm

INPUT_DIR = "../pakistan_code_structured"
OUTPUT_CSV = "../pakistan_code_summary.csv"

def summarize():
    print("📊 Generating summary of all parsed laws...")
    rows = []
    json_files = [f for f in os.listdir(INPUT_DIR) if f.endswith(".json")]

    for fname in tqdm(json_files):
        path = os.path.join(INPUT_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            rows.append({
                "file": fname,
                "error": f"Invalid JSON: {e}",
                "law_name": "",
                "year": "",
                "chapters": "",
                "sections": ""
            })
            continue

        law_name = data.get("law_name", "")
        year = data.get("year", "")
        chapters = data.get("chapters", [])
        chap_count = len(chapters) if isinstance(chapters, list) else 0
        sec_count = 0
        if isinstance(chapters, list):
            for ch in chapters:
                sec_count += len(ch.get("sections", [])) if isinstance(ch.get("sections"), list) else 0

        rows.append({
            "file": fname,
            "law_name": law_name,
            "year": year,
            "chapters": chap_count,
            "sections": sec_count
        })

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["file", "law_name", "year", "chapters", "sections"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✅ Summary file created: {OUTPUT_CSV}")
    print("Open this in Excel or VS Code to inspect extraction coverage.")

if __name__ == "__main__":
    summarize()
