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
# Point to Tesseract if on Windows (On GitHub Actions, this is automatic)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def load_cookies(context):
    """Injects the saved session cookies into the browser."""
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, 'r') as f:
            cookies = json.load(f)
            # Ensure cookies is a list; sometimes it's saved as a dict with a 'cookies' key
            if isinstance(cookies, dict) and 'cookies' in cookies:
                cookies = cookies['cookies']
            context.add_cookies(cookies)
        print(">> Cookies injected successfully.")
    else:
        print(">> WARNING: No cookie file found! Script may fail to login.")

def handle_banner(page):
    """Detects and closes the unskippable ad banner."""
    try:
        # Check if the specific banner container exists
        banner_selector = "#nudge-countdown-container"
        close_button_selector = "#nudge-countdown-container a[data-dismiss='modal']"
        
        if page.is_visible(banner_selector):
            print(">> Banner detected. Waiting for 'Close' button (approx 30s)...")
            # Wait up to 40 seconds for the close button to become clickable
            page.wait_for_selector(close_button_selector, state="visible", timeout=40000)
            
            # Small buffer to ensure text is "Close"
            time.sleep(2) 
            page.click(close_button_selector)
            print(">> Banner closed.")
            time.sleep(1) # Wait for fade out
        else:
            print(">> No banner detected.")
    except Exception as e:
        print(f">> Banner handling warning: {e}")

def get_price_via_ocr(cell_element):
    """Takes a screenshot of the cell and reads the VISUAL text."""
    try:
        # 1. Take a screenshot of the specific <td> element
        png_bytes = cell_element.screenshot()
        
        # 2. Convert to an Image object
        image = Image.open(BytesIO(png_bytes))
        
        # 3. Use Tesseract to read the image
        # config='--psm 7' treats the image as a single text line
        text = pytesseract.image_to_string(image, config='--psm 7').strip()
        
        return text
    except Exception as e:
        return "OCR_ERROR"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        
        # 1. Login via Cookies
        load_cookies(context)
        page = context.new_page()
        
        # 2. Go to NameBio
        print(">> Navigating to NameBio...")
        page.goto("https://namebio.com/", timeout=60000)
        
        # 3. Handle Ad Banner
        handle_banner(page)

        # 4. Apply Filters
        print(">> Applying filters...")
        
        # A. Extension -> .com
        # Click the dropdown button
        page.click("button[data-id='extension']")
        # Click the option '.com' (assuming standard bootstrap-select structure)
        page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('.com')")
        print("   - Extension: .com set")
        time.sleep(0.5)

        # B. Venue -> GoDaddy
        page.click("button[data-id='venue']")
        page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('GoDaddy')")
        print("   - Venue: GoDaddy set")
        time.sleep(0.5)

        # C. Date Range -> First available option ("Today")
        # Click dropdown
        page.click("button[data-id='date-range']")
        # We select the 2nd <li>. The 1st is usually 'Any'. The 2nd is the newest date.
        # We use nth-child(2) 
        page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:nth-child(2) a")
        print("   - Date: Set to first available option (Today)")
        time.sleep(0.5)

        # 5. Set Row Count to 25
        # This is a <select> element, so we use select_option
        page.select_option("select[name='search-results_length']", "25")
        print("   - Rows: Set to 25")

        # 6. Click Search
        print(">> Clicking Search...")
        page.click("#search-submit")
        
        # Wait for table to update (look for the processing indicator to disappear or table to load)
        page.wait_for_selector("#search-results tbody tr", state="visible")
        # Small sleep to ensure the font rendering is complete
        time.sleep(3)

        # 7. Scrape Data
        print(">> Scraping rows...")
        rows = page.query_selector_all("#search-results tbody tr")
        
        data = []
        for row in rows:
            # Check if row is empty/placeholder
            if "No matching records" in row.inner_text():
                continue

            cols = row.query_selector_all("td")
            if len(cols) < 4: 
                continue

            # Column 0: Domain (Text)
            domain = cols[0].inner_text().strip()
            
            # Column 1: Price (Visual/OCR)
            # We pass the ElementHandle (cols[1]) to our OCR function
            price_visual = get_price_via_ocr(cols[1])
            
            # Clean up Price (remove non-numeric chars except comma/dot if needed)
            # Keeping it simple for now, just removing 'USD' if OCR caught it
            price_clean = price_visual.replace("USD", "").replace("$", "").strip()

            # Column 2: Date (Text)
            date = cols[2].inner_text().strip()
            
            # Column 3: Venue (Text)
            venue = cols[3].inner_text().strip()

            print(f"   Found: {domain} | Price (OCR): {price_clean}")
            
            data.append([domain, price_clean, date, venue])

        # 8. Save to CSV
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Domain", "Price", "Date", "Venue"])
            writer.writerows(data)
            
        print(f">> Done! Saved {len(data)} rows to {OUTPUT_FILE}")
        browser.close()

if __name__ == "__main__":
    main()
