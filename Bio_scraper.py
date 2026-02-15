import os
import json
import csv
import time
import random
import pytesseract
from PIL import Image
from io import BytesIO
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
COOKIES_FILE = "namebio_session.json"
OUTPUT_FILE = "namebio_data.csv"

# --- STEALTH FUNCTIONS ---
def add_stealth_js(context):
    """Injects JavaScript to hide automation properties."""
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    """)

def human_mouse_move(page):
    """Jiggles the mouse randomly."""
    try:
        for _ in range(random.randint(2, 4)):
            page.mouse.move(random.randint(100, 800), random.randint(100, 600), steps=5)
            time.sleep(random.uniform(0.1, 0.3))
    except:
        pass

def get_price_via_ocr(cell_element):
    """Reads the price visually using OCR."""
    try:
        png_bytes = cell_element.screenshot()
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

def main():
    print(">> Starting DropDax Proxy Scraper...")
    
    # 1. SETUP PROXY FROM GITHUB SECRETS
    # GitHub Action will pass this as an environment variable
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
        print(">> PROXY DETECTED! Routing traffic through residential network...")
        launch_options["proxy"] = {"server": proxy_url}
    else:
        print(">> No proxy found. Running on default IP (High Risk of Block).")

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_options)
        
        # Create context with standard viewport
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        add_stealth_js(context)
        load_cookies(context)
        
        try:
            page = context.new_page()
            
            # 2. NAVIGATE
            print(">> Connecting to NameBio...")
            page.goto("https://namebio.com/", timeout=90000, wait_until="domcontentloaded")
            human_mouse_move(page)
            
            # Check for Block
            if "blocked" in page.title().lower() or "cloudflare" in page.title().lower():
                print(">> STILL BLOCKED. The proxy might be flagged or not working.")
                page.screenshot(path="debug_block_proxy.png")
                raise Exception("Cloudflare blocked access.")

            # 3. HANDLE BANNER
            try:
                if page.is_visible("#nudge-countdown-container"):
                    print(">> Banner detected. Waiting...")
                    page.wait_for_selector("#nudge-countdown-container a[data-dismiss='modal']", state="visible", timeout=45000)
                    time.sleep(1)
                    page.click("#nudge-countdown-container a[data-dismiss='modal']")
                    print(">> Banner closed.")
            except:
                pass

            # 4. APPLY FILTERS (The usual logic)
            print(">> Applying filters...")
            page.wait_for_selector("button[data-id='extension']", state="attached", timeout=20000)
            
            # Extension: .com
            page.click("button[data-id='extension']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('.com')")
            time.sleep(1)

            # Venue: GoDaddy
            page.click("button[data-id='venue']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('GoDaddy')")
            time.sleep(1)

            # Date: Today
            page.click("button[data-id='date-range']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:nth-child(2) a")
            time.sleep(1)

            # Rows: 25
            page.select_option("select[name='search-results_length']", "25")
            
            # Search
            print(">> Clicking Search...")
            page.click("#search-submit")
            page.wait_for_selector("#search-results tbody tr", state="visible", timeout=30000)
            time.sleep(3)

            # 5. SCRAPE
            rows = page.query_selector_all("#search-results tbody tr")
            data = []
            
            for row in rows:
                if "No matching records" in row.inner_text(): continue
                cols = row.query_selector_all("td")
                if len(cols) < 4: continue

                domain = cols[0].inner_text().strip()
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
            page.screenshot(path="debug_crash.png")
            raise e
        
        browser.close()

if __name__ == "__main__":
    main()
