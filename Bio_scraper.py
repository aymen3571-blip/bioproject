import os
import csv
import time
import json
import shutil
import sys
import random
import math
import pytesseract
from PIL import Image
from io import BytesIO
from urllib.parse import urlparse
from DrissionPage import ChromiumPage, ChromiumOptions

# --- CONFIGURATION ---
OUTPUT_FILE = "namebio_data.csv"
UA_LINUX = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# --- PROXY SETUP ---
def create_proxy_auth_extension(proxy_string, plugin_dir="proxy_auth_plugin"):
    try:
        parsed = urlparse(proxy_string)
        if not parsed.username or not parsed.password: return None
        if os.path.exists(plugin_dir): shutil.rmtree(plugin_dir)
        os.makedirs(plugin_dir)
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
                    scheme: "{parsed.scheme or 'http'}",
                    host: "{parsed.hostname}",
                    port: parseInt({parsed.port})
                }},
                bypassList: ["localhost"]
            }}
        }};
        chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
        chrome.webRequest.onAuthRequired.addListener(
            function(details) {{
                return {{authCredentials: {{username: "{parsed.username}", password: "{parsed.password}"}}}};
            }},
            {{urls: ["<all_urls>"]}},
            ['blocking']
        );
        """
        with open(os.path.join(plugin_dir, "manifest.json"), "w") as f: f.write(manifest_json)
        with open(os.path.join(plugin_dir, "background.js"), "w") as f: f.write(background_js)
        return os.path.abspath(plugin_dir)
    except: return None

def human_mouse_move(page):
    """Simulates realistic human mouse movement to trick Cloudflare."""
    print("   > Simulating Human Mouse Jiggle...")
    width, height = 1920, 1080
    for _ in range(5):
        x = random.randint(100, width - 100)
        y = random.randint(100, height - 100)
        page.run_js(f"""
            var event = new MouseEvent('mousemove', {{
                'view': window,
                'bubbles': true,
                'cancelable': true,
                'clientX': {x},
                'clientY': {y}
            }});
            document.dispatchEvent(event);
        """)
        time.sleep(random.uniform(0.1, 0.3))

def get_price_via_ocr(ele):
    try:
        png_bytes = ele.get_screenshot(as_bytes=True)
        image = Image.open(BytesIO(png_bytes))
        text = pytesseract.image_to_string(image, config='--psm 7').strip()
        return text
    except: return "OCR_ERROR"

def main():
    print(">> Starting DropDax 'Human Emulator' Scraper...")
    proxy_url = os.environ.get("PROXY_URL")
    plugin_path = create_proxy_auth_extension(proxy_url) if proxy_url else None
    
    co = ChromiumOptions()
    if plugin_path: co.add_extension(plugin_path)
    
    # CRITICAL: Force non-headless-looking flags
    co.set_argument(f'--user-agent={UA_LINUX}')
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--lang=en-US')
    co.set_argument('--start-maximized') 
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_paths(browser_path='/usr/bin/google-chrome')

    page = ChromiumPage(addr_or_opts=co)
    
    try:
        # 1. NAVIGATION
        print(">> Navigating to NameBio (Last Sold)...")
        # Direct link to the data page, skipping homepage
        page.get("https://namebio.com/last-sold")
        
        # 2. THE LONG WAIT (Trust Score Building)
        print(">> Waiting 20s for Cloudflare Trust Score...")
        # While waiting, we "jiggle" the mouse
        for i in range(10):
            time.sleep(2)
            human_mouse_move(page)
            
            # Check if we passed
            if "blocked" not in page.title.lower() and "just a moment" not in page.title.lower():
                # Verify we see the table
                if page.ele('#search-results', timeout=1):
                    print(">> SUCCESS! Table detected early.")
                    break
        
        # 3. IFRAME CHECK
        iframe = page.ele('xpath://iframe[starts-with(@src, "https://challenges.cloudflare.com")]', timeout=2)
        if iframe:
            print(">> Cloudflare Challenge Detected. Attempting Click...")
            time.sleep(2)
            try: iframe.ele('tag:body').click()
            except: pass
            time.sleep(5)
            
        # 4. FINAL VERIFICATION
        if "blocked" in page.title.lower() or "security" in page.html.lower():
            print(">> FAILED: Still blocked after wait.")
            # Dump HTML to see what's happening
            print(page.html[:500])
            sys.exit(1)

        # 5. FILTERS
        print(">> Attempting Filters...")
        try:
            # Try to set filters if the button exists
            ext_btn = page.ele('css:button[data-id="extension"]', timeout=5)
            if ext_btn:
                ext_btn.click()
                time.sleep(0.5)
                page.ele('xpath://div[contains(@class, "open")]//li//span[text()=".com"]').click()
                time.sleep(1)
                
                page.ele('css:button[data-id="venue"]').click()
                time.sleep(0.5)
                page.ele('xpath://div[contains(@class, "open")]//li//span[text()="GoDaddy"]').click()
                time.sleep(1)
                
                page.ele('#search-submit').click()
                print(">> Filters Applied.")
                time.sleep(3)
        except Exception as e:
            print(f">> Filters skipped (using defaults): {e}")

        # 6. SCRAPE
        print(">> Extracting Data...")
        page.wait.ele_displayed('#search-results tbody tr', timeout=15)
        
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

        # 7. SAVE
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Domain", "Price", "Date", "Venue"])
            writer.writerows(data)
            
        print(f">> SUCCESS! Saved {len(data)} rows.")

    except Exception as e:
        print(f">> FATAL ERROR: {e}")
        try: page.get_screenshot(path="debug_fatal.png")
        except: pass
        sys.exit(1)
    
    finally:
        page.quit()
        if os.path.exists("proxy_auth_plugin"): shutil.rmtree("proxy_auth_plugin")

if __name__ == "__main__":
    main()
