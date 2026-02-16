import os
import csv
import time
import json
import shutil
import sys
import random
import pytesseract
from PIL import Image
from io import BytesIO
from urllib.parse import urlparse
from DrissionPage import ChromiumPage, ChromiumOptions

# --- CONFIGURATION ---
COOKIES_FILE = "namebio_session.json"
OUTPUT_FILE = "namebio_data.csv"
# We switch to standard Windows 10 for "Corporate User" trust score
WINDOWS_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# --- PROXY AUTH EXTENSION (MANIFEST V3) ---
def create_proxy_auth_extension(proxy_string, plugin_dir="proxy_auth_plugin"):
    try:
        parsed = urlparse(proxy_string)
        username = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port
        scheme = parsed.scheme or "http"

        if not username or not password: return None
        if os.path.exists(plugin_dir): shutil.rmtree(plugin_dir)
        os.makedirs(plugin_dir)

        manifest_json = """
        {
            "name": "Proxy Auth V3",
            "version": "1.0.0",
            "manifest_version": 3,
            "permissions": ["proxy", "webRequest", "webRequestAuthProvider"],
            "host_permissions": ["<all_urls>"],
            "background": {"service_worker": "background.js"}
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
        chrome.webRequest.onAuthRequired.addListener(
            function(details) {{
                return {{authCredentials: {{username: "{username}", password: "{password}"}}}};
            }},
            {{urls: ["<all_urls>"]}},
            ['blocking']
        );
        """
        with open(os.path.join(plugin_dir, "manifest.json"), "w") as f: f.write(manifest_json)
        with open(os.path.join(plugin_dir, "background.js"), "w") as f: f.write(background_js)
        return os.path.abspath(plugin_dir)
    except: return None

# --- HELPER FUNCTIONS ---
def get_price_via_ocr(ele):
    try:
        png_bytes = ele.get_screenshot(as_bytes=True)
        image = Image.open(BytesIO(png_bytes))
        text = pytesseract.image_to_string(image, config='--psm 7').strip()
        return text
    except: return "OCR_ERROR"

def safe_screenshot(page, name):
    try: page.get_screenshot(path=name)
    except: pass

def get_ip_info(page):
    """
    Robust IP checker using multiple sources.
    Returns (ip, isp, success_bool)
    """
    # 1. Try IP-API
    try:
        page.get("http://ip-api.com/json", timeout=10)
        if "json" in page.url: # Verify we loaded the JSON
            data = json.loads(page.ele('tag:pre').text)
            return data.get('query', 'Unknown'), data.get('isp', 'Unknown'), True
    except: pass

    # 2. Try IPIFY (Backup)
    try:
        page.get("https://api.ipify.org?format=json", timeout=10)
        if "json" in page.url:
            data = json.loads(page.ele('tag:pre').text)
            return data.get('ip', 'Unknown'), "Unknown (Backup)", True
    except: pass

    return "Unknown", "Unknown", False

def check_connection_safety(page):
    """
    STRICT GATEKEEPER: Returns True only if IP is verified residential.
    """
    ip, isp, success = get_ip_info(page)
    
    print(f">> CONNECTION TEST: IP={ip} | ISP={isp}")
    
    if not success or ip == "Unknown":
        print(">> ERROR: Could not verify IP. Connection unstable.")
        return False
        
    # BAD ISP LIST (Datacenters)
    bad_keywords = ["Microsoft", "Azure", "Google", "Amazon", "Datacenter", "DigitalOcean", "Hetzner", "Unknown"]
    
    for kw in bad_keywords:
        if kw.lower() in isp.lower():
            print(f">> BLOCKING: Detected Datacenter ISP ({kw}). Unsafe.")
            return False
            
    print(">> SUCCESS: Residential connection verified.")
    return True

def is_blocked(page):
    if "blocked" in page.title.lower() or "security service" in page.html.lower():
        print(">> CRITICAL: Firewall Ban Detected.")
        safe_screenshot(page, "debug_ban.png")
        return True
    return False

def bypass_turnstile(page):
    print(">> Checking Security...")
    time.sleep(3)
    if is_blocked(page): return False
    
    if "Just a moment" in page.title or "robot" in page.title.lower():
        print(">> Turnstile Challenge Detected. Engaging...")
        for i in range(25):
            if "Just a moment" not in page.title and "robot" not in page.title.lower():
                print(">> SUCCESS! Security Cleared.")
                return True
            
            iframe = page.ele('xpath://iframe[starts-with(@src, "https://challenges.cloudflare.com")]', timeout=2)
            if iframe:
                try:
                    iframe.ele('tag:body').click() 
                    time.sleep(2)
                except: pass
            time.sleep(1)
        return False
    print(">> No Challenge Detected.")
    return True

def apply_filters(page):
    print(">> Applying Filters...")
    try:
        if is_blocked(page): return False

        ext_btn = page.wait.ele_displayed('css:button[data-id="extension"]', timeout=10)
        if not ext_btn:
            if "/account" in page.url:
                print(">> Stuck on Dashboard. Redirecting...")
                page.get("https://namebio.com/")
                return False
            raise Exception("Filter UI missing.")

        ext_btn.click()
        time.sleep(0.5)
        page.ele('xpath://div[contains(@class, "open")]//li//span[text()=".com"]').click()
        print("   -> Extension: .com")
        time.sleep(1)

        page.ele('css:button[data-id="venue"]').click()
        time.sleep(0.5)
        page.ele('xpath://div[contains(@class, "open")]//li//span[text()="GoDaddy"]').click()
        print("   -> Venue: GoDaddy")
        time.sleep(1)

        page.ele('css:button[data-id="date-range"]').click()
        time.sleep(0.5)
        dates = page.eles('xpath://div[contains(@class, "open")]//ul/li')
        if len(dates) > 1:
            dates[1].click()
            print("   -> Date: Today")
        time.sleep(1)

        try:
            page.ele('css:select[name="search-results_length"]').select('25')
            print("   -> Rows: 25")
        except:
            print("   -> Rows: Default")
        
        return True
    except Exception as e:
        print(f">> Filter Error: {e}")
        safe_screenshot(page, "debug_filter_fail.png")
        return False

def main():
    print(">> Starting DropDax Scraper (Strict Gatekeeper V2)...")
    
    proxy_url = os.environ.get("PROXY_URL")
    plugin_path = None
    
    if proxy_url:
        print(">> Generating Auth Plugin...")
        plugin_path = create_proxy_auth_extension(proxy_url)

    # --- THE GATEKEEPER LOOP ---
    page = None
    clean_connection = False
    
    # Try up to 5 times to get a clean proxy
    for attempt in range(1, 6): 
        print(f"\n>> Connection Check (Attempt {attempt}/5)...")
        
        co = ChromiumOptions()
        if plugin_path: 
            co.add_extension(plugin_path)
            co.set_argument(f'--load-extension={plugin_path}')
        
        co.set_argument(f'--user-agent={WINDOWS_UA}')
        co.set_argument('--window-size=1920,1080')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-gpu')
        co.set_argument('--lang=en-US')
        # This argument is critical for stealth
        co.set_argument('--disable-blink-features=AutomationControlled') 
        co.set_paths(browser_path='/usr/bin/google-chrome')
        
        try:
            if page: page.quit()
            page = ChromiumPage(addr_or_opts=co)
            
            # CHECK IP STRICTLY
            if check_connection_safety(page):
                clean_connection = True
                break
            else:
                print(">> Retrying for better IP...")
                
        except Exception as e:
            print(f">> Init Failed: {e}")
            time.sleep(2)

    if not clean_connection:
        print(">> FATAL: No clean IP found. Aborting to protect account.")
        if page: page.quit()
        sys.exit(1)

    try:
        # --- EXECUTION PHASE ---
        print(">> Connection Secure. Warming up...")
        page.get("https://www.google.com")
        time.sleep(2)
        
        print(">> Entering NameBio...")
        page.get("https://namebio.com/")
        
        if not bypass_turnstile(page):
            raise Exception("Banned.")

        try:
            banner = page.ele('#nudge-countdown-container', timeout=2)
            if banner: 
                banner.ele('css:a[data-dismiss="modal"]').click()
                print(">> Banner Cleared.")
        except: pass

        if not apply_filters(page):
            print(">> Retrying Filters...")
            page.refresh()
            time.sleep(3)
            if not apply_filters(page):
                raise Exception("Filters Failed.")

        print(">> Executing Search...")
        page.ele('#search-submit').click()
        
        print(">> Waiting for Data...")
        page.wait.ele_displayed('#search-results tbody tr', timeout=30)
        
        rows = page.eles('#search-results tbody tr')
        data = []
        print(f">> Found {len(rows)} potential rows.")

        for row in rows:
            if "No matching" in row.text: continue
            cols = row.eles('tag:td')
            if len(cols) < 4: continue

            domain = cols[0].text.strip()
            date = cols[2].text.strip()
            venue = cols[3].text.strip()
            price = get_price_via_ocr(cols[1]).replace("USD","").replace("$","").strip()

            print(f"   + {domain} | {price}")
            data.append([domain, price, date, venue])

        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Domain", "Price", "Date", "Venue"])
            writer.writerows(data)
            
        print(f">> DONE. {len(data)} rows saved.")

    except Exception as e:
        print(f">> FATAL ERROR: {e}")
        safe_screenshot(page, "debug_fatal.png")
        sys.exit(1)
    
    finally:
        if page: page.quit()
        if os.path.exists("proxy_auth_plugin"): shutil.rmtree("proxy_auth_plugin", ignore_errors=True)

if __name__ == "__main__":
    main()
