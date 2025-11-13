import os
import json
import re
from tqdm import tqdm

INPUT_DIR = "../pakistan_code_structured"
RENAME_LOG = "../pakistan_code_rename_log.txt"

def safe_filename(name: str) -> str:
    """Convert law name to a filesystem-safe filename."""
    # Replace spaces & punctuation
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:180]  # Windows filename safety

def rename_files():
    print("🧱 Renaming JSON files using law titles...")
    files = [f for f in os.listdir(INPUT_DIR) if f.endswith(".json")]
    renamed, skipped = 0, []

    with open(RENAME_LOG, "w", encoding="utf-8") as log:
        for fname in tqdm(files):
            path = os.path.join(INPUT_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                skipped.append(f"{fname} (invalid JSON: {e})")
                continue

            title = data.get("law_name", "").strip()
            if not title:
                skipped.append(f"{fname} (missing law_name)")
                continue

            year = data.get("year")
            # Build clean filename
            base = safe_filename(title)
            if year:
                new_fname = f"{base}_{year}.json"
            else:
                new_fname = f"{base}.json"

            new_path = os.path.join(INPUT_DIR, new_fname)
            if os.path.exists(new_path):
                # Avoid collisions by adding short hash
                new_fname = f"{base}_{str(abs(hash(fname)))[:6]}.json"
                new_path = os.path.join(INPUT_DIR, new_fname)

            os.rename(path, new_path)
            log.write(f"{fname}  -->  {new_fname}\n")
            renamed += 1

    print(f"\n✅ Renamed {renamed} files.")
    if skipped:
        print(f"⚠️ Skipped {len(skipped)} files (see rename log).")
        with open(RENAME_LOG, "a", encoding="utf-8") as log:
            log.write("\nSkipped files:\n")
            log.writelines(f"{s}\n" for s in skipped)
    print(f"📝 Log saved to {RENAME_LOG}")

if __name__ == "__main__":
    rename_files()
