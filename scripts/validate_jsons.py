import os
import json
from tqdm import tqdm

INPUT_DIR = "../pakistan_code_structured"
REPORT_PATH = "../pakistan_code_validation_report.txt"

def validate_json_structure(data, filename):
    """
    Validate structure of each parsed law JSON file.
    Returns a tuple (is_valid, issues).
    """
    issues = []

    # Top-level keys
    expected_keys = ["file", "law_name", "year", "chapters", "full_text"]
    for k in expected_keys:
        if k not in data:
            issues.append(f"Missing key: {k}")

    # Validate law_name
    if not data.get("law_name") or len(data.get("law_name", "").strip()) < 5:
        issues.append("Invalid or too short law_name")

    # Validate chapters
    chapters = data.get("chapters")
    if not isinstance(chapters, list):
        issues.append("chapters is not a list or missing")
        chapters = []

    # Validate sections inside chapters
    total_sections = 0
    for ch in chapters:
        if "chapter_title" not in ch:
            issues.append("chapter missing chapter_title")
        if "sections" not in ch:
            issues.append(f"chapter {ch.get('chapter_title', '?')} missing sections key")
            continue
        if not isinstance(ch["sections"], list):
            issues.append(f"chapter {ch.get('chapter_title', '?')} sections not a list")
            continue
        total_sections += len(ch["sections"])

    return len(issues) == 0, issues, len(chapters), total_sections


def validate_all():
    print("🔍 Validating structured JSONs...")
    results = []
    all_files = [f for f in os.listdir(INPUT_DIR) if f.endswith(".json")]

    for fname in tqdm(all_files):
        path = os.path.join(INPUT_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            results.append(f"{fname}: ❌ Invalid JSON ({e})")
            continue

        ok, issues, ch_count, sec_count = validate_json_structure(data, fname)
        if ok:
            results.append(f"{fname}: ✅ OK ({ch_count} chapters, {sec_count} sections)")
        else:
            results.append(f"{fname}: ⚠️ Issues ({len(issues)}): {', '.join(issues[:5])}")

    # Write report
    with open(REPORT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(results))
    print(f"\n📄 Validation complete. Report saved to {REPORT_PATH}")


if __name__ == "__main__":
    validate_all()
    