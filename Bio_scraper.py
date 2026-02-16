import os
import csv
import time
import json
import sys
import tls_client
from urllib.parse import urlparse

# --- CONFIGURATION ---
OUTPUT_FILE = "namebio_data.csv"
PROXY_URL = os.environ.get("PROXY_URL")

# --- PARSE PROXY ---
def get_proxy_string():
    if not PROXY_URL: return None
    try:
        parsed = urlparse(PROXY_URL)
        # tls_client format: http://user:pass@host:port
        return f"http://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}"
    except:
        return None

def main():
    print(">> Starting DropDax API Scraper (TLS-Client)...")

    # 1. INITIALIZE CLIENT (Spoofing Chrome 120 on Windows)
    session = tls_client.Session(
        client_identifier="chrome_120",
        random_tls_extension_order=True
    )

    # 2. CONFIGURE PROXY
    proxy_str = get_proxy_string()
    if proxy_str:
        print(f">> Proxy Configured: {proxy_str.split('@')[1]}")
        session.proxies = {
            "http": proxy_str,
            "https": proxy_str
        }
    else:
        print(">> WARNING: No Proxy Detected. Running Locally.")

    # 3. SET HEADERS (Mimic Real Browser)
    headers = {
        "Host": "namebio.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://namebio.com",
        "Referer": "https://namebio.com/",
        "X-Requested-With": "XMLHttpRequest",  # CRITICAL: Tells server it's an AJAX request
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    # 4. PREPARE PAYLOAD (The Search Parameters)
    # This matches your filters: .com, GoDaddy, Last Sold (Date)
    payload = {
        "draw": "1",
        "columns[0][data]": "domain",
        "columns[0][name]": "domain",
        "columns[1][data]": "price",
        "columns[1][name]": "price",
        "columns[2][data]": "date",
        "columns[2][name]": "date",
        "columns[3][data]": "venue",
        "columns[3][name]": "venue",
        "start": "0",
        "length": "25",  # 25 rows
        "search[value]": "",
        "search[regex]": "false",
        "placement": "all",
        "tld[]": "com",        # FILTER: .com
        "venue[]": "godaddy",  # FILTER: GoDaddy
        "date_start": "today", # FILTER: Today (Dynamic)
        "date_end": "today",
        "order[0][column]": "2", # Sort by Date
        "order[0][dir]": "desc"
    }

    try:
        # 5. EXECUTE REQUEST
        print(">> Sending API Request...")
        # NameBio uses this endpoint for the table data
        response = session.post(
            "https://namebio.com/jm-ajax/search",
            headers=headers,
            data=payload,
            timeout_seconds=30
        )

        print(f">> Status Code: {response.status_code}")
        
        # 6. HANDLE RESPONSE
        if response.status_code == 200:
            try:
                json_data = response.json()
                
                # Check for "Error" in JSON (Soft Block)
                if "error" in json_data and json_data["error"]:
                    print(f">> API Error: {json_data['error']}")
                    sys.exit(1)

                rows = json_data.get("data", [])
                print(f">> Success! Found {len(rows)} records.")
                
                # 7. SAVE TO CSV
                clean_data = []
                for row in rows:
                    # Parse the raw HTML snippet in the JSON
                    domain = row.get('domain', '').split('<')[0].strip() # Clean HTML tags if present
                    price = row.get('price', '').replace('$', '').replace(',', '').strip()
                    date = row.get('date', '')
                    venue = row.get('venue', '')
                    
                    print(f"   + {domain} | ${price}")
                    clean_data.append([domain, price, date, venue])

                with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Domain", "Price", "Date", "Venue"])
                    writer.writerows(clean_data)
                
                print(f">> Saved to {OUTPUT_FILE}")

            except json.JSONDecodeError:
                # If not JSON, it's likely a Cloudflare Challenge Page (HTML)
                print(">> FAILED: Received HTML instead of JSON (Cloudflare Block).")
                # Debug: Print first 200 chars to confirm
                print(f">> Response Snippet: {response.text[:200]}")
                sys.exit(1)
        
        elif response.status_code == 403:
            print(">> CRITICAL: 403 Forbidden (Cloudflare Hard Block).")
            sys.exit(1)
            
        else:
            print(f">> ERROR: Unexpected Status {response.status_code}")

    except Exception as e:
        print(f">> FATAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
