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

    # Define the headers to look like a real browser doing an AJAX call
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",  # <--- CRITICAL: This makes NameBio return JSON
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }

    # Scrape.do parameters: super=true uses Residential IPs to bypass Cloudflare
    params = {
        "token": API_TOKEN,
        "url": target_url,
        "super": "true"
    }

    print(">> Calling Scrape.do API with Headers (Super Mode)...")
    
    # Send the request with headers
    response = requests.post(api_url, params=params, data=payload, headers=headers, timeout=60)
    
    # Debugging: Try to parse JSON, catch errors if we get HTML instead
    try:
        data = response.json()
        rows = data.get("data", [])
        
        print(f">> Success! Found {len(rows)} rows.")
        
        filename = "daily_sales.csv"
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Domain", "Price", "Date", "Venue"])
            for item in rows:
                domain = item.get('domain', '').split('<')[0].strip()
                writer.writerow([domain, item.get('price'), item.get('date'), item.get('venue')])
        
        print(f">> Successfully saved {len(rows)} sales to {filename}")
        
    except json.JSONDecodeError:
        print(">> ERROR: We got HTML instead of JSON.")
        print(f">> Response Status Code: {response.status_code}")
        print(f">> Response Text (First 500 chars): {response.text[:500]}")
        exit(1)

if __name__ == "__main__":
    main()
