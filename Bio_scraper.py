import os
import csv
import time
import random
import json
import shutil
import pytesseract
from PIL import Image
from io import BytesIO
from urllib.parse import urlparse
from DrissionPage import ChromiumPage, ChromiumOptions

# --- CONFIGURATION ---
COOKIES_FILE = "namebio_session.json"
OUTPUT_FILE = "namebio_data.csv"

# --- PROXY AUTH EXTENSION GENERATOR ---
def create_proxy_auth_extension(proxy_string, plugin_dir="proxy_auth_plugin"):
    """
    Creates a temporary Chrome extension to handle Proxy Authentication.
    DrissionPage/Chrome cannot handle user:pass@host directly.
    """
    try:
        # Parse the proxy URL
        parsed = urlparse(proxy_string)
        username = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port
        scheme = parsed.scheme

        if not username or not password:
            print(">> Proxy does not have authentication. Using standard method.")
            return None

        # Clean up old plugin if exists
        if os.path.exists(plugin_dir):
            shutil.rmtree(plugin_dir)
        os.makedirs(plugin_dir)

        # 1. Create manifest.json
        manifest_json = """
        {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Chrome Proxy Auth",
            "permissions": [
                "proxy",
                "tabs",
                "unlimitedStorage",
                "storage",
                "<all_urls>",
                "webRequest",
                "webRequestBlocking"
            ],
            "background": {
                "scripts": ["background.js"]
            },
            "minimum_chrome_version": "22.0.0"
        }
        """

        # 2. Create background.js
        background_js = f"""
        var config = {{
            mode: "fixed_servers",
            rules: {{
                singleProxy: {{
                    scheme: "{scheme}",
                    host: "{host}",
                    port: parseInt({port})
                }},
                bypassList: ["localhost"]
            }}
        }};

        chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

        function callbackFn(details) {{
            return {{
                authCredentials: {{
                    username: "{username}",
                    password: "{password}"
                }}
            }};
        }}

        chrome.webRequest.onAuthRequired.addListener(
            callbackFn,
            {{urls: ["<all_urls>"]}},
            ['blocking']
        );
        """

        with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
            f.write(manifest_json)
        
        with open(os.path.join(plugin_dir, "background.js"), "w") as f:
            f.write(background_js)

        print(f">> Created Proxy Auth Plugin for {host}:{port}")
        return os.path.abspath(plugin_dir)

    except Exception as e:
        print(f">> Failed to create proxy plugin: {e}")
        return None

# --- HELPER FUNCTIONS ---

def get_price_via_ocr(ele):
    """Takes a screenshot of the price element and OCRs it."""
    try:
        # DrissionPage can get bytes directly
        png_bytes = ele.get_screenshot(as_bytes=True)
        image = Image.open(BytesIO(png_bytes))
        # --psm 7 treats the image as a single text line
        text = pytesseract.image_to_string(image, config='--psm 7').strip()
        return text
    except Exception as e:
        print(f"   [OCR Error] {e}")
        return "OCR_ERROR"

def safe_screenshot(page, name):
    """Safely takes a screenshot without crashing on timeout."""
    try:
        page.get_screenshot(path=name)
    except Exception as e:
        print(f">> Could not take screenshot {name}: {e}")

def bypass_turnstile(page):
    """
    Scans for Cloudflare Turnstile widget and clicks it.
    DrissionPage handles iframes much better than Playwright.
    """
    print(">> Checking for Cloudflare Turnstile...")
    
    # Give it a moment to render
    time.sleep(3)
    
    # Check if we are blocked
    if "Just a moment" not in page.title and "robot" not in page.title.lower():
        print(">> No challenge detected.")
        return True

    print(">> Challenge Detected! Scanning for widget...")
    
    # Try for 30 seconds
    for i in range(30):
        try:
            # 1. Check success
            if "Just a moment" not in page.title and "robot" not in page.title.lower():
                print(">> SUCCESS! Challenge passed.")
                return True

            # 2. Find the iframe
            # DrissionPage can search for elements inside specific iframes easily
            iframe = page.ele('xpath://iframe[starts-with(@src, "https://challenges.cloudflare.com")]', timeout=2)
            
            if iframe:
                print(f">> Found Turnstile Iframe. Attempting click... ({i}s)")
                
                # 3. Click the checkbox inside the iframe
                # We target the body or the specific checkbox wrapper
                body = iframe.ele('tag:body', timeout=2)
                if body:
                    # Click slightly offset from center to look human
                    body.click(by_js=False) 
                    time.sleep(2)
            
            time.sleep(1)
            
        except Exception as e:
            pass
            
    # Final Check
    if "Just a moment" in page.title:
        print(">> FAILED: Cloudflare stuck.")
        return False
        
    return True

def apply_filters(page):
    """
    Interacts with the NameBio UI to set filters manually.
    """
    print(">> Applying Search Filters...")
    
    try:
        # 1. Extension -> .com
        # Find the button by its data-id
        ext_btn = page.ele('css:button[data-id="extension"]', timeout=5)
        if not ext_btn:
            raise Exception("Extension button not found (Page load error?)")
        
        ext_btn.click()
        time.sleep(0.5)
        
        # Click the .com option in the dropdown list
        # We look for the open dropdown
        page.ele('xpath://div[contains(@class, "open")]//li//span[text()=".com"]').click()
        time.sleep(1)
        print("   -> Extension set to .com")

        # 2. Venue -> GoDaddy
        venue_btn = page.ele('css:button[data-id="venue"]')
        venue_btn.click()
        time.sleep(0.5)
        
        page.ele('xpath://div[contains(@class, "open")]//li//span[text()="GoDaddy"]').click()
        time.sleep(1)
        print("   -> Venue set to GoDaddy")

        # 3. Date -> Today (First Option)
        # The user requested the first option in the list.
        date_btn = page.ele('css:button[data-id="date-range"]')
        date_btn.click()
        time.sleep(0.5)
        
        # Select the 2nd LI (Index 1) because Index 0 is usually 'Any' or a header
        # DrissionPage element search finds the list in the open container
        date_options = page.eles('xpath://div[contains(@class, "open")]//ul/li')
        if len(date_options) > 1:
            # Click the second item (the first real date)
            date_options[1].click()
            print("   -> Date set to Today (First Option)")
        else:
            print("   [!] Could not find date options.")
        time.sleep(1)

        # 4. Rows -> 25
        # This is a <select> element
        sel = page.ele('css:select[name="search-results_length"]')
        sel.select('25')
        print("   -> Rows set to 25")
        time.sleep(2)

    except Exception as e:
        print(f">> Error applying filters: {e}")
        safe_screenshot(page, "debug_filter_error.png")
        raise e

def main():
    print(">> Starting DropDax Scraper (DrissionPage Engine)...")
    
    proxy_url = os.environ.get("PROXY_URL")
    
    # --- SETUP CHROMIUM OPTIONS ---
    co = ChromiumOptions()
    
    # 1. SETUP PROXY (Using Extension Method)
    if proxy_url:
        print(">> PROXY DETECTED. Generating Auth Extension...")
        auth_plugin_path = create_proxy_auth_extension(proxy_url)
        
        if auth_plugin_path:
            # Add the extension that handles User/Pass
            co.add_extension(auth_plugin_path)
        else:
            # Fallback for simple IPs (no password)
            co.set_proxy(proxy_url)
    
    # 2. Set Arguments for GitHub Actions
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage') # Prevents crashes in docker
    co.set_argument('--lang=en-US')
    
    # 3. Explicitly set browser path for GHA
    co.set_paths(browser_path='/usr/bin/google-chrome')

    # Initialize Page
    page = ChromiumPage(addr_or_opts=co)
    
    try:
        # --- LOGIN VIA COOKIES ---
        print(">> Injecting Cookies...")
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                cookies = json.load(f)
                if isinstance(cookies, dict) and 'cookies' in cookies:
                    cookies = cookies['cookies']
                
                for cookie in cookies:
                    page.set.cookies(cookie)
        else:
            print(">> WARNING: No cookie file found.")

        # --- NAVIGATE ---
        print(">> Navigating to NameBio...")
        page.get("https://namebio.com/")
        
        # --- CLOUDFLARE CHECK ---
        if not bypass_turnstile(page):
            safe_screenshot(page, "debug_cloudflare_fail.png")
            raise Exception("Could not bypass Cloudflare.")

        # --- DASHBOARD CHECK ---
        # If we logged in, we might be on /account
        if "/account" in page.url or "dashboard" in page.url:
            print(">> Landed on Dashboard. Redirecting to Home...")
            page.get("https://namebio.com/")
            time.sleep(5)
            # Check Cloudflare again after redirect
            bypass_turnstile(page)

        # --- BANNER HANDLING ---
        # <div id="nudge-countdown-container"><a data-dismiss="modal">Close</a>
        try:
            banner = page.ele('#nudge-countdown-container', timeout=2)
            if banner:
                close_btn = banner.ele('css:a[data-dismiss="modal"]')
                if close_btn:
                    close_btn.click()
                    print(">> Banner Closed.")
        except:
            pass

        # --- APPLY FILTERS ---
        apply_filters(page)

        # --- SEARCH ---
        print(">> Clicking Search...")
        page.ele('#search-submit').click()
        
        # Wait for table
        print(">> Waiting for results...")
        # Wait until the table has rows. Timeout 60s
        page.wait.ele_displayed('#search-results tbody tr', timeout=60)
        time.sleep(3)

        # --- SCRAPE ---
        rows = page.eles('#search-results tbody tr')
        data = []
        
        print(f">> Processing {len(rows)} rows...")
        
        for row in rows:
            if "No matching records" in row.text:
                continue
                
            cols = row.eles('tag:td')
            if len(cols) < 4: continue

            # Text Extraction
            domain = cols[0].text.strip()
            date = cols[2].text.strip()
            venue = cols[3].text.strip()
            
            # OCR for Price
            # cols[1] contains the image
            price_raw = get_price_via_ocr(cols[1])
            price = price_raw.replace("USD", "").replace("$", "").strip()

            print(f"   Found: {domain} | {price}")
            data.append([domain, price, date, venue])

        # --- SAVE ---
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Domain", "Price", "Date", "Venue"])
            writer.writerows(data)
            
        print(f">> Success! {len(data)} rows saved.")

    except Exception as e:
        print(f">> ERROR: {e}")
        safe_screenshot(page, "debug_crash.png")
        raise e
    
    finally:
        page.quit()
        # Clean up the temp plugin
        if os.path.exists("proxy_auth_plugin"):
            shutil.rmtree("proxy_auth_plugin", ignore_errors=True)

if __name__ == "__main__":
    main()
