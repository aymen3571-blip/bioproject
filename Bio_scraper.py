import os
import csv
import json
import time
import sys
import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
OUTPUT_FILE = "namebio_data.csv"
FLARESOLVERR_URL = "http://localhost:8191/v1"
TARGET_URL = "https://namebio.com/last-sold"

def init_csv():
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Domain", "Price", "Date", "Venue"])

def send_cmd(cmd):
    """Helper to send commands to FlareSolverr"""
    try:
        resp = requests.post(FLARESOLVERR_URL, json=cmd, timeout=70)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}

def main():
    print(">> Starting DropDax Diagnostic Scraper...")
    init_csv()
    proxy_url = os.environ.get("PROXY_URL")
    
    # ---------------------------------------------------------
    # TEST 1: CONTAINER HEALTH (No Proxy)
    # ---------------------------------------------------------
    print("\n>> [TEST 1] Checking Container Internet Access (No Proxy)...")
    cmd_health = {
        "cmd": "request.get",
        "url": "http://www.google.com/",
        "maxTimeout": 30000
    }
    data = send_cmd(cmd_health)
    if data.get("status") == "ok":
        print(">> SUCCESS: Container has internet.")
    else:
        print(f">> FAIL: Container is offline. Message: {data.get('message')}")
        sys.exit(1)

    # ---------------------------------------------------------
    # TEST 2: PROXY HEALTH
    # ---------------------------------------------------------
    if proxy_url:
        print(f"\n>> [TEST 2] Checking Proxy Connection ({proxy_url.split('@')[1]})...")
        cmd_proxy = {
            "cmd": "request.get",
            "url": "http://example.com/", # Simple site, low block rate
            "proxy": {"url": proxy_url},
            "maxTimeout": 60000
        }
        data = send_cmd(cmd_proxy)
        if data.get("status") == "ok":
            print(">> SUCCESS: Proxy is working!")
        else:
            print(">> FATAL: Proxy Connection Failed.")
            print(f">> Error: {data.get('message')}")
            print(">> The container cannot tunnel through your proxy. Check your credentials.")
            sys.exit(1)
    else:
        print(">> WARNING: Skipping Proxy Test (No Proxy Set).")

    # ---------------------------------------------------------
    # TEST 3: NAMEBIO ATTACK (With Session)
    # ---------------------------------------------------------
    print("\n>> [TEST 3] Targeting NameBio with Sticky Session...")
    
    # Step A: Create a Session (Keeps browser open)
    session_id = f"session_{int(time.time())}"
    print(f">> Creating Session: {session_id}")
    
    create_cmd = {
        "cmd": "sessions.create",
        "session": session_id,
        "proxy": {"url": proxy_url} if proxy_url else None
    }
    send_cmd(create_cmd)
    
    # Step B: Request Data using that Session
    print(">> Requesting Data...")
    req_cmd = {
        "cmd": "request.get",
        "session": session_id,
        "url": TARGET_URL,
        "maxTimeout": 60000,
        # IMPORTANT: Wait for the table to actually load
        # We assume the table has ID 'search-results' or class 'table'
        # If we don't wait, we might get the 'Just a moment' page HTML
    }
    
    data = send_cmd(req_cmd)
    
    # Cleanup Session
    send_cmd({"cmd": "sessions.destroy", "session": session_id})
    
    if data.get("status") != "ok":
        print(">> FATAL: NameBio Request Failed.")
        print(f">> Message: {data.get('message')}")
        
        # Check if it was a timeout (common with proxies)
        if "Timeout" in data.get("message", ""):
            print(">> CAUSE: The proxy was too slow to solve the challenge in 60s.")
        sys.exit(1)

    # Step C: Parse
    print(">> SUCCESS: Cloudflare Bypassed! Parsing HTML...")
    html_content = data["solution"]["response"]
    
    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table", id="search-results")
    
    if not table:
        print(">> ERROR: Table '#search-results' not found.")
        print(">> DUMPING PAGE TITLE:")
        print(soup.title.string if soup.title else "No Title")
        sys.exit(1)

    rows = table.find("tbody").find_all("tr")
    print(f">> Found {len(rows)} raw rows.")

    new_data = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 4: continue
        
        domain = cols[0].get_text(strip=True)
        price = cols[1].get_text(strip=True).replace("$", "").replace(",", "")
        date = cols[2].get_text(strip=True)
        venue = cols[3].get_text(strip=True)
        
        # Filters: .com + GoDaddy
        if not domain.endswith(".com") or "godaddy" not in venue.lower():
            continue
        
        print(f"   + MATCH: {domain} | {price} | {venue}")
        new_data.append([domain, price, date, venue])

    if new_data:
        with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(new_data)
        print(f">> SAVED {len(new_data)} rows.")
    else:
        print(">> No rows matched filters.")

if __name__ == "__main__":
    main()
