import os
import json
import csv
import time
import random
import pytesseract
from PIL import Image
from io import BytesIO
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# --- CONFIGURATION ---
COOKIES_FILE = "namebio_session.json"
OUTPUT_FILE = "namebio_data.csv"
MAX_RETRIES = 3  # How many times to try connecting

# --- STEALTH FUNCTIONS ---
def add_stealth_js(context):
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    """)

def human_mouse_move(page):
    try:
        for _ in range(random.randint(2, 4)):
            page.mouse.move(random.randint(100, 800), random.randint(100, 600), steps=5)
            time.sleep(random.uniform(0.1, 0.3))
    except:
        pass

def get_price_via_ocr(cell_element):
    try:
        # animations="disabled" helps stability
        png_bytes = cell_element.screenshot(animations="disabled")
        image = Image.open(BytesIO(png_bytes))
        text = pytesseract.image_to_string(image, config='--psm 7').strip()
        return text
    except:
        return "OCR_ERROR"

def load_cookies(context):
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'r') as f:
                data = json.load(f)
                cookies = data['cookies'] if isinstance(data, dict) and 'cookies' in data else data
                context.add_cookies(cookies)
            print(">> Cookies injected.")
        except Exception as e:
            print(f">> Cookie error: {e}")

def connect_with_retries(page, url, retries=3):
    """Tries to load the page. If it fails, it refreshes and tries again."""
    for attempt in range(1, retries + 1):
        try:
            print(f">> Connection Attempt {attempt}/{retries}...")
            # 'commit' is faster than 'domcontentloaded'. We wait for selectors later.
            page.goto(url, timeout=60000, wait_until="commit") 
            
            # Now wait for the body to ensure actual load
            page.wait_for_selector("body", timeout=30000)
            print(">> Page loaded successfully.")
            return True
        except Exception as e:
            print(f">> Attempt {attempt} failed: {e}")
            if attempt < retries:
                print(">> Retrying in 5 seconds...")
                time.sleep(5)
            else:
                return False
    return False

def main():
    print(">> Starting DropDax Proxy Scraper (Robust Mode)...")
    
    proxy_url = os.environ.get("PROXY_URL") 
    
    launch_options = {
        "headless": True,
        "args": [
            "--headless=new",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox"
        ]
    }

    if proxy_url:
        print(">> PROXY DETECTED.")
        launch_options["proxy"] = {"server": proxy_url}
    else:
        print(">> No proxy found. Running on default IP.")

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_options)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        add_stealth_js(context)
        load_cookies(context)
        
        try:
            page = context.new_page()
            
            # 1. ROBUST CONNECTION
            if not connect_with_retries(page, "https://namebio.com/"):
                raise Exception("Failed to connect to NameBio after multiple retries.")
            
            human_mouse_move(page)
            
            # Check for Block
            title = page.title()
            print(f">> Page Title: {title}")
            if "blocked" in title.lower() or "cloudflare" in title.lower():
                print(">> BLOCKED. Taking screenshot...")
                # 'animations="disabled"' prevents the font-wait crash
                page.screenshot(path="debug_block_proxy.png", animations="disabled")
                raise Exception("Cloudflare blocked access.")

            # 2. HANDLE BANNER
            try:
                if page.is_visible("#nudge-countdown-container"):
                    print(">> Banner detected. Waiting...")
                    page.wait_for_selector("#nudge-countdown-container a[data-dismiss='modal']", state="visible", timeout=45000)
                    time.sleep(1)
                    page.click("#nudge-countdown-container a[data-dismiss='modal']")
                    print(">> Banner closed.")
            except:
                pass

            # 3. APPLY FILTERS
            print(">> Applying filters...")
            # We wait longer here because proxies can be laggy
            page.wait_for_selector("button[data-id='extension']", state="attached", timeout=30000)
            
            page.click("button[data-id='extension']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('.com')")
            time.sleep(1)

            page.click("button[data-id='venue']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('GoDaddy')")
            time.sleep(1)

            page.click("button[data-id='date-range']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:nth-child(2) a")
            time.sleep(1)

            page.select_option("select[name='search-results_length']", "25")
            
            # 4. SEARCH & SCRAPE
            print(">> Clicking Search...")
            page.click("#search-submit")
            page.wait_for_selector("#search-results tbody tr", state="visible", timeout=40000)
            time.sleep(5) # Extra sleep for fonts on slow proxy

            rows = page.query_selector_all("#search-results tbody tr")
            data = []
            
            for row in rows:
                if "No matching records" in row.inner_text(): continue
                cols = row.query_selector_all("td")
                if len(cols) < 4: continue

                domain = cols[0].inner_text().strip()
                # Pass element to OCR function
                price = get_price_via_ocr(cols[1]).replace("USD", "").replace("$", "").strip()
                date = cols[2].inner_text().strip()
                venue = cols[3].inner_text().strip()
                
                print(f"   Found: {domain} | {price}")
                data.append([domain, price, date, venue])

            with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Domain", "Price", "Date", "Venue"])
                writer.writerows(data)
                
            print(f">> Success! {len(data)} rows saved.")

        except Exception as e:
            print(f">> ERROR: {e}")
            try:
                page.screenshot(path="debug_crash.png", animations="disabled")
            except:
                print(">> Could not take crash screenshot.")
            raise e
        
        browser.close()

if __name__ == "__main__":
    main()
