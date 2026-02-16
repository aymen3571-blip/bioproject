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
TARGET_URL = "https://namebio.com/last-sold" # The live feed

def init_csv():
    """Initializes CSV if it doesn't exist."""
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Domain", "Price", "Date", "Venue"])

def main():
    print(">> Starting DropDax 'FlareSolverr' Client...")
    
    init_csv()
    proxy_url = os.environ.get("PROXY_URL") # Format: http://user:pass@host:port

    # 1. CONSTRUCT REQUEST
    # We ask FlareSolverr to fetch the page for us
    payload = {
        "cmd": "request.get",
        "url": TARGET_URL,
        "maxTimeout": 60000, # Wait up to 60s for Cloudflare to solve
    }
    
    # Add Proxy if available
    if proxy_url:
        print(f">> Using Proxy: {proxy_url.split('@')[1]}")
        payload["proxy"] = {"url": proxy_url}
    else:
        print(">> WARNING: No Proxy found (Running Local IP)")

    try:
        # 2. SEND TO FLARESOLVERR
        print(">> Sending Command to FlareSolverr (localhost:8191)...")
        response = requests.post(FLARESOLVERR_URL, json=payload, timeout=70)
        
        if response.status_code != 200:
            print(f">> FATAL: FlareSolverr Error {response.status_code}")
            print(response.text)
            sys.exit(1)

        data = response.json()
        
        # Check 'status' field from FlareSolverr
        if data.get("status") != "ok":
            print(">> FATAL: FlareSolverr failed to bypass Cloudflare.")
            print(f">> Message: {data.get('message')}")
            # Save screenshot if available (Base64)
            sys.exit(1)

        print(">> SUCCESS: Cloudflare Bypassed! Parsing HTML...")
        html_content = data["solution"]["response"]
        
        # 3. PARSE DATA (BeautifulSoup)
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Find the main table
        table = soup.find("table", id="search-results")
        if not table:
            print(">> ERROR: Table '#search-results' not found in HTML.")
            # Debug: Dump HTML snippet
            print(html_content[:500])
            sys.exit(1)

        rows = table.find("tbody").find_all("tr")
        print(f">> Found {len(rows)} raw rows.")

        new_data = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4: continue
            
            # Extract Text
            domain = cols[0].get_text(strip=True)
            price = cols[1].get_text(strip=True).replace("$", "").replace(",", "")
            date = cols[2].get_text(strip=True)
            venue = cols[3].get_text(strip=True)
            
            # --- APPLY FILTERS (Client-Side) ---
            # 1. Must be .com
            if not domain.endswith(".com"):
                continue
                
            # 2. Must be GoDaddy
            if "godaddy" not in venue.lower():
                continue
            
            print(f"   + MATCH: {domain} | {price} | {venue}")
            new_data.append([domain, price, date, venue])

        # 4. SAVE
        if new_data:
            with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(new_data)
            print(f">> SAVED {len(new_data)} verified rows.")
        else:
            print(">> No rows matched filters (.com + GoDaddy) in this batch.")

    except Exception as e:
        print(f">> FATAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
