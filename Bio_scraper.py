import os
import csv
import sys
import time
import json
from urllib.parse import urlparse

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
    print(">> Starting DropDax API Scraper (Robust Mode)...")
    
    # 0. INITIALIZE FILE
    init_csv()

    # 1. IMPORT TLS_CLIENT (Handle missing dependency error)
    try:
        import tls_client
    except ImportError as e:
        print(">> FATAL: 'tls_client' or 'typing_extensions' missing.")
        print(">> Please ensure your workflow installs: pip install requests tls_client typing_extensions")
        sys.exit(1)

    # 2. SETUP SESSION
    session = tls_client.Session(
        client_identifier="chrome_120",
        random_tls_extension_order=True
    )

    proxy_str = get_proxy_string()
    if proxy_str:
        print(f">> Proxy Configured: {proxy_str.split('@')[1]}")
        session.proxies = {"http": proxy_str, "https": proxy_str}

    # 3. HEADERS
    headers = {
        "Host": "namebio.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://namebio.com",
        "Referer": "https://namebio.com/",
        "X-Requested-With": "XMLHttpRequest",
    }

    # 4. PAYLOAD
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

    try:
        print(">> Sending API Request...")
        response = session.post(
            "https://namebio.com/jm-ajax/search",
            headers=headers,
            data=payload,
            timeout_seconds=30
        )

        print(f">> Status Code: {response.status_code}")

        if response.status_code == 200:
            try:
                json_data = response.json()
                rows = json_data.get("data", [])
                
                if not rows:
                    print(">> Success, but 0 records found for today.")
                    return # Exit cleanly, file is already created (empty)

                print(f">> Success! Found {len(rows)} records.")
                
                clean_data = []
                for row in rows:
                    domain = row.get('domain', '').split('<')[0].strip()
                    price = row.get('price', '').replace('$', '').replace(',', '').strip()
                    date = row.get('date', '')
                    venue = row.get('venue', '')
                    
                    print(f"   + {domain} | ${price}")
                    clean_data.append([domain, price, date, venue])

                # Append data to the file we created
                with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerows(clean_data)
                
            except json.JSONDecodeError:
                print(">> ERROR: Received HTML (Cloudflare Block).")
                print(">> DUMPING RESPONSE BODY FOR DEBUG:")
                print(response.text[:500]) # Print first 500 chars to identify the block
                sys.exit(1) # Fail the build
        
        else:
            print(f">> ERROR: Unexpected Status {response.status_code}")
            sys.exit(1)

    except Exception as e:
        print(f">> FATAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
