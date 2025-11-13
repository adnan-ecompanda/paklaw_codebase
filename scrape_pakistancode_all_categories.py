#!/usr/bin/env python3
import os, re, time, csv
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ---------- CONFIG ----------
ENGLISH_ROOT     = "https://www.pakistancode.gov.pk/english/"
CATEGORIES_URL   = ENGLISH_ROOT  # page that contains the #category tab with the list you pasted
SAVE_DIR         = "pakistan_code_pdfs"
LOG_CSV          = "download_log.csv"
DOWNLOADED_LIST  = "downloaded_urls.txt"  # for cross-run dedupe by PDF URL
TIMEOUT          = 45
POLITE_DELAY_ACT = 1.0    # delay between acts
POLITE_DELAY_CAT = 1.5    # delay between categories
HEADLESS         = True   # set False to watch
SKIP_ZERO_COUNT  = True   # skip categories that show (0)
ONLY_CAT_IDS     = None   # e.g., [1,2,3]; leave None to run all
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
# ----------------------------

def slugify(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip().replace("/", "-")
    return re.sub(r"[^A-Za-z0-9\\-_.() ]", "_", s)[:180]

def build_driver(download_dir=None):
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1366,2000")
    opts.add_argument(f"user-agent={UA}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    prefs = {
        "download.default_directory": os.path.abspath(download_dir or os.getcwd()),
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    }
    opts.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=opts)
    driver.set_page_load_timeout(90)
    return driver

def requests_session_from_driver(driver):
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    # pass cookies to requests (if any)
    for c in driver.get_cookies():
        s.cookies.set(c.get("name"), c.get("value"))
    return s

def open_categories_tab(driver):
    driver.get(CATEGORIES_URL)
    WebDriverWait(driver, TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
    time.sleep(1.5)
    # try clicking the tab if required
    try:
        tab = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//a[@id='pills-home-tab' or contains(., 'Categories')][contains(@href, '#category')]"))
        )
        tab.click()
        WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#category")))
    except Exception:
        pass
    return driver.page_source

def parse_categories(html):
    soup = BeautifulSoup(html, "html.parser")
    cats = []
    for div in soup.select("#category .deptlist"):
        a = div.select_one("a[href]")
        if not a: 
            continue
        href = a.get("href","").strip()
        title = a.get_text(strip=True)
        count = 0
        sc = div.select_one(".showCount")
        if sc:
            m = re.search(r"\\((\\d+)\\)", sc.get_text())
            if m: count = int(m.group(1))
        full = urljoin(ENGLISH_ROOT, href)
        # optional filter by ONLY_CAT_IDS
        if ONLY_CAT_IDS is not None:
            m_id = re.search(r"catid=(\\d+)", full)
            if not (m_id and int(m_id.group(1)) in ONLY_CAT_IDS):
                continue
        if SKIP_ZERO_COUNT and count == 0:
            continue
        cats.append({"title": title, "url": full, "count": count})
    # de-dup by URL, preserve order
    seen, uniq = set(), []
    for c in cats:
        if c["url"] in seen: 
            continue
        seen.add(c["url"])
        uniq.append(c)
    return uniq

def find_act_links_on_listing(driver, list_url):
    driver.get(list_url)
    WebDriverWait(driver, TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
    time.sleep(1.2)
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.select(".accordion-section-title a[href], .accordion a[href]")
    if not anchors:
        anchors = soup.select("a[href]")
    acts = []
    for a in anchors:
        href = (a.get("href") or "").strip()
        title = (a.get_text() or "").strip()
        if not href or href.startswith("#") or not title:
            continue
        if "coat.jpg" in href.lower() or "javascript:" in href.lower():
            continue
        full = urljoin(ENGLISH_ROOT, href)
        acts.append((title, full))
    # de-dup
    seen, uniq = set(), []
    for t, u in acts:
        if u in seen:
            continue
        seen.add(u)
        uniq.append((t, u))
    return uniq

def try_extract_pdf_urls(driver):
    pdf_urls = set()
    # ensure #download present if possible
    try:
        WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#download")))
    except Exception:
        pass

    containers = []
    try:
        containers.append(driver.find_element(By.CSS_SELECTOR, "#download"))
    except Exception:
        pass
    containers.append(driver)

    def collect_from(el, selector):
        try:
            return el.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            return []

    for el in containers:
        for a in collect_from(el, "a[href]"):
            href = a.get_attribute("href") or ""
            if any(k in href.lower() for k in [".pdf", "download", "print", "export"]):
                pdf_urls.add(href)
        for ifr in collect_from(el, "iframe[src]"):
            src = ifr.get_attribute("src") or ""
            if any(k in src.lower() for k in [".pdf", "download", "print", "export"]):
                pdf_urls.add(src)
        for emb in collect_from(el, "embed[src]"):
            src = emb.get_attribute("src") or ""
            if any(k in src.lower() for k in [".pdf", "download", "print", "export"]):
                pdf_urls.add(src)
        for btn in collect_from(el, "button[onclick], a[onclick]"):
            js = btn.get_attribute("onclick") or ""
            m = re.search(r"['\\\"](.*?\\.pdf[^'\\\"]*)['\\\"]", js, re.I)
            if m:
                pdf_urls.add(m.group(1))

    base = driver.current_url
    return [urljoin(base, u) for u in pdf_urls if u]

def download_pdf(session, url, out_dir, fname_hint=None):
    os.makedirs(out_dir, exist_ok=True)
    parsed = urlparse(url)
    base_name = os.path.basename(parsed.path)
    if not base_name or "." not in base_name:
        base_name = slugify((fname_hint or "document")) + ".pdf"
    safe_name = slugify(base_name)
    out_path = os.path.join(out_dir, safe_name)
    # avoid overwriting: if file exists, append short hash
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
        root, ext = os.path.splitext(safe_name)
        out_path = os.path.join(out_dir, f"{root}_{abs(hash(url)) % (10**8)}{ext}")
    with session.get(url, stream=True, timeout=90) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
    return out_path

def ensure_dedupe_store():
    if not os.path.exists(DOWNLOADED_LIST):
        with open(DOWNLOADED_LIST, "w", encoding="utf-8") as f:
            f.write("")
    with open(DOWNLOADED_LIST, "r", encoding="utf-8") as f:
        urls = set([ln.strip() for ln in f if ln.strip()])
    return urls

def mark_downloaded(url):
    with open(DOWNLOADED_LIST, "a", encoding="utf-8") as f:
        f.write(url + "\\n")

def process_act(driver, session, act_title, act_url, cat_title, cat_id):
    status, pdf_url, saved = "skipped", "", ""
    try:
        driver.get(act_url)
        # click Print/Download tab if present
        try:
            tab = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, "//a[@id='pills-profile-tab' or contains(., 'Print/Download')][contains(@href, '#download')]"))
            )
            tab.click()
            WebDriverWait(driver, 8).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#download")))
        except Exception:
            pass
        candidates = try_extract_pdf_urls(driver)
        if not candidates:
            status = "no_pdf_found"
        else:
            candidates.sort(key=lambda u: (".pdf" not in u.lower(), len(u)))
            pdf_url = candidates[0]
            saved = download_pdf(session, pdf_url, SAVE_DIR, fname_hint=act_title)
            status = "downloaded"
    except Exception as e:
        status = f"error: {e}"
    return {"category_id": cat_id, "category_title": cat_title, "act_title": act_title,
            "act_url": act_url, "pdf_url": pdf_url, "saved_path": saved, "status": status}

def get_cat_id_from_url(u):
    m = re.search(r"catid=(\\d+)", u)
    return int(m.group(1)) if m else None

def main():
    os.makedirs(SAVE_DIR, exist_ok=True)
    driver  = build_driver(download_dir=SAVE_DIR)
    session = requests_session_from_driver(driver)
    downloaded_urls = ensure_dedupe_store()

    # 1) categories
    html = open_categories_tab(driver)
    cats = parse_categories(html)
    if not cats:
        print("No categories found on the page. Make sure CATEGORIES_URL points to the main 'English' landing page.")
        driver.quit()
        return
    print(f"Found {len(cats)} categories.")

    rows = []
    for ci, cat in enumerate(cats, 1):
        cat_title, cat_url, cat_id = cat["title"], cat["url"], get_cat_id_from_url(cat["url"])
        print(f"\\n=== [{ci}/{len(cats)}] Category: {cat_title} (id={cat_id}, count={cat['count']}) ===")
        acts = find_act_links_on_listing(driver, cat_url)
        print(f"Found {len(acts)} acts in this category.")

        for i, (act_title, act_url) in enumerate(acts, 1):
            print(f"  [{i}/{len(acts)}] {act_title}")
            # if this act’s PDF URL was seen before, we’ll still need to open the page
            # BUT we will dedupe right before downloading, based on the chosen PDF URL.
            res = process_act(driver, session, act_title, act_url, cat_title, cat_id)
            # dedupe by pdf_url after we discover it
            if res["pdf_url"]:
                if res["pdf_url"] in downloaded_urls and res["status"] == "downloaded":
                    res["status"] = "duplicate_skipped"
                else:
                    if res["status"] == "downloaded":
                        downloaded_urls.add(res["pdf_url"])
                        mark_downloaded(res["pdf_url"])
            rows.append(res)
            time.sleep(POLITE_DELAY_ACT)
        time.sleep(POLITE_DELAY_CAT)

    # write CSV
    with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["category_id","category_title","act_title","act_url","pdf_url","saved_path","status"]
        )
        w.writeheader()
        w.writerows(rows)

    driver.quit()
    print(f"\\nDone. PDFs → {os.path.abspath(SAVE_DIR)}")
    print(f"Log  → {os.path.abspath(LOG_CSV)}")
    print(f"Dedupe file → {os.path.abspath(DOWNLOADED_LIST)}")

if __name__ == "__main__":
    main()