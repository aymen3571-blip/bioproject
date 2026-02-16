import requests
import csv
import os
import time
from bs4 import BeautifulSoup

# This now loads your SCRAPINGANT key
API_KEY = os.getenv("SCRAPE_DO_TOKEN") 

def main():
    print(">> Starting NameBio Scrape via ScrapingAnt...")

    # We scrape the homepage because it has the "Latest Sales" table
    target_url = "https://namebio.com"
    
    # ScrapingAnt API Endpoint
    api_url = "https://api.scrapingant.com/v2/general"

    # ScrapingAnt Parameters:
    # 'browser': true -> Spins up a real Chrome browser (Critical for NameBio)
    # 'proxy_type': residential -> Uses real home IPs to avoid "Robot" blocks
    # 'return_page_source': true -> Returns the HTML after the JS loads
    params = {
        "x-api-key": API_KEY,
        "url": target_url,
        "browser": "true",
        "proxy_type": "residential", 
        "wait_for_selector": "#sales-table", # Wait until the table actually appears
        "timeout": "120" # Allow extra time for the browser to load
    }

    try:
        print(">> Sending request to ScrapingAnt (Browser + Residential)...")
        response = requests.get(api_url, params=params)

        if response.status_code == 200:
            # ScrapingAnt returns a JSON object where the HTML is in the "content" field
            data = response.json()
            html_content = data.get("content", "")
            
            if not html_content:
                print(">> Error: Received empty content from ScrapingAnt.")
                exit(1)

            soup = BeautifulSoup(html_content, 'html.parser')
            
            # --- PARSING LOGIC ---
            table = soup.find('table', id='sales-table')
            
            # Backup search if ID is missing
            if not table:
                for t in soup.find_all('table'):
                    th = t.find('th')
                    if th and "Domain" in th.get_text():
                        table = t
                        break
            
            if not table:
                print(">> CRITICAL: Table not found. We might still be blocked.")
                print(">> Page Title:", soup.title.string if soup.title else "No Title")
                exit(1)

            rows = table.find('tbody').find_all('tr')
            print(f">> Found {len(rows)} sales. Filtering for GoDaddy/.com...")

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
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Domain", "Price", "Date", "Venue"])
                writer.writerows(filtered_sales)
                
            print(f">> SUCCESS! Saved {len(filtered_sales)} GoDaddy .com sales.")

        else:
            print(f">> FAILED. Status: {response.status_code}")
            print(f">> Error: {response.text}")
            exit(1)

    except Exception as e:
        print(f">> ERROR: {e}")
        exit(1)

if __name__ == "__main__":
    main()
