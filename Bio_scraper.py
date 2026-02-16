import os
import csv
import sys
import time
import json
from urllib.parse import urlparse
import tls_client

# --- CONFIGURATION ---
OUTPUT_FILE = "namebio_data.csv"
PROXY_URL = os.environ.get("PROXY_URL")

def init_csv():
    """Creates the CSV file immediately to prevent Git errors."""
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Domain", "Price", "Date", "Venue"])
    print(f">> Initialized {OUTPUT_FILE}")

def get_proxy_string():
    if not PROXY_URL: return None
    try:
        parsed = urlparse(PROXY_URL)
        return f"http://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}"
    except:
        return None

def main():
    print(">> Starting DropDax API Scraper (Session Priming Mode)...")
    
    init_csv()

    # 1. SETUP SESSION
    # We use 'chrome_120' to match the User-Agent perfectly
    session = tls_client.Session(
        client_identifier="chrome_120",
        random_tls_extension_order=True
    )

    proxy_str = get_proxy_string()
    if proxy_str:
        print(f">> Proxy Configured: {proxy_str.split('@')[1]}")
        session.proxies = {"http": proxy_str, "https": proxy_str}

    # 2. COMMON HEADERS
    base_headers = {
        "Host": "namebio.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    try:
        # 3. STEP 1: VISIT HOMEPAGE (Get Cookies)
        print(">> Step 1: Visiting Homepage to prime cookies...")
        resp_home = session.get(
            "https://namebio.com/",
            headers=base_headers,
            timeout_seconds=30
        )
        
        if resp_home.status_code != 200:
            print(f">> FATAL: Homepage Blocked (Status {resp_home.status_code})")
            print(resp_home.text[:500])
            sys.exit(1)
            
        print(">> Cookies Acquired:", session.cookies.get_dict())
        time.sleep(2) # Slight pause to look human

        # 4. STEP 2: CALL SEARCH API
        print(">> Step 2: Sending Authenticated Search Request...")
        
        # Update headers for AJAX request
        api_headers = base_headers.copy()
        api_headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://namebio.com",
            "Referer": "https://namebio.com/",
            "X-Requested-With": "XMLHttpRequest",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })
        # Remove 'Upgrade-Insecure-Requests' for AJAX
        del api_headers["Upgrade-Insecure-Requests"]

        # Payload matching your filters
        payload = {
            "draw": "1",
            "start": "0",
            "length": "25",
            "search[value]": "",
            "search[regex]": "false",
            "tld[]": "com",
            "venue[]": "godaddy",
            "date_start": "today",
            "date_end": "today",
            "order[0][column]": "2",
            "order[0][dir]": "desc"
        }

        resp_api = session.post(
            "https://namebio.com/jm-ajax/search",
            headers=api_headers,
            data=payload,
            timeout_seconds=30
        )

        print(f">> Status Code: {resp_api.status_code}")

        if resp_api.status_code == 200:
            try:
                json_data = resp_api.json()
                rows = json_data.get("data", [])
                
                print(f">> Success! Found {len(rows)} records.")
                
                clean_data = []
                for row in rows:
                    domain = row.get('domain', '').split('<')[0].strip()
                    price = row.get('price', '').replace('$', '').replace(',', '').strip()
                    date = row.get('date', '')
                    venue = row.get('venue', '')
                    
                    print(f"   + {domain} | ${price}")
                    clean_data.append([domain, price, date, venue])

                with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerows(clean_data)
                
            except json.JSONDecodeError:
                print(">> ERROR: Response was not JSON (Likely Cloudflare Block).")
                print(">> RESPONSE SNIPPET:")
                print(resp_api.text[:500])
                sys.exit(1)
        
        elif resp_api.status_code == 403:
            print(">> CRITICAL: 403 Forbidden (Cloudflare Hard Block).")
            # Dump the HTML to see if it's a captcha page
            print(resp_api.text[:500])
            sys.exit(1)
            
        else:
            print(f">> ERROR: Unexpected Status {resp_api.status_code}")
            sys.exit(1)

    except Exception as e:
        print(f">> FATAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
