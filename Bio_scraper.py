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
# Matching Linux UA to Server OS reduces "Mismatch" flags
LINUX_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

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
        
        abs_plugin_dir = os.path.abspath(plugin_dir)
        if os.path.exists(abs_plugin_dir): shutil.rmtree(abs_plugin_dir)
        os.makedirs(abs_plugin_dir)

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
        with open(os.path.join(abs_plugin_dir, "manifest.json"), "w") as f: f.write(manifest_json)
        with open(os.path.join(abs_plugin_dir, "background.js"), "w") as f: f.write(background_js)
        return abs_plugin_dir
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
    # Try multiple sources to verify IP
    for url in ["https://ifconfig.me/ip", "https://icanhazip.com", "https://api.ipify.org"]:
        try:
            page.get(url, timeout=10)
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
    time.sleep(2)
    if is_blocked(page): return False
    
    if "Just a moment" in page.title or "robot" in page.title.lower():
        print(">> Turnstile Challenge Detected...")
        for i in range(20):
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
        
        # Extension
        page.wait.ele_displayed('css:button[data-id="extension"]', timeout=10).click()
        page.ele('xpath://div[contains(@class, "open")]//li//span[text()=".com"]').click()
        time.sleep(0.5)

        # Venue
        page.ele('css:button[data-id="venue"]').click()
        page.ele('xpath://div[contains(@class, "open")]//li//span[text()="GoDaddy"]').click()
        time.sleep(0.5)

        # Date
        page.ele('css:button[data-id="date-range"]').click()
        dates = page.eles('xpath://div[contains(@class, "open")]//ul/li')
        if len(dates) > 1: dates[1].click()
        time.sleep(0.5)

        # Rows
        try: page.ele('css:select[name="search-results_length"]').select('25')
        except: pass
        
        return True
    except: return False

def main():
    print(">> Starting DropDax Scraper (Rotation Engine)...")
    proxy_url = os.environ.get("PROXY_URL")
    plugin_path = None
    if proxy_url:
        plugin_path = create_proxy_auth_extension(proxy_url)

    # --- THE ROTATION LOOP ---
    MAX_ATTEMPTS = 10
    success = False
    
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n========================================")
        print(f"   SESSION ATTEMPT {attempt}/{MAX_ATTEMPTS}")
        print(f"========================================")
        
        co = ChromiumOptions()
        if plugin_path: co.set_argument(f'--load-extension={plugin_path}')
        
        # Standard Linux Stealth Config
        co.set_argument(f'--user-agent={LINUX_UA}')
        co.set_argument('--window-size=1920,1080')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-gpu')
        co.set_argument('--lang=en-US')
        co.set_argument('--disable-blink-features=AutomationControlled') 
        co.set_paths(browser_path='/usr/bin/google-chrome')
        
        page = None
        try:
            page = ChromiumPage(addr_or_opts=co)
            
            # 1. Verify IP (Is Proxy working?)
            ip, status = get_ip_info(page)
            print(f">> IP Check: {ip}")
            
            if not status or ip.startswith("20.") or ip.startswith("172."):
                print(">> BAD IP. Rotating...")
                page.quit()
                continue # Next attempt
            
            # 2. Go to NameBio
            print(">> Approaching Target...")
            page.get("https://namebio.com/")
            
            # 3. Check for Immediate Ban
            if is_blocked(page):
                print(">> Hard Block detected on this IP. Rotating...")
                page.quit()
                continue # Next attempt (New IP)
            
            # 4. Security Check
            if not bypass_turnstile(page):
                print(">> Security check failed. Rotating...")
                page.quit()
                continue
                
            # 5. Clear Banner
            try:
                banner = page.ele('#nudge-countdown-container', timeout=2)
                if banner: banner.ele('css:a[data-dismiss="modal"]').click()
            except: pass

            # 6. Filters
            if not apply_filters(page):
                print(">> Filters failed. Rotating...")
                page.quit()
                continue

            # 7. Search
            print(">> Executing Search...")
            page.ele('#search-submit').click()
            page.wait.ele_displayed('#search-results tbody tr', timeout=30)
            
            # 8. Scrape
            rows = page.eles('#search-results tbody tr')
            data = []
            print(f">> Found {len(rows)} rows. Extracting...")

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
            success = True
            break # Exit loop on success

        except Exception as e:
            print(f">> Crash on attempt {attempt}: {e}")
            if page: page.quit()
    
    if not success:
        print("\n>> FATAL: All 10 attempts failed.")
        if os.path.exists("proxy_auth_plugin"): shutil.rmtree("proxy_auth_plugin")
        sys.exit(1)
        
    if os.path.exists("proxy_auth_plugin"): shutil.rmtree("proxy_auth_plugin")

if __name__ == "__main__":
    main()
