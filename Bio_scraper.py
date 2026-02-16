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
WINDOWS_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# --- PROXY AUTH EXTENSION (MANIFEST V2 - STABLE) ---
def create_proxy_auth_extension(proxy_string, plugin_dir="proxy_auth_plugin"):
    """
    Creates a Manifest V2 extension. More reliable for initial connection interception.
    """
    try:
        parsed = urlparse(proxy_string)
        username = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port
        scheme = parsed.scheme or "http"
        
        if not username or not password: 
            print(">> ERROR: Proxy missing username/password")
            return None
            
        print(f">> Configuring Proxy: {host}:{port}")
        
        abs_plugin_dir = os.path.abspath(plugin_dir)
        if os.path.exists(abs_plugin_dir): shutil.rmtree(abs_plugin_dir)
        os.makedirs(abs_plugin_dir)

        # Manifest V2
        manifest_json = """
        {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Proxy Auth V2",
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
        
        with open(os.path.join(abs_plugin_dir, "manifest.json"), "w") as f: f.write(manifest_json)
        with open(os.path.join(abs_plugin_dir, "background.js"), "w") as f: f.write(background_js)
        
        return abs_plugin_dir
    except Exception as e:
        print(f">> Proxy Plugin Creation Failed: {e}")
        return None

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
    # Try multiple sources
    for url in ["https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"]:
        try:
            page.get(url, timeout=20)
            ip = page.ele('tag:body').text.strip()
            if len(ip) > 6 and "." in ip:
                return ip, True
        except: continue
    return "Unknown", False

def is_blocked(page):
    if "blocked" in page.title.lower() or "security service" in page.html.lower():
        print("   >> DETECTED: Firewall Ban.")
        return True
    return False

def bypass_turnstile(page):
    print(">> Checking Security...")
    time.sleep(3)
    if is_blocked(page): return False
    
    if "Just a moment" in page.title or "robot" in page.title.lower():
        print(">> Turnstile Challenge Detected...")
        for i in range(25):
            if "Just a moment" not in page.title and "robot" not in page.title.lower():
                print(">> SUCCESS! Security Cleared.")
                return True
            iframe = page.ele('xpath://iframe[starts-with(@src, "https://challenges.cloudflare.com")]', timeout=2)
            if iframe:
                try: iframe.ele('tag:body').click(); time.sleep(1)
                except: pass
            time.sleep(1)
        return False
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
        time.sleep(0.5)

        page.ele('css:button[data-id="venue"]').click()
        time.sleep(0.5)
        page.ele('xpath://div[contains(@class, "open")]//li//span[text()="GoDaddy"]').click()
        time.sleep(0.5)

        page.ele('css:button[data-id="date-range"]').click()
        time.sleep(0.5)
        dates = page.eles('xpath://div[contains(@class, "open")]//ul/li')
        if len(dates) > 1: dates[1].click()
        time.sleep(0.5)

        try: page.ele('css:select[name="search-results_length"]').select('25')
        except: pass
        
        return True
    except: return False

def main():
    print(">> Starting DropDax Scraper (Manifest V2 Fix)...")
    proxy_url = os.environ.get("PROXY_URL")
    plugin_path = None
    
    if proxy_url:
        plugin_path = create_proxy_auth_extension(proxy_url)

    # --- SINGLE ROBUST ATTEMPT ---
    co = ChromiumOptions()
    
    # 1. EXTENSION
    if plugin_path: 
        co.add_extension(plugin_path)
    
    # 2. BROWSER CONFIG
    co.set_argument(f'--user-agent={WINDOWS_UA}')
    co.set_argument('--window-size=1920,1080')
    # CRITICAL: Do NOT use --headless. We use Xvfb.
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--lang=en-US')
    co.set_paths(browser_path='/usr/bin/google-chrome')
    
    page = None
    try:
        page = ChromiumPage(addr_or_opts=co)
        
        # 3. INITIALIZE EXTENSION
        print(">> Waiting for Proxy Extension...")
        time.sleep(5) # Give V2 extension time to load background page
        
        # 4. CHECK IP
        print(">> Verifying IP...")
        ip, status = get_ip_info(page)
        print(f">> IP: {ip}")
        
        if not status or ip.startswith("20.") or ip.startswith("172."):
            print(">> BAD IP (Azure/Failed). Aborting.")
            sys.exit(1)
        else:
            print(">> GOOD IP. Proceeding...")

        # 5. EXECUTION
        print(">> Approaching NameBio...")
        page.get("https://namebio.com/")
        
        if is_blocked(page):
            print(">> Hard Block detected on arrival.")
            sys.exit(1)
        
        if not bypass_turnstile(page):
            print(">> Turnstile Failed.")
            sys.exit(1)

        # Clear Banner
        try:
            banner = page.ele('#nudge-countdown-container', timeout=3)
            if banner: banner.ele('css:a[data-dismiss="modal"]').click()
        except: pass

        # Filters
        if not apply_filters(page):
            print(">> Filters Failed.")
            page.quit()
            sys.exit(1)

        # Search
        print(">> Executing Search...")
        page.ele('#search-submit').click()
        page.wait.ele_displayed('#search-results tbody tr', timeout=30)
        
        # Scrape
        rows = page.eles('#search-results tbody tr')
        data = []
        print(f">> Found {len(rows)} rows.")

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
        
        print(f">> SUCCESS! Saved {len(data)} rows.")

    except Exception as e:
        print(f">> FATAL ERROR: {e}")
        safe_screenshot(page, "debug_fatal.png")
        sys.exit(1)
    
    finally:
        if page: page.quit()
        if os.path.exists("proxy_auth_plugin"): shutil.rmtree("proxy_auth_plugin")

if __name__ == "__main__":
    main()
