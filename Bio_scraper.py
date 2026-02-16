import requests
import json
import csv
import os
from datetime import date

# Get token from GitHub Secrets
API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")

def main():
    target_url = "https://namebio.com/jm-ajax/search"
    api_url = "https://api.scrape.do/"
    
    # Same payload we used before for GoDaddy .com sales
    payload = {
        "draw": "1", "start": "0", "length": "25", "tld[]": "com",
        "venue[]": "godaddy", "date_start": "today", "date_end": "today",
        "order[0][column]": "2", "order[0][dir]": "desc"
    }

    # Scrape.do parameters: render=true is the "Cloudflare Killer"
    params = {
        "token": API_TOKEN,
        "url": target_url,
        "super": "true"      # <-- ADD THIS (Uses Residential IPs to bypass Cloudflare)
    }

    print(">> Calling Scrape.do API (Super Mode)...")
    # We send the payload (search options) normally, Scrape.do forwards it
    response = requests.post(api_url, params=params, data=payload, timeout=60)
    
    if response.status_code == 200:
        data = response.json()
        rows = data.get("data", [])
        
        filename = "daily_sales.csv"
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Domain", "Price", "Date", "Venue"])
            for item in rows:
                domain = item.get('domain', '').split('<')[0].strip()
                writer.writerow([domain, item.get('price'), item.get('date'), item.get('venue')])
        print(f">> Successfully saved {len(rows)} sales to {filename}")
    else:
        print(f">> Error: {response.status_code} - {response.text}")
        exit(1) # Tell GitHub the action failed

if __name__ == "__main__":
    main()
