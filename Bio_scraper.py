import os
import json
import csv
import time
import pytesseract
from PIL import Image
from io import BytesIO
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
COOKIES_FILE = "namebio_session.json"
OUTPUT_FILE = "namebio_data.csv"

def load_cookies(context):
    """Injects the saved session cookies into the browser."""
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'r') as f:
                data = json.load(f)
                # Handle different cookie export formats
                if isinstance(data, dict) and 'cookies' in data:
                    cookies = data['cookies']
                elif isinstance(data, list):
                    cookies = data
                else:
                    print(">> ERROR: Unknown cookie format.")
                    return
                context.add_cookies(cookies)
            print(">> Cookies injected successfully.")
        except Exception as e:
            print(f">> ERROR loading cookies: {e}")
    else:
        print(">> WARNING: No cookie file found! Script may fail to login.")

def handle_banner(page):
    """Detects and closes the unskippable ad banner."""
    try:
        # Check if the specific banner container exists
        banner_selector = "#nudge-countdown-container"
        close_button_selector = "#nudge-countdown-container a[data-dismiss='modal']"
        
        # Quick check if banner is there
        if page.is_visible(banner_selector):
            print(">> Banner detected. Waiting for 'Close' button (approx 30s)...")
            # Wait up to 40 seconds for the close button to become clickable
            page.wait_for_selector(close_button_selector, state="visible", timeout=40000)
            time.sleep(2) 
            page.click(close_button_selector)
            print(">> Banner closed.")
            time.sleep(1) 
        else:
            print(">> No banner detected (or page not loaded yet).")
    except Exception as e:
        print(f">> Banner handling warning: {e}")

def get_price_via_ocr(cell_element):
    """Takes a screenshot of the cell and reads the VISUAL text."""
    try:
        png_bytes = cell_element.screenshot()
        image = Image.open(BytesIO(png_bytes))
        # --psm 7 treats the image as a single text line
        text = pytesseract.image_to_string(image, config='--psm 7').strip()
        return text
    except Exception as e:
        return "OCR_ERROR"

def main():
    print(">> Starting DropDax Bio Scraper...")
    with sync_playwright() as p:
        # NEW: Add arguments to hide automation features
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"] 
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        
        try:
            # 1. Login via Cookies
            load_cookies(context)
            page = context.new_page()
            
            # 2. Go to NameBio
            print(">> Navigating to NameBio...")
            page.goto("https://namebio.com/", timeout=60000)
            
            # NEW: Wait for the page to actually load content (e.g. the navbar or footer)
            # This confirms we aren't stuck on a blank screen
            try:
                page.wait_for_selector("body", timeout=10000)
            except:
                print(">> Page body did not load.")

            # 3. Handle Ad Banner
            handle_banner(page)

            # NEW: Check if we are stuck on a Cloudflare Challenge or Login
            title = page.title()
            print(f">> Page Title: {title}")
            
            # Take a "State Check" screenshot before clicking
            # This helps us see if the filters are actually visible
            page.screenshot(path="debug_state_check.png")

            # 4. Apply Filters
            print(">> Applying filters...")
            
            # Wait specifically for the extension button to be attached to DOM
            page.wait_for_selector("button[data-id='extension']", state="attached", timeout=10000)

            # A. Extension -> .com
            page.click("button[data-id='extension']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('.com')")
            print("   - Extension: .com set")
            time.sleep(0.5)

            # B. Venue -> GoDaddy
            page.click("button[data-id='venue']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('GoDaddy')")
            print("   - Venue: GoDaddy set")
            time.sleep(0.5)

            # C. Date Range -> First available option ("Today")
            page.click("button[data-id='date-range']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:nth-child(2) a")
            print("   - Date: Set to Today")
            time.sleep(0.5)

            # 5. Set Row Count to 25
            page.select_option("select[name='search-results_length']", "25")
            print("   - Rows: Set to 25")

            # 6. Click Search
            print(">> Clicking Search...")
            page.click("#search-submit")
            
            # Wait for results
            page.wait_for_selector("#search-results tbody tr", state="visible", timeout=15000)
            time.sleep(3) # Let font render

            # 7. Scrape Data
            print(">> Scraping rows...")
            rows = page.query_selector_all("#search-results tbody tr")
            
            data = []
            for row in rows:
                if "No matching records" in row.inner_text():
                    continue

                cols = row.query_selector_all("td")
                if len(cols) < 4: continue

                domain = cols[0].inner_text().strip()
                price_visual = get_price_via_ocr(cols[1])
                price_clean = price_visual.replace("USD", "").replace("$", "").strip()
                date = cols[2].inner_text().strip()
                venue = cols[3].inner_text().strip()

                print(f"   Found: {domain} | Price (OCR): {price_clean}")
                data.append([domain, price_clean, date, venue])

            # 8. Save to CSV
            with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Domain", "Price", "Date", "Venue"])
                writer.writerows(data)
                
            print(f">> Done! Saved {len(data)} rows.")
        
        except Exception as e:
            print(f"\n>> CRITICAL ERROR: {e}")
            print(">> Taking emergency screenshot: 'debug_error.png'")
            page.screenshot(path="debug_error.png")
            raise e # Re-raise to fail the workflow

        browser.close()

if __name__ == "__main__":
    main()
