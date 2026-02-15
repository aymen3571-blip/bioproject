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
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel(R) Iris(TM) Plus Graphics 640';
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

# --- ENHANCED CLOUDFLARE BYPASS (THE EMERGENCY EXIT) ---
def bypass_challenge(page, is_round_2=False):
    print(f">> CHECKING FOR CLOUDFLARE CHALLENGE (Round 2: {is_round_2})...")
    time.sleep(5)
    
    # Check if we are even on a challenge page
    title = page.title().lower()
    if "robot" not in title and "moment" not in title and "attention" not in title:
        print(">> No challenge detected (Clean entry).")
        return True

    # 1. TRY TO CLICK THE TURNSTILE WIDGET
    turnstile_frame = None
    for frame in page.frames:
        if "cloudflare" in frame.url or "turnstile" in frame.url:
            turnstile_frame = frame
            break
            
    if turnstile_frame:
        print(">> Turnstile Widget found. Clicking...")
        try:
            # METHOD A: Geometry Click (Most Reliable)
            # We find where the frame is on the screen and click the exact center
            box = turnstile_frame.frame_element().bounding_box()
            if box:
                # Calculate center of the widget
                click_x = box['x'] + (box['width'] / 2)
                click_y = box['y'] + (box['height'] / 2)
                
                # Move mouse there slowly
                page.mouse.move(click_x, click_y, steps=20)
                time.sleep(0.5)
                page.mouse.click(click_x, click_y)
            else:
                # METHOD B: Selector Click (Fallback)
                turnstile_frame.click("body", force=True)
        except:
            pass

    # 2. WAIT AND MONITOR
    print(">> Waiting for reaction (20s)...")
    for i in range(20):
        if "robot" not in page.title().lower():
            print(">> SUCCESS! Challenge passed.")
            return True
        time.sleep(1)

    # 3. EMERGENCY EXIT LOGIC
    if not is_round_2:
        # ROUND 1: We are not logged in (or session is fresh). 
        # Clicking "Member Login" is safe and helps bypass.
        print(">> STUCK! Attempting 'Member Login' bypass...")
        try:
            login_link = page.get_by_text("Member Login")
            if login_link.count() > 0:
                login_link.click()
                print(">> Clicked 'Member Login'. Waiting for redirect...")
                
                # Wait for navigation
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                time.sleep(5)
                
                # If we are redirected to Dashboard or Home, we win.
                if "login" not in page.url and "robot" not in page.title().lower():
                     print(">> SUCCESS! Login link bypassed the block.")
                     return True
        except Exception as e:
            print(f">> Login bypass failed: {e}")
            
    else:
        # ROUND 2: We are ALREADY logged in (Redirected from Dashboard).
        # Clicking "Member Login" causes an infinite loop back to the dashboard.
        # So we DISABLE it here. Instead, we try a reload.
        print(">> Round 2 (Logged In): Skipping 'Member Login' click to avoid loop.")
        if "robot" in page.title().lower():
             print(">> Stalled on Captcha. Attempting Page Reload (Refreshes Cookies)...")
             try:
                 page.reload(timeout=30000)
                 time.sleep(5)
             except:
                 pass

    # Final check
    if "robot" in page.title().lower():
        print(">> FAILED: Still blocked.")
        return False
        
    return True

def connect_with_retries(page, url, retries=3):
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
    print(">> Starting DropDax Proxy Scraper (Final Loop Fix)...")
    
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
            # Pass is_round_2=False because this is our first attempt
            bypass_success = bypass_challenge(page, is_round_2=False)
            if not bypass_success:
                page.screenshot(path="debug_block_round1.png", animations="disabled")
                raise Exception("Cloudflare blocked access (Round 1).")

            # 3. DASHBOARD REDIRECT LOGIC
            # If we bypassed by clicking "Member Login", we end up on /account
            # We must go back to the home page to search.
            print(f">> Current URL: {page.url}")
            
            # Catch ANY sub-page that isn't the home search
            bad_paths = ["/account", "dashboard", "memberships", "login"]
            if any(path in page.url for path in bad_paths):
                print(">> Landed on Account/Sub-Page. Redirecting to Home for search...")
                
                try:
                    # UPDATED: Use 'referer' to make it look like a natural click back to home
                    # This reduces the chance of Cloudflare flagging the navigation
                    current_url = page.url
                    page.goto("https://namebio.com/", referer=current_url, timeout=60000, wait_until="domcontentloaded")
                except:
                     pass

                time.sleep(5)
                print(f">> New URL after redirect: {page.url}")
                
                # 4. HANDLE CLOUDFLARE (ROUND 2 - CRITICAL)
                # We pass is_round_2=True to DISABLE the "Member Login" loop
                print(">> Running Round 2 Bypass Check...")
                bypass_success_2 = bypass_challenge(page, is_round_2=True)
                
                if not bypass_success_2:
                    # One last chance: Check if we are actually ON the home page despite the spinner?
                    if page.locator("button[data-id='extension']").count() > 0:
                        print(">> Filters detected despite spinner. Proceeding...")
                    else:
                        page.screenshot(path="debug_block_round2.png", animations="disabled")
                        raise Exception("Cloudflare blocked access (Round 2).")

            
            # 5. HANDLE BANNER
            try:
                # Look for the banner more aggressively
                if page.locator("#nudge-countdown-container").is_visible(timeout=10000):
                    print(">> Banner detected. Waiting...")
                    # Wait for close button
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
