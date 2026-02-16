import os
import csv
import time
import json
import shutil
import sys
import random
import requests
from urllib.parse import urlparse
from DrissionPage import ChromiumPage, ChromiumOptions

# --- CONFIGURATION ---
OUTPUT_FILE = "namebio_data.csv"
# We match the server OS (Linux) to avoid "OS Mismatch" flags
UA_LINUX = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# --- PROXY SETUP (Manifest V2) ---
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

def get_cookies_via_browser(proxy_url):
    print(">> PHASE 1: Harvesting Cookies via Browser...")
    plugin_path = create_proxy_auth_extension(proxy_url) if proxy_url else None
    
    co = ChromiumOptions()
    if plugin_path: co.add_extension(plugin_path)
    
    # STEALTH SETTINGS
    co.set_argument(f'--user-agent={UA_LINUX}')
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--lang=en-US')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_paths(browser_path='/usr/bin/google-chrome')

    page = ChromiumPage(addr_or_opts=co)
    
    try:
        # 1. Open Site
        print(">> Navigating to NameBio...")
        page.get("https://namebio.com/")
        
        # 2. Wait for Cloudflare Solve
        print(">> Waiting for Cloudflare Challenge...")
        time.sleep(5)
        
        for i in range(15):
            title = page.title.lower()
            if "blocked" in title:
                print(">> BROWSER BLOCKED. Retrying...")
                return None
            
            if "just a moment" not in title and "robot" not in title:
                print(">> SUCCESS: Challenge Passed!")
                break
                
            # Random mouse wiggle to prove humanity
            try:
                page.run_js(f"window.scrollBy(0, {random.randint(10, 50)});")
            except: pass
            
            # Check for iframe click
            iframe = page.ele('xpath://iframe[starts-with(@src, "https://challenges.cloudflare.com")]', timeout=1)
            if iframe:
                print(f"   > Clicking Turnstile... ({i})")
                try: iframe.ele('tag:body').click()
                except: pass
            
            time.sleep(2)
        else:
            print(">> FAILED: Timeout waiting for challenge.")
            return None

        # 3. Extract Cookies
        cookies = page.cookies(as_dict=True)
        ua = page.run_js("return navigator.userAgent")
        print(f">> Cookies Secured: {len(cookies)} found.")
        return cookies, ua

    except Exception as e:
        print(f">> Browser Error: {e}")
        return None
    finally:
        page.quit()
        if os.path.exists("proxy_auth_plugin"): shutil.rmtree("proxy_auth_plugin")

def scrape_api(cookies, user_agent, proxy_url):
    print("\n>> PHASE 2: API Injection (The Heist)...")
    
    # Headers matching the browser session EXACTLY
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://namebio.com",
        "Referer": "https://namebio.com/",
    }

    # Payload matching your filters
    payload = {
        "draw": "1",
        "start": "0",
        "length": "25",
        "tld[]": "com",
        "venue[]": "godaddy",
        "date_start": "today",
        "date_end": "today",
        "order[0][column]": "2",
        "order[0][dir]": "desc"
    }

    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    try:
        print(">> Sending API Request...")
        resp = requests.post(
            "https://namebio.com/jm-ajax/search",
            headers=headers,
            data=payload,
            cookies=cookies,
            proxies=proxies,
            timeout=30
        )
        
        if resp.status_code == 200:
            data = resp.json()
            rows = data.get("data", [])
            print(f">> SUCCESS! API returned {len(rows)} rows.")
            
            clean_data = []
            for row in rows:
                domain = row.get('domain', '').split('<')[0].strip()
                # Price often comes as HTML image or text. Simple fallback:
                price_raw = row.get('price', '')
                if "<img" in price_raw:
                    price = "IMAGE_PRICE" # We can fix this later if needed
                else:
                    price = price_raw.replace('$', '').replace(',', '').strip()
                
                date = row.get('date', '')
                venue = row.get('venue', '')
                
                print(f"   + {domain} | {price}")
                clean_data.append([domain, price, date, venue])
                
            return clean_data
        else:
            print(f">> API FAILED. Status: {resp.status_code}")
            # print(resp.text[:500]) # Debug
            return None

    except Exception as e:
        print(f">> API Error: {e}")
        return None

def main():
    print(">> Starting DropDax 'Cookie Handoff' Scraper...")
    proxy_url = os.environ.get("PROXY_URL")
    
    # 1. Initialize CSV
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Domain", "Price", "Date", "Venue"])

    # 2. Try up to 3 times to get a valid session
    for attempt in range(1, 4):
        print(f"\n=== ATTEMPT {attempt}/3 ===")
        
        # Step A: Get Cookies
        result = get_cookies_via_browser(proxy_url)
        if not result:
            print(">> Cookie Harvest failed. Rotating...")
            continue
            
        cookies, ua = result
        
        # Step B: Use Cookies for API
        data = scrape_api(cookies, ua, proxy_url)
        
        if data:
            # Step C: Save and Exit
            with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(data)
            print(f"\n>> MISSION COMPLETE. Saved {len(data)} rows to {OUTPUT_FILE}")
            sys.exit(0)
            
        print(">> API rejected cookies. Retrying session...")
        time.sleep(5)

    print("\n>> FATAL: All attempts failed.")
    sys.exit(1)

if __name__ == "__main__":
    main()
