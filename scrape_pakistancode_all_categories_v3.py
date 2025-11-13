#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scrape ALL categories on Pakistan Code (English) and download each Act's PDF.
- Opens categories page
- Iterates categories (skips (0) by default)
- Enters each Act, clicks "Print/Download PDF", grabs the real PDF URL
- Downloads PDFs, logs to CSV, keeps a dedupe list across runs

Requires: selenium, webdriver-manager, requests, beautifulsoup4
"""

import os
import re
import time
import csv
import argparse
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


# ========= DEFAULTS (edit if you like) =========
DEFAULT_CATEGORIES_URL = "https://www.pakistancode.gov.pk/english/LGu0xVD.php"
ENGLISH_ROOT = "https://www.pakistancode.gov.pk/english/"
DEFAULT_OUT_DIR = "pakistan_code_pdfs"
DEFAULT_LOG = "download_log.csv"
DEFAULT_DEDUPE_FILE = "downloaded_urls.txt"

TIMEOUT = 45
POLITE_DELAY_ACT = 1.0
POLITE_DELAY_CAT = 1.2
HEADLESS_DEFAULT = True
SKIP_ZERO_DEFAULT = True  # ignore categories showing (0)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
# ===============================================


def slugify(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip().replace("/", "-")
    return re.sub(r"[^A-Za-z0-9\-_.() ]", "_", s)[:180]


def build_driver(headless: bool, download_dir=None):
    opts = Options()
    if headless:
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
    driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()), options=opts
    )
    driver.set_page_load_timeout(90)
    return driver


def requests_session_from_driver(driver):
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    # copy cookies from Selenium
    for c in driver.get_cookies():
        s.cookies.set(c.get("name"), c.get("value"))
    return s


def open_categories_page(driver, url):
    driver.get(url)
    WebDriverWait(driver, TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
    )
    time.sleep(1.5)

    # Try clicking the Categories tab if present
    try:
        tab = WebDriverWait(driver, 4).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//a[contains(@href,'#category') and (@id='pills-home-tab' or contains(.,'Categories'))]",
                )
            )
        )
        tab.click()
        WebDriverWait(driver, 6).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#category"))
        )
    except Exception:
        pass

    html = driver.page_source
    with open("debug_categories.html", "w", encoding="utf-8") as f:
        f.write(html)
    return html


def parse_categories(html: str, skip_zero: bool, only_ids_set):
    soup = BeautifulSoup(html, "html.parser")

    # Prefer within the #category pane, fall back to any .deptlist
    blocks = soup.select("#category .deptlist")
    if not blocks:
        blocks = soup.select(".deptlist")

    cats = []
    for div in blocks:
        a = div.select_one("a[href]")
        if not a:
            continue
        href = a.get("href", "").strip()
        title = a.get_text(strip=True)

        # count in "(123)" style
        count = 0
        sc = div.select_one(".showCount")
        if sc:
            m = re.search(r"\((\d+)\)", sc.get_text())
            if m:
                count = int(m.group(1))

        full = urljoin(ENGLISH_ROOT, href)
        m_id = re.search(r"catid=(\d+)", full)
        cat_id = int(m_id.group(1)) if m_id else None

        if skip_zero and count == 0:
            continue
        if only_ids_set and (cat_id not in only_ids_set):
            continue

        cats.append({"id": cat_id, "title": title, "url": full, "count": count})

    # de-dup by url
    seen, out = set(), []
    for c in cats:
        if c["url"] in seen:
            continue
        seen.add(c["url"])
        out.append(c)
    return out


def find_act_links_on_listing(driver, list_url):
    driver.get(list_url)
    WebDriverWait(driver, TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
    )
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

    # Ensure #download pane exists (best effort)
    try:
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#download"))
        )
    except Exception:
        pass

    containers = []
    try:
        containers.append(driver.find_element(By.CSS_SELECTOR, "#download"))
    except Exception:
        pass
    containers.append(driver)

    def els(el, sel):
        try:
            return el.find_elements(By.CSS_SELECTOR, sel)
        except Exception:
            return []

    for el in containers:
        for a in els(el, "a[href]"):
            href = a.get_attribute("href") or ""
            if any(k in href.lower() for k in [".pdf", "download", "print", "export"]):
                pdf_urls.add(href)
        for ifr in els(el, "iframe[src]"):
            src = ifr.get_attribute("src") or ""
            if any(k in src.lower() for k in [".pdf", "download", "print", "export"]):
                pdf_urls.add(src)
        for emb in els(el, "embed[src]"):
            src = emb.get_attribute("src") or ""
            if any(k in src.lower() for k in [".pdf", "download", "print", "export"]):
                pdf_urls.add(src)
        for btn in els(el, "button[onclick], a[onclick]"):
            js = btn.get_attribute("onclick") or ""
            m = re.search(r"['\"](.*?\.pdf[^'\"}]*)['\"]", js, re.I)
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

    # avoid overwriting: if same name exists, append short hash
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


def ensure_dedupe_file(path):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
    with open(path, "r", encoding="utf-8") as f:
        return set(ln.strip() for ln in f if ln.strip())


def append_dedupe(path, url):
    with open(path, "a", encoding="utf-8") as f:
        f.write(url + "\n")


def process_act(driver, session, act_title, act_url, cat_title, cat_id, save_dir):
    status, pdf_url, saved = "skipped", "", ""
    try:
        driver.get(act_url)

        # Click the Print/Download tab if present
        try:
            tab = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//a[@id='pills-profile-tab' or contains(., 'Print/Download')]"
                        "[contains(@href, '#download')]",
                    )
                )
            )
            tab.click()
            WebDriverWait(driver, 8).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "#download"))
            )
        except Exception:
            pass

        candidates = try_extract_pdf_urls(driver)
        if not candidates:
            status = "no_pdf_found"
        else:
            # prefer URLs that already end with .pdf
            candidates.sort(key=lambda u: (".pdf" not in u.lower(), len(u)))
            pdf_url = candidates[0]
            saved = download_pdf(session, pdf_url, save_dir, fname_hint=act_title)
            status = "downloaded"
    except Exception as e:
        status = f"error: {e}"
    return {
        "category_id": cat_id,
        "category_title": cat_title,
        "act_title": act_title,
        "act_url": act_url,
        "pdf_url": pdf_url,
        "saved_path": saved,
        "status": status,
    }


def get_cat_id_from_url(u: str):
    m = re.search(r"catid=(\d+)", u)
    return int(m.group(1)) if m else None


def main():
    # Optional CLI flags (all have safe defaults so you can run without args)
    ap = argparse.ArgumentParser(description="Scrape Pakistan Code categories & download PDFs.")
    ap.add_argument("--categories-url", default=DEFAULT_CATEGORIES_URL, help="Categories page URL")
    ap.add_argument("--headful", action="store_true", help="Run Chrome with UI (not headless)")
    ap.add_argument("--only", default="", help="Comma-separated catids to include (e.g., 1,2,3)")
    ap.add_argument("--include-zero", action="store_true", help="Include categories with (0) items")
    ap.add_argument("--out", default=DEFAULT_OUT_DIR, help="Output folder for PDFs")
    ap.add_argument("--log", default=DEFAULT_LOG, help="CSV log path")
    ap.add_argument("--dedupe", default=DEFAULT_DEDUPE_FILE, help="Text file to track downloaded PDF URLs")
    args = ap.parse_args()

    only_ids_set = set(int(x) for x in args.only.split(",") if x.strip().isdigit()) if args.only else None
    skip_zero = SKIP_ZERO_DEFAULT and (not args.include_zero)

    os.makedirs(args.out, exist_ok=True)

    driver = build_driver(headless=(not args.headful), download_dir=args.out)

    # Navigate first, THEN create the requests session so cookies carry over
    html = open_categories_page(driver, args.categories_url)
    session = requests_session_from_driver(driver)

    downloaded_urls = ensure_dedupe_file(args.dedupe)
    cats = parse_categories(html, skip_zero=skip_zero, only_ids_set=only_ids_set)

    if not cats:
        print("No categories found. Check debug_categories.html to see what Selenium received.")
        driver.quit()
        return

    print(f"Found {len(cats)} categories.")
    rows = []
    for ci, cat in enumerate(cats, 1):
        cat_title, cat_url, cat_id = cat["title"], cat["url"], cat["id"]
        print(f"\n=== [{ci}/{len(cats)}] Category: {cat_title} (id={cat_id}, count={cat['count']}) ===")

        acts = find_act_links_on_listing(driver, cat_url)
        print(f"Found {len(acts)} acts in this category.")

        for i, (act_title, act_url) in enumerate(acts, 1):
            print(f"  [{i}/{len(acts)}] {act_title}")
            res = process_act(driver, session, act_title, act_url, cat_title, cat_id, args.out)

            # cross-run de-dupe by final pdf_url
            if res["pdf_url"]:
                if res["pdf_url"] in downloaded_urls and res["status"] == "downloaded":
                    res["status"] = "duplicate_skipped"
                elif res["status"] == "downloaded":
                    downloaded_urls.add(res["pdf_url"])
                    append_dedupe(args.dedupe, res["pdf_url"])

            rows.append(res)
            time.sleep(POLITE_DELAY_ACT)

        time.sleep(POLITE_DELAY_CAT)

    # Write CSV log
    with open(args.log, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "category_id",
                "category_title",
                "act_title",
                "act_url",
                "pdf_url",
                "saved_path",
                "status",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    driver.quit()
    print(f"\nDone. PDFs → {os.path.abspath(args.out)}")
    print(f"Log  → {os.path.abspath(args.log)}")
    print(f"Dedupe file → {os.path.abspath(args.dedupe)}")


if __name__ == "__main__":
    main()