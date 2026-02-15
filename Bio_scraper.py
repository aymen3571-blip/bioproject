import os
import json
import csv
import time
import random
import sys
from urllib.parse import urlparse
import subprocess

# --- LIBRARY FIX ---
import pytesseract
from PIL import Image
from io import BytesIO
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
COOKIES_FILE = "namebio_session.json"
OUTPUT_FILE = "namebio_data.csv"
MAX_RETRIES = 3 

# --- ADVANCED NATIVE STEALTH ---
def apply_advanced_stealth(page):
    """
    Injects specific JavaScript overrides to mask the bot.
    """
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel(R) Iris(TM) Plus Graphics 640';
            return getParameter(parameter);
        };
    """)

def human_mouse_move(page):
    try:
        # Move mouse to random positions to simulate human 'hesitation'
        for _ in range(random.randint(2, 4)):
            x = random.randint(100, 1000)
            y = random.randint(100, 800)
            page.mouse.move(x, y, steps=10)
            time.sleep(random.uniform(0.1, 0.3))
    except:
        pass

def get_price_via_ocr(cell_element):
    try:
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

# --- ENHANCED CLOUDFLARE BYPASS (THE PATIENT WAITER) ---
def bypass_challenge(page):
    print(">> CHECKING FOR CLOUDFLARE CHALLENGE...")
    time.sleep(5)
    
    # 1. IDENTIFY THE FRAME
    turnstile_frame = None
    for frame in page.frames:
        if "cloudflare" in frame.url or "turnstile" in frame.url:
            turnstile_frame = frame
            print(f">> Found Turnstile Frame: {frame.url}")
            break
            
    if turnstile_frame:
        print(">> Attempting to click Turnstile Checkbox...")
        try:
            # METHOD A: Geometry Click
            box = turnstile_frame.frame_element().bounding_box()
            if box:
                print(f">> Frame detected at X={box['x']}, Y={box['y']}")
                click_x = box['x'] + (box['width'] / 2)
                click_y = box['y'] + (box['height'] / 2)
                
                # Move mouse there slowly
                page.mouse.move(click_x, click_y, steps=20)
                time.sleep(0.5)
                page.mouse.click(click_x, click_y)
                print(">> Clicked via Coordinates.")
            else:
                # METHOD B: Selector Click
                print(">> Coordinates failed. Trying selector...")
                turnstile_frame.click("body", force=True)
                
        except Exception as e:
            print(f">> Click failed: {e}")

    # 2. PATIENT WAIT LOOP (Updated)
    # Cloudflare spinners can take 20-30s on proxies. We wait up to 45s.
    print(">> Waiting for spinner to finish (Max 45s)...")
    
    for i in range(45):
        title = page.title().lower()
        if "robot" not in title and "moment" not in title and "attention" not in title:
            print(">> SUCCESS! Challenge passed.")
            return True
            
        # Every 5 seconds, wiggle mouse to show we are alive
        if i % 5 == 0:
            print(f">> Still verifying... ({i}s)")
            human_mouse_move(page)
            
        time.sleep(1)
        
    print(">> FAILED: Spinner timed out. Taking screenshot.")
    return False

def connect_with_retries(page, url, retries=3):
    for attempt in range(1, retries + 1):
        try:
            print(f">> Connection Attempt {attempt}/{retries}...")
            # Use 'domcontentloaded' to return faster
            page.goto(url, timeout=90000, wait_until="domcontentloaded") 
            
            if "chrome-error" in page.url:
                raise Exception("Proxy dropped connection (Chrome Error).")

            time.sleep(5)
            return True
        except Exception as e:
            print(f">> Attempt {attempt} failed: {e}")
            if attempt < retries:
                time.sleep(10)
            else:
                return False
    return False

def main():
    print(">> Starting DropDax Proxy Scraper (Patient Edition)...")
    
    proxy_url = os.environ.get("PROXY_URL") 
    
    launch_options = {
        "headless": False, 
        "args": [
            "--no-sandbox",
            "--ignore-certificate-errors",
            "--disable-infobars",
            "--disable-blink-features=AutomationControlled",
            "--enable-features=NetworkService,NetworkServiceInProcess",
            "--window-size=1920,1080"
        ]
    }

    if proxy_url:
        print(">> PROXY DETECTED.")
        try:
            parsed = urlparse(proxy_url)
            server_address = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
            launch_options["proxy"] = {
                "server": server_address,
                "username": parsed.username,
                "password": parsed.password
            }
            print(f">> Proxy Configured: {parsed.hostname}:{parsed.port}")
        except:
             print(">> WARNING: Could not parse proxy URL. Using raw string.")
             launch_options["proxy"] = {"server": proxy_url}

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_options)
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        
        try:
            page = context.new_page()
            apply_advanced_stealth(page)

            # 1. LOGIN & CONNECT
            load_cookies(context)
            
            if not connect_with_retries(page, "https://namebio.com/"):
                raise Exception("Failed to connect to NameBio.")
            
            # 2. HANDLE CLOUDFLARE
            bypass_success = bypass_challenge(page)
            if not bypass_success:
                page.screenshot(path="debug_block_final.png", animations="disabled")
                raise Exception("Cloudflare blocked access (Challenge not solved).")

            # 3. HANDLE BANNER
            try:
                # Look for the banner more aggressively
                if page.locator("#nudge-countdown-container").is_visible(timeout=10000):
                    print(">> Banner detected. Waiting...")
                    page.locator("#nudge-countdown-container a[data-dismiss='modal']").click(timeout=45000)
                    print(">> Banner closed.")
            except:
                pass

            # 4. APPLY FILTERS
            print(">> Applying filters...")
            try:
                # Wait longer for filters to appear after challenge
                page.wait_for_selector("button[data-id='extension']", state="attached", timeout=60000)
            except:
                print(">> ERROR: Filters not found. We might still be on the Challenge screen.")
                page.screenshot(path="debug_error_nofilters.png", animations="disabled")
                raise Exception("Filters did not load.")
            
            page.click("button[data-id='extension']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('.com')")
            time.sleep(2)

            page.click("button[data-id='venue']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:has-text('GoDaddy')")
            time.sleep(2)

            page.click("button[data-id='date-range']")
            page.click("div.dropdown-menu.open ul.dropdown-menu.inner li:nth-child(2) a")
            time.sleep(2)

            page.select_option("select[name='search-results_length']", "25")
            
            # 5. SCRAPE
            print(">> Clicking Search...")
            page.click("#search-submit")
            page.wait_for_selector("#search-results tbody tr", state="visible", timeout=60000)
            time.sleep(5) 

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
            try:
                page.screenshot(path="debug_crash.png", animations="disabled")
            except:
                pass
            raise e
        
        browser.close()

if __name__ == "__main__":
    main()
