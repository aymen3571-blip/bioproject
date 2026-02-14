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

def add_stealth_js(context):
    """Injects JavaScript to hide automation properties from Cloudflare."""
    context.add_init_script("""
        // Overwrite the `webdriver` property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // Mock chrome object
        window.chrome = {
            runtime: {}
        };

        // Mock plugins to look like a real Intel Mac or Windows PC
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });

        // Mock languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
    """)

def human_mouse_move(page):
    """Jiggles the mouse randomly to simulate human presence."""
    try:
        for _ in range(random.randint(3, 5)):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            page.mouse.move(x, y, steps=10)
            time.sleep(random.uniform(0.1, 0.3))
    except:
        pass

def load_cookies(context):
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'cookies' in data:
                    cookies = data['cookies']
                elif isinstance(data, list):
                    cookies = data
                else:
                    return
                context.add_cookies(cookies)
            print(">> Cookies injected.")
        except Exception as e:
            print(f">> Cookie error: {e}")
    else:
        print(">> No cookie file found.")

def get_price_via_ocr(cell_element):
    try:
        png_bytes = cell_element.screenshot()
        image = Image.open(BytesIO(png_bytes))
        text = pytesseract.image_to_string(image, config='--psm 7').strip()
        return text
    except:
        return "OCR_ERROR"

def main():
    print(">> Starting DropDax Stealth Scraper...")
    with sync_playwright() as p:
        # 1. LAUNCH WITH STEALTH ARGUMENTS
        browser = p.chromium.launch(
            headless=True,  # We use the args below to make it 'new' headless
            args=[
                "--headless=new", # The modern, stealthier headless mode
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ]
        )
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        
        # 2. INJECT STEALTH SCRIPTS
        add_stealth_js(context)
        
        try:
            load_cookies(context)
            page = context.new_page()
            
            # 3. NAVIGATE SLOWLY
            print(">> Navigating...")
            page.goto("https://namebio.com/", timeout=60000, wait_until="domcontentloaded")
            
            # 4. CHECK FOR BLOCK
            human_mouse_move(page)
            time.sleep(3)
            
            title = page.title()
            print(f">> Page Title: {title}")
            
            if "blocked" in title.lower() or "cloudflare" in title.lower():
                print(">> DETECTED BLOCK. Saving screenshot...")
                page.screenshot(path="debug_block.png")
                raise Exception("Cloudflare blocked access.")

            # 5. BANNER LOGIC
            try:
                if page.is_visible("#nudge-countdown-container"):
                    print(">> Banner found. Waiting...")
                    page.wait_for_selector("#nudge-countdown-container a[data-dismiss='modal']", state="visible", timeout=45000)
                    time.sleep(1)
                    page.click("#nudge-countdown-container a[data-dismiss='modal']")
                    print(">> Banner closed.")
            except Exception as e:
                print(f">> Banner skipped: {e}")

            # 6. FILTERS
            print(">> Applying filters...")
            page.wait_for_selector("button[data-id='extension']", state="attached", timeout=15000)
            
            # Extension
            page.click("button[data-id='extension']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('.com')")
            time.sleep(random.uniform(0.5, 1.5))

            # Venue
            page.click("button[data-id='venue']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('GoDaddy')")
            time.sleep(random.uniform(0.5, 1.5))

            # Date (Today)
            page.click("button[data-id='date-range']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:nth-child(2) a")
            time.sleep(random.uniform(0.5, 1.5))

            # Rows
            page.select_option("select[name='search-results_length']", "25")
            
            # Search
            print(">> Clicking Search...")
            page.click("#search-submit")
            page.wait_for_selector("#search-results tbody tr", state="visible", timeout=30000)
            time.sleep(3)

            # 7. SCRAPE
            print(">> Scraping...")
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
            print(f">> CRITICAL ERROR: {e}")
            page.screenshot(path="debug_crash.png")
            raise e
        
        browser.close()

if __name__ == "__main__":
    main()
