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
    try:
        parsed = urlparse(proxy_string)
        username = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port
        scheme = parsed.scheme

        if not username or not password:
            return None

        if os.path.exists(plugin_dir):
            shutil.rmtree(plugin_dir)
        os.makedirs(plugin_dir)

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

        return os.path.abspath(plugin_dir)

    except Exception as e:
        print(f">> Failed to create proxy plugin: {e}")
        return None

# --- HELPER FUNCTIONS ---

def get_price_via_ocr(ele):
    try:
        png_bytes = ele.get_screenshot(as_bytes=True)
        image = Image.open(BytesIO(png_bytes))
        text = pytesseract.image_to_string(image, config='--psm 7').strip()
        return text
    except Exception as e:
        return "OCR_ERROR"

def safe_screenshot(page, name):
    try:
        page.get_screenshot(path=name)
    except:
        pass

def check_for_hard_block(page):
    """Checks if we are on the 'Sorry, you have been blocked' page."""
    # Check title and content for block messages
    if "blocked" in page.title.lower() or "security service" in page.html.lower():
        print(">> CRITICAL: Detected Hard Block (Firewall Ban).")
        safe_screenshot(page, "debug_hard_block.png")
        return True
    return False

def bypass_turnstile(page):
    print(">> Checking for Cloudflare Turnstile...")
    time.sleep(5)
    
    if check_for_hard_block(page):
        return False

    if "Just a moment" not in page.title and "robot" not in page.title.lower():
        print(">> No challenge detected.")
        return True

    print(">> Challenge Detected! Scanning for widget...")
    
    for i in range(30):
        try:
            if "Just a moment" not in page.title and "robot" not in page.title.lower():
                print(">> SUCCESS! Challenge passed.")
                return True

            iframe = page.ele('xpath://iframe[starts-with(@src, "https://challenges.cloudflare.com")]', timeout=2)
            
            if iframe:
                print(f">> Found Turnstile Iframe. Attempting click... ({i}s)")
                body = iframe.ele('tag:body', timeout=2)
                if body:
                    body.click(by_js=False) 
                    time.sleep(2)
            time.sleep(1)
        except:
            pass
            
    if "Just a moment" in page.title:
        print(">> FAILED: Cloudflare stuck.")
        return False
        
    return True

def apply_filters(page):
    print(">> Applying Search Filters...")
    
    try:
        # Check if we are blocked before trying filters
        if check_for_hard_block(page):
             raise Exception("Hard Block detected before filters.")

        # 1. Extension -> .com
        ext_btn = page.ele('css:button[data-id="extension"]', timeout=10)
        if not ext_btn:
             # Double check for block
             if check_for_hard_block(page):
                 raise Exception("Hard Block detected.")
             
             # Check if we are on the wrong page (Dashboard)
             if "account" in page.url or "dashboard" in page.url:
                 print(">> Wrong Page (Dashboard). Redirecting...")
                 return False # Signal to retry navigation
                 
             safe_screenshot(page, "debug_no_filters.png")
             raise Exception("Extension button not found.")
        
        ext_btn.click()
        time.sleep(0.5)
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

        # 3. Date -> Today
        date_btn = page.ele('css:button[data-id="date-range"]')
        date_btn.click()
        time.sleep(0.5)
        date_options = page.eles('xpath://div[contains(@class, "open")]//ul/li')
        if len(date_options) > 1:
            date_options[1].click()
            print("   -> Date set to Today")
        time.sleep(1)

        # 4. Rows -> 25
        sel = page.ele('css:select[name="search-results_length"]')
        sel.select('25')
        print("   -> Rows set to 25")
        time.sleep(2)
        
        return True

    except Exception as e:
        print(f">> Error applying filters: {e}")
        safe_screenshot(page, "debug_filter_error.png")
        raise e

def main():
    print(">> Starting DropDax Scraper (DrissionPage Stealth V2)...")
    
    proxy_url = os.environ.get("PROXY_URL")
    
    co = ChromiumOptions()
    
    # 1. SETUP PROXY
    if proxy_url:
        print(">> PROXY DETECTED. Generating Auth Extension...")
        auth_plugin_path = create_proxy_auth_extension(proxy_url)
        if auth_plugin_path:
            co.add_extension(auth_plugin_path)
        else:
            co.set_proxy(proxy_url)
    
    # 2. STEALTH ARGUMENTS
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--lang=en-US')
    # Removes the "Automated" flag
    co.set_argument('--disable-blink-features=AutomationControlled') 
    # Latest Chrome User Agent (v124)
    co.set_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

    co.set_paths(browser_path='/usr/bin/google-chrome')

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
        
        # --- NAVIGATE ---
        print(">> Navigating to NameBio...")
        page.get("https://namebio.com/")
        
        # --- CHECK BLOCKS ---
        if check_for_hard_block(page):
            # FIXED: Correct way to clear cookies in DrissionPage
            print(">> Cookies caused a ban. Clearing cookies and retrying...")
            try:
                page.run_cdp('Network.clearBrowserCookies')
                page.run_cdp('Network.clearBrowserCache')
            except:
                # Fallback if CDP fails
                page.set.cookies.clear()
            
            # Refresh to try again without cookies
            print(">> Retrying navigation clean...")
            page.get("https://namebio.com/")
            time.sleep(5)
        
        if not bypass_turnstile(page):
            safe_screenshot(page, "debug_cloudflare_fail.png")
            raise Exception("Could not bypass Cloudflare.")

        # --- DASHBOARD REDIRECT ---
        if "/account" in page.url or "dashboard" in page.url:
            print(">> Landed on Dashboard. Redirecting to Home...")
            page.get("https://namebio.com/")
            time.sleep(5)
            bypass_turnstile(page)

        # --- BANNER ---
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
        success = apply_filters(page)
        if not success:
             print(">> Retry: Navigating Home again...")
             page.get("https://namebio.com/")
             time.sleep(5)
             apply_filters(page)

        # --- SEARCH ---
        print(">> Clicking Search...")
        page.ele('#search-submit').click()
        print(">> Waiting for results...")
        page.wait.ele_displayed('#search-results tbody tr', timeout=60)
        time.sleep(3)

        # --- SCRAPE ---
        rows = page.eles('#search-results tbody tr')
        data = []
        
        print(f">> Processing {len(rows)} rows...")
        
        for row in rows:
            if "No matching records" in row.text: continue
            cols = row.eles('tag:td')
            if len(cols) < 4: continue

            domain = cols[0].text.strip()
            date = cols[2].text.strip()
            venue = cols[3].text.strip()
            price_raw = get_price_via_ocr(cols[1])
            price = price_raw.replace("USD", "").replace("$", "").strip()

            print(f"   Found: {domain} | {price}")
            data.append([domain, price, date, venue])

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
        if os.path.exists("proxy_auth_plugin"):
            shutil.rmtree("proxy_auth_plugin", ignore_errors=True)

if __name__ == "__main__":
    main()
