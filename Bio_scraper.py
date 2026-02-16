import os
import csv
import json
import time
import sys
import requests

# --- CONFIGURATION ---
OUTPUT_FILE = "namebio_data.csv"
FLARESOLVERR_URL = "http://localhost:8191/v1"
NAMEBIO_API = "https://namebio.com/jm-ajax/search"

def init_csv():
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Domain", "Price", "Date", "Venue"])

def send_cmd(cmd):
    try:
        resp = requests.post(FLARESOLVERR_URL, json=cmd, timeout=70)
        return resp.json()
    except Exception as e:
        print(f">> FlareSolverr Error: {e}")
        sys.exit(1)

def main():
    print(">> Starting DropDax 'Hybrid' Scraper...")
    init_csv()
    proxy_url = os.environ.get("PROXY_URL")
    
    # 1. CREATE SESSION & SOLVE CAPTCHA
    print(">> Step 1: Waking up FlareSolverr & Solving Captcha...")
    session_id = f"session_{int(time.time())}"
    
    # We visit the HOMEPAGE first to get the cookies.
    # We do NOT need the proxy here because FlareSolverr handles the connection internally.
    cmd_warmup = {
        "cmd": "request.get",
        "url": "https://namebio.com/",
        "maxTimeout": 60000,
        "session": session_id,
    }
    
    if proxy_url:
        print(f">> Using Proxy: {proxy_url.split('@')[1]}")
        cmd_warmup["proxy"] = {"url": proxy_url}

    resp = send_cmd(cmd_warmup)
    
    if resp.get("status") != "ok":
        print(">> FATAL: Could not pass Cloudflare Challenge.")
        print(f">> Message: {resp.get('message')}")
        sys.exit(1)

    print(">> SUCCESS: Cloudflare Bypassed.")
    
    # 2. EXTRACT CREDENTIALS
    print(">> Step 2: Extracting Golden Cookies...")
    solution = resp.get("solution", {})
    
    user_agent = solution.get("userAgent")
    cookies_list = solution.get("cookies", [])
    
    # Convert FlareSolverr cookie list to Python Dict
    cookies_dict = {}
    for c in cookies_list:
        cookies_dict[c['name']] = c['value']
        
    print(f">> Secured {len(cookies_dict)} cookies.")
    if "PHPSESSID" not in cookies_dict:
        print(">> WARNING: PHPSESSID missing (Session might be invalid).")

    # 3. DIRECT API INJECTION
    print(">> Step 3: Injecting API Request...")
    
    # Critical: Use the EXACT same User-Agent as FlareSolverr
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest", # Tells NameBio "I am a script"
        "Origin": "https://namebio.com",
        "Referer": "https://namebio.com/",
    }

    # Payload matching your filters (.com + GoDaddy + Today)
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
    
    # We use requests here (Python) to hit the API, tunneling through the SAME proxy
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    try:
        api_resp = requests.post(
            NAMEBIO_API,
            data=payload,
            headers=headers,
            cookies=cookies_dict,
            proxies=proxies,
            timeout=30
        )
        
        # 4. PROCESS RESULTS
        if api_resp.status_code == 200:
            try:
                data = api_resp.json()
            except:
                print(">> ERROR: API returned HTML (Cloudflare blocked the API call).")
                # This means the cookies weren't enough, or the IP rotated.
                print(api_resp.text[:200])
                sys.exit(1)
                
            rows = data.get("data", [])
            print(f">> SUCCESS! API returned {len(rows)} rows.")
            
            new_data = []
            for row in rows:
                domain = row.get('domain', '').split('<')[0].strip()
                price_raw = row.get('price', '')
                
                # Clean Price
                if "<img" in str(price_raw):
                    price = "IMAGE_PRICE" 
                else:
                    price = str(price_raw).replace('$', '').replace(',', '').strip()
                
                date = row.get('date', '')
                venue = row.get('venue', '')
                
                print(f"   + {domain} | {price}")
                new_data.append([domain, price, date, venue])

            if new_data:
                with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerows(new_data)
                print(f">> SAVED {len(new_data)} rows to {OUTPUT_FILE}")
            else:
                print(">> No rows found matching filters.")

        else:
            print(f">> API Failed with Status {api_resp.status_code}")
            sys.exit(1)

    except Exception as e:
        print(f">> API Request Error: {e}")
        sys.exit(1)
    
    finally:
        # Cleanup FlareSolverr Session
        send_cmd({"cmd": "sessions.destroy", "session": session_id})

if __name__ == "__main__":
    main()
