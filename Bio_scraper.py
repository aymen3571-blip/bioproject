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
                
            try:
                page.run_js(f"window.scrollBy(0, {random.randint(10, 50)});")
            except: pass
            
            iframe = page.ele('xpath://iframe[starts-with(@src, "https://challenges.cloudflare.com")]', timeout=1)
            if iframe:
                print(f"   > Clicking Turnstile... ({i})")
                try: iframe.ele('tag:body').click()
                except: pass
            
            time.sleep(2)
        else:
            print(">> FAILED: Timeout waiting for challenge.")
            return None

        # 3. Extract Cookies (FIXED SYNTAX)
        print(">> Extracting Cookies...")
        
        # Try multiple methods to get the raw list of cookies
        try:
            raw_cookies = page.get_cookies() # Method in newer versions
        except:
            try:
                raw_cookies = page.cookies # Property in older versions
            except:
                print(">> Error: Could not retrieve cookie object.")
                return None
                
        # Manually convert list of dicts to simple dict {name: value}
        cookie_dict = {}
        for c in raw_cookies:
            # DrissionPage sometimes returns objects, sometimes dicts
            if isinstance(c, dict):
                cookie_dict[c.get('name')] = c.get('value')
            else:
                # Assuming it's an object with attributes
                try:
                    cookie_dict[c.name] = c.value
                except: pass

        ua = page.run_js("return navigator.userAgent")
        print(f">> Cookies Secured: {len(cookie_dict)} found.")
        return cookie_dict, ua

    except Exception as e:
        print(f">> Browser Error: {e}")
        return None
    finally:
        page.quit()
        if os.path.exists("proxy_auth_plugin"): shutil.rmtree("proxy_auth_plugin")

def scrape_api(cookies, user_agent, proxy_url):
    print("\n>> PHASE 2: API Injection (The Heist)...")
    
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://namebio.com",
        "Referer": "https://namebio.com/",
    }

    # API Payload
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
            try:
                data = resp.json()
            except:
                print(">> API returned HTML (Cloudflare blocked the API call).")
                print(resp.text[:200])
                return None
                
            rows = data.get("data", [])
            print(f">> SUCCESS! API returned {len(rows)} rows.")
            
            clean_data = []
            for row in rows:
                domain = row.get('domain', '').split('<')[0].strip()
                price_raw = row.get('price', '')
                
                # Handle Image Prices vs Text Prices
                if "<img" in str(price_raw):
                    price = "IMAGE_PRICE" 
                else:
                    price = str(price_raw).replace('$', '').replace(',', '').strip()
                
                date = row.get('date', '')
                venue = row.get('venue', '')
                
                print(f"   + {domain} | {price}")
                clean_data.append([domain, price, date, venue])
                
            return clean_data
        else:
            print(f">> API FAILED. Status: {resp.status_code}")
            return None

    except Exception as e:
        print(f">> API Error: {e}")
        return None

def main():
    print(">> Starting DropDax 'Cookie Handoff' Scraper...")
    proxy_url = os.environ.get("PROXY_URL")
    
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Domain", "Price", "Date", "Venue"])

    for attempt in range(1, 4):
        print(f"\n=== ATTEMPT {attempt}/3 ===")
        
        result = get_cookies_via_browser(proxy_url)
        if not result:
            print(">> Cookie Harvest failed. Rotating...")
            continue
            
        cookies, ua = result
        data = scrape_api(cookies, ua, proxy_url)
        
        if data:
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
