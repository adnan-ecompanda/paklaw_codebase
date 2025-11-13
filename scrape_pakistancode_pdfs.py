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

BASE_LIST_URL = "https://www.pakistancode.gov.pk/english/LGu0xVD-apaUY2Fqa-ag%3D%3D&action=primary&catid=1"
ENGLISH_ROOT   = "https://www.pakistancode.gov.pk/english/"
SAVE_DIR = "pakistan_code_pdfs"
LOG_CSV  = "download_log.csv"
TIMEOUT  = 40
POLITE_DELAY = 1.2
HEADLESS = True  # set False to watch the browser for debugging

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "\
     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def slugify(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip().replace("/", "-")
    return re.sub(r"[^A-Za-z0-9\-\_\.\(\) ]", "_", s)[:180]

def build_driver(download_dir=None):
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1366,2000")
    opts.add_argument(f"user-agent={UA}")
    # reduce headless detection a bit
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
    for c in driver.get_cookies():
        s.cookies.set(c.get("name"), c.get("value"))
    return s

def find_act_links_on_listing(driver, list_url):
    driver.get(list_url)
    WebDriverWait(driver, TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
    time.sleep(1.5)  # allow dynamic content to settle
    html = driver.page_source
    # debug dump
    with open("debug_listing.html", "w", encoding="utf-8") as f:
        f.write(html)

    soup = BeautifulSoup(html, "html.parser")
    # Grab anchors in typical containers, fall back to all anchors:
    anchors = soup.select(".accordion-section-title a[href], .accordion a[href]")
    if not anchors:
        anchors = soup.select("a[href]")

    acts = []
    for a in anchors:
        href = (a.get("href") or "").strip()
        title = (a.get_text() or "").strip()
        if not href or href.startswith("#") or not title:
            continue
        # these list-page links are short/encoded and relative (like your sample)
        # make them absolute against the /english/ root
        full = urljoin(ENGLISH_ROOT, href)
        # simple heuristic: keep only links that look like act-detail pages (exclude nav, images, etc.)
        if "coat.jpg" in full.lower():
            continue
        if "javascript:" in full.lower():
            continue
        # exclude the current listing page
        if full == list_url:
            continue
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
    # 1) ensure the download tab content is visible (if available)
    try:
        tab = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#download"))
        )
    except Exception:
        tab = None

    containers = [tab] if tab else []
    # also scan whole doc as fallback
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
            m = re.search(r"['\"](.*?\.pdf[^'\"]*)['\"]", js, re.I)
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
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
        return out_path
    with session.get(url, stream=True, timeout=90) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
    return out_path

def main():
    os.makedirs(SAVE_DIR, exist_ok=True)
    driver = build_driver(download_dir=SAVE_DIR)
    session = requests_session_from_driver(driver)

    acts = find_act_links_on_listing(driver, BASE_LIST_URL)
    if not acts:
        print("No act links found. See debug_listing.html for the exact HTML the browser saw.")
        driver.quit()
        return

    print(f"Found {len(acts)} candidate acts.")
    rows = []
    for i, (title, url) in enumerate(acts, 1):
        print(f"[{i}/{len(acts)}] {title} -> {url}")
        status, pdf_url, saved = "skipped", "", ""
        try:
            driver.get(url)
            # Click the “Print/Download PDF” tab if present
            try:
                tab = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[@id='pills-profile-tab' or contains(., 'Print/Download')][contains(@href, '#download')]"))
                )
                tab.click()
                WebDriverWait(driver, 8).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#download")))
            except Exception:
                pass  # tab may already be visible or named differently

            # gather PDF-like URLs
            candidates = try_extract_pdf_urls(driver)
            if not candidates:
                status = "no_pdf_found"
            else:
                # prefer real .pdf first
                candidates.sort(key=lambda u: (".pdf" not in u.lower(), len(u)))
                pdf_url = candidates[0]
                saved = download_pdf(session, pdf_url, SAVE_DIR, fname_hint=title)
                status = "downloaded"
        except Exception as e:
            status = f"error: {e}"

        rows.append({"act_title": title, "act_url": url, "pdf_url": pdf_url, "saved_path": saved, "status": status})
        time.sleep(POLITE_DELAY)

    with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["act_title","act_url","pdf_url","saved_path","status"])
        w.writeheader()
        w.writerows(rows)

    driver.quit()
    print(f"\nDone.\nPDFs → {os.path.abspath(SAVE_DIR)}\nLog  → {os.path.abspath(LOG_CSV)}")

if __name__ == "__main__":
    main()