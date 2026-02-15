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

# --- STEALTH FUNCTIONS ---
def add_stealth_js(context):
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    """)

# --- ADVANCED NATIVE STEALTH ---
def apply_advanced_stealth(page):
    """
    Injects specific JavaScript overrides to mask the bot.
    Includes WebGL spoofing which is crucial for Cloudflare.
    """
    
    # 1. Mask the WebDriver flag (The #1 detection method)
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    # 2. Mock the Chrome Object (So it looks like Google Chrome, not a script)
    page.add_init_script("""
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
    """)

    # 3. Spoof WebGL Vendor (CRITICAL FOR CLOUDFLARE)
    page.add_init_script("""
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            // 37445 = UNMASKED_VENDOR_WEBGL
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            // 37446 = UNMASKED_RENDERER_WEBGL
            if (parameter === 37446) {
                return 'Intel(R) Iris(TM) Plus Graphics 640';
            }
            return getParameter(parameter);
        };
    """)

    # 4. Mock Plugins (Bots have 0 plugins, Humans have PDF viewers etc)
    page.add_init_script("""
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
    """)

    # 5. Fix Window Dimensions (Headless windows sometimes report 0)
    page.add_init_script("""
        Object.defineProperty(window, 'outerWidth', { value: window.innerWidth });
        Object.defineProperty(window, 'outerHeight', { value: window.innerHeight });
    """)

    # 6. Mask Permissions
    page.add_init_script("""
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
        );
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

# --- ENHANCED CLOUDFLARE BYPASS (RADAR MODE) ---
def bypass_challenge(page, is_round_2=False):
    print(f">> CHECKING FOR CLOUDFLARE CHALLENGE (Round 2: {is_round_2})...")
    
    # 0. WAIT FOR LOAD (Crucial for Round 2)
    # If we just redirected, the widget might not be ready yet.
    time.sleep(5)
    
    # 1. RADAR SCAN: Look for the frame for up to 15 seconds
    turnstile_frame = None
    print(">> Scanning for Turnstile Widget...")
    
    for i in range(15): # Loop 15 times (15 seconds)
        for frame in page.frames:
            if "cloudflare" in frame.url or "turnstile" in frame.url:
                turnstile_frame = frame
                break
        
        if turnstile_frame:
            print(f">> Turnstile Widget FOUND on attempt {i+1}!")
            break
            
        time.sleep(1) # Wait 1 second before looking again

    # 2. CLICK LOGIC
    if turnstile_frame:
        print(">> Clicking Turnstile Widget...")
        try:
            time.sleep(1) # Settle
            box = turnstile_frame.frame_element().bounding_box()
            if box:
                # Geometry Click (Most Reliable)
                click_x = box['x'] + (box['width'] / 2)
                click_y = box['y'] + (box['height'] / 2)
                
                # Move mouse there slowly
                page.mouse.move(click_x, click_y, steps=20)
                time.sleep(0.5)
                page.mouse.click(click_x, click_y)
            else:
                # Fallback
                turnstile_frame.click("body", force=True)
        except Exception as e:
            print(f">> Click error: {e}")
    else:
        print(">> Turnstile Widget NOT found after scan.")

    # 3. WAIT AND MONITOR (Active Waiting)
    print(">> Waiting for reaction (30s)...")
    for i in range(30):
        if "robot" not in page.title().lower():
            print(">> SUCCESS! Challenge passed.")
            return True
        
        # Wiggle mouse AND scroll to simulate reading (New)
        if i % 3 == 0: 
            human_mouse_move(page)
            page.mouse.wheel(0, random.randint(100, 500)) # Scroll down
            time.sleep(0.5)
            page.mouse.wheel(0, random.randint(-500, -100)) # Scroll up
            
        time.sleep(1)

    # 4. EMERGENCY EXIT LOGIC
    if not is_round_2:
        # ROUND 1: Try Member Login
        print(">> STUCK! Attempting 'Member Login' bypass...")
        try:
            login_link = page.get_by_text("Member Login")
            if login_link.count() > 0:
                login_link.click()
                print(">> Clicked 'Member Login'. Waiting for redirect...")
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                time.sleep(5)
                if "login" not in page.url and "robot" not in page.title().lower():
                     print(">> SUCCESS! Login link bypassed the block.")
                     return True
        except:
            pass
    else:
        # ROUND 2: Do NOT click Member Login (Avoids Loop).
        # We try to access the Search Param directly as a last resort.
        print(">> Round 2 Stuck. Trying direct Search param injection...")
        try:
            page.goto("https://namebio.com/?s=rescue", timeout=30000, wait_until="domcontentloaded")
            time.sleep(5)
        except:
            pass

    # Final check
    if "robot" in page.title().lower():
        print(">> FAILED: Still blocked.")
        return False
        
    return True

def connect_with_retries(page, url, retries=3):
    """Tries to load the page with extended timeouts."""
    for attempt in range(1, retries + 1):
        try:
            print(f">> Connection Attempt {attempt}/{retries}...")
            # Use 'domcontentloaded' to return faster
            page.goto(url, timeout=90000, wait_until="domcontentloaded") 
            
            # Check for immediate chrome error (proxy failure)
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
    print(">> Starting DropDax Proxy Scraper (Stepping Stone Fix)...")
    
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
            
            # APPLY THE ADVANCED STEALTH
            apply_advanced_stealth(page)

            # 1. LOGIN & CONNECT
            load_cookies(context)
            
            if not connect_with_retries(page, "https://namebio.com/"):
                raise Exception("Failed to connect to NameBio.")
            
            # 2. HANDLE CLOUDFLARE (ROUND 1)
            bypass_success = bypass_challenge(page, is_round_2=False)
            if not bypass_success:
                page.screenshot(path="debug_block_round1.png", animations="disabled")
                raise Exception("Cloudflare blocked access (Round 1).")

            # 3. DASHBOARD REDIRECT LOGIC (STEPPING STONE)
            # If we bypassed by clicking "Member Login", we end up on /account
            print(f">> Current URL: {page.url}")
            
            bad_paths = ["/account", "dashboard", "memberships", "login"]
            if any(path in page.url for path in bad_paths):
                print(">> Landed on Dashboard. Using Stepping Stone Navigation...")
                
                # STEP 1: Go to "Trends" first (Neutral Page)
                try:
                    print(">> Step 1: Visiting Trends...")
                    page.get_by_text("Trends").first.click()
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(3)
                except:
                    print(">> Trends link failed. Trying direct navigation...")
                
                # STEP 2: Now go to Home via Logo (Looks natural from Trends)
                print(">> Step 2: Clicking Logo to return Home...")
                try:
                    logo = page.locator(".navbar-brand")
                    if logo.count() > 0:
                        logo.click()
                    else:
                        # Fallback: Use Search Param to trick Cloudflare
                        page.goto("https://namebio.com/?s=", timeout=60000, wait_until="domcontentloaded")
                except:
                     page.goto("https://namebio.com/?s=", timeout=60000, wait_until="domcontentloaded")

                time.sleep(5)
                print(f">> New URL after redirect: {page.url}")
                
                # 4. HANDLE CLOUDFLARE (ROUND 2)
                if "captcha" in page.url or "robot" in page.title().lower():
                    print(">> Redirect triggered Cloudflare. Running Round 2 Bypass...")
                    bypass_success_2 = bypass_challenge(page, is_round_2=True)
                    if not bypass_success_2:
                         if page.locator("button[data-id='extension']").count() > 0:
                            print(">> Filters detected despite spinner. Proceeding...")
                         else:
                            page.screenshot(path="debug_block_round2.png", animations="disabled")
                            raise Exception("Cloudflare blocked access (Round 2).")

            # 5. HANDLE BANNER
            try:
                if page.locator("#nudge-countdown-container").is_visible(timeout=10000):
                    print(">> Banner detected. Waiting...")
                    page.locator("#nudge-countdown-container a[data-dismiss='modal']").click(timeout=45000)
                    print(">> Banner closed.")
            except:
                pass

            # 6. APPLY FILTERS
            print(">> Applying filters...")
            try:
                # Wait longer for filters to appear after potential redirect
                page.wait_for_selector("button[data-id='extension']", state="attached", timeout=60000)
            except:
                print(">> ERROR: Filters not found. Taking screenshot...")
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
            
            # 7. SCRAPE
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
