import os
import csv
import time
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
    """Creates a temporary Chrome extension to handle Proxy Authentication."""
    try:
        parsed = urlparse(proxy_string)
        username = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port
        scheme = parsed.scheme or "http"

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
        print(f"   [Snapshot] Saved to {name}")
    except:
        pass

def bypass_turnstile(page):
    print(">> Checking for Cloudflare Turnstile...")
    time.sleep(3)
    
    # Quick check for Hard Block
    if "blocked" in page.title.lower() or "security service" in page.html.lower():
        print(">> CRITICAL: Detected Hard Block (Firewall Ban).")
        safe_screenshot(page, "debug_hard_block.png")
        return False

    if "Just a moment" not in page.title and "robot" not in page.title.lower():
        print(">> No challenge detected.")
        return True

    print(">> Challenge Detected! Scanning...")
    
    # Try for 25 seconds
    for i in range(25):
        try:
            if "Just a moment" not in page.title and "robot" not in page.title.lower():
                print(">> SUCCESS! Challenge passed.")
                return True

            iframe = page.ele('xpath://iframe[starts-with(@src, "https://challenges.cloudflare.com")]', timeout=2)
            if iframe:
                body = iframe.ele('tag:body', timeout=2)
                if body:
                    print(f">> Clicking Turnstile... ({i}s)")
                    body.click(by_js=False) 
                    time.sleep(2)
            time.sleep(1)
        except:
            pass
            
    return False

def apply_filters(page):
    print(">> Applying Search Filters...")
    try:
        # 1. Extension -> .com
        ext_btn = page.ele('css:button[data-id="extension"]', timeout=5)
        if not ext_btn:
             # Check if we were redirected to Dashboard
             if "account" in page.url or "dashboard" in page.url:
                 print(">> Filters not found (We are on Dashboard).")
                 return False
             
             safe_screenshot(page, "debug_no_filters.png")
             raise Exception("Filters did not load.")
        
        ext_btn.click()
        time.sleep(0.5)
        page.ele('xpath://div[contains(@class, "open")]//li//span[text()=".com"]').click()
        time.sleep(1)
        print("   -> Extension: .com")

        # 2. Venue -> GoDaddy
        page.ele('css:button[data-id="venue"]').click()
        time.sleep(0.5)
        page.ele('xpath://div[contains(@class, "open")]//li//span[text()="GoDaddy"]').click()
        time.sleep(1)
        print("   -> Venue: GoDaddy")

        # 3. Date -> Today
        page.ele('css:button[data-id="date-range"]').click()
        time.sleep(0.5)
        date_options = page.eles('xpath://div[contains(@class, "open")]//ul/li')
        if len(date_options) > 1:
            date_options[1].click()
            print("   -> Date: Today")
        time.sleep(1)

        # 4. Rows -> 25
        page.ele('css:select[name="search-results_length"]').select('25')
        print("   -> Rows: 25")
        time.sleep(2)
        
        return True

    except Exception as e:
        print(f">> Error applying filters: {e}")
        safe_screenshot(page, "debug_filter_error.png")
        return False

def main():
    print(">> Starting DropDax Scraper (Professional Diagnostic Mode)...")
    
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
    
    # 2. PROFESSIONAL STEALTH ARGUMENTS
    # We remove the specific user-agent to let Chrome match the binary version naturally
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--lang=en-US')
    co.set_argument('--disable-blink-features=AutomationControlled') 
    
    # Explicitly set browser path
    co.set_paths(browser_path='/usr/bin/google-chrome')

    page = ChromiumPage(addr_or_opts=co)
    
    try:
        # --- PRE-FLIGHT CHECK (CRITICAL) ---
        print(">> Running Pre-Flight IP Diagnostic...")
        # We visit a neutral site to verify the proxy is working
        page.get("https://api.ipify.org")
        print(f">> Current Public IP: {page.ele('tag:body').text}")
        
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
        page.set.window.max() # Maximize window to look "Human"
        page.get("https://namebio.com/")
        
        # --- CHECK BLOCKS ---
        if not bypass_turnstile(page):
            raise Exception("Cloudflare blocked access.")

        # --- DASHBOARD REDIRECT ---
        if "/account" in page.url or "dashboard" in page.url:
            print(">> Landed on Dashboard. Redirecting to Home...")
            page.get("https://namebio.com/")
            time.sleep(5)
            if not bypass_turnstile(page):
                 raise Exception("Blocked on Redirect.")

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
             print(">> Retry: Reloading Page...")
             page.refresh()
             time.sleep(5)
             bypass_turnstile(page)
             if not apply_filters(page):
                 raise Exception("Filters failed to load after retry.")

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
