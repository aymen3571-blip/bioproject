import requests
import csv
import os
import time
from bs4 import BeautifulSoup

# This now loads your SCRAPERAPI key
API_KEY = os.getenv("SCRAPE_DO_TOKEN") 

def main():
    print(">> Starting ScraperAPI (The Heavyweight)...")

    # Target URL
    target_url = "https://namebio.com"
    
    # ScraperAPI Endpoint
    api_url = "http://api.scraperapi.com"

    # CONFIGURATION:
    # api_key: Your key
    # url: The target
    # render=true: Uses their specialized Cloudflare-Bypass browser
    # country_code=us: Uses a clean US Residential IP
    params = {
        "api_key": API_KEY,
        "url": target_url,
        "render": "true",
        "country_code": "us" 
    }

    try:
        print(">> Sending request...")
        response = requests.get(api_url, params=params, timeout=60)

        if response.status_code == 200:
            # Check for Captcha in text
            if "captcha" in response.text.lower() or "just a moment" in response.text.lower():
                print(">> FAILED: ScraperAPI also got caught.")
                exit(1)

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # --- PARSING ---
            table = None
            for t in soup.find_all('table'):
                if "Domain" in t.get_text():
                    table = t
                    break
            
            if not table:
                print(">> CRITICAL: Page loaded, but table missing.")
                print(f">> Title: {soup.title.string if soup.title else 'No Title'}")
                exit(1)

            rows = table.find_all('tr')
            print(f">> SUCCESS! Found {len(rows)} rows.")

            filtered_sales = []
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 4: continue
                
                domain = cols[0].get_text(strip=True)
                price = cols[1].get_text(strip=True)
                date_sold = cols[2].get_text(strip=True)
                venue = cols[3].get_text(strip=True)

                if ".com" in domain.lower() and "godaddy" in venue.lower():
                    filtered_sales.append([domain, price, date_sold, venue])

            # Save to CSV
            filename = "daily_sales.csv"
            file_exists = os.path.isfile(filename)
            with open(filename, "a" if file_exists else "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Domain", "Price", "Date", "Venue"])
                writer.writerows(filtered_sales)
                
            print(f">> SAVED {len(filtered_sales)} rows.")

        else:
            print(f">> FAILED. Status: {response.status_code}")
            print(f">> Error: {response.text}")
            exit(1)

    except Exception as e:
        print(f">> ERROR: {e}")
        exit(1)

if __name__ == "__main__":
    main()
