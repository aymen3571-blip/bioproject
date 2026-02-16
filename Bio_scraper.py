import os
import csv
import time
import shutil
import sys
import pytesseract
from PIL import Image
from io import BytesIO
from urllib.parse import urlparse
from DrissionPage import ChromiumPage, ChromiumOptions

# --- CONFIGURATION ---
OUTPUT_FILE = "namebio_data.csv"
# We act as a generic Android device. This matches the Linux kernel of the server.
ANDROID_UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"

# --- PROXY EXTENSION (MANIFEST V2 - RELIABLE) ---
def create_proxy_auth_extension(proxy_string, plugin_dir="proxy_auth_plugin"):
    try:
        parsed = urlparse(proxy_string)
        username = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port
        scheme = parsed.scheme or "http"
        
        if not username or not password: return None
        
        abs_dir = os.path.abspath(plugin_dir)
        if os.path.exists(abs_dir): shutil.rmtree(abs_dir)
        os.makedirs(abs_dir)

        manifest_json = """
        {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Proxy Auth",
            "permissions": ["proxy", "tabs", "<all_urls>", "webRequest", "webRequestBlocking"],
            "background": {"scripts": ["background.js"]}
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
        with open(os.path.join(abs_dir, "manifest.json"), "w") as f: f.write(manifest_json)
        with open(os.path.join(abs_dir, "background.js"), "w") as f: f.write(background_js)
        return abs_dir
    except: return None

def get_price_via_ocr(ele):
    try:
        png_bytes = ele.get_screenshot(as_bytes=True)
        image = Image.open(BytesIO(png_bytes))
        text = pytesseract.image_to_string(image, config='--psm 7').strip()
        return text
    except: return "OCR_ERROR"

def is_blocked(page):
    if "blocked" in page.title.lower() or "security service" in page.html.lower():
        print("   >> DETECTED: Hard Block.")
        return True
    return False

def bypass_turnstile(page):
    print(">> Checking Security...")
    time.sleep(3)
    if is_blocked(page): return False
    
    if "Just a moment" in page.title or "robot" in page.title.lower():
        print(">> Turnstile Challenge Detected...")
        # Android Emulation handles touch events automatically in DrissionPage
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

def apply_filters_mobile(page):
    print(">> Applying Mobile Filters...")
    try:
        # On mobile, we might need to click a "Filters" toggle first, 
        # but usually the inputs are just stacked.
        
        # 1. Extension (.com)
        # Wait for the dropdown button
        ext_btn = page.wait.ele_displayed('css:button[data-id="extension"]', timeout=10)
        ext_btn.click()
        time.sleep(0.5)
        page.ele('xpath://div[contains(@class, "open")]//li//span[text()=".com"]').click()
        
        # 2. Venue (GoDaddy)
        page.ele('css:button[data-id="venue"]').click()
        time.sleep(0.5)
        page.ele('xpath://div[contains(@class, "open")]//li//span[text()="GoDaddy"]').click()
        
        # 3. Date (Today)
        page.ele('css:button[data-id="date-range"]').click()
        time.sleep(0.5)
        dates = page.eles('xpath://div[contains(@class, "open")]//ul/li')
        if len(dates) > 1: dates[1].click()
        
        # 4. Search
        page.ele('#search-submit').click()
        return True
    except Exception as e:
        print(f">> Filter Error: {e}")
        return False

def main():
    print(">> Starting DropDax Scraper (Android GPU-Kill Mode)...")
    proxy_url = os.environ.get("PROXY_URL")
    plugin_path = create_proxy_auth_extension(proxy_url) if proxy_url else None

    co = ChromiumOptions()
    
    # 1. PROXY
    if plugin_path: co.add_extension(plugin_path)
    
    # 2. IDENTITY: ANDROID
    co.set_argument(f'--user-agent={ANDROID_UA}')
    
    # 3. CRITICAL: KILL THE GPU (Prevents Linux Fingerprinting)
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-software-rasterizer')
    co.set_argument('--disable-webgl')
    co.set_argument('--disable-webgl2')
    co.set_argument('--disable-3d-apis')
    co.set_argument('--disable-accelerated-2d-canvas')
    
    # 4. MOBILE VIEWPORT
    co.set_argument('--window-size=375,812') # iPhone X / Pixel size
    
    # 5. STANDARD
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--lang=en-US')
    co.set_paths(browser_path='/usr/bin/google-chrome')

    page = ChromiumPage(addr_or_opts=co)

    try:
        print(">> Waiting for Proxy...")
        time.sleep(5)
        
        # IP CHECK
        page.get("https://api.ipify.org", timeout=15)
        print(f">> IP: {page.ele('tag:body').text}")

        # NAVIGATION
        print(">> Loading NameBio (Last Sold)...")
        # Direct entry to the table page
        page.get("https://namebio.com/last-sold")
        
        if not bypass_turnstile(page):
            print(">> FAILED: Turnstile blocked.")
            sys.exit(1)
            
        # CLEAR BANNER
        try:
            banner = page.ele('#nudge-countdown-container', timeout=3)
            if banner: banner.ele('css:a[data-dismiss="modal"]').click()
        except: pass
        
        # APPLY FILTERS
        if not apply_filters_mobile(page):
            print(">> Filters failed.")
            sys.exit(1)
            
        print(">> Waiting for Results...")
        page.wait.ele_displayed('#search-results tbody tr', timeout=30)
        
        # SCRAPE
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
            
        print(f">> SUCCESS. Saved {len(data)} rows.")

    except Exception as e:
        print(f">> FATAL: {e}")
        try: page.get_screenshot(path="debug_final.png")
        except: pass
        sys.exit(1)
    
    finally:
        page.quit()
        if os.path.exists("proxy_auth_plugin"): shutil.rmtree("proxy_auth_plugin")

if __name__ == "__main__":
    main()
