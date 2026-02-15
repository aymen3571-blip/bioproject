import os
import json
import csv
import time
import random
import pytesseract
from PIL import Image
from io import BytesIO
# NEW: Import urlparse to safely split the proxy string
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
COOKIES_FILE = "namebio_session.json"
OUTPUT_FILE = "namebio_data.csv"
MAX_RETRIES = 3 

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
        # Move mouse more naturally to trigger Cloudflare "Human" detection
        for _ in range(random.randint(3, 6)):
            x = random.randint(100, 1000)
            y = random.randint(100, 800)
            page.mouse.move(x, y, steps=10)
            time.sleep(random.uniform(0.2, 0.5))
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

# NEW: Specific function to handle "Prove you are not a robot" screens
def bypass_challenge(page):
    print(">> CHECKING FOR CHALLENGE SCREEN...")
    title = page.title()
    
    if "robot" in title.lower() or "challenge" in title.lower() or "attention" in title.lower():
        print(f">> Challenge Detected (Title: {title}). Starting Bypass...")
        
        # 1. Take a picture of the challenge so we know what we are dealing with
        try:
            page.screenshot(path="debug_challenge_screen.png", animations="disabled")
        except: 
            pass

        # 2. Wait and Wiggle (Turnstile often auto-solves with good IPs)
        print(">> Waiting 15 seconds for auto-solve...")
        human_mouse_move(page)
        time.sleep(10)
        human_mouse_move(page)
        time.sleep(5)
        
        # 3. Check if we passed
        if "robot" not in page.title().lower():
            print(">> SUCCESS! Challenge bypassed automatically.")
            return True

        # 4. If still stuck, try to click any frames (Last Resort)
        print(">> Still stuck. Attempting to click frames...")
        try:
            # Click center of screen (common for big buttons)
            page.mouse.click(960, 540)
            
            # Look for common Cloudflare iframes and click them
            frames = page.frames
            for frame in frames:
                try:
                    # Generic click in the middle of every frame found
                    box = frame.bounding_box()
                    if box:
                        x = box['x'] + (box['width'] / 2)
                        y = box['y'] + (box['height'] / 2)
                        page.mouse.click(x, y)
                except:
                    pass
        except:
            pass
            
        time.sleep(10) # Wait for click to process
        
        # Final Check
        if "robot" in page.title().lower():
             print(">> FAILED to bypass challenge.")
             return False
        else:
             print(">> SUCCESS! Challenge bypassed after clicks.")
             return True
             
    print(">> No challenge detected.")
    return True

def connect_with_retries(page, url, retries=3):
    """Tries to load the page with extended timeouts."""
    for attempt in range(1, retries + 1):
        try:
            print(f">> Connection Attempt {attempt}/{retries}...")
            # Increased timeout to 90 seconds for slow proxies
            page.goto(url, timeout=90000, wait_until="commit") 
            
            # Wait for body (Success indicator)
            page.wait_for_selector("body", timeout=60000)
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
    print(">> Starting DropDax Proxy Scraper...")
    
    proxy_url = os.environ.get("PROXY_URL") 
    
    launch_options = {
        "headless": True,
        "args": [
            "--headless=new",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--ignore-certificate-errors", # NEW: Ignore SSL certificate errors from proxy
            "--enable-features=NetworkService,NetworkServiceInProcess" # Extra stability
        ]
    }

    if proxy_url:
        print(">> PROXY DETECTED.")
        try:
            # NEW: Explicitly parse the proxy string to separate credentials from the server.
            # This fixes issues where Playwright fails to parse complex auth strings automatically.
            parsed = urlparse(proxy_url)
            server_address = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
            launch_options["proxy"] = {
                "server": server_address,
                "username": parsed.username,
                "password": parsed.password
            }
            print(f">> Proxy Configured: {parsed.hostname}:{parsed.port} (Auth: Explicit)")
        except Exception as e:
             print(f">> WARNING: Could not parse proxy URL ({e}). Using raw string.")
             launch_options["proxy"] = {"server": proxy_url}
    else:
        print(">> No proxy found. Running on default IP.")

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_options)
        
        # NEW: Added ignore_https_errors=True to trust the proxy certificate
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        
        add_stealth_js(context)
        
        try:
            page = context.new_page()

            # 1. TEST PROXY CONNECTION FIRST
            print(">> Testing Proxy Connection (ipify)...")
            try:
                # NEW: Increased timeout to 60s because rotating proxies can be slow to handshake
                page.goto("https://api.ipify.org?format=json", timeout=60000)
                content = page.content()
                print(f">> Proxy is working! IP Info: {page.inner_text('body')}")
            except Exception as e:
                print(f">> WARNING: Proxy test failed. URL format might be wrong or proxy is slow. Error: {e}")

            # 2. LOGIN & CONNECT
            load_cookies(context)
            
            if not connect_with_retries(page, "https://namebio.com/"):
                raise Exception("Failed to connect to NameBio. Check Proxy URL.")
            
            # NEW: CHECK FOR AND HANDLE ROBOT/CHALLENGE SCREEN
            human_mouse_move(page)
            bypass_challenge(page)
            
            # Check for Block (Final Verification)
            title = page.title()
            print(f">> Page Title: {title}")
            if "blocked" in title.lower() or "prove" in title.lower():
                print(">> BLOCKED. Saving screenshot...")
                page.screenshot(path="debug_block_proxy.png", animations="disabled")
                raise Exception("Cloudflare blocked access (Challenge not solved).")

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

            # 4. APPLY FILTERS
            print(">> Applying filters...")
            page.wait_for_selector("button[data-id='extension']", state="attached", timeout=60000)
            
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
